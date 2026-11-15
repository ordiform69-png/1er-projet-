"""Mesures du son pour l'analyse : canal muet, canaux en opposition de phase,
saturation (écrêtage), ronflement du secteur. FFmpeg seul (astats, pan, bandpass),
sur les deux premières minutes au plus. Ces mesures ne servent qu'à CONSEILLER :
rien n'est corrigé sans que l'utilisateur le demande."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .tools import run_capture

SECONDS = 120


@dataclass
class AudioCheck:
    channels: int = 0
    channel_issue: str = ""         # "" | left_silent | right_silent | phase
    clipped: float = 0.0            # part des échantillons au plafond (0 à 1)
    hum_hz: int = 0                 # 0 | 50 | 60


def _levels(ffmpeg: str, path: Path, af: str) -> list[dict[str, float]]:
    """Statistiques astats par canal (dB et compteurs) après le filtre af."""
    r = run_capture([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:a:0",
                     "-t", str(SECONDS), "-af",
                     f"{af}astats=measure_perchannel=Peak_level+RMS_level+Peak_count:"
                     "measure_overall=Number_of_samples", "-f", "null", "-"], timeout=300)
    chans: list[dict[str, float]] = []
    total = 0.0      # « Number of samples » n'existe qu'en bilan global (par canal)
    for line in r.stderr.splitlines():
        if re.search(r"\] Channel: \d+", line):
            chans.append({})
            continue
        m = re.search(r"\] Number of samples: (\d+)", line)
        if m:
            total = float(m.group(1))
            continue
        m = re.search(r"\] (Peak level dB|RMS level dB|Peak count|Number of samples): (\S+)", line)
        if m and chans:
            val = m.group(2)
            chans[-1][m.group(1)] = float("-inf") if val == "-inf" else float(val)
    for ch in chans:
        ch["Number of samples"] = total
    return chans


def _rms(chans: list[dict[str, float]]) -> float:
    return chans[0].get("RMS level dB", float("-inf")) if chans else float("-inf")


def measure(ffmpeg: str, path: Path, channels: int) -> AudioCheck:
    c = AudioCheck(channels=channels)
    try:
        per = _levels(ffmpeg, path, "")
        # Saturation : beaucoup d'échantillons collés au plafond numérique
        for ch in per:
            n = ch.get("Number of samples", 0) or 0
            if n and ch.get("Peak level dB", -99) > -0.1:
                c.clipped = max(c.clipped, ch.get("Peak count", 0) / n)
        if channels == 2 and len(per) == 2:
            left, right = (ch.get("RMS level dB", float("-inf")) for ch in per)
            if left < -70 and right > -50:
                c.channel_issue = "left_silent"
            elif right < -70 and left > -50:
                c.channel_issue = "right_silent"
            elif left > -50 and right > -50:
                mid = _rms(_levels(ffmpeg, path, "pan=mono|c0=0.5*c0+0.5*c1,"))
                side = _rms(_levels(ffmpeg, path, "pan=mono|c0=0.5*c0-0.5*c1,"))
                if mid < side - 10:          # en mono, les deux canaux s'annuleraient
                    c.channel_issue = "phase"
        # Ronflement : bande étroite autour de 50 (ou 60) Hz nettement au-dessus des voisines
        mono = "pan=mono|c0=0.5*c0+0.5*c1," if channels == 2 else ""
        if c.channel_issue == "phase":
            mono = "pan=mono|c0=c0,"
        band = {f: _rms(_levels(ffmpeg, path, f"{mono}bandpass=f={f}:width_type=h:w=4,"))
                for f in (50, 60, 75, 90)}
        for hz, ref in ((50, 75), (60, 90)):
            if band[hz] > -65 and band[hz] - band[ref] > 12 and band[hz] >= band[110 - hz]:
                c.hum_hz = hz
    except (subprocess.TimeoutExpired, OSError, ValueError, KeyError):
        pass
    return c
