"""Calcul en 10 bits : plus de marches dans les dégradés, même rendu moyen, temps borné.

Recette de la rampe (différente de la rampe 16 bits grise de l'agent E, voir
partage-grok/mesures-n17/recette-agent-B.md) : une image 720×576, une colonne =
une valeur, Y en codes 10 bits de 180 à 700, chroma neutre 512, format yuv420p10le.
Chaîne « niveaux + gamma » : profil Fidèle sans débruitage, lumière +2 (gamma 1,2),
noirs 0,2 et blancs 0,75. La référence 8 bits est la même correction via colorlevels
puis eq, qui ne travaille qu'en 8 bits.
"""
import dataclasses
import re
import subprocess
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

from vhs_restore import pipeline
from vhs_restore.probe import MediaInfo
from vhs_restore.profiles import profile_for

W, H = 720, 576
Y0, Y1 = 180, 700          # codes 10 bits, rampe linéaire sur la largeur
CHROMA = 512


def _profil_nu():
    return dataclasses.replace(profile_for("fidele", "video"), denoise=None, sharpen=0.0, despeckle=False)


def _info(**kw):
    base = dict(path=Path("rampe.yuv"), width=W, height=H, fps=Fraction(25), duration=0.04,
                dar=Fraction(4, 3), sar=Fraction(1), scan="progressive", pix_fmt="yuv420p10le")
    base.update(kw)
    return MediaInfo(**base)


def _rampe() -> bytes:
    y = np.zeros((H, W), np.uint16)
    for x in range(W):
        y[:, x] = Y0 + int(round(x * (Y1 - Y0) / (W - 1)))
    c = np.full((H // 2, W // 2), CHROMA, np.uint16)
    return y.tobytes() + c.tobytes() + c.tobytes()


def _ligne(data: bytes) -> np.ndarray:
    return np.frombuffer(data, np.uint8).reshape(H, W)[H // 2]


def _stats(row: np.ndarray) -> dict:
    dif = np.abs(np.diff(row.astype(int)))
    nz = dif[dif > 0]
    return {"distinct": int(len(np.unique(row))), "maxstep": int(dif.max()),
            "mean_nz": float(nz.mean()), "ymin": int(row.min()), "ymax": int(row.max()),
            "mean": float(row.mean())}


def _ffmpeg_raw(src_fmt: str, raw: bytes, vf: str, pix_out: str) -> bytes:
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", src_fmt,
         "-s", f"{W}x{H}", "-i", "pipe:0", "-vf", vf, "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", pix_out, "-"],
        input=raw, capture_output=True)
    if p.returncode:
        raise AssertionError(p.stderr.decode()[-400:])
    return p.stdout


def test_rampe_plus_de_niveaux_et_plus_petits_sauts():
    nu = pipeline.Settings(_profil_nu(), scan="progressive", lumiere=2,
                           level_black=0.2, level_white=0.75, restore_audio=False)
    info = _info()
    new = pipeline.filter_chain(info, nu)
    niveaux = next(f for f in new.split(",") if f.startswith("colorlevels="))
    old = f"format=yuv420p,{niveaux},eq=contrast=1:saturation=1:gamma=1.2,format=yuv420p"
    raw = _rampe()
    avant = _stats(_ligne(_ffmpeg_raw("yuv420p10le", raw, old + ",format=gray", "gray")))
    apres = _stats(_ligne(_ffmpeg_raw("yuv420p10le", raw, new + ",format=gray", "gray")))
    # Mesuré : 117 niveaux / saut max 5 / saut moyen 1,58  →  159 / 2 / 1,15.
    assert apres["distinct"] >= avant["distinct"] + 30, (avant, apres)
    assert apres["maxstep"] < avant["maxstep"], (avant, apres)
    assert apres["mean_nz"] < avant["mean_nz"] - 0.2, (avant, apres)
    assert abs(apres["mean"] - avant["mean"]) < 3, (avant, apres)


def test_image_ordinaire_moyennes_a_un_255_pres():
    """testsrc2, profil Équilibré : la chaîne 10 bits reste à 1/255 près de l'ancienne."""
    info = MediaInfo(path=Path("t.mp4"), width=320, height=240, fps=Fraction(1), duration=1,
                     dar=Fraction(4, 3), sar=Fraction(1), scan="progressive", pix_fmt="yuv420p")
    s = pipeline.Settings(profile_for("equilibre", "video"), scan="progressive")
    new = pipeline.filter_chain(info, s)
    old = ("removegrain=m0=1:m1=1:m2=1,hqdn3d=3:5:4.5:7,eq=contrast=1.04:saturation=1.08,"
           "cas=strength=0.3,setsar=1/1,format=yuv420p")
    src = "testsrc2=s=320x240:r=1:d=1,format=yuv420p"

    def moyennes(vf):
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", src,
             "-vf", vf + ",format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True)
        if p.returncode:
            raise AssertionError(p.stderr.decode()[-300:])
        return np.frombuffer(p.stdout, np.uint8).reshape(-1, 3).astype(float).mean(0)

    ecart = np.abs(moyennes(new) - moyennes(old))
    assert ecart.max() <= 1.0, ecart


def test_aucune_descente_8bits_cachee():
    nu = pipeline.Settings(_profil_nu(), scan="progressive", lumiere=2,
                           level_black=0.2, level_white=0.75)
    chain = pipeline.filter_chain(_info(), nu)
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "debug", "-f", "lavfi", "-i",
         "testsrc2=s=64x64:r=25:d=0.12,format=yuv420p", "-vf", chain,
         "-frames:v", "2", "-f", "null", "-"],
        capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-400:]
    # swscale répète les mêmes lignes (un thread par plan) : on ne garde que les couples.
    couples = []
    for line in p.stderr.splitlines():
        if "->" not in line or "fmt:" not in line:
            continue
        fmts = re.findall(r"fmt:([A-Za-z0-9]+)", line)
        if len(fmts) >= 2 and fmts[0] != fmts[-1]:
            couple = (fmts[0], fmts[-1])
            if couple not in couples:
                couples.append(couple)
    assert couples, "aucune conversion vue"
    huit = {"yuv420p", "yuv422p", "yuv444p", "gbrp", "rgb24", "gray"}
    # La seule arrivée en 8 bits part du 10 bits (tramage final). Le RVB des niveaux est en 16 bits.
    assert ("yuv420p10le", "yuv420p") in couples
    assert not [c for c in couples if c[1] in huit and c != ("yuv420p10le", "yuv420p")], couples
    assert ("yuv420p10le", "gbrp16le") in couples and ("gbrp16le", "yuv420p10le") in couples


def test_le_passage_final_trame():
    """Une valeur 10 bits entre deux codes 8 bits doit se répartir, pas se tronquer."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "color=c=black:s=32x32,format=yuv420p10le,lutyuv=y=101:u=512:v=512,format=yuv420p,format=gray",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True)
    assert p.returncode == 0
    vals = np.frombuffer(p.stdout, np.uint8)
    assert len(np.unique(vals)) >= 2
    assert 10.2 < float(vals.mean()) < 10.8


def test_temps_au_plus_25_pourcent(tmp_path):
    clip = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "testsrc2=s=720x576:r=25:d=4,format=yuv420p", "-c:v", "libx264", "-crf", "16",
         "-pix_fmt", "yuv420p", str(clip)], check=True)
    info = MediaInfo(path=clip, width=720, height=576, fps=Fraction(25), duration=4,
                     dar=Fraction(4, 3), sar=Fraction(1), scan="progressive", pix_fmt="yuv420p")
    s = pipeline.Settings(profile_for("equilibre", "video"), scan="progressive",
                          restore_audio=False, preset="medium", crf=18)
    new = pipeline.filter_chain(info, s)
    old = ("removegrain=m0=1:m1=1:m2=1,hqdn3d=3:5:4.5:7,eq=contrast=1.04:saturation=1.08,"
           "cas=strength=0.3,setsar=1/1,format=yuv420p")

    def duree(vf, dest=None):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(clip), "-vf", vf, "-an",
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
        cmd += ["-f", "null", "-"] if dest is None else [str(dest)]
        t0 = time.perf_counter()
        subprocess.run(cmd, check=True, capture_output=True)
        return time.perf_counter() - t0

    avant, apres = duree(old), duree(new, tmp_path / "out.mp4")
    assert apres <= avant * 1.25, (avant, apres)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt,codec_name",
         "-of", "csv=p=0", str(tmp_path / "out.mp4")], capture_output=True, text=True, check=True)
    assert "h264" in probe.stdout and "yuv420p" in probe.stdout
