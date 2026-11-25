"""Assistant pas à pas (film, photo) et son propre à chaque film (demande n°14)."""
import subprocess
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore import assistant


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
        for _ in range(3):
            while win.worker is not None and win.worker.isRunning():
                app.processEvents()
                win.worker.wait(20)
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
    assert a.compteur.text() == "Étape 1 sur 4" and a.titre.text() == "Choisir le rendu"
    assert not win.run_btn.isEnabled()                                     # rien à lancer à l'étape 1
    assert all(not t.icon().isNull() for t in a.tuiles.values())           # quatre images à comparer
    a.tuiles["maximum"].click()
    assert win.settings().profile.key == "maximum"
    a.suivant.click()
    a.chercher.click()
    attendre(win)
    assert abs(win.trim_start.value() - 3) <= 0.6 and abs(win.trim_end.value() - 63) <= 0.6, a.note_coupe.text()
    a.suivant.click()
    attendre(win)
    assert a.titre.text() == "Le son"
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
    assert a.titre.text() == "Vérifier et lancer" and "Maximum" in a.resume.text()
    assert not win.run_btn.isEnabled()                                     # pas sans l'avant / après
    a.voir.click()
    attendre(win)
    assert win.preview is not None and win.run_btn.isEnabled()
    win.profile_buttons["fidele"].click()                                  # réglage changé : aperçu à revoir
    assert not win.run_btn.isEnabled() and a.voir.text() == "Voir l'avant / après"
    win.son_zero.click()
    assert win.offset_spin.value() == 0 and win.drift_spin.value() == 0 and not win.son_zero.isVisible()
    win.libre.click()                                                      # « Réglages libres »
    assert win.options.isVisible() and not a.isVisible() and win.run_btn.isEnabled()
    assert win.sections["Couper le film"][1].parent() is not a._page_coupe   # la coupe est rendue
    win.libre.click()
    assert a.isVisible() and not win.options.isVisible()


def test_chaque_etape_tient_a_1280_641(fenetre, cassette):
    ouvrir, attendre, _ = fenetre
    win = ouvrir()
    win.load_file(str(cassette))
    attendre(win)
    a = win.assistant
    for _ in range(4):
        assert (win.width(), win.height()) == (1280, 641), a.titre.text()
        assert win.rect().contains(win.run_btn.geometry().bottomRight())
        a.suivant.click()
        attendre(win)
    win.libre.click()
    attendre(win)
    assert (win.width(), win.height()) == (1280, 641)


def test_photo_en_deux_etapes(fenetre, tmp_path):
    ouvrir, attendre, _ = fenetre
    p = tmp_path / "photo.png"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240", "-frames:v", "1", "-update", "1", str(p))
    win = ouvrir()
    win.load_file(str(p))
    attendre(win)
    a = win.assistant
    assert a.compteur.text() == "Étape 1 sur 2"
    a.suivant.click()
    assert a.titre.text() == "Vérifier et lancer" and not a.suivant.isVisible()


def test_le_son_n_est_plus_garde_d_un_film_a_l_autre(fenetre, cassette, tmp_path):
    from PySide6.QtCore import QSettings
    ouvrir, attendre, _ = fenetre
    QSettings("VHSRestoreAI", "VHSRestoreAI").setValue("audio_drift_ms_per_min", -190)   # ancienne version
    win = ouvrir()
    assert win.drift_spin.value() == 0
    assert QSettings("VHSRestoreAI", "VHSRestoreAI").value("audio_drift_ms_per_min") is None
    win.load_file(str(cassette))
    attendre(win)
    win.offset_spin.setValue(-40)
    autre = tmp_path / "autre.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=5", "-f", "lavfi", "-i", "sine=d=5",
       "-c:v", "libx264", "-c:a", "aac", str(autre))
    win.load_file(str(autre))
    attendre(win)
    assert win.offset_spin.value() == 0                                    # propre à chaque film
    win.close()
    win2 = ouvrir()
    assert win2.offset_spin.value() == 0 and win2.drift_spin.value() == 0
