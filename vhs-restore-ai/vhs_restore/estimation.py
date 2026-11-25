"""Durée et place annoncées avant de lancer.

L'aperçu chronomètre seulement la restauration de ses 10 secondes. On étend
ce temps à la durée gardée (début, fin et passages enlevés déduits). La place
vient de pipeline.disk_needs et de l'espace libre du dossier de sortie.
Aucun filtre n'est modifié.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import pipeline
from .tools import ToolError


def duree_gardee(duree: float, debut: float, fin: float,
                 coupes: list[tuple[float, float]]) -> float:
    """Secondes gardées : fenêtre début / fin, moins les passages enlevés."""
    gardes = pipeline.passages_gardes(float(duree or 0), debut, fin, coupes)
    return sum(max(0.0, b - a) for a, b in gardes)


# Durée réelle / aperçu étendu, mesurée sur un film SD de synthèse avec son (60 et 180 s) :
# l'aperçu encode en « veryfast », la restauration en « medium » ; « Fidèle » garde les 50
# demi-images par seconde (deux fois plus d'images à encoder). Mesuré à 180 s : 2,11 / 1,66 /
# 1,57 ; à 60 s : 2,34 / 1,82 / 1,65. Arrondi vers le haut : mieux vaut finir avant l'heure dite.
FACTEUR = {"fidele": 2.2, "equilibre": 1.75, "maximum": 1.65}
FACTEUR_INCONNU = 2.2


def facteur(cle: str) -> float:
    return FACTEUR.get(cle, FACTEUR_INCONNU)


def extrapoler(secondes_apercu: float, duree_apercu: float, gardee: float) -> float:
    """Temps estimé pour toute la durée gardée, à partir du chronométrage de l'aperçu."""
    if secondes_apercu <= 0 or duree_apercu <= 0 or gardee <= 0:
        return 0.0
    return secondes_apercu * (gardee / duree_apercu)


def phrase_temps(secondes: float) -> str:
    """« environ 2 heures », « environ 40 minutes », « moins d'une minute »."""
    if secondes < 45:
        return "moins d'une minute"
    if secondes < 90:
        return "environ 1 minute"
    if secondes < 3600:
        return f"environ {max(2, round(secondes / 60))} minutes"
    if secondes < 5400:
        return "environ 1 heure"
    n = max(2, round(secondes / 3600))
    return f"environ {n} heure" if n == 1 else f"environ {n} heures"


def _go(octets: float) -> str:
    g = max(0.0, octets) / pipeline.GB
    if g >= 10:
        return f"{round(g):.0f}"
    texte = f"{g:.1f}".replace(".", ",")
    return texte[:-2] if texte.endswith(",0") else texte


def phrase(secondes: float, besoin: float, libre: float) -> str:
    """Phrase affichée. S'il manque de la place, cela est dit en premier."""
    temps = f"Durée estimée : {phrase_temps(secondes)} sur cet ordinateur."
    place = f"Il faut environ {_go(besoin)} Go ; il en reste {_go(libre)} Go."
    if libre < besoin * 1.1:
        return "Il manque de la place : " + place[0].lower() + place[1:] + " " + temps
    return temps + " " + place


def _besoin_et_libre(info, s, gardee: float, dossier: Path) -> tuple[float, float] | None:
    final, temp = pipeline.disk_needs(info, s, duration=gardee)
    try:
        libre = shutil.disk_usage(dossier).free
        besoin = final
        if os.stat(dossier).st_dev == os.stat(pipeline._work_root()).st_dev:
            besoin += temp
    except OSError:
        return None
    return besoin, libre


def calcul(w) -> tuple[float, tuple[float, float] | None] | None:
    """(secondes estimées, (octets nécessaires, octets libres) ou None), ou None sans aperçu chronométré."""
    info, preview = w.info, w.preview
    if info is None or preview is None or getattr(w, "is_photo", False):
        return None
    secondes = float(getattr(preview, "restauration_s", 0) or 0)
    duree_apercu = float(getattr(preview, "duration", 0) or 0)
    if secondes <= 0 or duree_apercu <= 0 or not info.duration:
        return None
    try:
        gardee = duree_gardee(info.duration, w.trim_start.value(), w.trim_end.value(),
                              list(getattr(w, "_coupes", ()) or ()))
    except ToolError:
        return None
    s = w.settings()
    estime = extrapoler(secondes, duree_apercu, gardee) * facteur(s.profile.key)
    if estime <= 0:
        return None
    dossier = Path(w.out_edit.text() or info.path.parent)
    if not dossier.is_dir():
        dossier = Path(info.path.parent)
    return estime, _besoin_et_libre(info, s, gardee, dossier)


def lignes(w) -> tuple[str, str] | None:
    """Deux lignes pour l'écran : la durée, puis la place (« » si elle n'a pas pu être lue).
    S'il manque de la place, la seconde commence par « Il manque de la place »."""
    res = calcul(w)
    if res is None:
        return None
    estime, place = res
    temps = f"Durée estimée : {phrase_temps(estime)} sur cet ordinateur."
    if place is None:
        return temps, ""
    besoin, libre = place
    texte = f"Il faut environ {_go(besoin)} Go ; il en reste {_go(libre)} Go."
    if libre < besoin * 1.1:
        texte = "Il manque de la place : " + texte[0].lower() + texte[1:]
    return temps, texte


def annonce(w) -> str:
    """Phrase pour l'écran, ou « » si l'aperçu n'a pas encore chronométré une restauration.
    S'il manque de la place, cela est dit en premier."""
    res = lignes(w)
    if res is None:
        return ""
    temps, place = res
    if place.startswith("Il manque"):
        return place + " " + temps
    return (temps + " " + place).strip()
