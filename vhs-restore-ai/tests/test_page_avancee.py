"""Options avancées : pas de grand cadre noir vide, pas de liste vide, textes entiers.

Constat sur l'écran de l'utilisateur (1920 × 1080 à 150 %) : l'aperçu s'étirait sur toute la
hauteur de la colonne de gauche (un rectangle noir de 1 300 px), une liste vide traînait à côté
de « Lire la comparaison », des libellés étaient coupés (« suggestion : v », « Ronflement 50 Hz (Eu »)
et les bords abîmés, masqués d'office, s'affichaient « 0 px ».
"""
import pytest

from conftest import ff


@pytest.fixture()
def fenetre(tools, tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: None))
    film = tmp_path / "DVD_041544_0.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25", "-f", "lavfi", "-i",
       "nullsrc=size=720x576:rate=25,geq=lum='128+60*sin(Y*0.9+T*40)':cb='128+90*sin(Y*1.7)':"
       "cr='128-90*cos(Y*1.3)'", "-filter_complex", "[1:v]crop=10:576:0:0[n];[0:v][n]overlay=0:0",
       "-t", "2", "-c:v", "ffv1", str(film))
    win = MainWindow(tools)
    win.resize(1276, 720)
    win.show()
    win.load_file(str(film))
    while win._busy():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(20):
        app.processEvents()
    yield win, app
    win.close()


def test_apercu_a_la_proportion_de_l_image(fenetre):
    win, _ = fenetre
    vue = win.compare
    assert vue.isVisible() and 180 <= vue.height() <= win.height()
    assert abs(vue.height() - ((vue.width() - 22) * 3 // 4 + 22)) <= 3
    win.sections["Régler le son"][0].click()
    assert win.audio_check.isVisible()
    assert win.audio_check.mapTo(win, win.audio_check.rect().topLeft()).x() > vue.width()


def test_rien_de_vide_ni_de_coupe(fenetre):
    win, _ = fenetre
    assert win.still_combo.isHidden()                                     # pas de liste vide avant l'aperçu
    assert win.preview_btn.text() == "Voir l'avant / après"               # même nom qu'en mode simple
    assert "bouton 2" not in win.status.text()
    for section, combo in (("Régler l'image", win.source_combo), ("Régler le son", win.mains_combo),
                           ("Régler le son", win.copy_combo)):
        bouton = win.sections[section][0]
        if not bouton.isChecked():
            bouton.click()
        win.plus_son.setChecked(True)
        fenetre[1].processEvents()
        assert combo.isVisible()
        assert combo.fontMetrics().horizontalAdvance(combo.currentText()) + 70 < combo.width(), combo.currentText()


def test_defauts_corriges_dits_clairement(fenetre):
    win, _ = fenetre
    win.details.click()
    assert win.a_advice.isVisible() and win.a_advice.isChecked() and win.s_advice.isChecked()
    assert win.edge_spin.text().startswith("auto (")                      # pas « 0 px »
    assert "Corrigé d'office" in win.warn_label.text() and "du son ci-dessous" not in win.warn_label.text()
    win.a_advice.setChecked(False)                                        # une seule case, deux endroits
    assert not win.s_advice.isChecked() and win.edge_spin.text() == "0 px"
    assert "pas corrigé" in win.warn_label.text() and "seront masqués" not in win.warn_label.text()
    assert win.settings().mask_sides == 0
    win.s_advice.setChecked(True)
    assert win.a_advice.isChecked() and win.settings().mask_sides > 0


def test_decoupage_hors_de_restauration_complete(fenetre):
    """Capture de l'utilisateur (n°69) : onze gros boutons de découpage dans « Restauration
    complète » repoussaient « Lancer la restauration » loin vers le bas. Ils ont leur carte."""
    win, _ = fenetre

    win.sections["Couper le film"][0].click()
    assert win.s_couper.isVisible() and win.run_btn.isVisible()
    assert not win.options.isAncestorOf(win.run_btn)
    assert win.s_couper.height() < 50


def test_colonnes_equilibrees(fenetre):
    win, app = fenetre
    for bouton, _ in win.sections.values():
        if not bouton.isChecked():
            bouton.click()
        app.processEvents()
        assert abs(win.options.height() - win.gauche.height()) < 15
