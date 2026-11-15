"""Lisibilité du thème : contraste WCAG AA, et la page avancée atteint le bouton
de restauration à 1280×720 (et 1366×768)."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from vhs_restore import theme  # noqa: E402
from vhs_restore.gui import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_contrastes_aa():
    for nom, fg, bg in theme.CONTRASTES:
        ratio = theme.contraste(fg, bg)
        assert ratio >= 4.5, f"{nom} : {fg} sur {bg} = {ratio:.2f}"


def test_polices_ofl_chargees(app):
    theme.apply(app)
    assert theme.BODY_FAMILY == "Inter"
    assert theme.DISPLAY_FAMILY == "Rajdhani"
    assert app.font().pointSizeF() >= 12


def test_balayage_arrete_au_repos(app):
    bar = theme.SweepBar()
    assert not bar._timer.isActive()
    bar.setValue(400)
    assert bar._timer.isActive()
    bar.setValue(1000)
    assert not bar._timer.isActive()
    bar.setRange(0, 0)
    assert bar._timer.isActive()
    bar.setRange(0, 1000)
    bar.setValue(0)
    assert not bar._timer.isActive()
    bar.deleteLater()


def _bouton_visible(scroll, btn, app) -> bool:
    app.processEvents()
    vp = scroll.viewport()

    def dedans() -> bool:
        pt = btn.mapTo(vp, QPoint(8, btn.height() // 2))
        return vp.rect().contains(pt)

    if dedans():
        return True
    barre = scroll.verticalScrollBar()
    if barre.maximum() <= barre.minimum():
        return False
    barre.setValue(barre.maximum())
    app.processEvents()
    return dedans()


@pytest.mark.parametrize("taille", [(1280, 720), (1366, 768)])
def test_options_avancées_défilent_jusqu_au_bouton(app, tools, taille):
    win = MainWindow(tools)
    win.show()
    win.resize(*taille)
    win.set_advanced(True)
    app.processEvents()
    scroll = win.pages.widget(1)
    assert isinstance(scroll, QScrollArea)
    assert _bouton_visible(scroll, win.run_btn, app)
    win.close()
