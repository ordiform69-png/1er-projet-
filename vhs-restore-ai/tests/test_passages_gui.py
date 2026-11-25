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

    win.show()
    win.sections["Couper le film"][0].click()
    assert win.s_couper.isVisible()
    assert not win.trim_passage_deb.isVisible() and not win.trim_passage_fin.isVisible()
    # plus de fenêtre « Détails des coupes » : tout est dans la section
    assert not [b for b in win.findChildren(QPushButton) if "Détails des coupes" in b.text()]
    zone = win.sections["Couper le film"][1]
    for b in (win.trim_ici_debut, win.trim_ici_fin):
        assert b.isVisible() and zone.isAncestorOf(b)
    win.start_spin.setValue(10)
    win.s_couper.click()
    assert "reprend" in win.s_couper.text()
    win.start_spin.setValue(25)
    win.s_couper.click()
    assert win.s_couper.text() == "Couper ici"

    assert len(win._coupes) == 1
    assert win._coupes[0][0] == pytest.approx(10)
    assert win._coupes[0][1] == pytest.approx(25)
    libelles = [lb.text() for lb in win.findChildren(QLabel) if lb.text().startswith("De ")]
    assert libelles
    ligne = win._passage_lignes[0][2]                     # le passage et « Remettre », dans la section
    assert ligne.isVisible() and zone.isAncestorOf(ligne)
    assert any("10" in t for t in libelles)
    assert any("seconde" in t or "min" in t for t in libelles)

    _cliquer(win, "Annuler la dernière coupe")
    assert win._coupes == []

    avant = win.status.text()
    win.s_couper.click()                  # un seul clic : le passage commence, rien n'est encore coupé
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


def test_avertissement_avant_restaurer(tools, samples):
    """Une coupe au milieu ne va pas avec l'IA, les réparations de bande… : la note le dit AVANT
    « Restaurer », avec les mots de l'écran, sans rien décocher ni lancer."""
    import dataclasses
    import sys

    from vhs_restore.tools import Tool
    app = QApplication.instance() or QApplication([])
    avec_ia = dataclasses.replace(tools, realesrgan=Tool("Real-ESRGAN", sys.executable))   # IA « installée »
    win = MainWindow(avec_ia)
    win.load_file(str(samples["long"]))
    _attendre(app, win)
    win.start_spin.setValue(10)
    win.s_couper.click()
    win.start_spin.setValue(25)
    win.s_couper.click()
    assert "Attention" not in win.s_passages_note.text()
    win.ai_check.setChecked(True)
    note = win.s_passages_note.text()
    assert "« Amélioration IA »" in note and "décochez" in note and win.ai_check.isChecked()
    win.tape_check.setChecked(True)
    assert "« Bruit de bande »" in win.s_passages_note.text()
    win.ai_check.setChecked(False)
    win.tape_check.setChecked(False)
    assert "Attention" not in win.s_passages_note.text()
    assert win.worker is None or not win.worker.isRunning()          # aucun export lancé
    win.close()


def test_dossier_sans_les_coupes(tools, tmp_path, monkeypatch):
    """Les coupes du film ouvert ne partent pas avec un dossier ; on le dit en haut de la page
    (la ligne d'état est remplacée tout de suite) et dans « C'est prêt ». Pas de vraie restauration."""
    from vhs_restore import ergonomie, pipeline
    from PySide6.QtWidgets import QMessageBox
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)      # message « aucun film » sans attendre
    win = MainWindow(tools)
    win._coupes = [(10.0, 25.0)]                          # une coupe posée sur le film ouvert
    vide = tmp_path / "dossier vide"
    vide.mkdir()
    win.restore_folder(vide)                              # échoue vite (aucun film) dans le fil de travail
    assert "ne seront pas appliquées" in win.s_info.text()
    assert "ne seront pas appliquées" in win.status.text()
    _attendre(app, win)
    win._remarque_dossier = ergonomie.PHRASE_COUPES_DOSSIER
    film = tmp_path / "a_restaure.mp4"
    film.write_bytes(b"")
    win._folder_done(pipeline.BatchResult(tmp_path, [film], []))
    assert "ne seront pas appliquées" in win.s_fini_texte.text()
    assert "ne seront pas appliquées" in ergonomie.resume_dossier(1, 0, [], remarque=ergonomie.PHRASE_COUPES_DOSSIER)
    assert "ne seront pas appliquées" not in ergonomie.resume_dossier(1, 0, [])
    win.close()


def test_molette_sans_focus_ne_change_pas_le_temps():
    """Défiler la page ne doit pas couper le film : la molette est ignorée sans focus."""
    app = QApplication.instance() or QApplication([])
    from vhs_restore.gui import TempsSpin

    class _Molette:
        def __init__(self) -> None:
            self.ignored = False

        def ignore(self) -> None:
            self.ignored = True

    spin = TempsSpin()
    spin.setRange(0, 120)
    spin.setValue(10)
    spin.clearFocus()
    ev = _Molette()
    spin.wheelEvent(ev)
    assert ev.ignored and spin.value() == 10
    app.processEvents()
