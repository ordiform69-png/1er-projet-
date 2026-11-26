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
    assert win.s_run.accessibleName() == "Lancer la restauration"
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
            assert win.width() == w and win.height() == h
            assert win.rect().contains(win.run_btn.mapTo(win, win.run_btn.rect().bottomRight()))
            win.close()


def test_phrases_de_reprise():
    """Textes exacts : 5 parties sur 11 font 45 %, comme l'exemple de la demande."""
    ouv = ergonomie.message_ouverture(5, 11)
    assert ouv == ("Une restauration de ce film s'était arrêtée à 45 %. "
                   "« Lancer la restauration » la reprendra.")
    assert "45 %" in ouv and "reprendra" in ouv
    assert ergonomie.message_progression(6, 12) == "Reprise : 6 parties sur 12 déjà faites."
    assert ergonomie.message_progression(1, 12) == "Reprise : 1 partie sur 12 déjà faite."
    arret = ergonomie.message_arret()
    assert arret == "Arrêté. Les parties déjà restaurées sont gardées : relancez pour reprendre."
    for texte in (ouv, ergonomie.message_progression(6, 12), arret):
        bas = f" {texte.lower()} "
        assert "morceau" not in bas and "chunk" not in bas
        assert " tu " not in bas and " te " not in bas
    assert ergonomie.lire_reprise(object(), object()) is None


def _brancher_reprise(monkeypatch, faux):
    """Le faux module doit être celui que `from . import reprise` retrouve."""
    import sys

    import vhs_restore

    monkeypatch.setitem(sys.modules, "vhs_restore.reprise", faux)
    monkeypatch.setattr(vhs_restore, "reprise", faux)


def test_lecture_reprise_tolerante(monkeypatch):
    """Moteur inutilisable : rien. Signatures de reprise.py : 5 parties sur 11, puis 6 sur 12."""
    import types

    info = types.SimpleNamespace(duration=3600.0, path="film.mp4")
    faux = types.ModuleType("vhs_restore.reprise")

    def applicable(info, reglages, passages=None, start=None, duration=None):
        return passages != "non"

    faux.applicable = applicable
    faux.dossier = lambda info, reglages, passages=None, start=None, duration=None: "dossier"
    faux.parties_faites = lambda dossier: list(range(5))
    faux.decouper = lambda passages, duree_partie=None, chauffe=None: list(range(11))
    _brancher_reprise(monkeypatch, faux)
    etat = ergonomie.lire_reprise(info, object(), passages=None, gardes=[(0.0, 3600.0)])
    assert etat is not None and (etat.faites, etat.total, etat.en_parties) == (5, 11, True)
    assert "45 %" in etat.phrase_ouverte()
    assert etat.phrase_en_cours() == "Reprise : 5 parties sur 11 déjà faites."
    assert ergonomie.message_ouverture(etat.faites, etat.total) == etat.phrase_ouverte()
    assert ergonomie.lire_reprise(info, object(), passages="non", gardes=[(0.0, 20.0)]) is None

    faux.parties_faites = lambda dossier: list(range(6))
    faux.decouper = lambda passages, duree_partie=None, chauffe=None: list(range(12))
    etat = ergonomie.lire_reprise(info, object(), gardes=[(0.0, 3600.0)])
    assert etat is not None and etat.phrase_en_cours() == "Reprise : 6 parties sur 12 déjà faites."
    assert "50 %" in etat.phrase_ouverte()


@pytest.mark.assistant
def test_reprise_annoncee_a_l_ecran(app, tools, tmp_path, monkeypatch):
    """Ligne d'état, résumé « Vérifier et lancer », reprise, arrêt et erreur. Fenêtre 1280 × 641."""
    import types
    from fractions import Fraction

    from PySide6.QtWidgets import QScrollArea

    from vhs_restore.probe import MediaInfo

    faux = types.ModuleType("vhs_restore.reprise")
    faux.applicable = lambda info, reglages, passages=None, start=None, duration=None: True
    faux.dossier = lambda info, reglages, passages=None, start=None, duration=None: tmp_path
    faux.parties_faites = lambda dossier: list(range(5))
    faux.decouper = lambda passages, duree_partie=None, chauffe=None: list(range(11))
    _brancher_reprise(monkeypatch, faux)
    vus = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: vus.append(self.text()) or 0)

    chemin = tmp_path / "famille.mp4"
    chemin.write_bytes(b"x")
    info = MediaInfo(path=chemin, duration=3600, width=720, height=576, fps=Fraction(25, 1),
                     has_audio=True, scenes_vues=True, suggested_source="video", scan="progressive")
    win = MainWindow(tools)
    win.info = info
    win.is_photo = False
    win.assistant._info = info
    win.status.setText(f"Vidéo analysée : {info.path.name}. Étape suivante : « Voir l'avant / après ».")
    win._annoncer_reprise_ouverte()
    assert "arrêtée à 45 %" in win.status.text()
    assert "Lancer la restauration" in win.status.text()
    assert "«\u00a0Lancer la restauration\u00a0»" in win.status.text()

    win.show()
    win.assistant.pages.setCurrentWidget(win.assistant._page_fin)
    win._update_state()
    assert "arrêtée à 45 %" in win.assistant.resume.text()
    assert "morceau" not in win.assistant.resume.text().lower()
    for pct in (100, 150):
        win.set_taille_texte(pct, annoncer=False)
        win.resize(1280, 641)
        app.processEvents()
        assert (win.width(), win.height()) == (1280, 641)
        for zone in win.findChildren(QScrollArea):
            if zone.isVisible():
                assert zone.horizontalScrollBar().maximum() == 0

    etat = win._etat_reprise()
    win._job = "export"
    win._reprise_courante = etat
    win.eta = Eta()
    win._on_progress(0.2, "Restauration")
    assert win.status.text().startswith("Reprise : 5 parties sur 11 déjà faites.")
    assert "Restauration" in win.status.text()
    assert ergonomie.PHRASE_PATIENCE in win.status.text()
    win._on_cancelled()
    assert win.status.text() == ergonomie.message_arret()
    win._reprise_courante = etat
    win._job = "export"
    win._on_failed("erreur bizarre xyz")
    assert win.status.text() == ergonomie.message_arret()
    assert vus and vus[-1].startswith(ergonomie.message_arret())
    assert "n'a pas abouti" in vus[-1]
    win._reprise_courante = None
    win._job = "export"
    win._on_cancelled()
    assert "cliquez sur" in win.status.text()
    win.close()


def test_fichier_recent_absent(app, tools, monkeypatch):
    textes = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: textes.append(self.text()) or 0)
    win = MainWindow(tools)
    win._rouvrir_recent("/tmp/plus-la.mp4")
    assert textes and "plus là" in win.status.text().lower() or "n'est plus" in textes[0]
    assert "plus là" in textes[0] or "clé USB" in textes[0]
    win.close()
