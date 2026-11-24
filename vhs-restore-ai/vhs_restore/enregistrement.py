"""Enregistrer une cassette depuis le magnétoscope.

Un seul FFmpeg ouvre le boîtier. La petite image en direct est une deuxième
sortie du même processus. L'arrêt envoie « q » sur l'entrée standard.
"""
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from .tools import Toolset


@dataclass(frozen=True)
class CaptureConfig:
    video: str = ""
    audio: str = ""
    norme: str = "pal"              # pal | ntsc
    qualite: str = "ffv1"           # ffv1 | x264
    sortie: Path = Path("cassette.mkv")
    simule: bool = False
    crossbar_video: int | None = None
    crossbar_audio: int | None = None


def build_capture_cmd(cfg: CaptureConfig, ffmpeg: str) -> list[str]:
    """Une seule ouverture. Image et son dans la même entrée. Pas de -nostdin :
    « Arrêter » envoie « q » sur le tube."""
    if cfg.norme == "ntsc":
        size, rate, standard = "720x480", "30000/1001", "ntsc_M"
    else:
        size, rate, standard = "720x576", "25", "pal_B"
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-n"]
    if cfg.simule:
        cmd += ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}",
                "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000"]
        vmap, amap = "0:v", "1:a"
    else:
        entree = f'video="{cfg.video}"'
        if cfg.audio:
            entree += f':audio="{cfg.audio}"'
        cmd += ["-f", "dshow", "-rtbufsize", "1024M", "-thread_queue_size", "4096",
                "-video_size", size, "-framerate", rate, "-analog_video_standard", standard]
        if cfg.crossbar_video is not None:
            cmd += ["-crossbar_video_input_pin_number", str(cfg.crossbar_video)]
        if cfg.crossbar_audio is not None:
            cmd += ["-crossbar_audio_input_pin_number", str(cfg.crossbar_audio)]
        cmd += ["-i", entree]
        vmap, amap = "0:v", "0:a"
    if cfg.qualite == "x264":
        vcodec = ["-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    else:
        vcodec = ["-c:v", "ffv1", "-level", "3", "-g", "1", "-pix_fmt", "yuv422p"]
    apercu = Path(str(cfg.sortie) + ".apercu.jpg")
    cmd += ["-map", vmap, "-map", amap, *vcodec, "-c:a", "pcm_s16le", "-ar", "48000",
            "-fps_mode", "passthrough", "-f", "matroska", str(cfg.sortie),
            "-map", vmap, "-vf", "fps=2,scale=320:-2", "-update", "1",
            "-f", "image2", str(apercu)]
    return cmd


def nom_unique(dossier: Path, horodatage: str) -> Path:
    base = dossier / f"Cassette_{horodatage}.mkv"
    if not base.exists():
        return base
    n = 2
    while True:
        cand = dossier / f"Cassette_{horodatage}_{n}.mkv"
        if not cand.exists():
            return cand
        n += 1


def arreter_proprement(proc: subprocess.Popen, timeout: float = 10.0) -> int:
    """Envoie « q » et attend. Tue seulement en dernier recours."""
    try:
        if proc.stdin:
            proc.stdin.write(b"q\n")
            proc.stdin.flush()
    except Exception:
        pass
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.wait(timeout=5)


def parse_dshow_devices(stderr: str) -> list[tuple[str, str]]:
    """[(nom, 'video'|'audio')] depuis -list_devices."""
    out = []
    for line in stderr.splitlines():
        if '"' not in line:
            continue
        nom = line.split('"')[1]
        kind = "video" if "(video)" in line else "audio" if "(audio)" in line else ""
        if nom and kind:
            out.append((nom, kind))
    return out
