"""Essai n°18, agent F1 : IAT (Illumination Adaptive Transformer) en ONNX, sur processeur.

Ce module ne dépend que de numpy et onnxruntime (CPUExecutionProvider). Il ne fait pas partie du
logiciel livré (dossier essais/, hors du paquet Windows).

Ce que fait IAT (code des auteurs, commit c764722, IAT_enhance/model/) :
  - partie locale  : img_high = img * mul + add          (IAT_main.py, l. 113-114)
  - partie globale : gamma (1 valeur) et matrice couleur 3 x 3, calculées sur l'image d'ENTRÉE
                     (IAT_main.py, l. 120 ; global_net.py, l. 113-121 : gamma = x[:, 0] -> Linear
                     -> + gamma_base, matrice = x[:, 1:] (9 requêtes) -> Linear -> view(-1, 3, 3)
                     + color_base, une matrice identité apprise)
  - sortie         : clamp(img_high · Mᵀ, 1e-8, 1) ** gamma   (IAT_main.py, l. 104-109 et 123)
                     tensordot(image, ccm, dims=[[-1], [-1]]) : sortie_i = Σ_j M[i, j] · entrée_j

« IAT global seul » (essai F1) = la même matrice et le même gamma appliqués à l'image d'entrée,
sans la partie locale. Ils ont été appris CONJOINTEMENT avec la partie locale : rien ne garantit
qu'ils suffisent seuls ; c'est précisément ce que l'essai mesure.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
MANIFESTE = ICI / "iat_modeles.json"
LOGICIEL = ICI.parent.parent          # vhs-restore-ai/
POIDS_RETENUS = ("lol_v1", "lol_v2")


def dossier_cache() -> Path:
    """Poids et ONNX : hors du dépôt (VHS_N18_CACHE, sinon ~/.cache/vhs-restore-n18/iat)."""
    d = Path(os.environ.get("VHS_N18_CACHE") or Path.home() / ".cache" / "vhs-restore-n18") / "iat"
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifeste() -> dict:
    return json.loads(MANIFESTE.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def telecharger(url: str, dest: Path, empreinte: str) -> Path:
    """Télécharge si absent, vérifie TOUJOURS le SHA-256 (fichier refusé et effacé sinon)."""
    if not dest.is_file():
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            while bloc := r.read(1 << 20):
                f.write(bloc)
        tmp.replace(dest)
    vu = sha256(dest)
    if vu != empreinte:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 incorrect pour {dest.name} : {vu} au lieu de {empreinte}")
    return dest


def chemin_onnx(poids: str, partie: str) -> Path:
    """ONNX produit une fois par iat_export_onnx.py. Vérifié contre le manifeste d'export
    (export_iat.json, écrit au même moment) ; refusé si les octets ne concordent pas."""
    d = dossier_cache()
    p = d / f"iat_{poids}_{partie}.onnx"
    exp = d / "export_iat.json"
    if not p.is_file() or not exp.is_file():
        raise FileNotFoundError(
            f"{p.name} absent. Faites l'export une fois (PyTorch, hors du logiciel) :\n"
            f"  python essais/n18/iat_export_onnx.py\n(dans un environnement à part avec torch et timm)")
    attendu = json.loads(exp.read_text(encoding="utf-8"))["onnx"][p.name]["sha256"]
    if sha256(p) != attendu:
        raise RuntimeError(f"{p.name} ne correspond pas à son manifeste d'export : refaites l'export")
    return p


def _session(path: Path, threads: int = 0):
    import onnxruntime as ort
    so = ort.SessionOptions()
    if threads:
        so.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


def _entree(img: np.ndarray) -> np.ndarray:
    """uint8 H x W x 3 (RGB) -> float32 1 x 3 x H x W dans [0, 1], sans normalisation
    (img_demo.py des auteurs : --normalize False par défaut)."""
    return np.ascontiguousarray(img.astype(np.float32).transpose(2, 0, 1)[None] / 255.0)


class IATGlobal:
    """Partie globale seule : (matrice 3 x 3, gamma) pour une image."""

    def __init__(self, poids: str, threads: int = 0):
        self.poids = poids
        self.s = _session(chemin_onnx(poids, "global"), threads)

    def estimer(self, img: np.ndarray) -> tuple[np.ndarray, float]:
        gamma, color = self.s.run(None, {"image": _entree(img)})
        return color[0].astype(np.float64), float(gamma.reshape(-1)[0])


class IATComplet:
    """Modèle complet (local + global), image par image : la référence de l'essai."""

    def __init__(self, poids: str, threads: int = 0):
        self.poids = poids
        self.s = _session(chemin_onnx(poids, "complet"), threads)

    def sorties(self, img: np.ndarray):
        mul, add, gamma, color = self.s.run(None, {"image": _entree(img)})
        return mul[0], add[0], color[0].astype(np.float64), float(gamma.reshape(-1)[0])

    @staticmethod
    def recomposer(img: np.ndarray, mul, add, M: np.ndarray, g: float) -> np.ndarray:
        """Exactement IAT.forward (IAT_main.py l. 113-124), en numpy."""
        x = img.astype(np.float32).transpose(2, 0, 1) / 255.0
        haut = (x * mul + add).transpose(1, 2, 0)
        return appliquer_global_numpy_f(haut, M, g)


def appliquer_global_numpy_f(x: np.ndarray, M: np.ndarray, g: float) -> np.ndarray:
    """x float H x W x 3 dans [0, 1] -> uint8. clamp(x · Mᵀ, 1e-8, 1) ** gamma."""
    y = np.clip(x @ M.T.astype(np.float32), 1e-8, 1.0) ** np.float32(g)
    return np.clip(np.rint(y * 255.0), 0, 255).astype(np.uint8)


def appliquer_global_numpy(img: np.ndarray, M: np.ndarray, g: float) -> np.ndarray:
    return appliquer_global_numpy_f(img.astype(np.float32) / 255.0, M, g)


def combiner(estimations: list[tuple[np.ndarray, float]]) -> tuple[np.ndarray, float, float, float]:
    """Une matrice et un gamma pour la scène : médiane élément par élément des 3 à 5 images
    (robuste à une image atypique). Renvoie aussi la dispersion (écart-type max de la matrice,
    écart-type du gamma) pour voir si l'IA est stable d'une image à l'autre."""
    Ms = np.stack([m for m, _ in estimations])
    gs = np.array([g for _, g in estimations])
    return np.median(Ms, axis=0), float(np.median(gs)), float(Ms.std(axis=0).max()), float(gs.std())


# ------------------------------------------------------------------ filtres FFmpeg
def filtres_ffmpeg(M: np.ndarray, g: float) -> str:
    """Matrice + gamma -> filtres FFmpeg pour toute la scène.

    - colorchannelmixer : sortie_R = rr·R + rg·G + rb·B (etc.), exactement M (lignes = sorties).
      Il écrête à [0, 1] comme le clamp d'IAT (le plancher 1e-8 d'IAT est sans effet en 16 bits).
    - gamma : lutrgb, puissance EXACTE val ** gamma sur chaque canal R, G, B, comme IAT.
      Pas eq=gamma (agit sur la luminance en YUV et change la saturation, pas le même calcul) ;
      pas curves (courbe interpolée entre des points, approximation inutile ici).
    - calcul en RGB 16 bits (rgb48le) entre les deux filtres pour ne pas arrondir deux fois en 8 bits.
    """
    (rr, rg, rb), (gr, gg, gb), (br, bg, bb) = M
    mix = (f"colorchannelmixer=rr={rr:.5f}:rg={rg:.5f}:rb={rb:.5f}:"
           f"gr={gr:.5f}:gg={gg:.5f}:gb={gb:.5f}:br={br:.5f}:bg={bg:.5f}:bb={bb:.5f}")
    e = f"'65535*pow(val/65535,{g:.5f})+0.5'"
    return f"format=rgb48le,{mix},lutrgb=r={e}:g={e}:b={e},format=rgb24"


# ------------------------------------------------------------------ plafonds du logiciel
def _logiciel():
    if str(LOGICIEL) not in sys.path:
        sys.path.insert(0, str(LOGICIEL))
    from vhs_restore import pipeline        # lecture seule : aucune modification du logiciel
    return pipeline


def plafonner(M: np.ndarray, g: float) -> tuple[np.ndarray, float]:
    """Transpose les plafonds du logiciel (vhs_restore/pipeline.py, safe_levels / safe_gains,
    MAX_CONTRAST = 1,6 ; GAIN_MIN, GAIN_MAX = 0,85, 1,18) à une matrice + gamma.

    Le logiciel n'a ni matrice ni gamma : transposition choisie par F1, à valider par Claude.
      1. effet sur un gris = somme de chaque ligne de M ; gain moyen k, gains relatifs k_c / k
      2. gains relatifs -> safe_gains() du logiciel (dominante : -15 % à +18 % par couleur)
      3. gain moyen -> au plus x MAX_CONTRAST (et au moins / MAX_CONTRAST), la limite que
         safe_levels() impose à l'étirement des niveaux
      4. chaque ligne est remise à l'échelle (proportions entre canaux gardées)
      5. gamma : le gain total sur le gris moyen (0,5) reste entre / et x MAX_CONTRAST
    """
    p = _logiciel()
    mc = float(p.MAX_CONTRAST)
    sommes = M.sum(axis=1)
    if np.any(np.abs(sommes) < 1e-6):
        return np.eye(3), 1.0
    k = float(sommes.mean())
    rel = np.array(p.safe_gains(tuple(float(x) for x in sommes / k)))
    k2 = min(mc, max(1.0 / mc, k))
    M2 = (k2 * rel / sommes)[:, None] * M
    gain_milieu = k2 * 0.5 ** (g - 1.0)
    gain_milieu = min(mc, max(1.0 / mc, gain_milieu))
    g2 = 1.0 + math.log(gain_milieu / k2) / math.log(0.5)
    return M2, g2


def chrono() -> float:
    return time.perf_counter()
