"""Caler la voix sur les lèvres : l'écran le dit, sans jargon.

Constat de l'utilisateur : « Il faut l'indiquer, sinon l'utilisateur ne comprend pas. »
- Réglages libres : la légende « Décalage entre la voix et les lèvres » était coupée à 150 %,
  et rien ne disait à quoi servent « − » et « + » (10 ms par clic) ; le calage au début et à
  la fin (dérive) n'existait que dans l'assistant, sans chemin pour y aller. Maintenant :
  « Avancer la voix » / « Retarder la voix », une image par clic, comme dans l'assistant.
- Assistant : « Le son est en retard ? » trompait (la voix peut être en avance), on ne savait
  pas où s'ouvrent les 10 secondes, ni ce qui était déjà corrigé.
"""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from vhs_restore import ecran  # noqa: E402
from vhs_restore.gui import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def attendre(app, win):
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(5):
        app.processEvents()


def _fenetre(app, tools, chemin, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    win = MainWindow(tools)
    win.resize(1280, 641)
    win.show()
    win.load_file(str(chemin))
    attendre(app, win)
    return win


def _fermer(win):
    try:
        win.lumiere.fermer()
    except Exception:
        pass
    win.close()


def test_reglages_libres_expliquent_et_menent_au_calage(app, tools, samples, monkeypatch):
    win = _fenetre(app, tools, samples["pal_tff"], monkeypatch)
    try:
        a = win.assistant
        assert not a.actif                                   # réglages libres (écran complet)
        ecran.ouvrir(win, "Régler le son")
        app.processEvents()
        lab = win.libelle_decalage
        consigne = lab.text().replace("\u00a0", " ")
        assert lab.isVisible()
        assert consigne == "Voix après les lèvres : « Avancer la voix ». Avant : « Retarder la voix »."
        avancer, retarder = win._son_moins, win._son_plus
        for b in (avancer, retarder):                 # libellé entier, pas « − » ni « + »
            assert b.isVisible() and b.width() >= b.sizeHint().width(), b.text()
        assert (avancer.text(), retarder.text()) == ("Avancer la voix", "Retarder la voix")
        assert not win.offset_spin.isVisible()        # les millisecondes restent cachées
        avancer.click()
        avancer.click()                               # deux clics = deux images plus tôt
        assert win.offset_spin.value() == -80
        assert lab.text().replace("\u00a0", " ").startswith("Voix avancée de 2 images.")
        for _ in range(5):
            retarder.click()
        assert win.offset_spin.value() == 120
        assert lab.text().replace("\u00a0", " ").startswith("Voix retardée de 3 images.")
        assert win.caler_debut_fin.isVisible() and win.caler_debut_fin.isEnabled()

        win.caler_debut_fin.click()                          # vers l'étape « Le son » de l'assistant
        app.processEvents()
        assert a.actif and a.titre.text() == "Le son"
        assert a.regler_son.isChecked() and a.aide_son.isVisible()
        assert all(b.isVisible() for b in a._reglages_son)
        assert win.libre.text() == "Réglages libres"
    finally:
        _fermer(win)


def test_assistant_dit_ou_s_ouvre_l_extrait_et_ce_qui_est_corrige(app, tools, samples, monkeypatch):
    win = _fenetre(app, tools, samples["pal_tff"], monkeypatch)
    try:
        a = win.assistant
        ecran.caler_la_voix(win)
        app.processEvents()
        page = " ".join(lab.text() for lab in a._page_son.findChildren(type(win.libelle_decalage)))
        assert "lecteur vidéo de Windows" in page
        assert a.regler_son.text() == "La voix ne colle pas aux lèvres ?"
        assert "Chaque clic décale la voix d'une image" in a.aide_son.text()
        assert a.etat_son.text() == ""                       # rien de corrigé : rien d'affiché

        trop_tard_debut, trop_tot_debut, trop_tard_fin, trop_tot_fin = a._reglages_son
        trop_tard_debut.click()
        trop_tard_debut.click()
        assert a.etat_son.text() == "Au début : voix avancée de 2 images. À la fin : rien de changé."
        trop_tot_fin.click()
        assert a.etat_son.text() == ("Au début : voix avancée de 2 images. "
                                     "À la fin : voix retardée d'une image.")
        assert a.rangs_son["debut"][2].value() == -80 and a.rangs_son["fin"][2].value() == 40
        for _ in range(3):
            trop_tard_fin.click()                            # la fin comme le début : pas de dérive
        assert a.etat_son.text() == ("Au début : voix avancée de 2 images. "
                                     "À la fin : voix avancée de 2 images.")
        a.suivant.click()                                    # validé : le résumé dit la même chose
        attendre(app, win)
        note = win.s_note.text()
        assert note.endswith("Correction du son : voix avancée de 2 images."), note
        assert win.offset_spin.value() == -80 and win.drift_spin.value() == 0
    finally:
        _fermer(win)


def test_film_sans_son_pas_de_calage(app, tools, samples, monkeypatch):
    win = _fenetre(app, tools, samples["prog"], monkeypatch)
    try:
        assert not win.caler_debut_fin.isEnabled()
        ecran.caler_la_voix(win)                             # sans effet : pas d'étape « Le son »
        assert not win.assistant.actif
    finally:
        _fermer(win)
