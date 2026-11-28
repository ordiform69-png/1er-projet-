"""Dominante mesurée sur tout le film (24 moments), pas sur un seul moment.

Avant : 8 images au tiers du film décidaient pour tout le film. Un plan de pelouse à cet
endroit faisait virer tout le film au magenta ; une lampe orangée à l'intérieur faisait
bleuir toutes les scènes du dehors. Scènes d'essai : une pièce, un jardin, de la neige, avec
le grain et la mollesse d'une VHS (jamais une mire seule pour juger la couleur).
"""
import math

import pytest

from conftest import ff
from vhs_restore.advice import advise
from vhs_restore.probe import analyze, cast_gains, rgb_mean

TAILLE = "320x240"


def _scene(fond, boites):
    s = f"color=c={fond}:size={TAILLE}:rate=25"
    for x, y, w, h, c in boites:
        s += f",drawbox=x={x}:y={y}:w={w}:h={h}:color={c}:t=fill"
    return s + ",noise=alls=10:allf=t,gblur=sigma=1.2"


PIECE = _scene("0xb4b0aa", [(0, 170, 320, 70, "0x6e5a46"), (20, 110, 120, 70, "0x3c5078"),
                            (180, 60, 50, 60, "0xd2a082"), (170, 120, 70, 80, "0xe6e6e6"),
                            (260, 90, 40, 90, "0x3c7832"), (40, 20, 70, 50, "0x8c8c96")])
JARDIN = _scene("0x4a8a2a", [(0, 0, 320, 80, "0x8cb4e6"), (180, 50, 110, 90, "0xd2d2c8"),
                             (180, 30, 110, 22, "0x8c3c32"), (60, 90, 30, 70, "0xd2a082"),
                             (55, 120, 40, 60, "0x283c64")])
LAMPE = ",lutrgb=r='clip(val*1.0+28,0,255)':g='val*0.92':b='val*0.70'"      # lampe orangée
JOUR_BLEU = ",lutrgb=r='val*0.85':g='val*0.95':b='clip(val*1.0+25,0,255)'"


def _film(chemin, parties):
    args, fc = [], ""
    for i, (src, duree) in enumerate(parties):
        args += ["-f", "lavfi", "-t", str(duree), "-i", src]
        fc += f"[{i}:v]setsar=1[v{i}];"
    fc += "".join(f"[v{i}]" for i in range(len(parties))) + f"concat=n={len(parties)}:v=1:a=0[o]"
    ff(*args, "-filter_complex", fc, "-map", "[o]", "-c:v", "ffv1", str(chemin))
    return chemin


def _ecart(rgb):
    return max(rgb) - min(rgb)


def _conseil(info):
    return [a for a in advise(info) if a.key == "cast"]


def test_pelouse_au_tiers_ne_colore_plus_tout_le_film(tools, tmp_path):
    f = _film(tmp_path / "pelouse.mkv", [(PIECE, 30), (JARDIN, 30), (PIECE, 30)])
    info = analyze(f, tools)
    ancien = rgb_mean(tools.ffmpeg.path, f, info.duration / 3)
    assert _ecart(ancien) > 30                   # le piège existe : au tiers, que de la pelouse
    assert _ecart(info.cast_rgb) < 12, info.cast_rgb
    assert not _conseil(info)
    assert not info.couleur_variable


def test_film_entier_au_jardin_sans_fausse_dominante(tools, tmp_path):
    info = analyze(_film(tmp_path / "jardin.mkv", [(JARDIN, 90)]), tools)
    assert not _conseil(info), info.cast_rgb


def test_piece_neutre_sans_conseil(tools, tmp_path):
    info = analyze(_film(tmp_path / "piece.mkv", [(PIECE, 90)]), tools)
    assert _ecart(info.cast_rgb) < 12, info.cast_rgb
    assert not _conseil(info) and not info.couleur_variable


def test_lampe_orangee_toujours_corrigee(tools, tmp_path):
    info = analyze(_film(tmp_path / "lampe.mkv", [(PIECE + LAMPE, 90)]), tools)
    tips = _conseil(info)
    assert tips and not info.couleur_variable
    gr, gg, gb = cast_gains(info.cast_rgb)
    assert gr < 0.9 and gb > 1.15                # moins de rouge, plus de bleu
    assert "change" not in tips[0].text


def test_interieur_puis_dehors_repere_et_dit(tools, tmp_path):
    f = _film(tmp_path / "melange.mkv", [(PIECE + LAMPE, 45), (JARDIN + JOUR_BLEU, 45)])
    info = analyze(f, tools)
    assert info.couleur_variable
    ancien = cast_gains(rgb_mean(tools.ffmpeg.path, f, info.duration / 3))
    nouveau = cast_gains(info.cast_rgb)
    # avant : la correction de la lampe (bleu +41 %) pour tout le film, dehors compris
    assert abs(math.log(nouveau[2])) < abs(math.log(ancien[2])) / 2
    tips = _conseil(info)
    if tips:
        assert "changent d'une scène à l'autre" in tips[0].text
