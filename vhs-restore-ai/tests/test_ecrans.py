"""Écrans standard : le logiciel tient sur chacun, sans défilement de côté ni fenêtre qui déborde.

Taille utile d'une fenêtre agrandie = largeur / zoom de Windows, hauteur / zoom − 79 (barre des
tâches 48 et barre de titre 31, en points logiques ; mesuré chez l'utilisateur : 1920 × 1080 à
150 % donne 1280 × 641, couvert par test_ecran_unique et test_assistant).
"""
from pathlib import Path

import pytest

from conftest import ff

ECRANS = [
    ("1024 × 768 à 100 %", 1024, 689),
    ("1366 × 768 à 125 %, 1920 × 1080 à 175 %", 1093, 535),
    ("1366 × 768 à 100 %", 1366, 689),
    ("1920 × 1080 à 125 %", 1536, 785),
    ("1920 × 1080 à 100 %, 4K à 200 %", 1920, 1001),
    ("4K à 150 %", 2560, 1361),
]


@pytest.fixture(scope="module")
def film(tmp_path_factory):
    f = tmp_path_factory.mktemp("ecrans") / "film.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=40", "-f", "lavfi", "-i", "sine=f=300:d=40",
       "-c:v", "libx264", "-c:a", "aac", str(f))
    return f


def _dans_fenetre(win, controle) -> bool:
    from PySide6.QtCore import QPoint, QRect
    return controle.isVisibleTo(win) and win.rect().contains(QRect(controle.mapTo(win, QPoint()), controle.size()))


@pytest.mark.assistant
@pytest.mark.parametrize("nom,largeur,hauteur", ECRANS, ids=[f"{l}x{h}" for _, l, h in ECRANS])
def test_chaque_ecran_standard(tools, film, nom, largeur, hauteur):
    import time
    from PySide6.QtWidgets import QApplication, QScrollArea
    from vhs_restore.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)

    def attendre():
        fin = time.monotonic() + 120
        while time.monotonic() < fin:
            app.processEvents()
            time.sleep(0.02)
            if (win.worker is None or not win.worker.isRunning()) and not win.assistant._en_cours \
                    and not win.lumiere.occupe():
                for _ in range(8):
                    app.processEvents()
                return

    def verifier(ou: str) -> None:
        win.resize(largeur, hauteur)
        for _ in range(6):
            app.processEvents()
        assert (win.width(), win.height()) == (largeur, hauteur), (nom, ou)
        for zone in win.findChildren(QScrollArea):
            if zone.isVisible():
                assert zone.horizontalScrollBar().maximum() == 0, (nom, ou)
        assert _dans_fenetre(win, win.run_btn), (nom, ou)
        a = win.assistant
        if a.isVisible():
            if a.suivant.isVisible():
                assert _dans_fenetre(win, a.suivant), (nom, ou)
            # l'assistant ne défile pas (texte à 100 %), même sur un écran bas
            assert a.pages_zone.verticalScrollBar().maximum() == 0, (nom, ou)

    try:
        win.show()
        win.resize(largeur, hauteur)
        win.set_taille_texte(100, annoncer=False)
        verifier("accueil")
        win.load_file(str(film))
        attendre()
        a = win.assistant
        for i in range(5):
            if i == 4:
                a.voir.click()
                attendre()
                assert win.preview is not None
            verifier(a.titre.text())
            a.suivant.click()
            attendre()
        win.libre.click()
        attendre()
        for section, (bouton, _zone) in win.sections.items():
            if not bouton.isChecked():
                bouton.click()
            attendre()
            verifier("réglages libres, " + section)     # défilement vertical permis ici sous 641 px
    finally:
        win.close()


@pytest.mark.parametrize("largeur,hauteur,plafond", [(1024, 689, 100), (1093, 535, 100), (1366, 580, 100),
                                                      (1280, 641, 150), (1920, 1001, 150)])
def test_texte_agrandi_selon_l_ecran(tools, largeur, hauteur, plafond, monkeypatch):
    """Écran étroit ou bas : « A » et « A+ » grisés, le texte reste à 100 % (sinon : défilement de
    côté). Le choix est gardé et revient quand la fenêtre est assez grande."""
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    try:
        win.show()
        win.resize(largeur, hauteur)
        app.processEvents()
        win.set_taille_texte(150)
        app.processEvents()
        assert round(win._echelle * 100) == plafond
        assert win._taille_btns[150].isEnabled() is (plafond == 150)
        if plafond < 150:
            assert "trop petit" in win.status.text() and "trop petit" in win._taille_btns[150].toolTip()
            win.resize(1280, 641)                       # fenêtre agrandie : le choix revient
            for _ in range(5):
                app.processEvents()
            assert round(win._echelle * 100) == 150 and win._taille_btns[150].isEnabled()
    finally:
        win.close()
