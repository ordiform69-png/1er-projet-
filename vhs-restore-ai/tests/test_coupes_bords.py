"""Coupe collée au bord, curseur jusqu'au bout, Entrée, huit coupes, prise des bords."""
from pathlib import Path

import pytest

from vhs_restore import pipeline

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QPoint, QEvent  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from vhs_restore.gui import BarreFilm, MainWindow  # noqa: E402


def test_coupe_au_bord_ne_garde_pas_tout_le_film():
    """Un seul intervalle restant (début ou fin enlevé) doit partir en début + durée."""
    gardes, start, length = pipeline.bornes_a_exporter(120, 0, 0, [(0, 30)])
    assert gardes == [(30.0, 120.0)]
    assert start == 30.0 and length == pytest.approx(90)

    gardes, start, length = pipeline.bornes_a_exporter(120, 0, 0, [(90, 120)])
    assert gardes == [(0.0, 90.0)]
    assert start is None and length == pytest.approx(90)

    # Fenêtre 1 → 9, coupe qui mange le début : on ne réexporte pas toute la fenêtre.
    gardes, start, length = pipeline.bornes_a_exporter(10, 1, 9, [(0, 4)])
    assert gardes == [(4.0, 9.0)]
    assert start == 4.0 and length == pytest.approx(5)

    _, start, length = pipeline.bornes_a_exporter(120, 0, 0, [])
    assert start is None and length is None

    gardes, start, length = pipeline.bornes_a_exporter(120, 0, 0, [(30, 50)])
    assert len(gardes) == 2 and start is None and length is None


def _attendre(app, win) -> None:
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(8):
        app.processEvents()


def _cliquer(win, texte: str) -> None:
    boutons = [b for b in win.findChildren(QPushButton) if texte in b.text() and not b.isHidden()]
    assert boutons, texte
    boutons[0].click()


def test_restaurer_envoie_la_coupe_du_debut(tools, samples, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.load_file(str(samples["long"]))
    _attendre(app, win)
    win._coupes = [(0.0, 30.0)]
    vu: dict = {}

    def faux(*_a, **k):
        vu.update(k)
        return Path("copie.mp4")

    monkeypatch.setattr(pipeline, "export", faux)
    win.start_export()
    _attendre(app, win)
    assert vu.get("start") == pytest.approx(30)
    assert vu.get("duration") == pytest.approx(win.info.duration - 30, abs=0.5)
    assert vu.get("passages") is None
    win.close()


def test_curseur_va_jusqu_au_bout_dun_film_court(tools, samples):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.load_file(str(samples["pal_tff"]))
    _attendre(app, win)
    assert win.info.duration <= 10
    assert win.start_spin.maximum() == pytest.approx(win.info.duration, abs=0.05)
    barre = win.findChild(BarreFilm)
    barre.resize(400, 56)
    app.processEvents()
    QTest.mouseClick(barre, Qt.LeftButton, pos=QPoint(380, 28))
    assert win.start_spin.value() > 1.0, win.start_spin.value()
    assert "Vous êtes à" in win.status.text()
    win.close()


def test_entree_sur_la_barre_coupe_sans_lancer(tools, samples):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.show()
    win.load_file(str(samples["long"]))
    _attendre(app, win)
    win.start_spin.setValue(12)
    barre = win.findChild(BarreFilm)
    barre.setFocus()
    app.processEvents()
    QApplication.sendEvent(barre, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    app.processEvents()
    assert win._coupe_ouverte == pytest.approx(12)
    assert "reprend" in win.s_couper.text().lower()
    assert win.worker is None or not win.worker.isRunning()
    # Entrée reçue par la fenêtre pendant que la barre a le focus ne lance pas l'étape 2.
    win.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    app.processEvents()
    assert win.worker is None or not win.worker.isRunning()
    assert win._coupes == []
    win.close()


def test_huitieme_coupe_et_annulation_du_geste(tools, samples):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.load_file(str(samples["long"]))
    _attendre(app, win)
    win._coupes = [(float(i), float(i) + 0.6) for i in range(0, 16, 2)]
    assert len(win._coupes) == 8
    win.start_spin.setValue(40)
    win.s_couper.click()
    assert win._coupe_ouverte == pytest.approx(40)
    win.start_spin.setValue(50)
    win.s_couper.click()
    assert win._coupe_ouverte is None
    assert win.s_couper.text() == "Couper ici"
    assert len(win._coupes) == 8
    assert "Huit passages" in win.status.text()

    win.start_spin.setValue(60)
    win.s_couper.click()
    assert win._coupe_ouverte == pytest.approx(60)
    _cliquer(win, "Annuler la dernière coupe")
    assert win._coupe_ouverte is None
    assert win.s_couper.text() == "Couper ici"
    assert len(win._coupes) == 8
    assert "annulée" in win.status.text()
    win.close()


def test_bord_dore_pris_a_44_px():
    app = QApplication.instance() or QApplication([])
    barre = BarreFilm()
    barre.resize(400, 56)
    barre.definir(120, 0, 0, 0, [(10, 40)])
    x = barre._x_de(10)
    assert barre._bord_sous(x + 40) == (0, False)
    assert barre._bord_sous(x + 50) is None
    assert barre.minimumHeight() <= 56
    app.processEvents()
