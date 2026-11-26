"""Essai n°18, agent F3 : modèles entraînés sur de la vraie VHS (OpenModelDB) contre l'IA actuelle.

    python essais/n18/f3_vhs.py                      # banc d'essai (images d'origine connues)
    python essais/n18/f3_vhs.py --extraits <dossier> # en plus : vrais extraits (pas d'origine connue)

Dépendances : onnxruntime, onnx, numpy et FFmpeg (ce que le logiciel a déjà). Les fichiers .onnx
sont produits À PART, une fois, par f3_convertir_onnx.py (torch + spandrel, dépendances d'essai).

Comparé, sur chaque image dégradée :
  - « degradee »        : l'image dégradée telle quelle (repère) ;
  - « sans_ia »         : chaîne du logiciel, pipeline.filter_chain, profil « Bien nettoyé, naturel » ;
  - « vhs_sharpen », « baldrick », « vhs_film_2x » : les trois candidats OpenModelDB ;
  - « realesrgan_x4plus » : l'IA actuelle (mêmes poids que realesrgan-x4plus du logiciel), seule ;
  - « rendu_maximum »   : comme le rendu « Nettoyage au plus fort » : pre_filters du profil
                          « maximum » puis Real-ESRGAN x4.
Les sorties agrandies (x2, x4) sont ramenées en 720 × 576 (moyenne par blocs) avant la mesure.

Résultats (CSV) et images avant / après : dans --sortie, HORS du dépôt
(par défaut <cache>/resultats, cache = VHSRA_N18_CACHE ou ~/.cache/vhsrestore-n18/f3).

BANC COMMUN (agent F4, branche grok/ia-essai). Ce script cherche dans essais/n18/ un module
(banc, f4_banc, banc_n18, banc_commun) qui fournit :
    references() -> list[tuple[str, numpy.ndarray]]   images d'origine RVB uint8 (H, W, 3), 720 × 576
    degrader(image) -> numpy.ndarray                   dégradation façon VHS, même taille
    mesurer(origine, image) -> dict                    clés psnr, ssim, delta_e2000 (ou deltae / de2000)
    chaine_sans_ia(image) -> numpy.ndarray             pipeline.filter_chain, « Bien nettoyé, naturel »
    zones(nom) -> list[tuple[str, int, int, int, int]] FACULTATIF : (type, x, y, l, h) visages / texte
S'il n'existe pas encore, un REPLI PROVISOIRE local (BancProvisoireF3 ci-dessous) est utilisé et
signalé dans les CSV (colonne « banc »). Ses chiffres ne remplacent pas ceux du banc commun.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import urllib.request
from fractions import Fraction
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
DEPOT = ICI.parents[1]                       # vhs-restore-ai/
sys.path.insert(0, str(ICI))
from f3_modeles import CACHE, MODELES, chemin_onnx  # noqa: E402

L, H = 720, 576
IMAGES_FILM_2H = 25 * 2 * 3600               # PAL 25 images/s x 7200 s = 180 000 images
CLES_MODELES = ["vhs_sharpen", "baldrick", "vhs_film_2x", "realesrgan_x4plus"]
INTERFACE = ("references", "degrader", "mesurer", "chaine_sans_ia")


# ------------------------------------------------------------------ FFmpeg (images en mémoire)
def ffmpeg_brut(entree: list[str], filtre: str | None = None, donnees: bytes | None = None,
                l: int = L, h: int = H) -> np.ndarray:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", *entree]
    if filtre:
        cmd += ["-vf", filtre]
    cmd += ["-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    sortie = subprocess.run(cmd, input=donnees, capture_output=True, check=True).stdout
    return np.frombuffer(sortie, np.uint8)[: l * h * 3].reshape(h, l, 3).copy()


def filtrer(img: np.ndarray, filtre: str) -> np.ndarray:
    h, l = img.shape[:2]
    return ffmpeg_brut(["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{l}x{h}", "-i", "-"],
                       filtre + ",format=rgb24", img.tobytes(), l, h)


def ecrire_png(img: np.ndarray, chemin: Path) -> None:
    h, l = img.shape[:2]
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "rawvideo",
                    "-pix_fmt", "rgb24", "-s", f"{l}x{h}", "-i", "-", str(chemin)],
                   input=img.tobytes(), check=True)


# ------------------------------------------------------------------ mesures (numpy seul)
def _lin(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def rgb_vers_lab(img: np.ndarray) -> np.ndarray:
    r, g, b = (_lin(img[..., i].astype(np.float64)) for i in range(3))
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883
    f = lambda t: np.where(t > 216 / 24389, np.cbrt(t), (24389 / 27 * t + 16) / 116)  # noqa: E731
    fx, fy, fz = f(x), f(y), f(z)
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], -1)


def delta_e2000(a: np.ndarray, b: np.ndarray) -> float:
    """ΔE2000 moyen entre deux images RVB (sRGB, D65)."""
    return float(delta_e2000_lab(rgb_vers_lab(a), rgb_vers_lab(b)).mean())


def delta_e2000_lab(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """ΔE2000 point par point (Sharma, Wu, Dalal 2005)."""
    l1, a1, b1 = np.moveaxis(np.asarray(lab1, np.float64), -1, 0)
    l2, a2, b2 = np.moveaxis(np.asarray(lab2, np.float64), -1, 0)
    c1, c2 = np.hypot(a1, b1), np.hypot(a2, b2)
    cm = (c1 + c2) / 2
    g = 0.5 * (1 - np.sqrt(cm ** 7 / (cm ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dl, dc = l2 - l1, c2p - c1p
    dh = h2p - h1p
    dh = np.where(c1p * c2p == 0, 0, np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh)))
    dhh = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2))
    lm, cmp_ = (l1 + l2) / 2, (c1p + c2p) / 2
    hs = h1p + h2p
    hm = np.where(c1p * c2p == 0, hs,
                  np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    t = (1 - 0.17 * np.cos(np.radians(hm - 30)) + 0.24 * np.cos(np.radians(2 * hm))
         + 0.32 * np.cos(np.radians(3 * hm + 6)) - 0.20 * np.cos(np.radians(4 * hm - 63)))
    sl = 1 + 0.015 * (lm - 50) ** 2 / np.sqrt(20 + (lm - 50) ** 2)
    sc, sh = 1 + 0.045 * cmp_, 1 + 0.015 * cmp_ * t
    rt = (-2 * np.sqrt(cmp_ ** 7 / (cmp_ ** 7 + 25.0 ** 7))
          * np.sin(np.radians(60 * np.exp(-(((hm - 275) / 25) ** 2)))))
    return np.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dhh / sh) ** 2 + rt * (dc / sc) * (dhh / sh))


def luma(img: np.ndarray) -> np.ndarray:
    f = img.astype(np.float64)
    return 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return float("inf") if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def _flou(x: np.ndarray, sigma: float = 1.5, r: int = 5) -> np.ndarray:
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    x = np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 0, x)
    return np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 1, x)


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    """SSIM sur la luminance, fenêtre gaussienne 11 × 11, σ = 1,5 (Wang et al. 2004)."""
    x, y = luma(a), luma(b)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mx, my = _flou(x), _flou(y)
    sxx, syy, sxy = _flou(x * x) - mx * mx, _flou(y * y) - my * my, _flou(x * y) - mx * my
    return float(np.mean(((2 * mx * my + c1) * (2 * sxy + c2)) / ((mx * mx + my * my + c1) * (sxx + syy + c2))))


def laplacien(img: np.ndarray) -> np.ndarray:
    y = luma(img)
    return 4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:]


def details(origine: np.ndarray, image: np.ndarray) -> dict:
    """Détails inventés ou perdus (fins contours, luminance) :
    hf_rapport = énergie des fins détails de l'image / celle de l'origine (> 1 : plus de détails
    que l'original, donc inventés ou accentués ; < 1 : lissé) ;
    hf_ecart   = écart moyen absolu entre les fins détails de l'image et ceux de l'origine
                 (0 = mêmes détails ; plus c'est grand, plus il y a de détails faux ou absents)."""
    lo, li = laplacien(origine), laplacien(image)
    eo = float(np.mean(np.abs(lo))) or 1e-9
    return {"hf_rapport": float(np.mean(np.abs(li))) / eo, "hf_ecart": float(np.mean(np.abs(li - lo)))}


# ------------------------------------------------------------------ chaîne du logiciel (lecture seule)
def _logiciel():
    if str(DEPOT) not in sys.path:
        sys.path.insert(0, str(DEPOT))
    from vhs_restore import pipeline
    from vhs_restore.probe import MediaInfo
    from vhs_restore.profiles import PROFILES
    info = MediaInfo(path=Path("banc.png"), container="image2", width=L, height=H, fps=Fraction(25),
                     sar=Fraction(16, 15), dar=Fraction(4, 3), scan="progressive",
                     standard="625/25", color_space="bt470bg")
    return pipeline, info, PROFILES


def chaine_logiciel(profil: str, *, pre_seulement: bool = False, use_ai: bool = False) -> str:
    """Filtres FFmpeg du logiciel pour une image 720 × 576 progressive (aucun fichier modifié)."""
    pipeline, info, profils = _logiciel()
    s = pipeline.Settings(profile=profils[profil], use_ai=use_ai)
    if pre_seulement:
        return ",".join(pipeline.pre_filters(info, s)) or "null"
    return pipeline.filter_chain(info, s)


# ------------------------------------------------------------------ repli provisoire du banc
class BancProvisoireF3:
    """PROVISOIRE, en attendant le banc commun de F4 : images CC0 de f3_references_provisoires.csv,
    dégradation simple en numpy, mesures ci-dessus, chaîne du logiciel par pipeline.filter_chain."""

    nom = "provisoire F3"

    def __init__(self) -> None:
        self._lignes = list(csv.DictReader(open(ICI / "f3_references_provisoires.csv", encoding="utf-8")))

    def references(self) -> list[tuple[str, np.ndarray]]:
        dossier = CACHE / "refs"
        dossier.mkdir(parents=True, exist_ok=True)
        sortie = []
        for ligne in self._lignes:
            f = dossier / (ligne["nom"] + ".jpg")
            if not (f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest() == ligne["sha256"]):
                req = urllib.request.Request(ligne["url"], headers={"User-Agent": "VHSRestoreAI-essai/1.0"})
                f.write_bytes(urllib.request.urlopen(req, timeout=60).read())
                if hashlib.sha256(f.read_bytes()).hexdigest() != ligne["sha256"]:
                    raise RuntimeError(f"SHA-256 différente pour {ligne['url']}")
            sortie.append((ligne["nom"], ffmpeg_brut(
                ["-i", str(f)], f"scale={L}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={L}:{H}")))
        return sortie

    def zones(self, nom: str) -> list[tuple[str, int, int, int, int]]:
        for ligne in self._lignes:
            if ligne["nom"] == nom and ligne["zones"]:
                return [(t, *map(int, r)) for t, *r in (z.split(":") for z in ligne["zones"].split(";"))]
        return []

    @staticmethod
    def degrader(img: np.ndarray) -> np.ndarray:
        rng = np.random.default_rng(18)
        f = img.astype(np.float64) / 255
        y = 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]
        cb, cr = (f[..., 2] - y) * 0.564, (f[..., 0] - y) * 0.713

        def flou_h(c, n):
            k = np.ones(n) / n
            return np.apply_along_axis(lambda v: np.convolve(np.pad(v, n // 2, mode="edge"), k, "valid"), 1, c)
        y = flou_h(y, 3)                                  # définition réduite (~ 250 points / ligne)
        cb, cr = flou_h(cb, 15), flou_h(cr, 15)           # couleur étalée horizontalement
        cb, cr = np.roll(cb, 3, 1) * 0.8, np.roll(cr, 3, 1) * 0.8   # décalée, ternie
        y = y + rng.normal(0, 0.025, y.shape)             # bruit de luminance
        cb = cb + flou_h(rng.normal(0, 0.03, y.shape), 7)  # bruit de couleur en traînées
        cr = cr + flou_h(rng.normal(0, 0.03, y.shape), 7)
        y = 0.06 + 0.9 * np.clip(y, 0, 1) ** 1.15         # noirs relevés, image assombrie
        r, b = y + cr / 0.713, y + cb / 0.564
        g = (y - 0.299 * r - 0.114 * b) / 0.587
        out = np.stack([r * 1.02, g * 1.03, b * 0.95], -1)  # dominante verte / jaune
        return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)

    @staticmethod
    def mesurer(origine: np.ndarray, image: np.ndarray) -> dict:
        return {"psnr": psnr(origine, image), "ssim": ssim(origine, image), "delta_e2000": delta_e2000(origine, image)}

    @staticmethod
    def chaine_sans_ia(img: np.ndarray) -> np.ndarray:
        return filtrer(img, chaine_logiciel("equilibre"))


def charger_banc():
    """Banc commun de F4 s'il a été poussé dans essais/n18/, sinon repli provisoire."""
    for nom in ("banc", "f4_banc", "banc_n18", "banc_commun"):
        try:
            mod = importlib.import_module(nom)
        except ImportError:
            continue
        if all(callable(getattr(mod, f, None)) for f in INTERFACE):
            mod.nom = f"F4 ({nom}.py)"
            return mod
        print(f"Module {nom}.py trouvé mais incomplet (attendu : {', '.join(INTERFACE)}) : repli provisoire.")
    print("Banc commun de F4 introuvable : REPLI PROVISOIRE F3 (chiffres à refaire sur le banc commun).")
    return BancProvisoireF3()


def mesure_commune(banc, origine, image) -> dict:
    m = banc.mesurer(origine, image)
    de = next((m[k] for k in ("delta_e2000", "deltae2000", "deltae", "de2000", "delta_e") if k in m), None)
    return {"psnr": m.get("psnr"), "ssim": m.get("ssim"), "delta_e2000": de}


# ------------------------------------------------------------------ modèles ONNX
class ModeleOnnx:
    def __init__(self, m: dict, coeurs: int, tuile: int, recouvrement: int = 16) -> None:
        import onnxruntime as ort
        chemin = chemin_onnx(m)
        if not chemin.is_file():
            raise FileNotFoundError(f"{chemin} absent : lancez d'abord python essais/n18/f3_convertir_onnx.py {m['cle']}")
        attendu = Path(str(chemin) + ".sha256")
        if attendu.is_file():
            if hashlib.sha256(chemin.read_bytes()).hexdigest() != json.loads(attendu.read_text())["sha256"]:
                raise RuntimeError(f"SHA-256 de {chemin} différente de celle notée à la conversion")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = coeurs
        opts.inter_op_num_threads = 1
        self.s = ort.InferenceSession(str(chemin), sess_options=opts, providers=["CPUExecutionProvider"])
        self.m, self.echelle, self.tuile, self.rec = m, m["echelle"], tuile, recouvrement
        self.s.run(None, {"image": np.zeros((1, 3, 32, 32), np.float32)})   # chauffe

    def _passe(self, x: np.ndarray) -> np.ndarray:
        return self.s.run(None, {"image": x[None]})[0][0]

    def __call__(self, img: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(img.transpose(2, 0, 1), np.float32) / 255
        _, h, l = x.shape
        e, t, r = self.echelle, self.tuile, self.rec
        if not t or (h <= t and l <= t):
            y = self._passe(x)
        else:   # tuiles avec recouvrement (comme realesrgan-ncnn-vulkan -t), bords recollés au centre
            y = np.zeros((3, h * e, l * e), np.float32)
            for y0 in range(0, h, t):
                for x0 in range(0, l, t):
                    a0, a1 = max(0, y0 - r), min(h, y0 + t + r)
                    b0, b1 = max(0, x0 - r), min(l, x0 + t + r)
                    p = self._passe(np.ascontiguousarray(x[:, a0:a1, b0:b1]))
                    yy, xx = (y0 - a0) * e, (x0 - b0) * e
                    hh, ll = (min(h, y0 + t) - y0) * e, (min(l, x0 + t) - x0) * e
                    y[:, y0 * e:y0 * e + hh, x0 * e:x0 * e + ll] = p[:, yy:yy + hh, xx:xx + ll]
        return (np.clip(y, 0, 1).transpose(1, 2, 0) * 255 + 0.5).astype(np.uint8)


def ramener(img: np.ndarray, e: int) -> np.ndarray:
    """Sortie x e ramenée à la taille d'origine : moyenne de chaque bloc e × e."""
    if e == 1:
        return img
    h, l = img.shape[0] // e, img.shape[1] // e
    return (img[: h * e, : l * e].reshape(h, e, l, e, 3).astype(np.float64).mean((1, 3)) + 0.5).astype(np.uint8)


# ------------------------------------------------------------------ essai
def machine(coeurs: int) -> dict:
    import onnxruntime as ort
    cpu = platform.processor() or ""
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    ff = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    return {"processeur": cpu, "coeurs_logiques": os.cpu_count(), "fils_onnx": coeurs,
            "systeme": platform.platform(), "python": platform.python_version(),
            "onnxruntime": ort.__version__, "numpy": np.__version__, "ffmpeg": ff.replace("ffmpeg version ", "")[:40]}


def variantes(args, coeurs):
    """Liste (nom, fonction image -> (image 720 × 576, durée du calcul en s))."""
    out = []

    def chrono(f):
        def g(img):
            t = time.perf_counter()
            r = f(img)
            return r, time.perf_counter() - t
        return g
    out.append(("degradee", chrono(lambda i: i)))
    out.append(("sans_ia", None))          # rempli par le banc
    modeles = {}
    for cle in args.modeles:
        m = next(x for x in MODELES if x["cle"] == cle)
        try:
            modeles[cle] = ModeleOnnx(m, coeurs, args.tuile)
        except Exception as exc:
            print(f"  {cle} : non mesuré ({exc})")
            continue
        out.append((cle, chrono(lambda i, mo=modeles[cle]: mo(i))))
    if "realesrgan_x4plus" in modeles:
        try:
            pre = chaine_logiciel("maximum", pre_seulement=True, use_ai=True)
            mo = modeles["realesrgan_x4plus"]
            out.append(("rendu_maximum", lambda i: (lambda t0, a: (lambda b: (b, time.perf_counter() - t0))(mo(a)))(
                time.perf_counter(), filtrer(i, pre))))
        except Exception as exc:
            print(f"  rendu_maximum : non mesuré ({exc})")
    return out, modeles


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--extraits", type=Path, help="dossier de vrais extraits (vidéos ou images), hors dépôt")
    ap.add_argument("--sortie", type=Path, default=CACHE / "resultats", help="dossier des CSV et images (hors dépôt)")
    ap.add_argument("--modeles", nargs="+", default=CLES_MODELES, choices=CLES_MODELES)
    ap.add_argument("--coeurs", type=int, default=os.cpu_count(), help="fils de calcul ONNX Runtime")
    ap.add_argument("--tuile", type=int, default=256, help="taille des tuiles (0 = image entière)")
    ap.add_argument("--images-par-extrait", type=int, default=3)
    args = ap.parse_args()
    sortie = args.sortie.resolve()
    if DEPOT.parent in sortie.parents or sortie == DEPOT.parent:
        sys.exit("--sortie doit être HORS du dépôt (aucune image dans le dépôt).")
    (sortie / "images").mkdir(parents=True, exist_ok=True)
    mach = machine(args.coeurs)
    print("Machine :", json.dumps(mach, ensure_ascii=False))
    banc = charger_banc()
    vars_, _ = variantes(args, args.coeurs)
    temps: dict[str, list[float]] = {}
    lignes = []

    def appliquer(nom, f, img):
        if nom == "sans_ia":
            t = time.perf_counter()
            r = banc.chaine_sans_ia(img)
            return r, time.perf_counter() - t
        r, dt = f(img)
        return ramener(r, r.shape[0] // img.shape[0]), dt

    # 1. banc : images d'origine connues
    for nom_img, origine in banc.references():
        if origine.shape[:2] != (H, L):
            origine = filtrer(origine, f"scale={L}:{H}:flags=lanczos")   # temps mesurés en 720 × 576
        degradee = banc.degrader(origine)
        zones = banc.zones(nom_img) if callable(getattr(banc, "zones", None)) else []
        ecrire_png(origine, sortie / "images" / f"{nom_img}__origine.png")
        for nom, f in vars_:
            try:
                img, dt = appliquer(nom, f, degradee)
            except Exception as exc:
                print(f"  {nom_img} / {nom} : non mesuré ({exc})")
                continue
            temps.setdefault(nom, []).append(dt)
            ecrire_png(img, sortie / "images" / f"{nom_img}__{nom}.png")
            ligne = {"banc": banc.nom, "image": nom_img, "variante": nom, "zone": "image entière",
                     **mesure_commune(banc, origine, img), **details(origine, img), "temps_s": round(dt, 3)}
            lignes.append(ligne)
            for k, (typ, x, y, w, h) in enumerate(zones):
                o, i = origine[y:y + h, x:x + w], img[y:y + h, x:x + w]
                lignes.append({"banc": banc.nom, "image": nom_img, "variante": nom, "zone": f"{typ} {k + 1} ({x},{y},{w}x{h})",
                               "psnr": psnr(o, i), "ssim": ssim(o, i), "delta_e2000": delta_e2000(o, i),
                               **details(o, i), "temps_s": ""})
                ecrire_png(np.ascontiguousarray(np.concatenate([o, degradee[y:y + h, x:x + w], i], 1)),
                           sortie / "images" / f"{nom_img}__{nom}__{typ}{k + 1}__origine-degradee-sortie.png")
            print(f"  {nom_img:10s} {nom:18s} PSNR {ligne['psnr']:.2f}  SSIM {ligne['ssim']:.4f}  "
                  f"ΔE {ligne['delta_e2000']:.2f}  {dt:.2f} s")

    # 2. extraits réels : pas d'origine connue -> temps, détails et images avant / après seulement
    lignes_ext = []
    if args.extraits:
        for fichier in sorted(p for p in args.extraits.iterdir() if p.is_file()):
            for k in range(args.images_par_extrait):
                try:
                    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                                "csv=p=0", str(fichier)], capture_output=True, text=True).stdout or 0)
                    ss = ["-ss", f"{dur * (k + 1) / (args.images_par_extrait + 1):.3f}"] if dur > 1 else []
                    avant = ffmpeg_brut([*ss, "-i", str(fichier)],
                                        f"bwdif=mode=send_frame:deint=interlaced,scale={L}:{H}:flags=lanczos")
                except Exception as exc:
                    print(f"  {fichier.name} : illisible ({exc})")
                    break
                base = f"extrait_{fichier.stem}_{k + 1}"
                ecrire_png(avant, sortie / "images" / f"{base}__avant.png")
                for nom, f in vars_:
                    if nom == "degradee":
                        continue
                    try:
                        img, dt = appliquer(nom, f, avant)
                    except Exception as exc:
                        print(f"  {base} / {nom} : non mesuré ({exc})")
                        continue
                    temps.setdefault(nom, []).append(dt)
                    ecrire_png(img, sortie / "images" / f"{base}__{nom}.png")
                    lignes_ext.append({"extrait": fichier.name, "image": k + 1, "variante": nom,
                                       **{f"{a}_vs_avant": b for a, b in details(avant, img).items()},
                                       "temps_s": round(dt, 3)})

    # 3. CSV
    def ecrire(nom, rows):
        if rows:
            with open(sortie / nom, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            print(f"Écrit : {sortie / nom}")
    ecrire("f3_resultats.csv", lignes)
    ecrire("f3_extraits.csv", lignes_ext)
    rows_t = []
    for nom, ts in temps.items():
        med = statistics.median(ts)
        rows_t.append({"variante": nom, "nb_images": len(ts), "temps_median_s": round(med, 3),
                       "temps_moyen_s": round(statistics.mean(ts), 3), "taille_image": f"{L}x{H}",
                       "tuile": args.tuile, "film_2h_images": IMAGES_FILM_2H,
                       "film_2h_heures": round(med * IMAGES_FILM_2H / 3600, 1), **mach})
    ecrire("f3_temps.csv", rows_t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
