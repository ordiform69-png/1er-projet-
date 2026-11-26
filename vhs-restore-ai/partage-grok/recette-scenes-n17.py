#!/usr/bin/env python3
"""Recette du film de synthèse des mesures « lumière par scène » (demande n°17).

Même film que l'agent E (Design Maquettes), fichier
`partage-grok/mesures-n17/mesurer.py` sur la branche `grok/qualite` :
PAL 720×576, 25 im/s, FFV1, sans son, trois scènes 8 s + 16 s + 8 s = 32 s.
Les recettes lavfi sont copiées telles quelles (RECETTE_S1, RECETTE_S2,
RECETTE_S3). L'assemblage est le filtre `concat` (une piste continue), pas le
démultiplexeur : E a constaté que le démultiplexeur faisait sauter la scène 2
à l'analyse du moteur.

L'aperçu à 20 s tombe dans la scène 2 (8–24 s).

La vidéo n'est pas versionnée. Elle est régénérée à la demande :

    python3 recette-scenes-n17.py /tmp/film-3scenes.mkv
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

LARGEUR, HAUTEUR, CADENCE = 720, 576, 25
DUREE_S1, DUREE_S2, DUREE_S3 = 8.0, 16.0, 8.0
RECETTE_S1 = (
    "testsrc2=size=720x576:rate=25,setsar=16/15,"
    "colorchannelmixer=rr=1.20:gg=0.92:bb=0.55,"
    "colorlevels=romin=0.16:gomin=0.16:bomin=0.16:"
    "romax=0.48:gomax=0.48:bomax=0.48"
)
RECETTE_S2 = "testsrc2=size=720x576:rate=25,setsar=16/15"
RECETTE_S3 = (
    "testsrc2=size=720x576:rate=25,setsar=16/15,"
    "colorchannelmixer=rr=0.55:gg=0.92:bb=1.20,"
    "colorlevels=romin=0.52:gomin=0.52:bomin=0.52:"
    "romax=0.90:gomax=0.90:bomax=0.90"
)
SCENES = (
    {"id": "1", "nom": "sombre et orangée", "duree": DUREE_S1, "recette": RECETTE_S1, "debut": 0.0},
    {"id": "2", "nom": "normale", "duree": DUREE_S2, "recette": RECETTE_S2, "debut": DUREE_S1},
    {"id": "3", "nom": "claire et bleutée", "duree": DUREE_S3, "recette": RECETTE_S3,
     "debut": DUREE_S1 + DUREE_S2},
)
DUREE_FILM = DUREE_S1 + DUREE_S2 + DUREE_S3  # 32 s


def _ff(ffmpeg: str, *args: str) -> None:
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode:
        raise RuntimeError(f"ffmpeg a échoué ({r.returncode}) : {r.stderr[-1200:]}\n{args}")


def fabriquer(ffmpeg: str, dossier: Path) -> dict[str, Path]:
    """Régénère les trois scènes et le film assemblé. Rien n'est écrit dans le dépôt."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemins: dict[str, Path] = {}
    for sc in SCENES:
        p = dossier / f"scene-{sc['id']}.mkv"
        _ff(ffmpeg, "-f", "lavfi", "-i", sc["recette"], "-t", f"{sc['duree']:.3f}",
            "-c:v", "ffv1", str(p))
        chemins[f"scene-{sc['id']}"] = p
    film = dossier / "film-3scenes.mkv"
    _ff(ffmpeg,
        "-i", str(chemins["scene-1"]),
        "-i", str(chemins["scene-2"]),
        "-i", str(chemins["scene-3"]),
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,setsar=16/15",
        "-c:v", "ffv1", str(film))
    chemins["film"] = film
    return chemins


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg est introuvable")
    dest = Path(sys.argv[1])
    chemins = fabriquer(ffmpeg, dest if dest.suffix == "" else dest.parent)
    if dest.suffix:
        if chemins["film"] != dest:
            chemins["film"].replace(dest)
        print(dest)
    else:
        print(chemins["film"])


if __name__ == "__main__":
    main()
