"""Adaptateur facultatif : poussières et rayures de pellicule, par Analog Repair.

Analog Repair (licence MIT, https://github.com/Bratwurstexe/ANALOG_REPAIR) est utilisé
dans une version figée (ANALOG_REPAIR_COMMIT), et SEULEMENT pour son étape
« poussières et rayures » : toutes ses autres corrections sont à 0. Mesuré sur une
vraie pellicule des années 1970 : 97 % du grain conservé avec ce seul réglage, contre
51 % avec son préréglage Super 8 complet (voir DECISIONS.md).

Il tourne dans un processus séparé (annulable), et écrit un intermédiaire ProRes 422
10 bits (quasi sans perte) ; la chaîne habituelle de VHS Restore AI part ensuite de
ce fichier. Une seule compression finale, donc.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
from pathlib import Path
from typing import Callable

from .tools import ToolError, run

ANALOG_REPAIR_COMMIT = "561ba5a18881422ad0415df6c13fa2b962159da2"
DUST_STRENGTH = 60      # 0-100, valeur de son préréglage « 8 mm / Super 8 »
# Préréglage « VHS tape » d'Analog Repair, sans le reste (pas de fusion qui mange
# le grain, pas d'agrandissement, pas d'effacement du tampon date).
TAPE_NOISE = 60         # poursuite, bande du bas, lignes qui ondulent
TAPE_COLOUR = 40       # arcs-en-ciel et couleur perdue ; la luminance reste
TAPE_DROPOUT = 30       # taches ou lignes présentes sur une seule image


def available() -> bool:
    return importlib.util.find_spec("analogrepair") is not None


def engine_command(settings: Path) -> list[str]:
    """Analog Repair est lancé par notre propre exécutable (« --poussieres »), ce qui
    fonctionne aussi dans l'application Windows empaquetée, sans Python installé."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--poussieres", str(settings)]
    return [sys.executable, "-m", "vhs_restore", "--poussieres", str(settings)]


def clean(source: Path, work: Path, ffmpeg_dir: str, start: float | None, duration: float | None,
          cancel: threading.Event | None = None,
          progress: Callable[[float, str], None] | None = None, *,
          signal: str = "film", dust_strength: int = DUST_STRENGTH,
          tape_strength: int = 0, colour_strength: int = 0,
          label: str = "Poussières et rayures…") -> Path:
    """Écrit work/poussieres.mov. Par défaut : poussières de pellicule seules.
    Les autres étapes d'Analog Repair restent à 0 sauf si on les demande
    (bruit de bande, couleur des décrochages, taches d'une image)."""
    if not available():
        raise ToolError("Le module « poussières et rayures » n'est pas installé "
                        "(relancez installer.bat -AvecPoussieres).")
    target = work / "poussieres.mov"
    begin = float(start or 0.0)
    recipe = dict(signalart=signal, farbberuhigung=int(colour_strength), rauschminderung=0,
                  kantendetail=0, stabilisierung=0, flackerausgleich=0,
                  staubentfernung=int(dust_strength), bandstoerung=int(tape_strength),
                  osd_entfernen=False, vergroesserung_prozent=100, look=False,
                  koernung_behalten=True, dateiformat="mov-prores", schnittbeginn=begin,
                  schnittende=begin + duration if duration else 0.0)
    settings = work / "poussieres.json"
    settings.write_text(json.dumps({"action": "export", "source": str(source), "target": str(target),
                                    "recipe": recipe}), encoding="utf-8")
    errors: list[str] = []

    def on_line(line: str) -> None:
        if not line.startswith("{"):
            return
        msg = json.loads(line)
        if msg.get("kind") == "progress" and progress:
            progress(float(msg.get("fraction", 0)), label)
        elif msg.get("kind") == "error":
            errors.append(str(msg.get("message")))

    # Analog Repair appelle « ffmpeg » par le PATH : on lui donne celui de l'application.
    env = dict(os.environ, PATH=ffmpeg_dir + os.pathsep + os.environ.get("PATH", ""))
    try:
        run(engine_command(settings), cancel=cancel, on_line=on_line, env=env,
            what="Analog Repair (poussières et rayures)")
    except ToolError as exc:
        raise ToolError(f"Poussières et rayures : {errors[0] if errors else exc}") from exc
    if errors or not target.is_file():
        raise ToolError("Poussières et rayures : " + (errors[0] if errors else "aucun fichier produit"))
    return target


def bridge_main(settings: str) -> int:
    """Point d'entrée « --poussieres » : exécute le moteur d'Analog Repair."""
    from analogrepair import bridge
    sys.argv = ["analogrepair", settings]
    return bridge.main()
