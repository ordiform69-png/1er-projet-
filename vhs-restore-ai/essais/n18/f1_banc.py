"""Essai n°18, agent F1 : adaptateur vers le banc d'essai commun de F4 (branche grok/ia-essai).

ÉTAT AU MOMENT DE L'ÉCRITURE (26/11/2026) : le banc de F4 n'était pas encore poussé
(grok/ia-essai = 38554ea, rien dans essais/n18/). Ce module isole donc tout ce qui touche au banc,
pour que l'essai F1 s'y branche en remplaçant TROIS fonctions, sans toucher au reste :

    scenes_banc(...)   -> liste de Scene (images d'origine connues + images dégradées)
    psnr(a, b)         -> dB, images uint8 RGB
    delta_e2000(a, b)  -> ΔE2000 moyen, images uint8 RGB (sRGB, D65)

Branchement automatique : si un module du banc F4 est présent à côté (banc.py, banc_n18.py ou
banc_commun.py) et fournit scenes(), psnr() et delta_e2000(), il est utilisé tel quel. Sinon on
utilise le BANC PROVISOIRE F1 ci-dessous : contenu de SYNTHÈSE généré par FFmpeg (mire de
couleurs, dégradés, fractale, mire animée), dégradé « façon VHS » par FFmpeg selon la liste de la
demande n°18. Ce contenu n'est pas une vraie image : il sert à faire tourner la chaîne et à
contrôler les calculs, pas à conclure.
"""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

LARGEUR, HAUTEUR = 720, 576


@dataclass
class Scene:
    nom: str
    degradees: list            # uint8 H x W x 3, RGB
    originales: list | None    # même taille ; None pour un extrait réel (origine inconnue)
    remarque: str = ""
    infos: dict = field(default_factory=dict)


def ffmpeg() -> str:
    return os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"


def coeurs() -> int:
    return os.cpu_count() or 0


# ------------------------------------------------------------------ FFmpeg <-> numpy
def lire(entree: list[str], n: int, w: int = LARGEUR, h: int = HAUTEUR, vf: str = "") -> list:
    """Décode n images en RGB 8 bits w x h (entree = arguments FFmpeg d'entrée)."""
    filtre = (vf + "," if vf else "") + f"scale={w}:{h}:flags=bicubic,format=rgb24"
    r = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", *entree,
                        "-vf", filtre, "-frames:v", str(n), "-an", "-f", "rawvideo", "-"],
                       capture_output=True, check=True)
    t = w * h * 3
    return [np.frombuffer(r.stdout[i:i + t], np.uint8).reshape(h, w, 3).copy()
            for i in range(0, len(r.stdout) - t + 1, t)]


def filtrer(images: list, vf: str) -> tuple[list, float]:
    """Passe les images dans une chaîne de filtres FFmpeg (RGB 8 bits en entrée et en sortie).
    Renvoie (images, secondes) ; le temps inclut le lancement de FFmpeg (≈ 0,05 s)."""
    if not images:
        return [], 0.0
    h, w, _ = images[0].shape
    vf = (vf + ",format=rgb24") if vf else "format=rgb24"
    t0 = time.perf_counter()
    r = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", "25", "-i", "-",
                        "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       input=b"".join(i.tobytes() for i in images), capture_output=True)
    dt = time.perf_counter() - t0
    if r.returncode:
        raise RuntimeError(f"FFmpeg a refusé « {vf} » : {r.stderr.decode(errors='replace')[-400:]}")
    t = w * h * 3
    return [np.frombuffer(r.stdout[i:i + t], np.uint8).reshape(h, w, 3).copy()
            for i in range(0, len(r.stdout) - t + 1, t)], dt


def png(image: np.ndarray, chemin: Path) -> None:
    h, w, _ = image.shape
    chemin.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
                    "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-",
                    "-frames:v", "1", str(chemin)], input=image.tobytes(), check=True)


# ------------------------------------------------------------------ mesures (numpy seul)
def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return float("inf") if mse == 0 else 10.0 * np.log10(255.0 ** 2 / mse)


def _lab(img: np.ndarray) -> np.ndarray:
    c = img.astype(np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    d = 6 / 29
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def delta_e2000_lab(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 (Sharma, Wu, Dalal 2005), élément par élément."""
    L1, a1, b1 = np.moveaxis(lab1, -1, 0)
    L2, a2, b2 = np.moveaxis(lab2, -1, 0)
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb7 = ((C1 + C2) / 2) ** 7
    G = 0.5 * (1 - np.sqrt(Cb7 / (Cb7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    nul = (C1p * C2p) == 0
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(nul, 0.0, dh)
    dL, dC = L2 - L1, C2p - C1p
    dH = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh) / 2)
    Lb, Cb = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hb = np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2))
    hb = np.where(nul, hs, hb)
    T = (1 - 0.17 * np.cos(np.radians(hb - 30)) + 0.24 * np.cos(np.radians(2 * hb))
         + 0.32 * np.cos(np.radians(3 * hb + 6)) - 0.20 * np.cos(np.radians(4 * hb - 63)))
    dth = 30 * np.exp(-(((hb - 275) / 25) ** 2))
    Cb7p = Cb ** 7
    RC = 2 * np.sqrt(Cb7p / (Cb7p + 25.0 ** 7))
    SL = 1 + 0.015 * (Lb - 50) ** 2 / np.sqrt(20 + (Lb - 50) ** 2)
    SC, SH = 1 + 0.045 * Cb, 1 + 0.015 * Cb * T
    RT = -np.sin(np.radians(2 * dth)) * RC
    return np.sqrt((dL / SL) ** 2 + (dC / SC) ** 2 + (dH / SH) ** 2 + RT * (dC / SC) * (dH / SH))


def delta_e2000(a: np.ndarray, b: np.ndarray) -> float:
    return float(delta_e2000_lab(_lab(a), _lab(b)).mean())


# ------------------------------------------------------------------ banc provisoire F1
# Dégradation « façon VHS » (liste de la demande n°18, section F4), réglable. Valeurs par défaut :
# choix F1 provisoires, inspirés du cas réel cité dans pipeline.py (VHS de 1988 très verte,
# niveaux 84-163) ; à remplacer par celles du banc F4.
DEGRADATION = {
    "definition": 0.5,        # définition réduite (x0,5 puis retour à 720 x 576)
    "chroma_flou": 3.0,       # couleur étalée horizontalement (gblur sur la chrominance)
    "bruit": 6,               # bruit (filtre noise, intensité)
    "gamma": 1.25,            # image assombrie : val ** 1,25
    "dominante": (0.92, 1.08, 0.90),   # gains R, G, B : dominante verte
    "saturation": 0.75,       # couleurs ternes
    "noirs": 0.12,            # noirs relevés (sortie min), blancs abaissés (sortie max)
    "blancs": 0.85,
}


def chaine_degradation(d: dict = DEGRADATION) -> str:
    r, g, b = d["dominante"]
    w2, h2 = int(LARGEUR * d["definition"]) // 2 * 2, int(HAUTEUR * d["definition"]) // 2 * 2
    e = f"'255*pow(val/255,{d['gamma']})'"
    return ",".join([
        f"scale={w2}:{h2}:flags=area,scale={LARGEUR}:{HAUTEUR}:flags=bicubic",
        f"format=yuv420p,gblur=sigma={d['chroma_flou']}:sigmaV=0.01:planes=6",
        f"noise=alls={d['bruit']}:allf=t:all_seed=18",
        f"eq=saturation={d['saturation']}",
        "format=rgb24",
        f"lutrgb=r={e}:g={e}:b={e}",
        f"colorchannelmixer=rr={r}:gg={g}:bb={b}",
        f"colorlevels=romin={d['noirs']}:gomin={d['noirs']}:bomin={d['noirs']}:"
        f"romax={d['blancs']}:gomax={d['blancs']}:bomax={d['blancs']}",
    ])


SYNTHESE = {
    "mire_couleurs": "colorchart=preset=reference:patch_size=104x104:rate=25",
    "degrades_ciel_peau": "gradients=s=720x576:c0=0x5d8fd6:c1=0xe0b49a:c2=0x6a8c4b:c3=0xf2e6d0:"
                          "nb_colors=4:speed=0.02:rate=25:seed=18",
    "interieur_sombre": "gradients=s=720x576:c0=0x1a120c:c1=0x5a3c28:c2=0x2c2a30:c3=0x9a7a5a:"
                        "nb_colors=4:speed=0.03:rate=25:seed=7",
    "fractale": "mandelbrot=s=720x576:rate=25",
    "mire_animee": "testsrc2=s=720x576:rate=25",
}


def _banc_f4():
    for nom in ("banc", "banc_n18", "banc_commun"):
        try:
            m = importlib.import_module(nom)
        except ImportError:
            continue
        if all(hasattr(m, f) for f in ("scenes", "psnr", "delta_e2000")):
            return m
    return None


def scenes_banc(n_images: int = 12) -> tuple[str, list[Scene]]:
    """(nom du banc, scènes). Banc F4 si présent, sinon banc provisoire de synthèse F1."""
    global psnr, delta_e2000
    f4 = _banc_f4()
    if f4 is not None:
        psnr, delta_e2000 = f4.psnr, f4.delta_e2000
        sc = []
        for s in f4.scenes():
            sc.append(Scene(getattr(s, "nom", str(len(sc))), list(s.degradees),
                            list(s.originales) if getattr(s, "originales", None) is not None else None,
                            "banc F4"))
        return "F4 (" + f4.__name__ + ")", sc
    vf = chaine_degradation()
    sc = []
    for nom, src in SYNTHESE.items():
        orig = lire(["-f", "lavfi", "-i", src], n_images)
        deg, _ = filtrer(orig, vf)
        sc.append(Scene(nom, deg, orig, "synthèse FFmpeg (banc provisoire F1)", {"degradation": vf}))
    return "provisoire F1 (synthèse FFmpeg)", sc
