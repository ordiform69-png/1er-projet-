"""Lecture intégrée, horodatage source et aperçu audio-vidéo du raccord."""
import array
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import time

import pytest

from conftest import ff
from vhs_restore import pipeline, raccord
from vhs_restore.probe import analyze
from vhs_restore.tools import _NO_WINDOW


@pytest.fixture(scope="module")
def cassette(tmp_path_factory):
    src = tmp_path_factory.mktemp("lecteur") / "Cassette été.mkv"
    couleurs = ("red", "green", "blue")
    tons = (440, 880, 660)
    entrees = []
    for couleur, ton in zip(couleurs, tons):
        entrees += ["-f", "lavfi", "-i", f"color={couleur}:s=160x120:r=25:d=3",
                    "-f", "lavfi", "-i", f"sine=f={ton}:sample_rate=48000:d=3"]
    ff(*entrees, "-filter_complex", "[0:v][1:a][2:v][3:a][4:v][5:a]concat=n=3:v=1:a=1",
       "-c:v", "ffv1", "-c:a", "pcm_s16le", str(src))
    return src


def test_extrait_choisit_le_raccord_ou_la_borne():
    coupes = [(30, 40), (70, 85)]
    assert raccord.extrait(120, 0, 0, coupes, 39) == ((27, 30), (40, 43))
    assert raccord.extrait(120, 0, 0, coupes, 82) == ((67, 70), (85, 88))
    assert raccord.extrait(120, 10, 112, coupes, 9) == ((10, 16),)
    assert raccord.extrait(120, 10, 112, coupes, 115) == ((106, 112),)
    assert raccord.extrait(120, 0, 0, [], 30) == ()


@pytest.mark.parametrize("son", [True, False])
def test_l_extrait_saute_l_image_et_le_son_du_passage(tmp_path, cassette, tools, son):
    info = replace(analyze(cassette, tools), has_audio=son)
    avant = sha256(cassette.read_bytes()).digest()
    chemin = raccord.fabriquer(info, tools, tmp_path, ((2, 3), (6, 7)))
    sortie = analyze(chemin, tools)
    assert sortie.duration == pytest.approx(2.0, abs=0.07)
    assert sortie.dar == info.dar and sortie.has_audio is son
    assert sha256(cassette.read_bytes()).digest() == avant
    assert list(tmp_path.iterdir()) == [chemin]
    from PySide6.QtGui import QImage
    for instant, composante in ((0.4, "red"), (1.4, "blue")):
        image = tmp_path / f"test_{instant:g}.png"
        ff("-ss", str(instant), "-i", str(chemin), "-frames:v", "1", str(image))
        couleur = QImage(str(image)).pixelColor(20, 20)
        assert getattr(couleur, composante)() > 170 and couleur.green() < 30
    if son:
        # Les échantillons doivent aussi passer du bip 440 Hz au bip 660 Hz.
        for instant, frequence in ((0.4, 440), (1.4, 660)):
            pcm = subprocess.check_output([
                tools.ffmpeg.path, "-v", "error", "-ss", str(instant), "-i", str(chemin),
                "-t", "0.2", "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-",
            ], creationflags=_NO_WINDOW)
            valeurs = array.array("h", pcm)
            montees = sum(a < 0 <= b for a, b in zip(valeurs, valeurs[1:]))
            assert montees / 0.2 == pytest.approx(frequence, abs=12)


def attendre(app, condition, secondes=12):
    limite = time.monotonic() + secondes
    while time.monotonic() < limite:
        app.processEvents()
        if condition():
            return
        time.sleep(0.01)
    assert condition(), "Le lecteur n’a pas atteint l’état attendu."


def test_film_et_comparaison_sur_la_meme_barre(tools, cassette):
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import BarreFilm, MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(tools)
    w.resize(1280, 641)
    w.show()
    try:
        w.load_file(str(cassette))
        attendre(app, lambda: w.info is not None and not w._busy())
        assert w.findChildren(BarreFilm) == [w.barre]
        assert w.barre.isVisible() and w.barre.y() > w.moniteur.mapToParent(QPoint()).y()
        assert w.lire_film.objectName() == "secondaire"
        w.start_spin.setValue(1)
        w.lire_film.click()
        attendre(app, lambda: w.lecteur.actif and w.barre.position > 1.2)
        assert w.moniteur.currentWidget() is w.lecteur.video
        assert w.lecteur.media.hasAudio()
        w.lire_film.click()
        attendre(app, lambda: not w.lecteur.joue)
        for pct in (100, 125, 150):
            w.set_taille_texte(pct, annoncer=False)
            app.processEvents()
            assert w.size().toTuple() == (1280, 641)
            assert w.lire_film.height() == 64
            for widget in (w.lecteur.video, w.barre, w.lire_film, w.heure_lecture, w.run_btn):
                assert widget.isVisibleTo(w)
                assert w.rect().contains(QRect(widget.mapTo(w, QPoint()), widget.size()))
        pos = QPoint(round(w.barre._x_de(5)), w.barre._zone().center().y())
        QTest.mouseClick(w.barre, Qt.LeftButton, Qt.NoModifier, pos)
        attendre(app, lambda: abs(w.lecteur.media.position() / 1000 - 5) < 0.08)
        w.revenir_image.click()
        assert w.moniteur.currentWidget() is w.s_compare

        w.preview = pipeline.PreviewResult(0, 9, cassette, cassette, [])
        w._update_state()
        w.play_btn.click()
        attendre(app, lambda: w.lecteur.mode == "comparaison" and w.lecteur.media.position() > 200)
        assert w.moniteur.currentWidget() is w.lecteur.video
        w._coupes = [(3, 6)]
        w._rafraichir_passages()
        w.verifier_coupe.click()
        attendre(app, lambda: w.lecteur.mode == "raccord" and w.lecteur.media.position() > 200)
        assert w._coupes == [(3, 6)]
        assert w.lecteur.media.duration() / 1000 == pytest.approx(6, abs=0.08)
        w.lecteur.ouvrir(Path("Film inexistant.mpg"), "original")
        attendre(app, lambda: not w.lecteur.actif and "petites images" in w.status.text())
        assert w.s_compare.isVisible() and w.barre.isVisible()
    finally:
        w.close()
        app.processEvents()


def test_les_trois_formats_du_paquet(tmp_path):
    # Une seule exécution pour les trois conteneurs ; rien n’est conservé après l’essai.
    commande = [sys.executable, "-m", "vhs_restore", "--autotest-lecteur", str(tmp_path)]
    essai = subprocess.run(commande, capture_output=True, timeout=60,
                           creationflags=_NO_WINDOW)
    rapport = (tmp_path / "autotest-lecteur.txt").read_text(encoding="utf-8")
    assert essai.returncode == 0, rapport
    for nom in ("DVD.mpg", "DV.avi", "Archive.mkv"):
        assert f"{nom} : image décodée" in rapport
    assert len(list(tmp_path.iterdir())) == 1
