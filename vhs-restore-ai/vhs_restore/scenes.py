"""Changements de scène : où le film passe d'une image à une autre.

FFmpeg, filtre scene, 4 images par seconde en petit. Aucun modèle, aucune
nouvelle dépendance. Le fichier d'origine n'est pas modifié. Les moments sont
proposés : rien n'est coupé sans un clic.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Callable

from .tools import Cancelled, ToolError, run, verifier_chemin

Progress = Callable[[float, str], None]

SEUIL = 0.30          # écart d'image au-delà duquel c'est un vrai changement
PAS = 0.25            # 4 images par seconde : assez pour une coupe, rapide sur une cassette
ECART_MIN = 2.0       # deux changements plus proches sont le même
MAX_AFFICHES = 8      # au-delà, on garde les plus espacés : l'écran reste lisible


def phrase(t: float) -> str:
    """« 1 min 20 », jamais un horodatage technique."""
    t = int(round(max(0.0, t)))
    if t < 60:
        return f"{t} seconde" if t == 1 else f"{t} secondes"
    m, s = divmod(t, 60)
    if m < 60:
        return f"{m} min {s:02d}" if s else f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d}"


def regrouper(moments: list[float], duree: float = 0.0, maximum: int = MAX_AFFICHES) -> list[float]:
    """Enlève le tout début, la toute fin, et les changements trop proches. Plafonne l'affichage."""
    gardes: list[float] = []
    for t in sorted(moments):
        if t < 0.5 or (duree and t > duree - 0.5):
            continue
        if gardes and t - gardes[-1] < ECART_MIN:
            continue
        gardes.append(round(t, 2))
    if len(gardes) <= maximum:
        return gardes
    if maximum <= 1:
        return gardes[:1]
    pas = (len(gardes) - 1) / (maximum - 1)
    return [gardes[round(i * pas)] for i in range(maximum)]


def detecter(ffmpeg: str, path: Path, duree: float | None = None, *,
             cancel: threading.Event | None = None, progress: Progress | None = None) -> list[float]:
    """Lit le film en petit et renvoie les moments où l'image change nettement."""
    verifier_chemin(Path(path), origine=True)
    duree = float(duree or 0.0)
    moments: list[float] = []

    def ligne(l: str) -> None:
        if "pts_time:" not in l or "showinfo" not in l:
            return
        m = re.search(r"pts_time:([\d.]+)", l)
        if not m:
            return
        t = float(m.group(1))
        moments.append(t)
        if progress and duree:
            progress(min(0.99, t / duree), "Recherche des changements…")

    run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:v:0", "-an",
         "-vf", f"fps={1 / PAS:g},scale=80:60:flags=area,select='gt(scene,{SEUIL})',showinfo",
         "-f", "null", "-"], cancel=cancel, on_line=ligne, what="FFmpeg (changements de scène)")
    if progress:
        progress(1.0, "Recherche terminée")
    return regrouper(moments, duree)


__all__ = ["MAX_AFFICHES", "detecter", "phrase", "regrouper"]
