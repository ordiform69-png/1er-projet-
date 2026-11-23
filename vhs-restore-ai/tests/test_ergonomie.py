"""Ergonomie pour un utilisateur de 76 ans : fin de travail, erreurs, texte, clavier."""
import threading
import time

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from vhs_restore import ergonomie  # noqa: E402
from vhs_restore.eta import Eta  # noqa: E402
from vhs_restore.gui import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_expliquer_et_resume():
    assert "place" in ergonomie.expliquer("Espace disque insuffisant dans D:\\")[0]
    assert "clé USB" in ergonomie.expliquer("Fichier introuvable : E:\\film.avi")[0]
    assert "abîmé" in ergonomie.expliquer("Fichier non reconnu comme vidéo")[0]
    clair, brut = ergonomie.expliquer("erreur bizarre xyz")
    assert "n'a pas abouti" in clair and brut == "erreur bizarre xyz"
    assert "Traceback" not in clair
    texte = ergonomie.resume_dossier(2, 1, [("vacances.avi", "Espace disque insuffisant")])
    assert "Réussis : 2." in texte and "Déjà faits" in texte and "En échec : 1." in texte
    assert "place" in texte and "vacances.avi" in texte
    assert ergonomie.memoriser_recent(["a", "b", "a"], "c") == ["c", "a", "b"]
    assert ergonomie.memoriser_recent(["a", "b", "c", "d", "e"], "f") == ["f", "a", "b", "c", "d"]


def test_boite_erreur_et_copier(app, monkeypatch):
    vus = []

    def faux_exec(self):
        vus.append((self.windowTitle(), self.text(), [b.text() for b in self.buttons()]))
        if self.windowTitle() == "Une étape n'a pas abouti":
            self._choix = next(b for b in self.buttons() if "Détails" in b.text())
        else:
            self._choix = next(b for b in self.buttons() if b.text() == "Copier")
        return 0

    monkeypatch.setattr(QMessageBox, "exec", faux_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: getattr(self, "_choix", None))
    ergonomie.montrer_erreur(None, "Fichier introuvable : Z:\\film.avi")
    assert "clé USB" in vus[0][1]
    assert "Détails pour l'aide" in vus[0][2] and "Fermer" in vus[0][2]
    assert "Traceback" not in vus[0][1]
    assert "Z:\\film.avi" in vus[1][1]
    assert "Z:\\film.avi" in QApplication.clipboard().text()


def test_ecran_cest_pret(app, tools, tmp_path, monkeypatch):
    ouvert = []
    monkeypatch.setattr("vhs_restore.gui.QDesktopServices.openUrl",
                        lambda u: ouvert.append(u.toLocalFile()) or True)
    win = MainWindow(tools)
    film = tmp_path / "famille.mp4"
    film.write_bytes(b"x")
    win._montrer_fini("Votre film restauré est prêt", tmp_path, film, "film")
    assert win.s_voir.text() == "Regarder le film"
    assert win.s_ouvrir.text() == "Ouvrir le dossier"
    assert win.s_autre.text() == "Restaurer un autre film"
    assert not win.s_fini.isHidden()
    win.s_voir.click()
    assert ouvert and ouvert[-1].endswith("famille.mp4")
    win.s_ouvrir.click()
    assert str(tmp_path) in ouvert[-1] or ouvert[-1].endswith(tmp_path.name)
    win._montrer_fini(ergonomie.resume_dossier(1, 0, []), tmp_path, None, "dossier")
    assert win.s_voir.isHidden() and "dossier" in win.s_autre.text().lower()
    assert "Réussis : 1." in win.s_fini_texte.text()
    win.close()


def test_phrase_et_arret(app, tools, monkeypatch):
    win = MainWindow(tools)
    win._job = "export"
    win.eta = Eta()
    win._on_progress(0.2, "Restauration")
    assert ergonomie.PHRASE_PATIENCE in win.status.text()
    assert "Restauration" in win.status.text()
    stop = threading.Event()
    win._launch(lambda c, p: stop.wait(30), lambda r: None, job="export")
    app.processEvents()
    win._debut_travail = time.monotonic() - 30
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.No)
    win.cancel(confirmer=True)
    assert win._busy() and "continue" in win.status.text()
    assert not win.worker.cancel_event.is_set()
    appeles = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: appeles.append(1) or QMessageBox.Yes)
    win.cancel()                                  # le robot d'audit appelle sans confirmation
    assert appeles == [] and win.worker.cancel_event.is_set()
    stop.set()
    while win._busy():
        app.processEvents()
        win.worker.wait(20)
    win.close()


def test_entree_noms_et_dossier(app, tools, tmp_path, monkeypatch):
    vu = {}

    def faux_ouvrir(*a, **k):
        vu["args"] = a
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", faux_ouvrir)
    win = MainWindow(tools)
    win.show()
    app.processEvents()
    assert "choisir" in win.s_choose.accessibleName().lower()
    assert "restaurer" in win.s_run.accessibleName().lower()
    assert win.s_choose.suggested
    ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    win.keyPressEvent(ev)
    assert vu["args"][1] == "Choisir un film ou une photo"
    assert vu["args"][2] == win._dossier_depart()
    reglage = QSettings(str(tmp_path / "prefs.ini"), QSettings.IniFormat)
    reglage.setValue("dernier_dossier", str(tmp_path))
    monkeypatch.setattr(win, "_prefs", lambda: reglage)
    win._choose_file()
    assert vu["args"][2] == str(tmp_path)
    assert win._simple.acceptDrops()
    win.close()


def test_texte_sans_defilement_horizontal(app, tools):
    tailles = [(1366, 740), (1280, 720), (1093, 600)]
    for pct in (100, 125, 150):
        for w, h in tailles:
            win = MainWindow(tools)
            win.show()
            win.resize(w, h)
            win.set_taille_texte(pct, annoncer=False)
            app.processEvents()
            simple = win.pages.widget(0)
            assert simple.horizontalScrollBar().maximum() == 0, (pct, w, h)
            win.set_advanced(True)
            app.processEvents()
            assert win.pages.widget(1).horizontalScrollBar().maximum() == 0, (pct, w, h)
            win.close()


def test_fichier_recent_absent(app, tools, monkeypatch):
    textes = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: textes.append(self.text()) or 0)
    win = MainWindow(tools)
    win._rouvrir_recent("/tmp/plus-la.mp4")
    assert textes and "plus là" in win.status.text().lower() or "n'est plus" in textes[0]
    assert "plus là" in textes[0] or "clé USB" in textes[0]
    win.close()
