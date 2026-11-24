"""La barre du film se comporte comme un petit montage."""
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QPoint  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from vhs_restore.gui import BarreFilm, MainWindow  # noqa: E402

_GUI = Path(__file__).resolve().parent.parent / "vhs_restore" / "gui.py"


def _exiger_montage() -> None:
    """Le montage n'est testable que lorsque la barre sait tirer un bord."""
    texte = _GUI.read_text(encoding="utf-8")
    manques = []
    if "borde = Signal" not in texte:
        manques.append("`borde = Signal`")
    if "Couper ici" not in texte:
        manques.append("le texte « Couper ici »")
    if manques:
        pytest.fail(
            "gui.py n'est pas prêt pour le montage : "
            + " et ".join(manques)
            + " absent(s). La barre ne se comporte pas encore comme un petit montage.")


def _attendre(app, win) -> None:
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(5):
        app.processEvents()


def _bouton(win, texte: str) -> QPushButton:
    boutons = [b for b in win.findChildren(QPushButton) if texte in b.text()]
    if not boutons:
        vus = sorted({b.text() for b in win.findChildren(QPushButton)})
        pytest.fail(
            f"Bouton introuvable : le texte doit contenir « {texte} ». "
            f"Boutons présents : {vus}")
    visibles = [b for b in boutons if not b.isHidden()]
    return (visibles or boutons)[0]


def _cliquer(win, texte: str) -> None:
    _bouton(win, texte).click()


def _glisser(widget, x1: int, x2: int, y: int) -> None:
    """Pression, déplacement bouton gauche enfoncé, relâchement."""
    depart = QPoint(int(x1), int(y))
    arrivee = QPoint(int(x2), int(y))
    QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, depart, 0)
    QTest.mouseMove(widget, arrivee, 0)
    QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, arrivee, 0)


def _x_de(barre: BarreFilm, temps: float) -> int:
    """Pixel du moment `temps`, même repère que le bord doré."""
    return int(round(float(barre._x_de(temps))))


def _ouvrir(tools, samples):
    _exiger_montage()
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.load_file(str(samples["long"]))
    _attendre(app, win)
    barre = win.findChild(BarreFilm)
    assert barre is not None and barre.duree > 0
    return app, win, barre


def test_barre_comme_un_montage(tools, samples):
    app, win, barre = _ouvrir(tools, samples)

    # 1. Le film long donne une barre qui a vraiment une durée.
    assert barre.duree > 0

    # 2. Glisser du quart vers la moitié place l'extrait au milieu du film.
    assert barre.width() > 0 and barre.height() > 0
    y = barre.height() // 2
    _glisser(barre, barre.width() // 4, barre.width() // 2, y)
    _attendre(app, win)
    assert win.start_spin.value() == pytest.approx(barre.duree / 2, abs=2), (
        f"start_spin={win.start_spin.value()} durée={barre.duree} largeur={barre.width()}")
    assert "Vous êtes à" in win.status.text(), win.status.text()

    # 3. « Couper ici », puis le même bouton devenu « reprend », enlève 10 s → 25 s.
    win.start_spin.setValue(10)
    bouton = _bouton(win, "Couper ici")
    assert "Couper ici" in bouton.text()
    bouton.click()
    _attendre(app, win)
    assert "commence" in win.status.text().lower(), win.status.text()
    assert "reprend" in bouton.text().lower(), bouton.text()
    assert "Couper ici" not in bouton.text()
    win.start_spin.setValue(25)
    assert "reprend" in bouton.text().lower()
    bouton.click()
    _attendre(app, win)
    assert win._coupes, "aucune coupe après le second clic"
    assert win._coupes[-1][0] == pytest.approx(10, abs=0.5)
    assert win._coupes[-1][1] == pytest.approx(25, abs=0.5)
    assert "Couper ici" in bouton.text(), bouton.text()

    # 4. Tirer le bord droit. On réutilise (10, 25) ; sinon on pose (10, 40).
    barre.resize(400, 56)
    _attendre(app, win)
    assert barre.width() == 400 and barre.height() == 56, (barre.width(), barre.height())
    reprise = next(
        (c for c in win._coupes
         if c[0] == pytest.approx(10, abs=0.5) and c[1] == pytest.approx(25, abs=0.5)),
        None)
    if reprise is None:
        win.start_spin.setValue(10)
        _cliquer(win, "Enlever 30 secondes ici")
        _attendre(app, win)
        reprise = next(c for c in win._coupes if c[0] == pytest.approx(10, abs=0.5))
        assert reprise[1] == pytest.approx(40, abs=0.5), reprise
    debut, fin_avant = float(reprise[0]), float(reprise[1])
    y = barre.height() // 2
    x_bord = _x_de(barre, fin_avant)
    x_apres = min(barre.width() - 1, x_bord + 40)
    assert x_apres >= x_bord + 30, (x_bord, x_apres, barre.width())
    _glisser(barre, x_bord, x_apres, y)
    _attendre(app, win)
    candidates = [c for c in win._coupes if abs(float(c[0]) - debut) <= 1.0]
    assert candidates, win._coupes
    a, b = max(candidates, key=lambda c: float(c[1]))
    assert float(b) >= fin_avant + 5, (a, b, fin_avant, win._coupes)
    assert float(b) - float(a) >= 0.5, (a, b)
    statut = win.status.text().lower()
    assert "ajusté" in statut or "restaur" in statut, win.status.text()
    win.close()
