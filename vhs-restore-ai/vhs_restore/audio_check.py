"""Mesures du son pour l'analyse : canal muet, canaux en opposition de phase,
saturation (écrêtage), ronflement du secteur, vent. FFmpeg seul, sur les deux
premières minutes au plus. Une seule lecture regroupe toutes les mesures
(une deuxième, groupée elle aussi, seulement si les canaux sont en opposition :
leur somme s'annulerait). Ces mesures ne servent qu'à CONSEILLER : rien n'est
corrigé sans que l'utilisateur le demande."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .tools import run_capture

SECONDS = 120
_ASTATS = ("astats@{name}=measure_perchannel=Peak_level+RMS_level+Peak_count:"
           "measure_overall=Number_of_samples")


@dataclass
class AudioCheck:
    channels: int = 0
    channel_issue: str = ""         # "" | left_silent | right_silent | phase
    clipped: float = 0.0            # part des échantillons au plafond (0 à 1)
    hum_hz: int = 0                 # 0 | 50 | 60
    wind: bool = False              # graves forts et irréguliers (vent, grondement)


def _parse_levels(text: str) -> list[dict[str, float]]:
    chans: list[dict[str, float]] = []
    total = 0.0      # « Number of samples » n'existe qu'en bilan global (par canal)
    for line in text.splitlines():
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


def _levels(ffmpeg: str, path: Path, af: str) -> list[dict[str, float]]:
    """Statistiques astats par canal (dB et compteurs) après le filtre af.
    Réservé aux mesures après export. L'analyse passe par measure(), en une lecture."""
    r = run_capture([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:a:0",
                     "-t", str(SECONDS), "-af",
                     f"{af}astats=measure_perchannel=Peak_level+RMS_level+Peak_count:"
                     "measure_overall=Number_of_samples", "-f", "null", "-"], timeout=300)
    return _parse_levels(r.stderr)


def _rms(chans: list[dict[str, float]]) -> float:
    return chans[0].get("RMS level dB", float("-inf")) if chans else float("-inf")


def _graph(channels: int, phase: bool = False) -> str:
    """Mesures d'une analyse en une lecture. `phase` : côté gauche seul
    (la somme des deux canaux s'annulerait)."""
    if phase:
        names = ["p50", "p60", "p75", "p90", "plow"]
    elif channels == 2:
        names = ["full", "mid", "side", "b50", "b60", "b75", "b90", "low"]
    else:
        names = ["full", "b50", "b60", "b75", "b90", "low"]
    mix = "pan=mono|c0=0.5*c0+0.5*c1,"
    left = "pan=mono|c0=c0,"
    stereo = channels == 2 and not phase
    parts = ["[0:a]asplit=" + str(len(names)) + "".join(f"[s{i}]" for i in range(len(names)))]
    outs: list[str] = []
    for i, name in enumerate(names):
        stats = _ASTATS.format(name=name)
        if name == "full":
            chain = stats + (",aformat=channel_layouts=mono" if channels == 2 else "")
        elif name == "mid":
            chain = mix + stats
        elif name == "side":
            chain = "pan=mono|c0=0.5*c0-0.5*c1," + stats
        elif name in ("low", "plow"):
            chain = (left if phase else mix if stereo else "") + "lowpass=f=80," + stats
        elif name.startswith("p"):
            chain = left + f"bandpass=f={name[1:]}:width_type=h:w=4," + stats
        else:
            chain = (mix if stereo else "") + f"bandpass=f={name[1:]}:width_type=h:w=4," + stats
        parts.append(f"[s{i}]{chain}[{name}]")
        outs.append(f"[{name}]")
    parts.append("".join(outs) + f"amix=inputs={len(names)}:normalize=0:duration=shortest")
    return ";".join(parts)


def _sections(stderr: str) -> dict[str, str]:
    buckets: dict[str, list[str]] = {}
    for line in stderr.splitlines():
        m = re.search(r"\[astats@([A-Za-z0-9]+)", line)
        if m:
            buckets.setdefault(m.group(1), []).append(line)
    return {k: "\n".join(v) for k, v in buckets.items()}


def _read(ffmpeg: str, path: Path, channels: int, phase: bool = False) -> dict[str, list[dict[str, float]]]:
    r = run_capture([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path),
                     "-filter_complex", _graph(channels, phase), "-t", str(SECONDS),
                     "-f", "null", "-"], timeout=300)
    return {k: _parse_levels(v) for k, v in _sections(r.stderr).items()}


def measure(ffmpeg: str, path: Path, channels: int) -> AudioCheck:
    c = AudioCheck(channels=channels)
    try:
        blocks = _read(ffmpeg, path, channels)
        per = blocks.get("full", [])
        # Saturation : beaucoup d'échantillons collés au plafond numérique
        for ch in per:
            n = ch.get("Number of samples", 0) or 0
            if n and ch.get("Peak level dB", -99) > -0.1:
                c.clipped = max(c.clipped, ch.get("Peak count", 0) / n)
        if channels == 2 and len(per) == 2:
            left_rms, right_rms = (ch.get("RMS level dB", float("-inf")) for ch in per)
            if left_rms < -70 and right_rms > -50:
                c.channel_issue = "left_silent"
            elif right_rms < -70 and left_rms > -50:
                c.channel_issue = "right_silent"
            elif left_rms > -50 and right_rms > -50:
                if _rms(blocks.get("mid", [])) < _rms(blocks.get("side", [])) - 10:
                    c.channel_issue = "phase"          # en mono, les deux canaux s'annuleraient
        if c.channel_issue == "phase":
            # Deuxième lecture groupée : le mélange des deux côtés annulerait le signal.
            blocks.update(_read(ffmpeg, path, channels, phase=True))
        key = "p" if c.channel_issue == "phase" else "b"
        band = {f: _rms(blocks.get(f"{key}{f}", [])) for f in (50, 60, 75, 90)}
        for hz, ref in ((50, 75), (60, 90)):
            if band[hz] > -65 and band[hz] - band[ref] > 12 and band[hz] >= band[110 - hz]:
                c.hum_hz = hz
        low = blocks.get("plow" if c.channel_issue == "phase" else "low", [])
        low_rms = _rms(low)
        low_peak = low[0].get("Peak level dB", float("-inf")) if low else float("-inf")
        full_rms = max((ch.get("RMS level dB", float("-inf")) for ch in per), default=float("-inf"))
        if low_rms > -36 and low_peak - low_rms > 8 and low_rms > full_rms - 8:
            c.wind = True
    except (subprocess.TimeoutExpired, OSError, ValueError, KeyError):
        pass
    return c

