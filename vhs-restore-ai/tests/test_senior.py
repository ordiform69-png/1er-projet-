"""Pensé pour une personne âgée : mots simples, étape suivante désignée, comparaison sans
geste précis, affichage clair possible, aide accessible."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from vhs_restore import theme  # noqa: E402
from vhs_restore.advice import Advice  # noqa: E402
from vhs_restore.gui import MainWindow, _duree, _en_clair  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait(app, win):
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(5):
        app.processEvents()


def test_mots_de_tous_les_jours():
    assert _duree(31) == "31 secondes" and _duree(1) == "1 seconde"
    assert _duree(725) == "12 min 05 s" and _duree(3840) == "1 h 04 min"
    assert _en_clair(Advice("levels", "Les noirs sont gris…", {})) == "image un peu terne"
    assert _en_clair(Advice("channel", "…", {"audio_channel_fix": "left"})) == "son d'un seul côté"


def test_etape_suivante_designee_et_comparaison(app, tools, samples, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    win = MainWindow(tools)
    assert win.s_choose.suggested and not win.s_preview.suggested
    assert not win.statusBar().isVisible() or not win.isVisible()         # pas de noms d'outils
    win.load_file(str(samples["pal_tff"]))
    wait(app, win)
    assert win.s_preview.suggested and not win.s_choose.suggested
    assert "Défauts repérés" not in win.s_info.text() or "niveaux" not in win.s_info.text()   # pas de jargon
    win.s_preview.click()
    wait(app, win)
    assert win.s_run.suggested
    assert win.s_segments.isVisibleTo(win.centralWidget())
    win.segments["after"].click()
    assert win.s_compare.mode == "after"
    assert win.compare.mode == "after"
    win.segments["before"].click()
    assert win.s_compare.mode == "before"
    win.details.click()
    assert win.tools_label.isVisible()                                  # voyants pour connaisseurs
    win.close()


def test_aide_et_premier_lancement(app, tools, monkeypatch):
    vus = []
    textes = []

    def capter(self):
        vus.append(self.windowTitle())
        textes.append(self.text())
        return 0

    monkeypatch.setattr(QMessageBox, "exec", capter)
    win = MainWindow(tools)
    win.maybe_welcome()                       # en test, pas de préférences : rien ne s'ouvre
    assert vus == []
    win.help_btn.click()
    assert vus == ["Bienvenue dans VHS Restore AI"]
    assert "Ce que le logiciel ne peut pas faire" in textes[0]
    assert "détail absent de la bande" in textes[0]
    assert "renumériser ou couper" in textes[0]
    assert "regardez toujours l'avant / après" in textes[0]
    win.close()


def test_coloriser_non_installee_propose_l_installation(app, tools, monkeypatch, tmp_path):
    from conftest import ff
    import dataclasses
    from vhs_restore.tools import Tool
    vus = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: vus.append(self.windowTitle()) or 0)
    img = tmp_path / "grand-mère.jpg"
    ff("-f", "lavfi", "-i", "mandelbrot=size=320x240", "-frames:v", "1", "-vf", "format=gray", str(img))
    win = MainWindow(dataclasses.replace(tools, colorizer=Tool("Colorisation (DDColor)")))
    win.load_file(str(img))
    wait(app, win)
    assert win.s_colorize.isEnabled()
    win.s_colorize.setChecked(True)
    assert not win.s_colorize.isChecked() and vus[-1] == "Colorisation"   # fiche « Installer »
    win.close()


def test_affichage_clair(app, tools):
    theme.set_mode("clair")
    try:
        theme.apply(app)
        win = MainWindow(tools)
        win.show()
        win.resize(1366, 740)
        app.processEvents()
        assert win.theme_btn.text() == "Affichage sombre"
        assert win.width() == 1366 and win.run_btn.isVisible()
        win.close()
    finally:
        theme.set_mode("sombre")
        theme.apply(app)
