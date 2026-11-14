"""Orchestration : construction de la chaîne de filtres FFmpeg, aperçu, export.

Ordre des traitements (du plus « physique » au plus « cosmétique ») :
  1. recadrage à des dimensions paires (si nécessaire, 1 pixel au plus)
  2. désentrelacement bwdif, une image par trame (50p / 59,94p) : conserve la
     fluidité de mouvement d'origine ; ordre des trames explicite
  3. suppression des parasites ponctuels (removegrain)
  4. réduction du bruit spatio-temporelle (hqdn3d) sur des images progressives
  5. correction modérée contraste / saturation (eq)
  6. [IA facultative : Real-ESRGAN x4 sur images PNG]
  7. mise à l'échelle lanczos vers la taille cible, matrice couleur BT.709 en HD
  8. netteté adaptative (cas), sauf si l'IA est utilisée
  9. rapport de pixel (setsar) pour un affichage 4:3 sans étirement, yuv420p
Une seule compression finale (H.264) : pas de conversions successives destructives
(l'intermédiaire du mode IA est sans perte : FFV1 + FLAC, images PNG).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from .probe import MediaInfo
from .profiles import Profile
from .tools import _NO_WINDOW, Cancelled, ToolError, Toolset, run, run_capture, terminate
from .upscaler import RealEsrganUpscaler

log = logging.getLogger("vhs_restore")
Progress = Callable[[float, str], None]
AI_CHUNK_FRAMES = 60


@dataclass
class Settings:
    profile: Profile
    resolution: str = "source"            # source | 1080 | 2160
    scan: str | None = None               # forçage manuel : progressive | tff | bff
    dar: Fraction | None = None           # forçage manuel du format d'affichage
    use_ai: bool = False
    crf: int = 18
    preset: str = "medium"


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def effective_scan(info: MediaInfo, s: Settings) -> str:
    """'unknown' n'est jamais traité comme entrelacé (pas de supposition)."""
    return s.scan or info.scan


def effective_dar(info: MediaInfo, s: Settings) -> Fraction:
    return s.dar or info.dar


def effective_resolution(s: Settings) -> str:
    if s.resolution == "2160" and not s.use_ai:
        raise ToolError("La 4K n'est proposée qu'avec l'amélioration IA "
                        "(un simple agrandissement n'apporte aucun détail).")
    if s.use_ai and s.resolution == "source":
        return "1080"   # l'IA agrandit forcément : on vise au moins le Full HD
    return s.resolution


def output_fps(info: MediaInfo, s: Settings) -> Fraction:
    return info.fps * 2 if effective_scan(info, s) in ("tff", "bff") else info.fps


def target_size(info: MediaInfo, s: Settings) -> tuple[int, int, Fraction]:
    """(largeur, hauteur, rapport de pixel) en sortie."""
    dar = effective_dar(info, s)
    res = effective_resolution(s)
    if res == "source":
        w, h = info.width // 2 * 2, info.height // 2 * 2
        return w, h, (dar * h / w).limit_denominator(1000)
    h = int(res)
    return _even(h * dar), h, Fraction(1)


def _in_matrix(info: MediaInfo) -> str:
    return "bt709" if info.color_space == "bt709" else "bt601"


def pre_filters(info: MediaInfo, s: Settings) -> list[str]:
    p = s.profile
    f: list[str] = []
    if info.width % 2 or info.height % 2:
        f.append(f"crop={info.width // 2 * 2}:{info.height // 2 * 2}:0:0")
    scan = effective_scan(info, s)
    if scan in ("tff", "bff"):
        f.append(f"bwdif=mode=send_field:parity={scan}:deint=all")
    if p.despeckle:
        f.append("removegrain=m0=1:m1=1:m2=1")
    if p.denoise:
        f.append("hqdn3d=" + ":".join(f"{v:g}" for v in p.denoise))
    if p.contrast != 1 or p.saturation != 1:
        f.append(f"eq=contrast={p.contrast:g}:saturation={p.saturation:g}")
    return f


def post_filters(info: MediaInfo, s: Settings, from_rgb: bool = False) -> list[str]:
    w, h, sar = target_size(info, s)
    f: list[str] = []
    if effective_resolution(s) != "source":
        src_m = "" if from_rgb else f":in_color_matrix={_in_matrix(info)}"
        f.append(f"scale={w}:{h}:flags=lanczos{src_m}:out_color_matrix=bt709")
    if s.profile.sharpen and not s.use_ai:
        f.append(f"cas=strength={s.profile.sharpen:g}")
    f.append(f"setsar={sar.numerator}/{sar.denominator}")
    f.append("format=yuv420p")
    return f


def filter_chain(info: MediaInfo, s: Settings) -> str:
    return ",".join(pre_filters(info, s) + post_filters(info, s))


def encode_args(info: MediaInfo, s: Settings) -> list[str]:
    if effective_resolution(s) != "source":
        color = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
    elif info.standard == "525/30":
        color = ["-colorspace", "smpte170m", "-color_primaries", "smpte170m", "-color_trc", "smpte170m"]
    else:
        color = ["-colorspace", "bt470bg", "-color_primaries", "bt470bg", "-color_trc", "bt709"]
    return ["-c:v", "libx264", "-preset", s.preset, "-crf", str(s.crf), "-pix_fmt", "yuv420p",
            *color, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]


def _ff_base(tools: Toolset) -> list[str]:
    return [tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
            "-progress", "pipe:1", "-nostats"]


def _seek(start: float | None, duration: float | None) -> list[str]:
    a: list[str] = []
    if start:
        a += ["-ss", f"{start:.3f}"]
    if duration:
        a += ["-t", f"{duration:.3f}"]
    return a


class _FFProgress:
    """Convertit les lignes 'out_time_us=' de -progress en fraction."""

    def __init__(self, total: float, cb: Progress | None, lo: float, hi: float, label: str):
        self.total, self.cb, self.lo, self.hi, self.label = max(total, 0.001), cb, lo, hi, label

    def __call__(self, line: str) -> None:
        if self.cb and line.startswith("out_time_us="):
            try:
                t = int(line.split("=", 1)[1]) / 1e6
            except ValueError:
                return
            self.cb(self.lo + (self.hi - self.lo) * min(1.0, max(0.0, t / self.total)), self.label)


def unique_output_path(info: MediaInfo, s: Settings, out_dir: Path) -> Path:
    res = effective_resolution(s)
    tag = {"source": "", "1080": "_1080p", "2160": "_4k"}[res] + ("_ia" if s.use_ai else "")
    base = f"{info.path.stem}_restaure_{s.profile.key}{tag}"
    cand = out_dir / f"{base}.mp4"
    n = 2
    while cand.exists() or cand.resolve() == info.path.resolve():
        cand = out_dir / f"{base} ({n}).mp4"
        n += 1
    return cand


def export(info: MediaInfo, s: Settings, out_path: Path, tools: Toolset, *,
           cancel: threading.Event | None = None, progress: Progress | None = None,
           start: float | None = None, duration: float | None = None) -> Path:
    """Restaure et encode vers out_path. Le fichier n'apparaît qu'une fois complet."""
    tools.require_ffmpeg()
    out_path = Path(out_path)
    if out_path.resolve() == info.path.resolve():
        raise ToolError("Le fichier de sortie ne peut pas être le fichier original.")
    if not out_path.parent.is_dir():
        raise ToolError(f"Dossier de sortie introuvable : {out_path.parent}")
    part = out_path.with_name(out_path.stem + ".partiel.mp4")
    total = duration or info.duration
    try:
        if s.use_ai:
            _export_ai(info, s, part, tools, cancel, progress, start, duration, total)
        else:
            cmd = (_ff_base(tools) + _seek(start, duration) + ["-i", str(info.path),
                   "-map", "0:v:0", "-map", "0:a:0?", "-vf", filter_chain(info, s),
                   *encode_args(info, s), "-f", "mp4", str(part)])
            run(cmd, cancel=cancel, what="FFmpeg (restauration)",
                on_line=_FFProgress(total, progress, 0, 1, "Restauration…"))
        os.replace(part, out_path)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if progress:
        progress(1.0, "Terminé")
    log.info("Export terminé : %s", out_path)
    return out_path


def _work_root() -> str:
    return os.environ.get("VHSRA_TMP") or tempfile.gettempdir()


def _export_ai(info: MediaInfo, s: Settings, part: Path, tools: Toolset,
               cancel: threading.Event | None, progress: Progress | None,
               start: float | None, duration: float | None, total: float) -> None:
    upscaler = RealEsrganUpscaler(tools.realesrgan)
    fps = output_fps(info, s)
    frames_est = int(total * fps) + 1
    px = info.width * info.height
    need = frames_est * px * 1.5 * 0.7 + AI_CHUNK_FRAMES * px * 3 * (1 + upscaler.scale ** 2)
    root = _work_root()
    free = shutil.disk_usage(root).free
    if free < need * 1.2:
        raise ToolError(f"Espace disque insuffisant dans {root} : environ {need / 1e9:.1f} Go "
                        f"nécessaires, {free / 1e9:.1f} Go libres.")
    tmp = Path(tempfile.mkdtemp(prefix="vhsrestore_", dir=root))
    enc: subprocess.Popen | None = None
    try:
        # 1. pré-traitement sans perte (vidéo FFV1 tout-intra + audio FLAC)
        inter = tmp / "inter.mkv"
        pre = ",".join(pre_filters(info, s)) or "null"
        run(_ff_base(tools) + _seek(start, duration) + [
            "-i", str(info.path), "-map", "0:v:0", "-map", "0:a:0?", "-vf", pre,
            "-c:v", "ffv1", "-level", "3", "-g", "1", "-c:a", "flac", "-f", "matroska", str(inter)],
            cancel=cancel, what="FFmpeg (pré-traitement)",
            on_line=_FFProgress(total, progress, 0, 0.1, "Nettoyage avant IA…"))
        meta = run_capture([tools.ffprobe.path, "-v", "error", "-count_packets",
                            "-show_entries", "stream=codec_type,start_time,nb_read_packets:format=start_time",
                            "-of", "json", str(inter)])
        d = json.loads(meta.stdout)
        vst = next(x for x in d["streams"] if x["codec_type"] == "video")
        n = int(vst["nb_read_packets"])
        v_off = float(vst.get("start_time", 0) or 0) - float(d["format"].get("start_time", 0) or 0)

        # 2. encodeur final unique, alimenté en PNG par un tube
        enc_log = open(tmp / "encodeur.log", "w", encoding="utf-8", errors="replace")
        enc_cmd = [tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
                   "-itsoffset", f"{v_off:.6f}", "-f", "image2pipe", "-c:v", "png",
                   "-framerate", f"{fps.numerator}/{fps.denominator}", "-i", "-",
                   "-i", str(inter), "-map", "0:v:0", "-map", "1:a:0?",
                   "-vf", ",".join(post_filters(info, s, from_rgb=True)),
                   *encode_args(info, s), "-f", "mp4", str(part)]
        log.info("exec: %s", subprocess.list2cmdline(enc_cmd))
        enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=enc_log, creationflags=_NO_WINDOW)

        # 3. traitement IA par paquets (limite l'espace disque utilisé)
        chunks = math.ceil(n / AI_CHUNK_FRAMES)
        for i in range(chunks):
            done = i * AI_CHUNK_FRAMES
            cnt = min(AI_CHUNK_FRAMES, n - done)
            d_in, d_out = tmp / "in", tmp / "out"
            for dd in (d_in, d_out):
                shutil.rmtree(dd, ignore_errors=True)
                dd.mkdir()
            ss = ["-ss", f"{v_off + (done - 0.5) / float(fps):.6f}"] if done else []
            run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
                 *ss, "-i", str(inter), "-map", "0:v:0", "-frames:v", str(cnt),
                 "-pix_fmt", "rgb24", "-start_number", "0", str(d_in / "%08d.png")],
                cancel=cancel, what="FFmpeg (extraction d'images)")

            def on_count(k: int, done=done) -> None:
                if progress:
                    progress(0.1 + 0.9 * (done + k) / n, f"Amélioration IA : image {done + k}/{n}")

            upscaler.upscale_dir(d_in, d_out, cancel=cancel, on_count=on_count)
            for png in sorted(d_out.glob("*.png")):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                try:
                    enc.stdin.write(png.read_bytes())
                except (BrokenPipeError, OSError) as exc:
                    raise ToolError("L'encodeur s'est arrêté :\n" + _tail(tmp / "encodeur.log")) from exc
        enc.stdin.close()
        while True:
            try:
                enc.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
        enc_log.close()
        if enc.returncode != 0:
            raise ToolError("Échec de l'encodage final :\n" + _tail(tmp / "encodeur.log"))
    finally:
        if enc is not None:
            terminate(enc)
            try:
                enc_log.close()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _tail(p: Path, n: int = 8) -> str:
    try:
        return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


# ---------------------------------------------------------------- aperçu
@dataclass
class PreviewResult:
    start: float
    duration: float
    restored: Path
    compare: Path
    stills: list[Path]


def make_preview(info: MediaInfo, s: Settings, tools: Toolset, workdir: Path, start: float,
                 duration: float = 10.0, *, cancel: threading.Event | None = None,
                 progress: Progress | None = None) -> PreviewResult:
    """Restaure un extrait puis fabrique une vidéo côte à côte (original | restauré)
    et trois images fixes : même instant, même cadrage, même taille d'affichage."""
    if info.duration > 0:
        duration = min(duration, info.duration)
        start = max(0.0, min(start, info.duration - duration))
    workdir.mkdir(parents=True, exist_ok=True)
    for old in workdir.glob("*"):
        if old.is_file():
            old.unlink()
    sp = dataclasses.replace(s, preset="veryfast")
    restored = workdir / "apercu_restaure.mp4"

    def sub(lo: float, hi: float) -> Progress | None:
        return (lambda f, m: progress(lo + (hi - lo) * f, m)) if progress else None

    export(info, sp, restored, tools, cancel=cancel, progress=sub(0, 0.8),
           start=start, duration=duration)

    h = 540
    w = _even(h * effective_dar(info, s))
    fps = output_fps(info, s)
    crop = f"crop={info.width // 2 * 2}:{info.height // 2 * 2}:0:0,"
    fc = (f"[0:v]{crop}scale={w}:{h}:flags=lanczos,setsar=1,fps={fps.numerator}/{fps.denominator}[a];"
          f"[1:v]scale={w}:{h}:flags=lanczos,setsar=1[b];[a][b]hstack=inputs=2,format=yuv420p[v]")
    compare = workdir / "apercu_comparaison.mp4"
    run(_ff_base(tools) + _seek(start, duration) + ["-i", str(info.path), "-i", str(restored),
        "-filter_complex", fc, "-map", "[v]", "-map", "1:a:0?", "-c:v", "libx264", "-preset",
        "veryfast", "-crf", "16", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(compare)], cancel=cancel, what="FFmpeg (comparaison)",
        on_line=_FFProgress(duration, progress, 0.8, 0.95, "Comparaison…"))
    stills = []
    for k, frac in enumerate((0.2, 0.5, 0.8)):
        still = workdir / f"image_{k + 1}.png"
        run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
             "-ss", f"{duration * frac:.3f}", "-i", str(compare), "-frames:v", "1", str(still)],
            cancel=cancel, what="FFmpeg (image fixe)")
        stills.append(still)
    if progress:
        progress(1.0, "Aperçu prêt")
    return PreviewResult(start, duration, restored, compare, stills)
