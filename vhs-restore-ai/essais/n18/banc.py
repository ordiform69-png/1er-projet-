"""Banc d'essai commun de la demande n°18 (agent F4).

Les essais F1, F2 et F3 importent ce module. Il ne modifie pas ``vhs_restore``.
Dépendances : numpy, FFmpeg, et la bibliothèque standard. Pas d'autre paquet.

Depuis ``vhs-restore-ai/`` :

    python essais/n18/reference.py
    python essais/n18/test_mesures.py

Usage pour un essai (le script est dans ``essais/n18/``, donc ``import banc``) ::

    import banc

    for image in banc.charger_references():
        origine = image.rgb                    # uint8, 720 × 576 × 3
        extrait = banc.degrader(origine)       # réglages VHS par défaut, reproductibles
        # Méthode FFmpeg (chaîne -vf) :
        chiffres = banc.evaluer(origine, extrait, banc.chaine_naturelle())
        # Méthode hors FFmpeg (ONNX, etc.) : l'image du milieu, puis mesurer et chronométrer.
        milieu = extrait.images[extrait.milieu]
        resultat, secondes = banc.chronometrer(lambda: ma_methode(milieu))
        chiffres = banc.mesurer(origine, resultat)   # .psnr .ssim .delta_e
    banc.ecrire_csv("essais/n18/mon-essai.csv", lignes, banc.COLONNES_RESULTAT)

``chaine_naturelle()`` appelle ``pipeline.filter_chain`` avec le profil
« Bien nettoyé, naturel », sans rien écrire dans le logiciel.

Le temps renvoyé est le temps mur du processus FFmpeg divisé par le nombre
d'images (démarrage inclus), sur le nombre de cœurs de ``coeurs()``.
La comparaison à l'origine se fait sur l'image du milieu (les voisines existent
pour le débruitage temporel). ``--extraits`` n'a pas d'origine connue :
PSNR, SSIM et ΔE restent « non mesuré ».
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
RACINE_LOGICIEL = ICI.parents[1]   # vhs-restore-ai/
REFERENCES = ICI / "references.csv"
LARGEUR, HAUTEUR = 720, 576
_UA = ("VHSRestoreAI-essai-n18/1.0 "
       "(banc d'essai, verification de licence et d'empreinte; "
       "https://github.com/ordiform69-png/1er-projet-)")
# Fenêtre de Wang et al., 2004. En dessous, le SSIM n'est pas défini.
_FENETRE_SSIM = 11
# Écart angulaire ignoré autour de π : un ulp de trop basculerait du mauvais
# côté de la discontinuité publiée par Sharma (paires à 0,0010 / 0,0011).
_EPSILON_PI = 1e-8

COLONNES_RESULTAT = (
    "identifiant", "sujet", "mode",
    "psnr_degrade", "ssim_degrade", "delta_e_degrade",
    "psnr", "ssim", "delta_e",
    "secondes_par_image", "secondes_total", "images",
    "coeurs", "largeur", "hauteur",
    "profil", "chaine",
    "definition", "etalement", "bruit_luma", "bruit_chroma",
    "gamma", "saturation", "dominante_r", "dominante_g", "dominante_b",
    "noirs", "graine",
    "note_juge", "definition_temps",
)

EXT_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
EXT_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m2ts", ".mts",
             ".vob", ".mpg", ".mpeg", ".wmv", ".ts"}


class ErreurBanc(RuntimeError):
    """Le banc ne peut pas produire un chiffre fiable."""


@dataclass(frozen=True)
class Reference:
    identifiant: str
    sujet: str
    titre: str
    auteur: str
    url: str
    page: str
    fichier: str
    licence: str
    licence_url: str
    modele: str
    sha256: str


@dataclass
class ImageChargee:
    reference: Reference
    chemin: Path
    rgb: np.ndarray


@dataclass(frozen=True)
class ReglagesVHS:
    """Dégradation façon VHS, toute chiffrée, appliquée par FFmpeg.

    ``gamma`` supérieur à 1 assombrit les tons moyens (le filtre ``eq`` reçoit
    l'inverse : chez FFmpeg, ``eq=gamma`` inférieur à 1 assombrit).
    ``definition`` est la part de définition gardée sur la luminance (0,5 = moitié).
    ``etalement`` est le facteur de rétrécissement horizontal de la chroma
    avant ré-étirement : 8 étale la couleur sur environ ce rapport.
    ``noirs`` relève le plancher (0 = noirs francs, 0,08 = noirs laiteux).
    ``images`` et ``graine`` fixent le court extrait et le bruit : les garder
    pour que tous les essais mesurent la même image du milieu.
    """
    definition: float = 0.5
    etalement: int = 8
    bruit_luma: int = 12
    bruit_chroma: int = 24
    gamma: float = 1.35
    saturation: float = 0.60
    dominante_r: float = 1.06
    dominante_g: float = 1.10
    dominante_b: float = 0.90
    noirs: float = 0.08
    images: int = 9
    graine: int = 1

    def __post_init__(self) -> None:
        if not (0 < self.definition <= 1):
            raise ErreurBanc("definition doit être dans ]0, 1].")
        if int(self.etalement) < 1:
            raise ErreurBanc("etalement doit être ≥ 1.")
        if not (0 <= int(self.bruit_luma) <= 100 and 0 <= int(self.bruit_chroma) <= 100):
            raise ErreurBanc("le bruit est un entier de 0 à 100.")
        if self.gamma <= 0 or self.saturation < 0:
            raise ErreurBanc("gamma doit être > 0 et la saturation ≥ 0.")
        if not (0 <= self.noirs < 1):
            raise ErreurBanc("noirs doit être dans [0, 1[.")
        if int(self.images) < 1 or int(self.graine) < 0:
            raise ErreurBanc("images ≥ 1 et graine ≥ 0.")
        for nom in ("dominante_r", "dominante_g", "dominante_b"):
            if getattr(self, nom) <= 0:
                raise ErreurBanc(f"{nom} doit être > 0.")


@dataclass
class ExtraitDegrade:
    images: np.ndarray
    milieu: int
    filtre: str
    reglages: ReglagesVHS


@dataclass
class ResultatFiltre:
    images: np.ndarray
    secondes: float

    @property
    def secondes_par_image(self) -> float:
        return self.secondes / max(1, int(self.images.shape[0]))


@dataclass(frozen=True)
class Mesures:
    psnr: float
    ssim: float
    delta_e: float


def coeurs() -> int:
    """Cœurs utilisables par ce processus (affinité Linux, sinon cpu_count)."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def chronometrer(appelable):
    """(valeur, secondes mur)."""
    debut = time.perf_counter()
    valeur = appelable()
    return valeur, time.perf_counter() - debut


def ffmpeg() -> str:
    chemin = shutil.which("ffmpeg")
    if not chemin:
        raise ErreurBanc("ffmpeg est introuvable dans le PATH.")
    return chemin


def ffprobe() -> str:
    chemin = shutil.which("ffprobe")
    if not chemin:
        raise ErreurBanc("ffprobe est introuvable dans le PATH.")
    return chemin


def lire_references(chemin: Path | None = None) -> list[Reference]:
    source = Path(chemin) if chemin else REFERENCES
    if not source.is_file():
        raise ErreurBanc(f"Liste d'images introuvable : {source}")
    with source.open(newline="", encoding="utf-8-sig") as fichier:
        lect = csv.DictReader(fichier)
        lignes = list(lect)
    if not lignes:
        raise ErreurBanc(f"Aucune image dans {source}")
    refs = []
    for n, ligne in enumerate(lignes, start=2):
        sha = (ligne.get("sha256") or "").strip().lower()
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ErreurBanc(f"{source}:{n} : SHA-256 absent ou illisible.")
        url = (ligne.get("url") or "").strip()
        if not url.startswith("https://"):
            raise ErreurBanc(f"{source}:{n} : URL https requise.")
        licence = (ligne.get("licence") or "").strip()
        if not licence_libre(licence):
            raise ErreurBanc(f"{source}:{n} : licence refusée ({licence}). "
                             "Seuls CC0 et le domaine public sont acceptés.")
        refs.append(Reference(
            identifiant=(ligne.get("identifiant") or "").strip(),
            sujet=(ligne.get("sujet") or "").strip(),
            titre=(ligne.get("titre") or "").strip(),
            auteur=(ligne.get("auteur") or "").strip(),
            url=url,
            page=(ligne.get("page") or "").strip(),
            fichier=(ligne.get("fichier") or "").strip(),
            licence=licence,
            licence_url=(ligne.get("licence_url") or "").strip(),
            modele=(ligne.get("modele") or "").strip(),
            sha256=sha,
        ))
    return refs


def licence_libre(nom: str) -> bool:
    """CC0 ou domaine public. CC BY, NC, ou « recherche seulement » : non."""
    n = (nom or "").strip().lower()
    if n.startswith("cc0") or n.startswith("cc-0") or n.startswith("cc zero"):
        return True
    return n in {"public domain", "domaine public", "pdm"} or n.startswith("public domain")


def charger_references(dossier: Path | None = None, chemin_csv: Path | None = None,
                       verifier_licence: bool = True) -> list[ImageChargee]:
    """Télécharge chaque image, vérifie le SHA-256, recadre en 720 × 576.

    La licence est revérifiée sur l'API de Wikimedia Commons (LicenseShortName
    CC0 ou domaine public, aucune restriction). Un écart arrête le banc.
    """
    refs = lire_references(chemin_csv)
    if verifier_licence:
        verifier_licences_commons(refs)
    cache = Path(dossier) if dossier else (ICI / "cache")
    cache.mkdir(parents=True, exist_ok=True)
    charges = []
    for ref in refs:
        fichier = cache / f"{ref.sha256}.img"
        if not (fichier.is_file() and _sha256_fichier(fichier) == ref.sha256):
            donnees = _http_get(ref.url)
            empreinte = hashlib.sha256(donnees).hexdigest()
            if empreinte != ref.sha256:
                raise ErreurBanc(
                    f"{ref.identifiant} : SHA-256 {empreinte} ≠ {ref.sha256} ({ref.url}).")
            temporaire = fichier.with_suffix(".partiel")
            temporaire.write_bytes(donnees)
            temporaire.replace(fichier)
        charges.append(ImageChargee(ref, fichier, preparer(fichier)))
    return charges


def verifier_licences_commons(refs: list[Reference]) -> None:
    """Relit LicenseShortName et Restrictions sur les pages Commons citées."""
    titres = [ref.fichier for ref in refs if ref.fichier]
    if len(titres) != len(refs):
        raise ErreurBanc("Chaque référence doit nommer son fichier Commons (colonne fichier).")
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": "|".join(titres),
        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiextmetadatalanguage": "en",
    })
    brut = _http_get(url, timeout=60)
    try:
        pages = json.loads(brut.decode("utf-8"))["query"]["pages"]
    except (KeyError, ValueError, UnicodeError) as exc:
        raise ErreurBanc(f"Réponse Commons illisible : {exc}") from exc
    par_titre = {page.get("title"): page for page in pages.values()}
    for ref in refs:
        page = par_titre.get(ref.fichier)
        if not page or page.get("missing") is not None and "imageinfo" not in page:
            raise ErreurBanc(f"{ref.identifiant} : page introuvable ({ref.fichier}).")
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            raise ErreurBanc(f"{ref.identifiant} : métadonnées d'image absentes.")
        meta = info.get("extmetadata") or {}

        def champ(cle: str) -> str:
            return str((meta.get(cle) or {}).get("value") or "").strip()

        courte = champ("LicenseShortName")
        restrictions = champ("Restrictions")
        if not licence_libre(courte):
            raise ErreurBanc(
                f"{ref.identifiant} : licence Commons « {courte} » refusée "
                f"(attendu CC0 ou domaine public). Page : {ref.page}")
        if restrictions:
            raise ErreurBanc(
                f"{ref.identifiant} : restriction Commons « {restrictions} ». "
                "Image écartée.")


def preparer(chemin: Path, largeur: int = LARGEUR, hauteur: int = HAUTEUR) -> np.ndarray:
    """RGB uint8 rempli par mise à l'échelle lanczos puis recadrage centré."""
    vf = (f"scale={largeur}:{hauteur}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={largeur}:{hauteur},format=rgb24")
    commande = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin",
                "-i", str(chemin), "-frames:v", "1", "-vf", vf,
                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    sortie = _lancer(commande, timeout=120)
    attendu = largeur * hauteur * 3
    if len(sortie) != attendu:
        raise ErreurBanc(f"Cadrage de {chemin.name} : {len(sortie)} octets, attendu {attendu}.")
    return np.frombuffer(sortie, dtype=np.uint8).reshape(hauteur, largeur, 3).copy()


def degrader(origine: np.ndarray, reglages: ReglagesVHS | None = None) -> ExtraitDegrade:
    """Court extrait dégradé. L'image comparée est ``images[milieu]``."""
    r = reglages or ReglagesVHS()
    image = _rgb(origine)
    hauteur, largeur = image.shape[:2]
    if hauteur < 2 or largeur < 2 or hauteur % 2 or largeur % 2:
        raise ErreurBanc("La dégradation attend une image paire d'au moins 2 × 2.")
    vf, graphe = _filtre_degradation(largeur, hauteur, r)
    pile = np.ascontiguousarray(np.broadcast_to(image, (int(r.images), hauteur, largeur, 3)))
    resultat = _ffmpeg_raw(pile, vf=vf, graphe=graphe)
    return ExtraitDegrade(resultat.images, int(r.images) // 2, graphe or vf or "", r)


def chaine_naturelle(largeur: int = LARGEUR, hauteur: int = HAUTEUR) -> str:
    """Chaîne FFmpeg du profil « Bien nettoyé, naturel ».

    Appelle ``pipeline.filter_chain``. Ne modifie aucun module de ``vhs_restore``.
    Image progressive 720 × 576 traitée comme une cassette PAL (SAR 16/15) :
    le nombre de pixels ne change pas.
    """
    if str(RACINE_LOGICIEL) not in sys.path:
        sys.path.insert(0, str(RACINE_LOGICIEL))
    from fractions import Fraction

    from vhs_restore.pipeline import Settings, filter_chain
    from vhs_restore.probe import MediaInfo
    from vhs_restore.profiles import PROFILES

    profil = PROFILES["equilibre"]
    if profil.name != "Bien nettoyé, naturel":
        raise ErreurBanc(f"Le profil equilibre s'appelle « {profil.name} », pas le profil attendu.")
    info = MediaInfo(
        path=Path("image"),
        width=largeur, height=hauteur,
        fps=Fraction(25, 1),
        sar=Fraction(1),
        dar=Fraction(4, 3) if (largeur, hauteur) == (LARGEUR, HAUTEUR) else Fraction(largeur, hauteur),
        scan="progressive",
        color_space="bt470bg",
        color_range="tv",
        color_primaries="bt470bg",
        color_transfer="bt470bg",
        standard="625/25",
        has_audio=False,
        codec="rawvideo",
        pix_fmt="rgb24",
    )
    reglages = Settings(
        profile=profil,
        resolution="source",
        scan="progressive",
        source="video",
        deinterlacer="bwdif",
        use_ai=False,
        denoise_hq=False,
        restore_audio=False,
        stabilize=False,
    )
    return filter_chain(info, reglages)


def appliquer_filtre(images: np.ndarray, vf: str, threads: int | None = None) -> ResultatFiltre:
    """Applique une chaîne ``-vf`` FFmpeg. Temps mur, démarrage inclus."""
    pile = _sequence(images)
    return _ffmpeg_raw(pile, vf=vf, threads=threads if threads is not None else coeurs())


def evaluer(origine: np.ndarray, extrait: ExtraitDegrade, vf: str,
            threads: int | None = None) -> dict:
    """Mesures de l'image dégradée et de l'image restaurée, plus le temps."""
    origine = _rgb(origine)
    brut = mesurer(origine, extrait.images[extrait.milieu])
    restaure = appliquer_filtre(extrait.images, vf, threads=threads)
    if restaure.images.shape[0] != extrait.images.shape[0]:
        raise ErreurBanc("Le filtre n'a pas rendu le même nombre d'images.")
    fin = mesurer(origine, restaure.images[extrait.milieu])
    r = extrait.reglages
    return {
        "psnr_degrade": brut.psnr, "ssim_degrade": brut.ssim, "delta_e_degrade": brut.delta_e,
        "psnr": fin.psnr, "ssim": fin.ssim, "delta_e": fin.delta_e,
        "secondes_par_image": restaure.secondes_par_image,
        "secondes_total": restaure.secondes,
        "images": int(restaure.images.shape[0]),
        "coeurs": coeurs(),
        "largeur": int(origine.shape[1]), "hauteur": int(origine.shape[0]),
        "chaine": vf,
        "definition": r.definition, "etalement": int(r.etalement),
        "bruit_luma": int(r.bruit_luma), "bruit_chroma": int(r.bruit_chroma),
        "gamma": r.gamma, "saturation": r.saturation,
        "dominante_r": r.dominante_r, "dominante_g": r.dominante_g, "dominante_b": r.dominante_b,
        "noirs": r.noirs, "graine": int(r.graine),
        "definition_temps": "mur/images, demarrage ffmpeg inclus",
        "note_juge": "non mesuré",
    }


def mesurer(origine: np.ndarray, resultat: np.ndarray) -> Mesures:
    a, b = _rgb(origine), _rgb(resultat)
    if a.shape != b.shape:
        raise ErreurBanc(f"Formes différentes : {a.shape} et {b.shape}.")
    return Mesures(psnr(a, b), ssim(a, b), delta_e_moyen(a, b))


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    """PSNR 8 bits sur tous les canaux. Infini si les images sont identiques."""
    diff = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    mse = float(np.mean(diff * diff))
    if mse == 0.0:
        return math.inf
    return float(10.0 * math.log10((255.0 * 255.0) / mse))


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    """SSIM de Wang (fenêtre gaussienne 11, σ = 1,5), moyenne des trois canaux."""
    x = np.ascontiguousarray(a, dtype=np.float64)
    y = np.ascontiguousarray(b, dtype=np.float64)
    if x.shape != y.shape or x.ndim != 3 or x.shape[2] != 3:
        raise ErreurBanc("SSIM attend deux images RGB de même forme.")
    if x.shape[0] < _FENETRE_SSIM or x.shape[1] < _FENETRE_SSIM:
        raise ErreurBanc(f"SSIM demande au moins {_FENETRE_SSIM} × {_FENETRE_SSIM} pixels.")
    noyau = _noyau_gaussien()
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    cartes = []
    for canal in range(3):
        u, v = x[..., canal], y[..., canal]
        mu_u, mu_v = _conv(u, noyau), _conv(v, noyau)
        var_u = np.maximum(_conv(u * u, noyau) - mu_u * mu_u, 0.0)
        var_v = np.maximum(_conv(v * v, noyau) - mu_v * mu_v, 0.0)
        cov = _conv(u * v, noyau) - mu_u * mu_v
        num = (2 * mu_u * mu_v + c1) * (2 * cov + c2)
        den = (mu_u * mu_u + mu_v * mu_v + c1) * (var_u + var_v + c2)
        cartes.append(num / den)
    return float(np.mean(cartes))


def delta_e_2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 (kL = kC = kH = 1).

    Même enchaînement que la mise en œuvre de référence de Sharma, Wu et Dalal
    (Color Research and Application, vol. 30, n° 1, p. 21-30, 2005), en radians.
    Le dernier axe de chaque tableau est L*, a*, b*.
    """
    lab1 = np.asarray(lab1, dtype=np.float64)
    lab2 = np.asarray(lab2, dtype=np.float64)
    l1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    l2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    c1 = np.hypot(a1, b1)
    c2 = np.hypot(a2, b2)
    c_barre = 0.5 * (c1 + c2)
    puissance = c_barre ** 7
    g = 0.5 * (1.0 - np.sqrt(puissance / (puissance + 25.0 ** 7)))
    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = np.hypot(a1p, b1)
    c2p = np.hypot(a2p, b2)
    h1 = np.arctan2(b1, a1p)
    h2 = np.arctan2(b2, a2p)
    h1 = np.where(h1 < 0.0, h1 + 2.0 * np.pi, h1)
    h2 = np.where(h2 < 0.0, h2 + 2.0 * np.pi, h2)
    h1 = np.where((np.abs(a1p) + np.abs(b1)) == 0.0, 0.0, h1)
    h2 = np.where((np.abs(a2p) + np.abs(b2)) == 0.0, 0.0, h2)
    d_l = l2 - l1
    d_c = c2p - c1p
    d_hp = h2 - h1
    d_hp = np.where(d_hp > np.pi + _EPSILON_PI, d_hp - 2.0 * np.pi, d_hp)
    d_hp = np.where(d_hp < -(np.pi + _EPSILON_PI), d_hp + 2.0 * np.pi, d_hp)
    chroma_nulle = (c1p * c2p) == 0.0
    d_hp = np.where(chroma_nulle, 0.0, d_hp)
    d_h = 2.0 * np.sqrt(np.maximum(c1p * c2p, 0.0)) * np.sin(d_hp / 2.0)
    l_barre = 0.5 * (l1 + l2)
    c_p = 0.5 * (c1p + c2p)
    h_barre = 0.5 * (h1 + h2)
    h_barre = h_barre - (np.abs(h1 - h2) > np.pi + _EPSILON_PI) * np.pi
    h_barre = np.where(h_barre < 0.0, h_barre + 2.0 * np.pi, h_barre)
    h_barre = np.where(chroma_nulle, h1 + h2, h_barre)
    t = (1.0
         - 0.17 * np.cos(h_barre - np.pi / 6.0)
         + 0.24 * np.cos(2.0 * h_barre)
         + 0.32 * np.cos(3.0 * h_barre + np.pi / 30.0)
         - 0.20 * np.cos(4.0 * h_barre - 63.0 * np.pi / 180.0))
    s_l = 1.0 + 0.015 * (l_barre - 50.0) ** 2 / np.sqrt(20.0 + (l_barre - 50.0) ** 2)
    s_c = 1.0 + 0.045 * c_p
    s_h = 1.0 + 0.015 * c_p * t
    r_c = 2.0 * np.sqrt((c_p ** 7) / (c_p ** 7 + 25.0 ** 7))
    d_theta = (30.0 * np.pi / 180.0) * np.exp(-(((180.0 / np.pi) * h_barre - 275.0) / 25.0) ** 2)
    r_t = -np.sin(2.0 * d_theta) * r_c
    interieur = ((d_l / s_l) ** 2 + (d_c / s_c) ** 2 + (d_h / s_h) ** 2
                 + r_t * (d_c / s_c) * (d_h / s_h))
    return np.sqrt(np.maximum(interieur, 0.0))


def rgb_vers_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB 8 bits vers CIE L*a*b* (D65). Le blanc du tableau est le blanc de la matrice."""
    x = np.asarray(rgb, dtype=np.float64) / 255.0
    lineaire = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    xyz = lineaire @ _MATRICE_XYZ.T
    rapport = xyz / _BLANC
    delta = 6.0 / 29.0
    f = np.where(rapport > delta ** 3, np.cbrt(rapport), rapport / (3.0 * delta * delta) + 4.0 / 29.0)
    lab = np.empty_like(f)
    lab[..., 0] = 116.0 * f[..., 1] - 16.0
    lab[..., 1] = 500.0 * (f[..., 0] - f[..., 1])
    lab[..., 2] = 200.0 * (f[..., 1] - f[..., 2])
    return lab


def delta_e_moyen(origine: np.ndarray, resultat: np.ndarray) -> float:
    """Moyenne arithmétique du ΔE2000 sur tous les pixels."""
    return float(np.mean(delta_e_2000(rgb_vers_lab(origine), rgb_vers_lab(resultat))))


def ecrire_csv(chemin: Path | str, lignes: list[dict], colonnes: tuple[str, ...] | list[str] = COLONNES_RESULTAT) -> Path:
    dest = Path(chemin)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=list(colonnes), extrasaction="ignore")
        writer.writeheader()
        for ligne in lignes:
            writer.writerow({cle: _cellule(ligne.get(cle, "")) for cle in colonnes})
    return dest


def lister_medias(dossier: Path | str) -> list[Path]:
    racine = Path(dossier)
    if not racine.is_dir():
        raise ErreurBanc(f"Dossier d'extraits introuvable : {racine}")
    medias = []
    for chemin in sorted(racine.iterdir()):
        if not chemin.is_file() or chemin.name.startswith("."):
            continue
        if chemin.suffix.lower() in EXT_IMAGE or chemin.suffix.lower() in EXT_VIDEO:
            medias.append(chemin)
    return medias


def charger_media(chemin: Path, n_images: int = 9,
                  largeur: int = LARGEUR, hauteur: int = HAUTEUR) -> np.ndarray:
    """N images consécutives au milieu d'une vidéo, ou une photo répétée n fois.

    Cadre 720 × 576, recadrage centré. Sert aux extraits sans origine connue.
    """
    n_images = max(1, int(n_images))
    vf = (f"scale={largeur}:{hauteur}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={largeur}:{hauteur},format=rgb24")
    if chemin.suffix.lower() in EXT_IMAGE:
        commande = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin",
                    "-loop", "1", "-i", str(chemin), "-frames:v", str(n_images),
                    "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    else:
        duree = _duree(chemin)
        debut = 0.0
        if duree and duree > 0.5:
            debut = max(0.0, duree / 2.0 - n_images / 50.0)
        commande = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin",
                    "-ss", f"{debut:.3f}", "-i", str(chemin), "-frames:v", str(n_images),
                    "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    sortie = _lancer(commande, timeout=180)
    pixels = largeur * hauteur * 3
    if len(sortie) < pixels or len(sortie) % pixels:
        raise ErreurBanc(f"{chemin.name} : lecture impossible ({len(sortie)} octets).")
    n = len(sortie) // pixels
    return np.frombuffer(sortie, dtype=np.uint8).reshape(n, hauteur, largeur, 3).copy()


def ecrire_png(rgb: np.ndarray, chemin: Path | str) -> Path:
    """Écrit une image RGB. Le dossier doit rester hors dépôt (voir .gitignore)."""
    image = _rgb(rgb)
    dest = Path(chemin)
    dest.parent.mkdir(parents=True, exist_ok=True)
    hauteur, largeur = image.shape[:2]
    commande = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{largeur}x{hauteur}",
                "-i", "pipe:0", "-frames:v", "1", str(dest)]
    _lancer(commande, entree=np.ascontiguousarray(image).tobytes(), timeout=60)
    return dest


def texte_non_mesure() -> str:
    return "non mesuré"


# ---------------------------------------------------------------------------
# interne

# IEC 61966-2-1, matrice sRGB → XYZ. Le blanc est la somme des colonnes,
# donc le blanc sRGB tombe sur L* = 100, a* = b* = 0.
_MATRICE_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
], dtype=np.float64)
_BLANC = _MATRICE_XYZ.sum(axis=1)


def _noyau_gaussien(taille: int = _FENETRE_SSIM, sigma: float = 1.5) -> np.ndarray:
    axe = np.arange(taille, dtype=np.float64) - (taille // 2)
    k = np.exp(-0.5 * (axe / sigma) ** 2)
    k /= k.sum()
    return k


def _conv(image: np.ndarray, noyau: np.ndarray) -> np.ndarray:
    from numpy.lib.stride_tricks import sliding_window_view
    horizontal = sliding_window_view(image, noyau.size, axis=1) @ noyau
    return np.tensordot(sliding_window_view(horizontal, noyau.size, axis=0), noyau, axes=(2, 0))


def _rgb(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 4:
        arr = arr[arr.shape[0] // 2]
    if arr.ndim != 3 or arr.shape[2] != 3 or arr.dtype != np.uint8:
        raise ErreurBanc("Image RGB uint8 attendue (H, L, 3).")
    return np.ascontiguousarray(arr)


def _sequence(images: np.ndarray) -> np.ndarray:
    arr = np.asarray(images)
    if arr.ndim == 3:
        arr = arr[np.newaxis, ...]
    if arr.ndim != 4 or arr.shape[-1] != 3 or arr.dtype != np.uint8:
        raise ErreurBanc("Séquence RGB uint8 attendue (N, H, L, 3).")
    if arr.shape[1] % 2 or arr.shape[2] % 2:
        raise ErreurBanc("Largeur et hauteur doivent être paires.")
    return np.ascontiguousarray(arr)


def _pair(valeur: float) -> int:
    return max(2, int(round(valeur)) // 2 * 2)


def _filtre_degradation(largeur: int, hauteur: int, r: ReglagesVHS) -> tuple[str | None, str | None]:
    """(chaîne -vf, filter_complex) : un seul des deux est renseigné."""
    rgb: list[str] = []
    gamma_ffmpeg = 1.0 / r.gamma
    if abs(gamma_ffmpeg - 1.0) > 1e-6 or abs(r.saturation - 1.0) > 1e-6:
        rgb.append(f"eq=gamma={gamma_ffmpeg:.6f}:saturation={r.saturation:.6f}")
    if any(abs(v - 1.0) > 1e-6 for v in (r.dominante_r, r.dominante_g, r.dominante_b)):
        rgb.append("colorchannelmixer="
                   f"rr={r.dominante_r:.6f}:gg={r.dominante_g:.6f}:bb={r.dominante_b:.6f}")
    if r.noirs > 1e-6:
        # colorlevels de FFmpeg 6.1 laisse des bandes intactes dès que le filtre
        # est découpé en tranches. lutrgb fait le même relevé de noir :
        # sortie = entrée × (1 − noirs) + 255 × noirs.
        n = f"{r.noirs:.6f}"
        formule = f"val*(1-{n})+255*{n}"
        rgb.append(f"lutrgb=r='{formule}':g='{formule}':b='{formule}'")
    lw, lh = _pair(largeur * r.definition), _pair(hauteur * r.definition)
    cw = _pair(largeur / int(r.etalement))
    reduit = lw != largeur or lh != hauteur or cw != largeur
    bruit = int(r.bruit_luma) > 0 or int(r.bruit_chroma) > 0
    if not reduit and not bruit:
        return (",".join(rgb) if rgb else "format=rgb24"), None
    graine = int(r.graine)
    bruit_f = ""
    if bruit:
        bruit_f = (f"noise=c0s={int(r.bruit_luma)}:c0f=t+u:c0_seed={graine}"
                   f":c1s={int(r.bruit_chroma)}:c1f=t+u:c1_seed={graine + 1}"
                   f":c2s={int(r.bruit_chroma)}:c2f=t+u:c2_seed={graine + 2}")
    if not reduit:
        chaine = [*rgb, "format=yuv444p"]
        if bruit_f:
            chaine.append(bruit_f)
        return ",".join(chaine), None
    debut = "[0:v]" + ((",".join(rgb) + ",") if rgb else "")
    if lw == largeur and lh == hauteur:
        luma = "[ys]extractplanes=y[y]"
    else:
        luma = (f"[ys]extractplanes=y,scale={lw}:{lh}:flags=bilinear,"
                f"scale={largeur}:{hauteur}:flags=bilinear[y]")
    if cw == largeur:
        cu, cv = "[u]copy[uu]", "[v]copy[vv]"
    else:
        cu = (f"[u]scale={cw}:{hauteur}:flags=bilinear,"
              f"scale={largeur}:{hauteur}:flags=bilinear[uu]")
        cv = (f"[v]scale={cw}:{hauteur}:flags=bilinear,"
              f"scale={largeur}:{hauteur}:flags=bilinear[vv]")
    graphe = (f"{debut}format=yuv444p,split[ys][cs];{luma};"
              f"[cs]extractplanes=u+v[u][v];{cu};{cv};"
              "[y][uu][vv]mergeplanes=map0s=0:map0p=0:map1s=1:map1p=0:map2s=2:map2p=0"
              ":format=yuv444p[m]")
    graphe += f";[m]{bruit_f}[out]" if bruit_f else ";[m]copy[out]"
    return None, graphe


def _ffmpeg_raw(images: np.ndarray, vf: str | None = None, graphe: str | None = None,
                threads: int | None = None, timeout: int = 180) -> ResultatFiltre:
    n, hauteur, largeur = images.shape[:3]
    commande = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin",
                "-threads", str(threads if threads is not None else coeurs()),
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{largeur}x{hauteur}",
                "-r", "25", "-i", "pipe:0"]
    if graphe:
        commande += ["-filter_complex", graphe, "-map", "[out]"]
    else:
        commande += ["-vf", vf or "format=rgb24"]
    commande += ["-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    debut = time.perf_counter()
    sortie = _lancer(commande, entree=images.tobytes(), timeout=timeout)
    secondes = time.perf_counter() - debut
    attendu = n * hauteur * largeur * 3
    if len(sortie) != attendu:
        raise ErreurBanc(f"FFmpeg a rendu {len(sortie)} octets, attendu {attendu}.")
    pile = np.frombuffer(sortie, dtype=np.uint8).reshape(n, hauteur, largeur, 3).copy()
    return ResultatFiltre(pile, secondes)


def _lancer(commande: list[str], entree: bytes | None = None, timeout: int = 180) -> bytes:
    try:
        proc = subprocess.run(commande, input=entree, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ErreurBanc(f"FFmpeg a dépassé {timeout} s.") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace")[-1500:]
        raise ErreurBanc(f"FFmpeg a échoué ({proc.returncode}) : {detail}")
    return proc.stdout


def _duree(chemin: Path) -> float | None:
    commande = [ffprobe(), "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", str(chemin)]
    try:
        proc = subprocess.run(commande, capture_output=True, timeout=30, check=False)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    texte = proc.stdout.decode("utf-8", "replace").strip()
    try:
        return float(texte)
    except ValueError:
        return None


def _http_get(url: str, timeout: int = 180) -> bytes:
    erreur: Exception | None = None
    for essai in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as reponse:
                return reponse.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            erreur = exc
            time.sleep(1.5 * (essai + 1))
    raise ErreurBanc(f"Téléchargement impossible ({url}) : {erreur}")


def _sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as fichier:
        for bloc in iter(lambda: fichier.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _cellule(valeur) -> str:
    if valeur is None or valeur == "":
        return ""
    if isinstance(valeur, str):
        return valeur
    if isinstance(valeur, (float, np.floating)):
        nombre = float(valeur)
        if math.isinf(nombre):
            return "inf"
        if math.isnan(nombre):
            return "non mesuré"
        return f"{nombre:.6f}"
    return str(valeur)
