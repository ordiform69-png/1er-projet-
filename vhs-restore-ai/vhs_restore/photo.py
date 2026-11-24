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
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from . import colorize, pipeline
from .probe import MediaInfo, parse_signals, rgb_mean
from .tools import copie_annexe
from .tools import partiel_unique, reserver_sorties
from .tools import (_NO_WINDOW, FichierOccupe, ToolError, Toolset, effacer, ff_input, finaliser, run,
                    run_capture, verifier_chemin)
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
                     "stream=width,height,codec_name", "-of", "json", *ff_input(p)[:-2], str(p)], timeout=60)
    streams = json.loads(r.stdout or "{}").get("streams") or []
    if r.returncode or not streams or not streams[0].get("width"):
        raise ToolError("Cette image n'a pas pu être lue (fichier abîmé ou format inconnu).")
    st = streams[0]
    info = MediaInfo(path=p, width=int(st["width"]), height=int(st["height"]), codec=st.get("codec_name", ""),
                     container="image", fps=Fraction(1), scan="progressive", sar=Fraction(1),
                     dar=Fraction(int(st["width"]), int(st["height"])), dar_source="photo")
    stats = run_capture([tools.ffmpeg.path, "-hide_banner", "-nostdin", *ff_input(p), "-vf",
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
    try:
        info.scanner = analyser_scanner(p, tools)   # type: ignore[attr-defined]
    except Exception:
        info.scanner = AnalyseScanner(message="Analyse impossible : la photo est gardée telle quelle.")
    return info



# --- Redressement et bord du scanner (demande n°11) ---------------------------
# D'abord redresser (coins vides remplis de la couleur du bord), ensuite seulement
# enlever le bord sur l'image redressée. Jamais de coupe dans la photo elle-même.


@dataclass(frozen=True)
class AnalyseScanner:
    tilt: float = 0.0
    border: str = ""                  # "white" | "black" | ""
    fill: str = "white"
    crop_frac: tuple[float, float, float, float] | None = None  # w, h, x, y en fraction
    cocher: bool = False
    message: str = ""


def _raw_gray(path: Path, tools: Toolset, w: int, h: int) -> list[int]:
    import subprocess
    raw = subprocess.check_output(
        [tools.ffmpeg.path, "-hide_banner", "-nostdin", "-loglevel", "error",
         *ff_input(path), "-vf", f"scale={w}:{h}:flags=area,format=gray",
         "-frames:v", "1", "-f", "rawvideo", "-"], timeout=60)
    return list(raw[: w * h])


def _tourner_memoire(src: list[int], w: int, h: int, deg: float, fill: int) -> list[int]:
    import math
    out = [fill] * (w * h)
    ca, sa = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    cx, cy = (w - 1) / 2, (h - 1) / 2
    for y in range(h):
        for x in range(w):
            dx, dy = x - cx, y - cy
            sx = ca * dx + sa * dy + cx
            sy = -sa * dx + ca * dy + cy
            ix, iy = int(round(sx)), int(round(sy))
            if 0 <= ix < w and 0 <= iy < h:
                out[y * w + x] = src[iy * w + ix]
    return out


def _bord(src: list[int], w: int, h: int) -> tuple[str, int]:
    ring = src[: w * 3] + src[-w * 3 :]
    moy = sum(ring) / max(1, len(ring))
    if moy >= 200:
        return "white", 255
    if moy <= 40:
        return "black", 0
    return "", 128


def _score_rect(src: list[int], w: int, h: int, border: str) -> float:
    if border == "white":
        pts = [(i % w, i // w) for i, p in enumerate(src) if p < 190]
    elif border == "black":
        pts = [(i % w, i // w) for i, p in enumerate(src) if p > 40]
    else:
        return 0.0
    if len(pts) < 30:
        return 0.0
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return len(pts) / ((max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1))


def analyser_scanner(path: Path, tools: Toolset) -> AnalyseScanner:
    """Bord uniforme et inclinaison nette (< 10°). Au doute : rien, case décochée."""
    w, h = 160, 120
    try:
        src = _raw_gray(Path(path), tools, w, h)
    except Exception:
        return AnalyseScanner(message="Analyse impossible : la photo est gardée telle quelle.")
    if len(src) != w * h:
        return AnalyseScanner(message="Analyse impossible : la photo est gardée telle quelle.")
    border, fill = _bord(src, w, h)
    best_a, best_s = 0.0, _score_rect(src, w, h, border) if border else 0.0
    if border:
        for i in range(-19, 20):
            a = i * 0.5
            if not a:
                continue
            s = _score_rect(_tourner_memoire(src, w, h, a, fill), w, h, border)
            if s > best_s + 0.008:
                best_s, best_a = s, a
    incertain = abs(best_a) >= 10
    tilt = 0.0 if incertain or abs(best_a) < 0.5 else best_a
    crop = None
    if border and not incertain:
        img = _tourner_memoire(src, w, h, tilt, fill) if tilt else src
        if border == "white":
            pts = [(i % w, i // w) for i, p in enumerate(img) if p < 200]
        else:
            pts = [(i % w, i // w) for i, p in enumerate(img) if p > 30]
        if len(pts) >= 30:
            x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
            y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
            # marge : on ne coupe pas dans le contenu
            if (x1 - x0) > w * 0.5 and (y1 - y0) > h * 0.5 and (x0 > 1 or y0 > 1):
                crop = ((x1 - x0 + 1) / w, (y1 - y0 + 1) / h, x0 / w, y0 / h)
    if incertain:
        return AnalyseScanner(message="Correction automatique incertaine : la photo est laissée telle quelle.")
    cocher = bool(border) or abs(tilt) >= 0.5
    if tilt and border:
        msg = f"Bord du scanner et inclinaison de {abs(tilt):.0f}° détectés."
    elif border:
        msg = f"Bord {'blanc' if border == 'white' else 'noir'} du scanner détecté."
    elif tilt:
        msg = f"Inclinaison de {abs(tilt):.0f}° détectée."
    else:
        msg = "Photo droite, aucun bord détecté."
        cocher = False
    return AnalyseScanner(tilt=tilt, border=border, fill=border or "white",
                          crop_frac=crop, cocher=cocher, message=msg)


def filtres_scanner(s: "pipeline.Settings", analyse: AnalyseScanner | None) -> list[str]:
    """Tours de 90° de l'utilisateur, puis redressement (remplissage), puis bord."""
    f: list[str] = []
    q = int(getattr(s, "photo_quarts", 0)) % 4
    if q == 1:
        f.append("transpose=2")          # gauche, 90° anti-horaire
    elif q == 2:
        f.append("hflip,vflip")
    elif q == 3:
        f.append("transpose=1")          # droite, 90° horaire
    if getattr(s, "redresser", False) and analyse and (analyse.tilt or analyse.crop_frac):
        if analyse.tilt:
            fill = "black" if analyse.fill == "black" else "white"
            f.append(f"rotate={analyse.tilt}*PI/180:fillcolor={fill}:ow=iw:oh=ih")
        if analyse.crop_frac:
            cw, ch, cx, cy = analyse.crop_frac
            f.append(f"crop=iw*{cw:.4f}:ih*{ch:.4f}:iw*{cx:.4f}:ih*{cy:.4f}")
    return f


def mesurer_inclinaison(path: Path, tools: Toolset) -> float:
    """Inclinaison résiduelle (degrés) après correction. Pour les tests."""
    return abs(analyser_scanner(path, tools).tilt)


def photo_chain(info: MediaInfo, s: pipeline.Settings, *, after_ai: bool = False) -> list[str]:
    """Filtres FFmpeg de la photo, dans l'ordre : tours et scanner, blocs, grain,
    niveaux, couleur, agrandissement, netteté, format de sortie."""
    base, sharpen, upscale = PHOTO_FILTERS[s.profile.key]
    f = [] if after_ai else list(base)
    if not after_ai:
        f = filtres_scanner(s, getattr(info, "scanner", None)) + f
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
    cible = Path(out_path).resolve()
    if cible == info.path.resolve():
        raise ToolError("Le fichier de sortie ne peut pas remplacer le fichier original.")
    annexes = lambda p: [colorized_path(p)] if wants_color(info, s) else []
    with reserver_sorties(cible, annexes) as libre:
        return _restore_photo(info, s, libre, tools, cancel=cancel, progress=progress)


def _restore_photo(info: MediaInfo, s: pipeline.Settings, out_path: Path, tools: Toolset, *,
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
                            + ". Cliquez sur « ○ Colorisation » en bas de la fenêtre pour l'installer, "
                            "ou décochez « Coloriser ».")
        if color_out.exists():
            raise ToolError(f"Une photo colorisée porte déjà ce nom : {color_out.name}. Rien n'a été remplacé.")
    part = partiel_unique(out_path)
    verifier_chemin(part)
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
            run(ff + [*ff_input(info.path), "-vf", ",".join(pre + ["format=rgb24"]),
                      str(src / "photo.png")], cancel=cancel, what="FFmpeg (photo)")
            up.upscale_dir(src, dst, cancel=cancel)
            run(ff + ["-i", str(dst / "photo.png"), "-vf", ",".join(photo_chain(info, s, after_ai=True)),
                      "-f", "image2", "-update", "1", str(part)], cancel=cancel, what="FFmpeg (photo)")
        else:
            run(ff + [*ff_input(info.path), "-vf", ",".join(photo_chain(info, s)),
                      "-frames:v", "1", "-f", "image2", "-update", "1", "-c:v", "png", str(part)],
                cancel=cancel, what="FFmpeg (photo)")
        finaliser(part, out_path)
        if color_out is not None:
            if progress:
                progress(0.6, "Colorisation par l'IA (couleurs inventées)…")
            copie_couleur(out_path, tools, cancel)
    except BaseException as exc:
        if not isinstance(exc, FichierOccupe):
            effacer(part)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(1.0, "Terminé")
    return out_path


def copie_couleur(principal, tools, cancel):
    with copie_annexe(principal, "La copie en couleur"):
        colorize.colorize(principal, colorized_path(principal), tools.ffmpeg.path, tools.ffprobe.path,
                          Path(tools.colorizer.path), cancel=cancel)


def make_photo_preview(info: MediaInfo, s: pipeline.Settings, tools: Toolset, workdir: Path, *,
                       cancel: threading.Event | None = None,
                       progress: Progress | None = None) -> pipeline.PreviewResult:
    """Avant / après côte à côte, à la même taille (l'original est agrandi s'il le faut)."""
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / "apercu_photo.png"
    effacer(target)
    colorized_path(target).unlink(missing_ok=True)       # aperçu précédent
    restored = restore_photo(info, s, target, tools, cancel=cancel, progress=progress)
    if wants_color(info, s):                              # avant (noir et blanc) / après (colorisé)
        restored = colorized_path(target)
    compare = workdir / "apercu_photo_comparaison.png"
    fmt = "gray" if info.black_and_white and not wants_color(info, s) else "rgb24"
    # -loop 1 : une seule image n'émet pas de trame avec scale2ref sous FFmpeg 7
    # (code 0, fichier vide). -update 1 : un PNG, pas une suite numérotée.
    r = subprocess.run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
                        "-loop", "1", *ff_input(info.path), "-loop", "1", "-i", str(restored),
                        "-filter_complex",
                        f"[0:v][1:v]scale2ref=flags=lanczos[a][b];[a]format={fmt}[a2];[b]format={fmt}[b2];"
                        "[a2][b2]hstack=inputs=2", "-frames:v", "1", "-update", "1", str(compare)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                       stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    if r.returncode or not compare.is_file():
        raise ToolError("Comparaison impossible : " + (r.stderr.strip()[-300:] or "fichier vide"))
    return pipeline.PreviewResult(0.0, 0.0, restored, compare, [compare], info.path)
