"""Boutons simples pour enlever un passage au milieu du film."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QPoint  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from vhs_restore.gui import BarreFilm, MainWindow  # noqa: E402


def _attendre(app, win) -> None:
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(5):
        app.processEvents()


def _cliquer(win, texte: str) -> None:
    boutons = [b for b in win.findChildren(QPushButton) if texte in b.text()]
    assert boutons, texte
    visibles = [b for b in boutons if not b.isHidden()]
    (visibles or boutons)[0].click()


def test_passages_au_milieu(tools, samples):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.load_file(str(samples["long"]))
    _attendre(app, win)

    win.start_spin.setValue(10)
    _cliquer(win, "commence ici")
    win.start_spin.setValue(25)
    _cliquer(win, "reprend ici")

    assert len(win._coupes) == 1
    assert win._coupes[0][0] == pytest.approx(10)
    assert win._coupes[0][1] == pytest.approx(25)
    libelles = [lb.text() for lb in win.findChildren(QLabel) if lb.text().startswith("De ")]
    assert libelles
    assert any("10" in t for t in libelles)
    assert any("seconde" in t or "min" in t for t in libelles)

    _cliquer(win, "Annuler la dernière coupe")
    assert win._coupes == []

    avant = win.status.text()
    _cliquer(win, "reprend ici")
    assert win._coupes == []
    assert win.status.text() != avant
    assert "commence" in win.status.text().lower()

    barre = win.findChild(BarreFilm)
    assert barre is not None and barre.duree > 0
    barre.resize(400, 56)
    QTest.mouseClick(barre, Qt.LeftButton, pos=QPoint(200, 28))
    assert win.start_spin.value() == pytest.approx(barre.duree / 2, abs=1.5)
    assert "Vous êtes à" in win.status.text()
    win.close()
