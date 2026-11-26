"""Essai n°18, agent F3 : catalogue des modèles comparés (aucune dépendance).

Partagé par f3_convertir_onnx.py (conversion, à part) et f3_vhs.py (essai).
Fiches vérifiées le 26/11/2026 sur OpenModelDB (dépôt OpenModelDB/open-model-database,
commit 5a35f802749699031d5cbb6ea660b989ebd3ac3d) et sur l'ancienne base upscale.wiki
(archive web.archive.org du 01/06/2023). Voir F3-MODELES-VHS.md.
Les empreintes SHA-256 des poids .pth ont été recalculées sur les fichiers téléchargés.
"""
from __future__ import annotations

import os
from pathlib import Path

# Dossier des poids et des .onnx : TOUJOURS hors du dépôt.
CACHE = Path(os.environ.get("VHSRA_N18_CACHE",
                            Path.home() / ".cache" / "vhsrestore-n18" / "f3")).expanduser()

OMDB = "https://github.com/OpenModelDB/open-model-database/blob/5a35f802749699031d5cbb6ea660b989ebd3ac3d/data/models/"

MODELES = [
    {
        "cle": "vhs_sharpen",
        "nom": "1x VHS Sharpen",
        "auteur": "RTX 2080 ti hoarder (rtx-2080-ti-hoarder)",
        "architecture": "ESRGAN (RRDBNet 64nf 23nb)",
        "echelle": 1,
        "fichier": "1x-VHS-Sharpen.pth",
        "taille": 66665765,
        "sha256": "201b470286fffe5d9f3cb75cd259ab50dce11a339920ee5f8a06180c3e2ec30e",
        "source": {"type": "mega", "url": "https://mega.nz/file/Z5IXBSrA#bE9VasE60zLqZ_NggOhs40Z9l2z8DapROZb5VX0F3h0"},
        "page": "https://openmodeldb.info/models/1x-VHS-Sharpen",
        "fiche": OMDB + "1x-VHS-Sharpen.json",
        "licence_modele": "CC-BY-NC-SA-4.0",
        "licence_donnees": "non trouvée (images de Blu-ray 4K du commerce repassées sur VHS)",
    },
    {
        "cle": "baldrick",
        "nom": "1x BaldrickVHSFix V0.2",
        "auteur": "NimRodZorg (nimrodzorg)",
        "architecture": "ESRGAN (RRDBNet 64nf 23nb)",
        "echelle": 1,
        "fichier": "1x-BaldrickVHSFixV0-2.pth",
        "taille": 66665765,
        "sha256": "9c945b10ab0d45f8f53d2e18f9bfe1017dbc3c6e7233d657cb4845de81cd5ea1",
        "source": {"type": "direct", "url": "https://objectstorage.us-phoenix-1.oraclecloud.com/n/ax6ygfvpvzka/b/open-modeldb-files/o/1x-BaldrickVHSFixV0-2.pth"},
        "page": "https://openmodeldb.info/models/1x-BaldrickVHSFixV0-2",
        "fiche": OMDB + "1x-BaldrickVHSFixV0-2.json",
        "licence_modele": "CC-BY-NC-SA-4.0",
        "licence_donnees": "non trouvée (enregistrement VHS d'un film et Blu-ray du même film)",
        "note": "Source déjà désentrelacée seulement (indication de l'auteur).",
    },
    {
        "cle": "vhs_film_2x",
        "nom": "2x VHS upscale and denoise Film",
        "auteur": "itewreed",
        "architecture": "ESRGAN (RRDBNet 64nf 23nb)",
        "echelle": 2,
        "fichier": "2x-VHS-upscale-and-denoise-Film.pth",
        "taille": 66809646,
        "sha256": "22b9b1178f5b20a925fdf62c05b56f167c05ca082234841666171f6262f0ac55",
        "source": {"type": "gdrive", "id": "1LFiaoiPDUoAIfNCTDBm2GzJnWvgjxft9",
                   "url": "https://drive.google.com/file/d/1LFiaoiPDUoAIfNCTDBm2GzJnWvgjxft9/view"},
        "page": "https://openmodeldb.info/models/2x-VHS-upscale-and-denoise-Film",
        "fiche": OMDB + "2x-VHS-upscale-and-denoise-Film.json",
        "licence_modele": "CC-BY-NC-SA-4.0",
        "licence_donnees": "non trouvée (enregistrement VHS d'un film à la télévision et Blu-ray du même film)",
    },
    {
        # Référence : l'IA actuelle du rendu « Nettoyage au plus fort ».
        # Le logiciel appelle realesrgan-ncnn-vulkan.exe -n realesrgan-x4plus -s 4
        # (vhs_restore/upscaler.py, paquets.json). Ici : mêmes poids d'origine
        # (RealESRGAN_x4plus.pth), convertis en ONNX pour une comparaison sur processeur.
        "cle": "realesrgan_x4plus",
        "nom": "Real-ESRGAN x4plus (IA actuelle, en ONNX)",
        "auteur": "Xintao Wang (xinntao)",
        "architecture": "ESRGAN (RRDBNet 64nf 23nb)",
        "echelle": 4,
        "fichier": "RealESRGAN_x4plus.pth",
        "taille": 67040989,
        "sha256": "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1",
        "source": {"type": "direct", "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"},
        "page": "https://github.com/xinntao/Real-ESRGAN",
        "fiche": "https://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE",
        "licence_modele": "BSD-3-Clause",
        "licence_donnees": "DIV2K : « academic research purpose only » ; Flickr2K, OST : non trouvée",
    },
]


def par_cle(cle: str) -> dict:
    for m in MODELES:
        if m["cle"] == cle:
            return m
    raise KeyError(cle)


def chemin_pth(m: dict) -> Path:
    return CACHE / m["fichier"]


def chemin_onnx(m: dict) -> Path:
    return CACHE / (Path(m["fichier"]).stem + ".onnx")
