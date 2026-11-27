"""Bugs d'image de la demande n°20, agent B. Rien n'est corrigé dans vhs_restore.

Chaque test décrit le comportement juste et échoue aujourd'hui : ``xfail(strict=True)``
garde la suite verte tant que le bug est là. Le film suit la recette réaliste
(plan qui se déplace, lumière qui varie, bruit, entrelacement, vraie coupure en concat),
pas une mire fixe.
"""
import dataclasses
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.probe import MediaInfo
from vhs_restore.profiles import profile_for

# Recette de la demande, durée raccourcie : le graphe est le même.
_RECETTE = (
    "testsrc2=s=1440x1152:r=50:d={d},crop=720:576:x='min(t*6\\,720)':y='min(t*4\\,576)',"
    "eq=brightness='0.03*sin(2*PI*t/7)':eval=frame,noise=alls=8:allf=t,interlace,"
    "format=yuv422p,setsar=16/15"
)
# Second plan : autre couleur, autre sens de déplacement, même bruit et même lumière.
_AUTRE = (
    "testsrc2=s=1440x1152:r=50:d={d},hue=H=100,"
    "crop=720:576:x='min(( {d}-t)*40\\,720)':y='min(t*8\\,576)',"
    "eq=brightness='-0.05+0.03*sin(2*PI*t/7)':eval=frame,noise=alls=8:allf=t,interlace,"
    "format=yuv422p,setsar=16/15"
)


def _info(path: Path, **kw) -> MediaInfo:
    base = dict(path=path, width=720, height=576, fps=Fraction(25), duration=4.0,
                dar=Fraction(4, 3), sar=Fraction(16, 15), scan="tff", pix_fmt="yuv422p",
                color_space="bt470bg", color_range="tv")
    base.update(kw)
    return MediaInfo(**base)


def _rgb(src, vf: str, w: int, h: int, n: int | None = None, raw: bytes | None = None) -> np.ndarray:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", *src, "-vf", vf,
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    if n:
        cmd = cmd[:-1] + ["-frames:v", str(n), "-"]
    r = subprocess.run(cmd, capture_output=True, input=raw)
    if r.returncode:
        raise AssertionError(r.stderr.decode()[-500:])
    data = np.frombuffer(r.stdout, np.uint8)
    if len(data) % (w * h * 3):
        raise AssertionError(f"taille inattendue {len(data)} pour {w}x{h}")
    return data.reshape((-1, h, w, 3))


def _film_coupe(tmp: Path, d: int = 2) -> Path:
    out = tmp / "recette-coupe.mkv"
    ff("-f", "lavfi", "-i", _RECETTE.format(d=d), "-f", "lavfi", "-i", _AUTRE.format(d=d),
       "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0", "-c:v", "ffv1", str(out))
    return out


@pytest.mark.xfail(strict=True, reason="deflicker=size=5 mélange la scène suivante : "
                    "la couleur dérive pendant 4 images avant la coupure")
def test_scintillement_ne_tire_pas_la_couleur_avant_la_coupure(tmp_path):
    """Transfert, recette entrelacée, deux plans concaténés.

    Les images juste avant la coupure doivent garder la couleur de leur plan.
    Aujourd'hui le vert chute (170 → 162) sur les quatre dernières images.
    """
    film = _film_coupe(tmp_path)
    info = _info(film, duration=4.0)

    def moyennes(scintille: bool) -> np.ndarray:
        s = pipeline.Settings(profile_for("equilibre", "transfer"), source="transfer", scan="tff",
                              restore_audio=False, deflicker=scintille)
        images = _rgb(["-i", str(film)], pipeline.filter_chain(info, s) + ",format=rgb24", 720, 576)
        return images.reshape(len(images), -1, 3).mean(1)

    sans, avec = moyennes(False), moyennes(True)
    saut = np.abs(np.diff(sans, axis=0)).sum(1)
    coupe = int(saut.argmax()) + 1          # première image du plan suivant
    assert 4 < coupe < len(sans) - 1, (coupe, len(sans))
    avant = slice(coupe - 4, coupe)
    ecart = np.abs(avec[avant] - sans[avant]).max()
    assert ecart < 3.0, (round(float(ecart), 1),
                         np.round(sans[avant], 1).tolist(),
                         np.round(avec[avant], 1).tolist())


@pytest.mark.xfail(strict=True, reason="le gain rouge est déjà au plafond 1,18 : "
                    "teinte +3 ajoute 0 de rouge au film et +13 à l'aperçu")
def test_teinte_chaude_arrive_dans_le_film_meme_au_plafond(tmp_path):
    """Cassette verte déjà corrigée jusqu'au plafond, puis « Plus chaude » (+3).

    Le rouge du film doit monter (l'aperçu, lui, monte d'environ 13 niveaux).
    Aujourd'hui le filtre reste rr=1,1800 et le rouge ne bouge pas.
    """
    src = tmp_path / "vert.mkv"
    # Recette, avec une dominante verte (rouge et bleu plus faibles).
    ff("-f", "lavfi", "-i",
       "testsrc2=s=1440x1152:r=50:d=1,crop=720:576:x='min(t*6\\,720)':y='min(t*4\\,576)',"
       "eq=brightness='0.03*sin(2*PI*t/7)':eval=frame,"
       "colorchannelmixer=rr=0.75:gg=1.15:bb=0.85,noise=alls=8:allf=t,interlace,"
       "format=yuv422p,setsar=16/15",
       "-c:v", "ffv1", str(src))
    brut = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "0.40", "-i", str(src),
         "-vf", "bwdif=mode=send_frame:parity=tff:deint=all", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "yuv422p", "-"],
        capture_output=True, check=True).stdout
    info = _info(src, duration=1.0, scan="progressive", fps=Fraction(25))
    # Plafonds de safe_gains : une dominante verte forte s'arrête à +18 % de rouge.
    gains = dict(gain_r=pipeline.GAIN_MAX, gain_g=pipeline.GAIN_MIN, gain_b=1.10)
    nu = dataclasses.replace(profile_for("fidele", "video"), denoise=None, despeckle=False, sharpen=0.0)

    def image(teinte: int) -> np.ndarray:
        s = pipeline.Settings(nu, source="video", scan="progressive", restore_audio=False,
                              teinte=teinte, **gains)
        return _rgb(["-f", "rawvideo", "-pix_fmt", "yuv422p", "-s", "720x576", "-i", "pipe:0"],
                    pipeline.filter_chain(info, s) + ",format=rgb24", 720, 576, raw=brut)[0]

    base, chaud = image(0), image(3)
    rouge = float(chaud[:, :, 0].mean() - base[:, :, 0].mean())
    # L'aperçu ajoute la teinte APRÈS le plafond (lumiere.filtres_utilisateur).
    tei = 3
    apercu_vf = (pipeline.filter_chain(
        info, pipeline.Settings(nu, source="video", scan="progressive", restore_audio=False,
                                teinte=0, **gains))
        + f",colorchannelmixer=rr={1 + pipeline.PAS_TEINTE * tei:.4f}"
          f":bb={1 - pipeline.PAS_TEINTE * tei:.4f},format=rgb24")
    apercu = _rgb(["-f", "rawvideo", "-pix_fmt", "yuv422p", "-s", "720x576", "-i", "pipe:0"],
                  apercu_vf, 720, 576, raw=brut)[0]
    annonce = float(apercu[:, :, 0].mean() - base[:, :, 0].mean())
    assert rouge >= 8.0, (round(rouge, 2), round(annonce, 2))


@pytest.mark.xfail(strict=True, reason="chromashift décale la chroma, pas l'image : "
                    "4 px demandés déplacent la couleur de 8 px")
def test_decalage_couleur_compte_en_pixels_d_image():
    """Un réglage de 4 px doit déplacer la couleur de 4 pixels d'image, pas de 8.

    DVD 4:2:0 et capture 4:2:2 : un cran de chromashift vaut deux pixels d'image.
    """
    w, h = 720, 576
    image = np.zeros((h, w, 3), np.uint8)
    image[:, : w // 2] = (220, 30, 30)
    image[:, w // 2 :] = (30, 30, 220)
    brut = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{w}x{h}", "-i", "pipe:0", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-frames:v", "1", "-"],
        input=image.tobytes(), capture_output=True, check=True).stdout
    info = MediaInfo(path=Path("frontiere.yuv"), width=w, height=h, fps=Fraction(25), duration=0.04,
                     dar=Fraction(4, 3), sar=Fraction(1), scan="progressive", pix_fmt="yuv420p",
                     color_space="bt470bg", color_range="tv")
    nu = dataclasses.replace(profile_for("fidele", "video"), denoise=None, despeckle=False, sharpen=0.0)

    def frontiere(decalage: int) -> int:
        s = pipeline.Settings(nu, source="video", scan="progressive", restore_audio=False,
                              chroma_shift=decalage)
        rgb = _rgb(["-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{w}x{h}", "-i", "pipe:0"],
                   pipeline.filter_chain(info, s) + ",format=rgb24", w, h, raw=brut)[0]
        rb = rgb[h // 2, :, 0].astype(int) - rgb[h // 2, :, 2].astype(int)
        xs = np.where(rb < 0)[0]
        assert len(xs), "frontière introuvable"
        return int(xs[0])

    deplacement = frontiere(4) - frontiere(0)
    assert abs(deplacement - 4) <= 1, deplacement


@pytest.mark.xfail(strict=True, reason="en Full HD le masque du bas reste à 16 lignes d'image "
                    "au lieu des 30 lignes que font 16 lignes de VHS")
def test_bande_du_bas_couvre_la_commutation_en_full_hd(tmp_path):
    """16 lignes de bande en 576 doivent devenir noires aussi après l'agrandissement en 1080.

    Aujourd'hui seules 16 lignes de 1080 sont noires : la ligne −20 reste rouge (R ≈ 200).
    """
    src = tmp_path / "bande.mkv"
    ff("-f", "lavfi", "-i", _RECETTE.format(d=1), "-c:v", "ffv1", str(src))
    brut = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "0.40", "-i", str(src),
         "-vf", "bwdif=mode=send_frame:parity=tff:deint=all,format=rgb24", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True).stdout
    image = np.frombuffer(brut, np.uint8).reshape(576, 720, 3).copy()
    image[-16:] = (220, 10, 10)
    code = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", "720x576", "-i", "pipe:0", "-f", "rawvideo", "-pix_fmt", "yuv422p", "-frames:v", "1", "-"],
        input=image.tobytes(), capture_output=True, check=True).stdout
    info = _info(src, duration=1.0, scan="progressive")
    nu = dataclasses.replace(profile_for("fidele", "video"), denoise=None, despeckle=False, sharpen=0.0)
    s = pipeline.Settings(nu, source="video", scan="progressive", restore_audio=False,
                          resolution="1080", mask_bottom=16)
    # 16 lignes de 576 → 30 lignes de 1080. Le masque n'en couvre que 16 : on regarde le reste.
    lignes = int(round(16 * 1080 / 576))
    rgb = _rgb(["-f", "rawvideo", "-pix_fmt", "yuv422p", "-s", "720x576", "-i", "pipe:0"],
               pipeline.filter_chain(info, s) + ",format=rgb24", 1440, 1080, raw=code)[0]
    reste = rgb[-lignes:-16, :, 0]
    assert reste.mean() < 20.0, round(float(reste.mean()), 1)
