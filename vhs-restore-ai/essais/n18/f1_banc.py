"""Essai n°18, agent F1 : branchement sur le banc commun de F4 (banc.py, grok/ia-essai d9d88e4).

Tout ce qui touche au banc passe par ce petit module ; l'essai F1 (ia_lumiere.py) n'appelle
rien d'autre. Rien n'est redéfini : images de référence, dégradation (réglages par défaut,
« images » et « graine » inchangés), mesures (PSNR, SSIM, ΔE2000) et chronométrage sont ceux
de F4. Comparaison sur l'image du milieu de chaque extrait, comme le banc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import banc

LARGEUR, HAUTEUR = banc.LARGEUR, banc.HAUTEUR
ErreurBanc = banc.ErreurBanc
coeurs, chronometrer, mesurer, ecrire_csv, ecrire_png = (
    banc.coeurs, banc.chronometrer, banc.mesurer, banc.ecrire_csv, banc.ecrire_png)
NON = banc.texte_non_mesure()


@dataclass
class Scene:
    nom: str
    sujet: str
    images: np.ndarray               # n x 576 x 720 x 3, uint8 RGB (extrait dégradé ou réel)
    milieu: int                      # image comparée à l'origine
    origine: np.ndarray | None       # None pour un extrait réel
    extrait: object | None = None    # banc.ExtraitDegrade (pour banc.evaluer)
    infos: dict = field(default_factory=dict)


def scenes_banc(cache: Path | None = None) -> list[Scene]:
    """Une scène par image de référence de F4 : banc.charger_references() puis banc.degrader()."""
    sc = []
    for im in banc.charger_references(cache):
        ex = banc.degrader(im.rgb)
        sc.append(Scene(im.reference.identifiant, im.reference.sujet, ex.images, ex.milieu, im.rgb, ex,
                        {"degradation": ex.filtre, "licence": im.reference.licence, "url": im.reference.url}))
    return sc


def scenes_extraits(dossier: Path, n_images: int = 9) -> list[Scene]:
    """Extraits réels : banc.lister_medias() + banc.charger_media() (images consécutives au milieu)."""
    sc = []
    for m in banc.lister_medias(dossier):
        pile = banc.charger_media(m, n_images=n_images)
        sc.append(Scene(m.name, "extrait", pile, pile.shape[0] // 2, None))
    return sc


def appliquer(scene: Scene, vf: str) -> tuple[np.ndarray, float]:
    """Chaîne FFmpeg sur tout l'extrait (banc.appliquer_filtre) : (images, secondes par image)."""
    if not vf:
        return scene.images, 0.0
    r = banc.appliquer_filtre(scene.images, vf)
    if r.images.shape[0] != scene.images.shape[0]:
        raise ErreurBanc("Le filtre n'a pas rendu le même nombre d'images.")
    return r.images, r.secondes_par_image


def mesures(scene: Scene, image: np.ndarray) -> dict:
    """Écart à l'origine (banc.mesurer) sur l'image du milieu ; « non mesuré » sans origine."""
    if scene.origine is None:
        return {"psnr": NON, "ssim": NON, "delta_e": NON}
    m = banc.mesurer(scene.origine, image)
    return {"psnr": round(m.psnr, 4), "ssim": round(m.ssim, 5), "delta_e": round(m.delta_e, 4)}


def stats_sans_reference(image: np.ndarray, entree: np.ndarray) -> dict:
    """Pour voir si une méthode dérape, même sans origine : luminance moyenne, part de pixels
    écrêtés (≤ 2 ou ≥ 253), et ΔE2000 moyen par rapport à l'entrée (ampleur du changement)."""
    luma = 0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]
    return {"luma_moy": round(float(luma.mean()), 2),
            "ecretes_pct": round(100 * float(((image <= 2) | (image >= 253)).mean()), 3),
            "ecart_entree_de2000": round(banc.delta_e_moyen(entree, image), 4)}


def chaine_naturelle() -> str:
    return banc.chaine_naturelle()
