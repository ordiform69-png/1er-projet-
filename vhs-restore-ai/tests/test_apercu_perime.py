"""Réglages libres : un réglage changé après l'avant / après le rend ancien, et l'écran le dit.

Constat de l'utilisateur : après avoir coché des réglages (voix, contraste…), l'ancienne image
restait affichée sans rien dire ; on croyait le réglage sans effet sur l'avant / après.
"""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from vhs_restore.gui import MainWindow  # noqa: E402

ANCIEN = "APRÈS (ancien réglage)"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait(app, win):
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(5):
        app.processEvents()


def test_reglage_change_apres_l_avant_apres(app, tools, samples, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    win = MainWindow(tools)
    try:
        win.load_file(str(samples["pal_tff"]))
        wait(app, win)
        win.s_preview.click()
        wait(app, win)
        assert win.preview is not None
        assert win.compare.after_label == "APRÈS"
        assert win.s_run.suggested and not win.s_preview.suggested

        # un réglage du son, coché après l'avant / après
        win.presence_check.setChecked(not win.presence_check.isChecked())
        app.processEvents()
        assert win.compare.after_label == ANCIEN                 # dit sur l'image elle-même
        assert "Réglage changé" in win.status.text()
        assert "Voir l'avant / après" in win.status.text()
        assert win.s_preview.suggested and not win.s_run.suggested

        # revenir au réglage vu : l'avertissement s'efface
        win.presence_check.setChecked(not win.presence_check.isChecked())
        app.processEvents()
        assert win.compare.after_label == "APRÈS"
        assert win.s_run.suggested and not win.s_preview.suggested

        # changer d'image fixe (« Image 1/3 ») ne change aucun réglage
        win.still_combo.setCurrentIndex(0)
        app.processEvents()
        assert win.compare.after_label == "APRÈS"

        # lumière et contraste (des boutons, pas des cases) : suivis aussi
        cle = next(iter(win.lumiere.valeurs))
        win.lumiere.changer(cle, 1)
        app.processEvents()
        assert win.compare.after_label == ANCIEN
        assert win.s_preview.suggested

        # nouvel avant / après : à jour, plus d'avertissement
        win.s_preview.click()
        wait(app, win)
        assert win.compare.after_label == "APRÈS"
        assert win.s_run.suggested and not win.s_preview.suggested
    finally:
        try:
            win.lumiere.fermer()
        except Exception:
            pass
        win.close()


def test_nouveau_film_sans_avertissement(app, tools, samples, monkeypatch):
    """Un autre film chargé : pas d'aperçu, donc rien d'« ancien » à signaler."""
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    win = MainWindow(tools)
    try:
        win.load_file(str(samples["pal_tff"]))
        wait(app, win)
        win.s_preview.click()
        wait(app, win)
        win.presence_check.setChecked(not win.presence_check.isChecked())
        app.processEvents()
        assert win.compare.after_label == ANCIEN
        win.load_file(str(samples["pal_tff"]))
        wait(app, win)
        assert win.preview is None
        assert win.compare.after_label == "APRÈS"
        assert "Réglage changé" not in win.status.text()
        assert win.s_preview.suggested
    finally:
        try:
            win.lumiere.fermer()
        except Exception:
            pass
        win.close()
