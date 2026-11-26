"""Assistant pas à pas (film, photo) et son propre à chaque film (demande n°14)."""
import subprocess
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore import assistant, pipeline

pytestmark = pytest.mark.assistant          # l'assistant est allumé, comme dans le logiciel


def test_calcul_decalage_et_derive():
    # 80 ms à 4,5 s et −40 ms à 54 s : la correction appliquée au temps t (décalage − dérive × t / 60)
    # redonne exactement ces deux valeurs
    decalage, derive = assistant.son_depuis_debut_fin(80, 4.5, -40, 54)
    assert (decalage, derive) == (91, 145)
    for t, attendu in ((4.5, 80), (54, -40)):
        assert abs(decalage - derive * t / 60 - attendu) <= 1
    assert assistant.son_depuis_debut_fin(120, 30, 120, 3000) == (120, 0)


def test_phrase_du_son():
    assert assistant.phrase_son(0, 0) == ""
    assert assistant.phrase_son(-40, -190) == "son avancé de 40 ms, ralenti de 190 ms par minute"
    assert assistant.phrase_son(91, 145) == "son retardé de 91 ms, accéléré de 145 ms par minute"


@pytest.mark.parametrize("son,attendu", [(70.21, 180), (70.0, None)])
def test_derive_proposee_d_apres_les_durees(tools, tmp_path, son, attendu):
    """Son PCM 0,3 % plus long que l'image (horloge du boîtier) : dérive proposée à ± 10 %."""
    f = tmp_path / "capture.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=s=160x120:r=25:d=70", "-f", "lavfi", "-i", f"sine=f=300:sample_rate=48000:d={son}",
       "-c:v", "libx264", "-c:a", "pcm_s16le", str(f))
    res = assistant.suggestion_derive(tools.ffprobe.path, f)
    if attendu is None:
        assert res is None
    else:
        assert res is not None and abs(res[0] - attendu) <= attendu * 0.1, res


def test_ecoute_de_dix_secondes(tools, tmp_path):
    from vhs_restore.probe import analyze
    f = tmp_path / "film.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=30", "-f", "lavfi", "-i", "sine=f=300:sample_rate=48000:d=30",
       "-c:v", "libx264", "-c:a", "aac", str(f))
    out = assistant.faire_ecoute(analyze(f, tools), tools, tmp_path / "ecoute", 12.0, 200)
    r = subprocess.run([tools.ffprobe.path, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                        "-of", "default=nw=1", str(out)], capture_output=True, text=True)
    assert "codec_type=video" in r.stdout and "codec_type=audio" in r.stdout
    assert abs(float(next(x.split("=")[1] for x in r.stdout.split() if x.startswith("duration="))) - 10) < 0.3


@pytest.fixture()
def fenetre(tools, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    QSettings("VHSRestoreAI", "VHSRestoreAI").clear()
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: None))
    ouverts = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: ouverts.append(url) or True))
    fenetres = []

    def ouvrir():
        win = MainWindow(tools)
        win.show()
        win.resize(1280, 641)
        fenetres.append(win)
        return win

    def attendre(win):
        import time
        fin = time.monotonic() + 120
        for _ in range(3):
            while win.worker is not None and win.worker.isRunning():
                app.processEvents()
                win.worker.wait(20)
            # images du rendu et proposition de dérive : fils de fond, relevés par un minuteur
            while (getattr(win, "assistant", None) is not None and (win.assistant._en_cours or win.lumiere.occupe())
                   and time.monotonic() < fin):
                app.processEvents()
                time.sleep(0.02)
            for _ in range(10):
                app.processEvents()
    yield ouvrir, attendre, ouverts
    for win in fenetres:
        win.close()


@pytest.fixture(scope="module")
def cassette(tmp_path_factory):
    """Neige 3 s, image 60 s, écran bleu 3 s, avec du son."""
    d = tmp_path_factory.mktemp("assistant")
    f = d / "cassette.mp4"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x240:r=25:d=3,noise=alls=100:allf=t+u",
       "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=60",
       "-f", "lavfi", "-i", "color=c=0x1030c8:s=320x240:r=25:d=3",
       "-f", "lavfi", "-i", "sine=f=300:sample_rate=48000:d=66",
       "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]",
       "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-crf", "20", "-c:a", "aac", str(f))
    return f


def test_parcours_complet_d_un_film(fenetre, cassette):
    ouvrir, attendre, ouverts = fenetre
    win = ouvrir()
    win.load_file(str(cassette))
    attendre(win)
    a = win.assistant
    assert a.isVisible() and not win.options.isVisible()
    assert a.compteur.text() == "Étape 1 sur 5" and a.titre.text() == "Choisir le rendu"
    assert "Bien nettoyé, naturel (conseillé)" in a.tuiles["equilibre"].text()
    assert "Bon équilibre" in a.tuiles["equilibre"].text()
    intro = a._page_rendu.findChild(type(a.note_rendu), "introRendu")
    assert intro is not None and intro.text() == "Cliquez sur la ligne qui vous plaît."
    assert "hésitez" not in intro.text()
    for cle in ("fidele", "equilibre", "maximum"):
        assert (a.tuiles[cle].iconSize().width(), a.tuiles[cle].iconSize().height()) == (96, 72)
    assert a.tuiles["original"].minimumHeight() < a.tuiles["fidele"].minimumHeight()
    assert "n'est jamais modifié" in win.bandeau_original.text()
    assert not win.run_btn.isEnabled()                                     # rien à lancer à l'étape 1
    assert all(not t.icon().isNull() for t in a.tuiles.values())           # quatre images à comparer
    a.tuiles["maximum"].click()
    assert win.settings().profile.key == "maximum"
    a.suivant.click()
    attendre(win)
    assert a.titre.text() == "Lumière et couleurs" and win.lumiere.dernier is not None
    a.suivant.click()                                                      # rien à changer : la suite
    a.chercher.click()
    attendre(win)
    assert win.trim_start.value() == win.trim_end.value() == 0 and not win._coupes
    assert len(win.barre.passages_vides) == 2, a.note_coupe.text()
    enlever = win.enlever_passage
    assert enlever.isVisible()
    assert enlever.text() == "Enlever 0:00 – 0:03"
    assert win.enlever_tous_passages.isVisible()
    enlever.click()  # neige au début
    assert enlever.isVisible()
    assert enlever.text() == "Enlever 1:03 – 1:06"
    assert not win.enlever_tous_passages.isVisible()
    enlever.click()  # écran bleu à la fin
    assert not enlever.isVisible()
    gardes = pipeline.passages_gardes(
        win.info.duration, win.trim_start.value(), win.trim_end.value(), win._coupes)
    assert len(gardes) == 1
    debut, fin = gardes[0]
    assert abs(debut - 3) <= 0.6 and abs(fin - 63) <= 0.6, a.note_coupe.text()
    a.suivant.click()
    attendre(win)
    assert a.titre.text() == "Le son"
    assert a.regler_son.text() == "Le son est en retard ?" and not a.regler_son.isChecked()
    a.rangs_son["debut"][1].click()                                        # « Écouter » : 10 s ouvertes
    attendre(win)
    assert ouverts and ouverts[-1].toLocalFile().endswith(".mp4")
    a.rangs_son["debut"][2].setValue(80)
    a.rangs_son["fin"][2].setValue(-40)
    a.suivant.click()
    t1, t2 = a._t_son["debut"], a._t_son["fin"]
    decalage, derive = assistant.son_depuis_debut_fin(80, t1, -40, t2)
    assert (win.offset_spin.value(), win.drift_spin.value()) == (decalage, derive)
    assert "Correction du son" in win.s_note.text() and win.son_zero.isVisible()
    assert a.titre.text() == "Vérifier et lancer" and "Nettoyage au plus fort" in a.resume.text()
    assert "Lumière et couleurs : comme proposé." in a.resume.text()
    assert not win.run_btn.isEnabled()                                     # pas sans l'avant / après
    assert "avant / après" in a.consigne.text() and "avant / après" in win.run_btn.toolTip()
    a.voir.click()
    attendre(win)
    assert win.preview is not None and win.run_btn.isEnabled()
    assert "Durée estimée" in a.resume.text() and "sur cet ordinateur" in a.resume.text()
    assert "Il faut environ" in a.resume.text() and "il en reste" in a.resume.text()
    assert win.status.text().startswith("Aperçu prêt")
    assert "«\u00a0Avant\u00a0» et «\u00a0Après\u00a0»" in win.status.text()
    assert "Durée estimée" not in win.status.text()                       # déjà dans le résumé
    assert (win.width(), win.height()) == (1280, 641)
    win.profile_buttons["fidele"].click()                                  # réglage changé : aperçu à revoir
    assert not win.run_btn.isEnabled() and a.voir.text() == "Voir l'avant / après"
    win.son_zero.click()
    assert win.offset_spin.value() == 0 and win.drift_spin.value() == 0 and not win.son_zero.isVisible()
    win.libre.click()                                                      # « Réglages libres »
    assert win.options.isVisible() and not a.isVisible() and win.run_btn.isEnabled()
    assert win.sections["Couper le film"][1].parent() is not a._page_coupe   # la coupe est rendue
    win.libre.click()
    assert a.isVisible() and not win.options.isVisible()


def _dans_fenetre(win, controle) -> bool:
    from PySide6.QtCore import QPoint, QRect
    return controle.isVisibleTo(win) and win.rect().contains(
        QRect(controle.mapTo(win, QPoint()), controle.size()))


def _pas_de_defilement_horizontal(win) -> None:
    from PySide6.QtWidgets import QScrollArea
    assert not isinstance(win.centralWidget(), QScrollArea)
    for zone in win.findChildren(QScrollArea):
        if zone.isVisible():
            assert zone.horizontalScrollBar().maximum() == 0


def test_chaque_etape_tient_a_1280_641(fenetre, cassette, tmp_path):
    """100, 125 et 150 % : la fenêtre ne grandit pas, film et photo.

    « Suivant » (tant que l'étape n'est pas la dernière) et « Lancer la restauration »
    restent dans la fenêtre. Pas de défilement horizontal.
    """
    ouvrir, attendre, _ = fenetre
    photo = tmp_path / "photo.png"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240", "-frames:v", "1", "-update", "1", str(photo))
    for pct in (100, 125, 150):
        for chemin, etapes in ((cassette, 5), (photo, 3)):
            win = ouvrir()
            win.set_taille_texte(pct, annoncer=False)
            win.load_file(str(chemin))
            attendre(win)
            a = win.assistant
            for i in range(etapes):
                if chemin == cassette and i == 2:
                    from PySide6.QtWidgets import QPushButton
                    from vhs_restore.vides import Passage
                    a._vides_trouves(([Passage(0, 3, "neige"), Passage(63, 66, "écran bleu")], 66))
                    attendre(win)
                    boutons = {b.text(): b for b in a._page_coupe.findChildren(QPushButton)}
                    for texte in ("Zoom −", "Zoom +", "Tout le film", "Enlever 0:00 – 0:03", "Tout enlever"):
                        assert 36 <= boutons[texte].height() <= 44
                        assert _dans_fenetre(win, boutons[texte]), (pct, texte)
                    _pas_de_defilement_horizontal(win)
                    if pct <= 125:
                        zone = win.sections["Couper le film"][1]
                        assert zone.verticalScrollBar().maximum() == a.pages_zone.verticalScrollBar().maximum() == 0
                    a._vides_trouves(([], 66))
                if i == etapes - 1:                    # la vraie fin : après l'avant / après
                    a.voir.click()
                    attendre(win)
                    assert win.preview is not None
                assert (win.width(), win.height()) == (1280, 641), (pct, a.titre.text())
                _pas_de_defilement_horizontal(win)
                if pct <= 125:                         # aucun défilement à 100 et 125 %
                    assert a.pages_zone.verticalScrollBar().maximum() == 0, (pct, a.titre.text())
                assert "Lancer la restauration" in win.run_btn.text()
                assert _dans_fenetre(win, win.run_btn), (pct, a.titre.text())
                if a.suivant.isVisible():
                    assert "Suivant" in a.suivant.text()
                    assert _dans_fenetre(win, a.suivant), (pct, a.titre.text())
                a.suivant.click()
                attendre(win)
            a.aller(1)                                 # retour à Lumière après l'avant / après
            attendre(win)
            assert (win.width(), win.height()) == (1280, 641), (pct, "retour")
            if pct <= 125:
                assert a.pages_zone.verticalScrollBar().maximum() == 0, (pct, "retour")
            if chemin == cassette and pct == 100:
                win.libre.click()
                attendre(win)
                assert (win.width(), win.height()) == (1280, 641)
                _pas_de_defilement_horizontal(win)
            win.close()


def test_photo_en_trois_etapes(fenetre, tmp_path):
    ouvrir, attendre, _ = fenetre
    p = tmp_path / "photo.png"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240", "-frames:v", "1", "-update", "1", str(p))
    win = ouvrir()
    win.load_file(str(p))
    attendre(win)
    a = win.assistant
    assert a.compteur.text() == "Étape 1 sur 3"
    a.suivant.click()
    attendre(win)
    assert a.titre.text() == "Lumière et couleurs" and not a._page_lumiere.autre.isVisible()   # pas de « moment »
    assert win.lumiere.dernier is not None and not win.lumiere.erreur
    a.suivant.click()
    assert a.titre.text() == "Vérifier et lancer" and not a.suivant.isVisible()


def test_le_son_n_est_plus_garde_d_un_film_a_l_autre(fenetre, cassette, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from vhs_restore.gui import MainWindow
    ouvrir, attendre, _ = fenetre
    reglages = QSettings(str(tmp_path / "reglages.ini"), QSettings.IniFormat)   # sous pytest, aucun réglage
    monkeypatch.setattr(MainWindow, "_prefs", lambda self: reglages)             # n'est lu : on en fournit
    reglages.setValue("audio_drift_ms_per_min", -190)                            # ancienne version
    reglages.setValue("audio_offset_ms", -40)
    win = ouvrir()
    assert win.drift_spin.value() == 0 and win.offset_spin.value() == 0
    assert reglages.value("audio_drift_ms_per_min") is None and reglages.value("audio_offset_ms") is None
    win.load_file(str(cassette))
    attendre(win)
    win.offset_spin.setValue(-40)
    autre = tmp_path / "autre.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=5", "-f", "lavfi", "-i", "sine=d=5",
       "-c:v", "libx264", "-c:a", "aac", str(autre))
    win.load_file(str(autre))
    attendre(win)
    assert win.offset_spin.value() == 0                                    # propre à chaque film
    win.offset_spin.setValue(120)
    win.close()                                                            # les réglages sont enregistrés
    assert reglages.value("audio_offset_ms") is None
    win2 = ouvrir()
    assert win2.offset_spin.value() == 0 and win2.drift_spin.value() == 0
