#!/usr/bin/env python3
"""Essai n°18, agent F2 : juges de qualité d'image sans référence, en ONNX sur processeur.

Juges : CLIP-IQA+, LIQE, MUSIQ (exports ONNX du dépôt Hugging Face 86Cao/IQA-ONNX-Models,
révision figée ci-dessous). Dépendances : onnxruntime, numpy (et FFmpeg pour lire les images).
Rien de ce fichier n'entre dans le logiciel ni dans le paquet.

Utilisation :
    python essais/n18/juges_iqa.py --telecharger            # poids -> ~/vhs-n18-juge/poids (SHA-256 vérifié)
    python essais/n18/juges_iqa.py --chrono                 # temps par image 720x576 -> resultats-juge-chrono.csv
    python essais/n18/juges_iqa.py --noter image.png ...    # notes de chaque juge
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

HF_DEPOT = "86Cao/IQA-ONNX-Models"
HF_REVISION = "2e32ab1ad40c592da9d199f4c7fb8a2383bbae94"   # révision figée (26/11/2026)
HF_URL = f"https://huggingface.co/{HF_DEPOT}/resolve/{HF_REVISION}/"

# Empreintes SHA-256 = empreintes LFS publiées par Hugging Face pour cette révision,
# revérifiées après téléchargement sur la box (sha256sum).
FICHIERS = {
    "clipiqa_model.onnx": (409923, "4f959db3c321a652ef45915aeade0eb05284a8145cc933dd9feaae4e633cac37"),
    "clipiqa_model.onnx.data": (152764416, "8c6b5a074405e85cda90155975588a3c4bc500d858ad994423380115610c19b6"),
    "musiq_model.onnx": (1180763, "a25cf5f0f1082b8f6e0f6d6bd74c3a36ce93dff10e27e3ff820cf25e620d5120"),
    "musiq_model.onnx.data": (108527616, "32a559c58e54601ea1b7f9b2f18952491bce04d8abe2341eb0da8d7fec1368ea"),
    "liqe_model.onnx": (1483016, "fab87cfdec7488fcc81312dd5de5209efbed04f3bddf78a425c15909d30c77ed"),
    "liqe_model.onnx.data": (352452608, "9f368e0c2d32cb06724dd0250b9686eccb11fe9576c74d5a502f21090969efa4"),
}
JUGE_FICHIERS = {
    "clipiqa+": ["clipiqa_model.onnx", "clipiqa_model.onnx.data"],
    "musiq": ["musiq_model.onnx", "musiq_model.onnx.data"],
    "liqe": ["liqe_model.onnx", "liqe_model.onnx.data"],
}
# Remarque : clip_model.onnx + text_features.json du même dépôt ne servent PAS : liqe_model.onnx
# contient déjà l'encodeur d'image CLIP et les textes (entrée « image_patches » 15x3x224x224).

CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32)
LIQE_LOGIT_SCALE = 4.6051702  # clip_model.logit_scale lu dans liqe_koniq.pt ; le graphe ONNX fait exp() lui-même

DOSSIER_DEFAUT = Path(os.environ.get("VHS_N18_JUGE", Path.home() / "vhs-n18-juge"))


# --------------------------------------------------------------------------- téléchargement
def sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def telecharger(poids: Path, juges=("clipiqa+", "musiq", "liqe")) -> None:
    poids.mkdir(parents=True, exist_ok=True)
    for j in juges:
        for nom in JUGE_FICHIERS[j]:
            taille, attendu = FICHIERS[nom]
            dest = poids / nom
            if dest.exists() and dest.stat().st_size == taille and sha256(dest) == attendu:
                print(f"ok   {nom}")
                continue
            print(f"...  {nom} ({taille / 1e6:.1f} Mo)")
            tmp = dest.with_suffix(dest.suffix + ".part")
            urllib.request.urlretrieve(HF_URL + nom, tmp)
            obtenu = sha256(tmp)
            if obtenu != attendu:
                tmp.unlink()
                raise SystemExit(f"SHA-256 différent pour {nom} : {obtenu} au lieu de {attendu}")
            tmp.replace(dest)
            print(f"ok   {nom} (SHA-256 vérifié)")


def taille_juge(poids: Path, juge: str) -> int:
    return sum(FICHIERS[n][0] for n in JUGE_FICHIERS[juge])


# --------------------------------------------------------------------------- images
def lire_image(chemin, largeur=None, hauteur=None) -> np.ndarray:
    """Lit une image en RGB uint8 avec FFmpeg (option : redimensionne/recadre en largeur x hauteur)."""
    vf = []
    if largeur and hauteur:
        vf = ["-vf", f"scale={largeur}:{hauteur}:force_original_aspect_ratio=increase:flags=lanczos,"
                     f"crop={largeur}:{hauteur}"]
    sonde = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(chemin)],
                           capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h = (largeur, hauteur) if largeur else (int(sonde[0]), int(sonde[1]))
    brut = subprocess.run(["ffmpeg", "-v", "error", "-i", str(chemin), *vf, "-frames:v", "1",
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, check=True).stdout
    return np.frombuffer(brut, np.uint8).reshape(h, w, 3)


def _poids_redim(n_in: int, n_out: int) -> np.ndarray:
    """Matrice de redimensionnement linéaire avec anticrénelage (filtre triangle élargi)."""
    echelle = n_in / n_out
    support = max(1.0, echelle)
    centres = (np.arange(n_out) + 0.5) * echelle - 0.5
    x = np.arange(n_in)[None, :]
    w = np.clip(1.0 - np.abs(x - centres[:, None]) / support, 0, None)
    return (w / w.sum(1, keepdims=True)).astype(np.float32)


def redim(img: np.ndarray, h: int, w: int) -> np.ndarray:
    f = img.astype(np.float32)
    a, b = _poids_redim(img.shape[0], h), _poids_redim(img.shape[1], w)
    return np.einsum("hy,yxc,wx->hwc", a, f, b, optimize=True)


def tuiles_224(img: np.ndarray, nx=3, ny=2) -> list[np.ndarray]:
    """Tuiles 224x224 à la définition d'origine, réparties régulièrement (nx x ny)."""
    H, W = img.shape[:2]
    ys = np.linspace(0, H - 224, ny).astype(int)
    xs = np.linspace(0, W - 224, nx).astype(int)
    return [img[y:y + 224, x:x + 224] for y in ys for x in xs]


def _nchw(lot: list[np.ndarray], mean, std) -> np.ndarray:
    x = np.stack([t.astype(np.float32) / 255.0 for t in lot])
    x = (x - mean) / std
    return np.ascontiguousarray(x.transpose(0, 3, 1, 2), dtype=np.float32)


# --------------------------------------------------------------------------- juges
class Juges:
    """Charge les juges ONNX (onnxruntime, processeur seulement)."""

    def __init__(self, poids: Path = DOSSIER_DEFAUT / "poids", juges=("clipiqa+", "liqe", "musiq"),
                 fils: int | None = None):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        if fils:
            opts.intra_op_num_threads = fils
        self.sessions = {}
        noms = {"clipiqa+": "clipiqa_model.onnx", "musiq": "musiq_model.onnx", "liqe": "liqe_model.onnx"}
        for j in juges:
            self.sessions[j] = ort.InferenceSession(str(poids / noms[j]), opts,
                                                    providers=["CPUExecutionProvider"])

    # CLIP-IQA+ : entrée 224x224 fixe (export ONNX), normalisation CLIP, note 0..1.
    def clipiqa(self, img, mode="tuiles"):
        lot = tuiles_224(img) if mode == "tuiles" else [redim(img, 224, 224)]
        s = self.sessions["clipiqa+"].run(None, {"input": _nchw(lot, CLIP_MEAN, CLIP_STD)})[0]
        return float(np.mean(s))

    # MUSIQ (KonIQ) : export ONNX une seule échelle 224x224, entrée dans [-1, 1], note 0..100.
    def musiq(self, img, mode="tuiles"):
        lot = tuiles_224(img) if mode == "tuiles" else [redim(img, 224, 224)]
        sess = self.sessions["musiq"]
        notes = [sess.run(None, {"input": _nchw([t], 0.5, 0.5)})[0].item() for t in lot]
        return float(np.mean(notes))

    # LIQE (KonIQ) : même découpage que pyiqa (liqe_arch.py) : tuiles 224 au pas de 32,
    # 15 tuiles choisies à intervalle régulier, à la définition d'origine. Note 1..5.
    def liqe(self, img, mode="natif"):
        H, W = img.shape[:2]
        if min(H, W) < 224:
            raise ValueError("LIQE : petit côté < 224")
        pas = 32
        tuiles = [img[y:y + 224, x:x + 224] for y in range(0, H - 224 + 1, pas)
                  for x in range(0, W - 224 + 1, pas)]
        n = min(15, len(tuiles))
        saut = max(1, len(tuiles) // n)
        choix = [tuiles[saut * i] for i in range(n)]
        # Le graphe ONNX normalise lui-même (Sub default_mean, Div default_std) : entrée dans [0, 1].
        x = _nchw(choix, 0.0, 1.0)[None]
        s = self.sessions["liqe"].run(None, {"image_patches": x,
                                             "logit_scale": np.array(LIQE_LOGIT_SCALE, np.float32)})[0]
        return float(s.ravel()[0])

    def noter(self, img, juge, mode=None):
        f = {"clipiqa+": self.clipiqa, "musiq": self.musiq, "liqe": self.liqe}[juge]
        return f(img, mode) if mode else f(img)


MODES = {"clipiqa+": ["tuiles", "redim"], "musiq": ["tuiles", "redim"], "liqe": ["natif"]}


def info_machine() -> dict:
    import onnxruntime as ort
    cpu = platform.processor()
    try:
        for l in open("/proc/cpuinfo"):
            if l.startswith("model name"):
                cpu = l.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {"processeur": cpu, "coeurs": os.cpu_count(), "onnxruntime": ort.__version__,
            "numpy": np.__version__, "systeme": platform.platform(),
            # machine partagée : la charge au moment de la mesure est notée (1, 5, 15 min)
            "charge_moyenne": " ".join(f"{x:.1f}" for x in os.getloadavg())}


def chrono(poids: Path, sortie: Path, fils_liste=(None, 1), repetitions=10) -> list[dict]:
    """Temps par image 720x576 (prétraitement compris), médiane sur `repetitions` après 2 tours à vide."""
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, (576, 720, 3), dtype=np.uint8)
    lignes, m = [], info_machine()
    for fils in fils_liste:
        juges = Juges(poids, fils=fils)
        for j, modes in MODES.items():
            for mode in modes:
                for _ in range(2):
                    juges.noter(img, j, mode)
                t = []
                for _ in range(repetitions):
                    t0 = time.perf_counter()
                    juges.noter(img, j, mode)
                    t.append(time.perf_counter() - t0)
                lignes.append({"juge": j, "mode": mode, "fils": fils or f"defaut({os.cpu_count()})",
                               "ms_mediane": round(1000 * statistics.median(t), 1),
                               "ms_min": round(1000 * min(t), 1), "ms_max": round(1000 * max(t), 1),
                               "repetitions": repetitions, "taille_mo": round(taille_juge(poids, j) / 1e6, 1),
                               **m})
                print(lignes[-1]["juge"], mode, lignes[-1]["fils"], lignes[-1]["ms_mediane"], "ms")
    sortie.parent.mkdir(parents=True, exist_ok=True)
    with open(sortie, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0]))
        w.writeheader()
        w.writerows(lignes)
    return lignes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dossier", type=Path, default=DOSSIER_DEFAUT, help="dossier de travail HORS dépôt")
    ap.add_argument("--telecharger", action="store_true")
    ap.add_argument("--chrono", action="store_true")
    ap.add_argument("--repetitions", type=int, default=10)
    ap.add_argument("--noter", nargs="*", type=Path)
    a = ap.parse_args(argv)
    poids = a.dossier / "poids"
    if a.telecharger or a.chrono or a.noter:
        telecharger(poids)
    if a.chrono:
        dest = Path(__file__).resolve().parent / "resultats-juge-chrono.csv"
        chrono(poids, dest, repetitions=a.repetitions)
        print("->", dest)
    if a.noter:
        juges = Juges(poids)
        for p in a.noter:
            img = lire_image(p)
            notes = {f"{j}/{m}": round(juges.noter(img, j, m), 4) for j, ms in MODES.items() for m in ms}
            print(p, json.dumps(notes))


if __name__ == "__main__":
    sys.exit(main())
