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


@pytest.mark.parametrize("mode", ["sombre", "clair"])
def test_contrastes_aa(mode):
    theme.set_mode(mode)
    try:
        for nom, fg, bg in theme.CONTRASTES:
            ratio = theme.contraste(fg, bg)
            assert ratio >= 4.5, f"{mode} — {nom} : {fg} sur {bg} = {ratio:.2f}"
    finally:
        theme.set_mode("sombre")


@pytest.mark.parametrize("mode", ["sombre", "clair"])
def test_action_principale_verte(mode):
    """Suivant, avant / après et Lancer allumé : texte blanc sur vert, au moins 4,5:1."""
    theme.set_mode(mode)
    try:
        assert theme.VERT_TEXTE == "#ffffff"
        couples = (
            ("action", theme.VERT_TEXTE, theme.VERT),
            ("survol", theme.VERT_TEXTE, theme.VERT_SURVOL),
            ("pressée", theme.VERT_TEXTE, theme.VERT_PRESSE),
            ("éteinte", theme.VERT_ETEINT_TEXTE, theme.VERT_ETEINT),
            ("repère à venir", theme.TEXTE_DESACTIVE, theme.FOND),
        )
        for nom, fg, bg in couples:
            ratio = theme.contraste(fg, bg)
            assert ratio >= 4.5, f"{mode} — {nom} : {fg} sur {bg} = {ratio:.2f}"
        qss = theme._qss()
        assert theme.VERT in qss and theme.VERT_TEXTE in qss
        assert "QPushButton#action" in qss
    finally:
        theme.set_mode("sombre")


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


@pytest.mark.parametrize("taille", [(1280, 720), (1366, 768)])
def test_lancer_toujours_visible(app, tools, taille):
    win = MainWindow(tools)
    win.show()
    win.resize(*taille)
    app.processEvents()
    assert win.run_btn.isVisible()
    assert win.rect().contains(win.run_btn.mapTo(win, win.run_btn.rect().bottomRight()))
    win.close()


@pytest.mark.parametrize("taille", [(1366, 740), (1280, 720), (1093, 600)])
def test_installation_accessible(app, tools, taille):
    win = MainWindow(tools)
    win.resize(*taille)
    win.show()
    win.details.click()
    app.processEvents()
    assert win.size().toTuple() == taille
    assert win.check_btn.isVisible()
    dlg = win.check_btn.window()
    assert dlg.rect().contains(win.check_btn.mapTo(dlg, win.check_btn.rect().bottomRight()))
    win.close()
