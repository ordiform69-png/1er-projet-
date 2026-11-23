"""Bords abîmés repérés tout seuls, corrections cochées d'office, messages et écran de fin.

Constat sur un vrai film de l'utilisateur (VHS, 1990 environ) : traits colorés sur le bord gauche,
liseré violet à droite, image terne et jaune-verte ; avec le réglage par défaut (case décochée),
presque rien ne changeait. Désormais les défauts repérés sont corrigés d'office, avec prudence.
"""
import dataclasses

import pytest

from conftest import ff
from vhs_restore import ergonomie, pipeline
from vhs_restore.advice import advise, apply as apply_advice
from vhs_restore.probe import analyze, edge_damage
from vhs_restore.profiles import profile_for


@pytest.fixture(scope="module")
def bords(tmp_path_factory):
    d = tmp_path_factory.mktemp("bords")
    propre = d / "propre.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25", "-t", "2", "-c:v", "ffv1", str(propre))
    abime = d / "abîmé.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25", "-f", "lavfi", "-i",
       "nullsrc=size=720x576:rate=25,geq=lum='128+60*sin(Y*0.9+T*40)':cb='128+90*sin(Y*1.7)':"
       "cr='128-90*cos(Y*1.3)'", "-filter_complex",
       "[1:v]crop=10:576:0:0[n];[0:v][n]overlay=0:0[a];[a]drawbox=x=713:y=0:w=3:h=576:color=0xa020f0:t=fill",
       "-t", "2", "-c:v", "ffv1", str(abime))
    noire = d / "bande noire.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=704x576:rate=25", "-vf", "pad=720:576:8:0:black",
       "-t", "2", "-c:v", "ffv1", str(noire))
    return {"propre": propre, "abime": abime, "noire": noire}


def test_mesure_des_bords(tools, bords):
    ffmpeg = tools.ffmpeg.path
    assert edge_damage(ffmpeg, bords["propre"], 720) == 0
    assert edge_damage(ffmpeg, bords["noire"], 720) == 0          # une bande noire régulière n'est pas un défaut
    n = edge_damage(ffmpeg, bords["abime"], 720)
    assert 10 <= n <= 16, n                                         # 10 px de traits colorés à gauche


def test_conseil_et_masque(tools, bords):
    info = analyze(bords["abime"], tools)
    conseils = {a.key: a for a in advise(info)}
    assert "edges" in conseils and conseils["edges"].fix["mask_sides"] == info.edge_damage
    s = pipeline.Settings(profile_for("equilibre", "video"))
    assert apply_advice(s, list(conseils.values())).mask_sides == info.edge_damage
    large = dataclasses.replace(s, mask_sides=30)                  # choix manuel plus large : gardé
    assert apply_advice(large, list(conseils.values())).mask_sides == 30
    assert "edges" not in {a.key for a in advise(analyze(bords["propre"], tools))}


def test_masque_en_pixels_du_film(tools, bords):
    info = analyze(bords["propre"], tools)
    s = dataclasses.replace(pipeline.Settings(profile_for("fidele", "video")), mask_sides=12, scan="progressive")
    assert "crop=696:576:12:0" in pipeline.filter_chain(info, s)                    # taille d'origine
    hd = pipeline.filter_chain(info, dataclasses.replace(s, resolution="1080"))      # 1440 de large : x2
    assert "crop=1392:1080:24:0" in hd


@pytest.mark.parametrize("message,attendu", [
    ("Ce fichier ne contient pas de piste vidéo.", "abîmé"),
    ("Caractéristiques vidéo illisibles (taille ou cadence inconnue).", "abîmé"),
    ("FFprobe ne répond pas (fichier illisible ?).", "abîmé"),
    ("FFmpeg est introuvable. Lancez installer.bat", "incomplet"),
    ("Fichier introuvable : E:\\films\\noel.avi", "n'est plus là"),
])
def test_erreurs_en_langage_clair(message, attendu):
    assert attendu in ergonomie.expliquer(message)[0]


def test_ecran_fini_boutons_d_abord(tools, tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import MainWindow
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: None))
    win = MainWindow(tools)
    win._montrer_fini("Votre film restauré est prêt :\nnoel_restaure.mp4", tmp_path, tmp_path / "x.mp4", "film")
    lay = win.s_fini.layout()
    ordre = [lay.itemAt(i).widget() or lay.itemAt(i).layout() for i in range(lay.count())]
    assert ordre.index(win._fini_boutons) < ordre.index(win.s_fini_texte)   # boutons avant le long chemin
    assert win.s_info.text().startswith("<b>Terminé.</b>")                   # plus de « cliquez sur le bouton 2 »
    win.close()
