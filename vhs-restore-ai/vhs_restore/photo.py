"""Mode Photo : restaurer une photo ou une carte postale numérisée (JPEG, PNG, TIFF…).

Mêmes principes que pour les films : l'original n'est jamais modifié, rien n'est
inventé par défaut (pas d'IA sur les visages), le noir et blanc reste noir et blanc, et les corrections de contraste et de couleur passent par les
conseils de l'analyse, avec les mêmes plafonds de fidélité (pipeline.safe_levels /
safe_gains).

Réglages choisis sur une vraie carte postale ancienne (730×1156, blocs JPEG) : un
débruitage plus fort (nlmeans s=2,5) donnait aux pierres d'un mur un aspect d'aquarelle.
On reste donc léger : `spp` atténue les blocs de compression, `nlmeans` le grain.

Colorisation (facultative, décochée par défaut) : voir colorize.py. Elle n'est faite que pour
une photo noir et blanc et produit une COPIE en plus (« …_colorisee_ia.png ») ; la photo
restaurée en noir et blanc est toujours écrite.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from fractions import Fraction
from pathlib import Path
from typing import Callable

from . import colorize, pipeline
from .probe import MediaInfo, parse_signals, rgb_mean
from .tools import Cancelled, ToolError, Toolset, run, run_capture
from .upscaler import RealEsrganUpscaler

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

# Par profil : blocs JPEG (spp), grain (nlmeans), netteté (cas), agrandissement x2.
PHOTO_FILTERS = {
    "fidele": (["spp=quality=3:qp=6"], None, False),
    "equilibre": (["spp=quality=4:qp=8", "nlmeans=s=1.2:p=3:r=9"], 0.2, False),
    "maximum": (["spp=quality=5:qp=10", "nlmeans=s=1.6:p=3:r=9"], 0.3, True),
}

Progress = Callable[[float, str], None]


def is_photo(path: str | Path) -> bool:
    return Path(path).suffix.lower() in PHOTO_EXTS


def analyze_photo(path: str | Path, tools: Toolset) -> MediaInfo:
    """Taille, noir et blanc, niveaux et dominante d'une photo. Renvoie un MediaInfo
    (sans son, une seule image) pour réutiliser les conseils de l'analyse."""
    tools.require_ffmpeg()
    p = Path(path).resolve()
    if not p.is_file():
        raise ToolError(f"Fichier introuvable : {p}")
    r = run_capture([tools.ffprobe.path, "-v", "error", "-select_streams", "v:0", "-show_entries",
                     "stream=width,height,codec_name", "-of", "json", str(p)], timeout=60)
    streams = json.loads(r.stdout or "{}").get("streams") or []
    if r.returncode or not streams or not streams[0].get("width"):
        raise ToolError("Cette image n'a pas pu être lue (fichier abîmé ou format inconnu).")
    st = streams[0]
    info = MediaInfo(path=p, width=int(st["width"]), height=int(st["height"]), codec=st.get("codec_name", ""),
                     container="image", fps=Fraction(1), scan="progressive", sar=Fraction(1),
                     dar=Fraction(int(st["width"]), int(st["height"])), dar_source="photo")
    stats = run_capture([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-i", str(p), "-vf",
                         "signalstats,metadata=print:key=lavfi.signalstats.SATHIGH,"
                         "metadata=print:key=lavfi.signalstats.SATAVG,"
                         "metadata=print:key=lavfi.signalstats.YLOW,"
                         "metadata=print:key=lavfi.signalstats.YHIGH",
                         "-frames:v", "1", "-f", "null", "-"], timeout=60)
    sig = parse_signals(stats.stderr)
    info.saturation, info.saturation_high = sig["saturation"], sig["saturation_high"]
    info.level_low, info.level_high = sig.get("level_low"), sig.get("level_high")
    if not info.black_and_white:          # une photo noir et blanc n'a pas de « dominante » à corriger
        info.cast_rgb = rgb_mean(tools.ffmpeg.path, p)
    return info


def photo_chain(info: MediaInfo, s: pipeline.Settings, *, after_ai: bool = False) -> list[str]:
    """Filtres FFmpeg de la photo, dans l'ordre : blocs, grain, niveaux, couleur,
    agrandissement, netteté, format de sortie."""
    base, sharpen, upscale = PHOTO_FILTERS[s.profile.key]
    f = [] if after_ai else list(base)
    if not after_ai:
        for flt in (pipeline._cast_filter(s), pipeline._levels_filter(s)):
            if flt:
                f.append(flt)
    if after_ai:
        f.append(f"scale={info.width * 2}:{info.height * 2}:flags=lanczos")   # IA x4 ramenée à x2
    elif upscale:
        f.append("scale=iw*2:ih*2:flags=lanczos")
    if sharpen and not s.use_ai:
        f.append(f"cas=strength={sharpen:g}")
    f.append("format=gray" if info.black_and_white else "format=rgb24")
    return f


def colorized_path(out_path: Path) -> Path:
    """Copie colorisée, à côté de la photo restaurée : « <nom>_colorisee_ia.png »."""
    out_path = Path(out_path)
    return out_path.with_name(f"{out_path.stem}_colorisee_ia.png")


def wants_color(info: MediaInfo, s: pipeline.Settings) -> bool:
    return bool(s.colorize and info.black_and_white)


def output_path(info: MediaInfo, s: pipeline.Settings, out_dir: Path) -> Path:
    base = f"{info.path.stem}_restaure_{s.profile.key}{'_ia' if s.use_ai else ''}"
    cand, n = out_dir / f"{base}.png", 2
    while (cand.exists() or cand.resolve() == info.path.resolve()
           or (wants_color(info, s) and colorized_path(cand).exists())):
        cand, n = out_dir / f"{base} ({n}).png", n + 1
    return cand


def restore_photo(info: MediaInfo, s: pipeline.Settings, out_path: Path, tools: Toolset, *,
                  cancel: threading.Event | None = None, progress: Progress | None = None) -> Path:
    """Écrit la photo restaurée (PNG, sans perte). L'original n'est jamais modifié.
    Si la colorisation est demandée pour une photo noir et blanc, écrit EN PLUS la copie
    colorisée (colorized_path) ; une copie déjà présente n'est jamais écrasée."""
    out_path = Path(out_path).resolve()
    if out_path == info.path.resolve():
        raise ToolError("Le fichier restauré ne peut pas remplacer la photo d'origine.")
    if not out_path.parent.is_dir():
        raise ToolError(f"Dossier de sortie introuvable : {out_path.parent}")
    color_out = colorized_path(out_path) if wants_color(info, s) else None
    if color_out is not None:
        if not tools.colorize_available:
            raise ToolError("La colorisation n'est pas installée"
                            + (f" ({tools.colorizer.problem})" if tools.colorizer.problem else "")
                            + ". Relancez installer.bat -AvecCouleurs, ou décochez « Coloriser ».")
        if color_out.exists():
            raise ToolError(f"Une photo colorisée porte déjà ce nom : {color_out.name}. Rien n'a été remplacé.")
    part = out_path.with_name(out_path.stem + ".partiel.png")
    ff = [tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
    work = Path(tempfile.mkdtemp(prefix="vhsrestore_photo_"))
    try:
        if progress:
            progress(0.1, "Restauration de la photo…")
        if s.use_ai:
            up = RealEsrganUpscaler(tools.realesrgan)
            src, dst = work / "in", work / "out"
            src.mkdir()
            base, _, _ = PHOTO_FILTERS[s.profile.key]
            pre = base + [x for x in (pipeline._cast_filter(s), pipeline._levels_filter(s)) if x]
            run(ff + ["-i", str(info.path), "-vf", ",".join(pre + ["format=rgb24"]),
                      str(src / "photo.png")], cancel=cancel, what="FFmpeg (photo)")
            up.upscale_dir(src, dst, cancel=cancel)
            run(ff + ["-i", str(dst / "photo.png"), "-vf", ",".join(photo_chain(info, s, after_ai=True)),
                      "-f", "image2", str(part)], cancel=cancel, what="FFmpeg (photo)")
        else:
            run(ff + ["-i", str(info.path), "-vf", ",".join(photo_chain(info, s)),
                      "-frames:v", "1", "-f", "image2", "-c:v", "png", str(part)],
                cancel=cancel, what="FFmpeg (photo)")
        os.replace(part, out_path)
        if color_out is not None:
            if progress:
                progress(0.6, "Colorisation par l'IA (couleurs inventées)…")
            colorize.colorize(out_path, color_out, tools.ffmpeg.path, tools.ffprobe.path,
                              Path(tools.colorizer.path), cancel=cancel)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(1.0, "Terminé")
    return out_path


def make_photo_preview(info: MediaInfo, s: pipeline.Settings, tools: Toolset, workdir: Path, *,
                       cancel: threading.Event | None = None,
                       progress: Progress | None = None) -> pipeline.PreviewResult:
    """Avant / après côte à côte, à la même taille (l'original est agrandi s'il le faut)."""
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / "apercu_photo.png"
    colorized_path(target).unlink(missing_ok=True)       # aperçu précédent
    restored = restore_photo(info, s, target, tools, cancel=cancel, progress=progress)
    if wants_color(info, s):                              # avant (noir et blanc) / après (colorisé)
        restored = colorized_path(target)
    compare = workdir / "apercu_photo_comparaison.png"
    fmt = "gray" if info.black_and_white and not wants_color(info, s) else "rgb24"
    r = subprocess.run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
                        "-i", str(info.path), "-i", str(restored), "-filter_complex",
                        f"[0:v][1:v]scale2ref=flags=lanczos[a][b];[a]format={fmt}[a2];[b]format={fmt}[b2];"
                        "[a2][b2]hstack=inputs=2", "-frames:v", "1", str(compare)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise ToolError("Comparaison impossible : " + r.stderr.strip()[-300:])
    return pipeline.PreviewResult(0.0, 0.0, restored, compare, [compare], info.path)
