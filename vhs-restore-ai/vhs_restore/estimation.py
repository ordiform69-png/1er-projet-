"""Durée, place et outils, dits avant de lancer. N'enchaîne aucun filtre."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import pipeline

GO = 1e9


def secondes(restauration_s: float, apercu_s: float, gardee_s: float) -> float | None:
    """Le temps mesuré sur l'extrait restauré, rapporté à la durée gardée.

    Les trois durées sont celles de la source (l'extrait de l'aperçu, puis le film
    après le début, la fin et les passages enlevés). None si l'aperçu n'a pas
    encore été chronométré."""
    if restauration_s <= 0 or apercu_s <= 0 or gardee_s <= 0:
        return None
    return restauration_s * (gardee_s / apercu_s)


def phrase_temps(secondes_estimees: float) -> str:
    """« Environ 2 heures sur cet ordinateur. Vous pouvez faire autre chose pendant ce temps. »"""
    s = max(0.0, float(secondes_estimees))
    if s < 90:
        corps = "1 minute"
    elif s < 3600:
        n = max(2, int(round(s / 60)))
        corps = f"{n} minutes"
    else:
        total = max(60, int(round(s / 60 / 15) * 15))
        h, m = divmod(total, 60)
        heures = "1 heure" if h == 1 else f"{h} heures"
        corps = heures if m == 0 else f"{heures} et {m} minutes"
    return (f"Environ {corps} sur cet ordinateur. "
            "Vous pouvez faire autre chose pendant ce temps.")


def _go(octets: float) -> str:
    g = max(0.0, float(octets)) / GO
    if g < 0.1:
        return "0,1"
    if g >= 10:
        return str(int(round(g)))
    texte = f"{g:.1f}".replace(".", ",")
    return texte[:-2] if texte.endswith(",0") else texte


def phrase_place(info, s, dossier: Path, duree: float | None) -> tuple[str, bool]:
    """(phrase, assez de place). Phrase vide si la taille ne se calcule pas."""
    dossier = Path(dossier)
    if info.width <= 0 or info.height <= 0:
        return "", True
    if not dossier.exists():
        dossier = Path(".")
    try:
        final, temp = pipeline.disk_needs(info, s, None, duree if duree and duree > 0 else None)
        libre = shutil.disk_usage(dossier).free
        meme_disque = os.stat(dossier).st_dev == os.stat(pipeline._work_root()).st_dev
    except (OSError, ZeroDivisionError, pipeline.ToolError):
        return "", True
    besoin = final + (temp if meme_disque else 0.0)
    if besoin < 1e6:
        return "", True
    assez = libre >= besoin * 1.1
    if assez:
        return (f"Il faut environ {_go(besoin)} Go ; il en reste {_go(libre)} Go "
                "dans le dossier choisi.", True)
    return (f"Il manque de la place : il faut environ {_go(besoin)} Go, il en reste "
            f"{_go(libre)} Go dans le dossier choisi.", False)


def phrases_outils(info, s, *, qtgmc: bool, ia: bool) -> list[str]:
    """Dit ce qui sera remplacé, seulement si le réglage le voulait et qu'il manque."""
    lignes = []
    if (s.source == "video" and s.profile.deinterlacer == "qtgmc"
            and pipeline.effective_scan(info, s) in ("tff", "bff") and not qtgmc):
        lignes.append("Le désentrelacement le plus fin n'est pas installé : "
                      "un autre, un peu moins fin, sera utilisé.")
    if s.profile.ai_default and not ia and not s.use_ai:
        lignes.append("L'amélioration par intelligence artificielle n'est pas installée : "
                      "elle ne sera pas utilisée.")
    return lignes


def texte(info, s, dossier: Path, duree: float | None, temps: float | None, *,
          qtgmc: bool, ia: bool) -> str:
    lignes = []
    if temps is not None and temps > 0:
        lignes.append(phrase_temps(temps))
    place, _assez = phrase_place(info, s, dossier, duree)
    if place:
        lignes.append(place)
    lignes.extend(phrases_outils(info, s, qtgmc=qtgmc, ia=ia))
    return "\n".join(lignes)
