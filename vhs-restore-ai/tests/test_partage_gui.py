"""Écran « C'est prêt » : nommer, copie à partager, séparer en plusieurs films (fenêtre réelle)."""
import hashlib
import shutil

import pytest

from conftest import ff
from vhs_restore import partage


@pytest.fixture()
def fenetre(tools, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    QSettings("VHSRestoreAI", "VHSRestoreAI").clear()
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: None))
    fenetres = []

    def ouvrir():
        win = MainWindow(tools)
        fenetres.append(win)
        return win

    def attendre(win):
        while win.worker is not None and win.worker.isRunning():
            app.processEvents()
            win.worker.wait(20)
        for _ in range(5):
            app.processEvents()
    yield ouvrir, attendre
    for win in fenetres:
        win.close()


@pytest.fixture(scope="module")
def film(tmp_path_factory):
    d = tmp_path_factory.mktemp("film")
    f = d / "DVD_041544_0.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25", "-f", "lavfi", "-i", "sine=f=440:sample_rate=48000",
       "-t", "4", "-vf", "setsar=16/15", "-c:v", "libx264", "-crf", "22", "-c:a", "aac", "-ac", "2", str(f))
    return f


def _restaure(win, film, dossier):
    """Un film ouvert, et son « résultat » affiché sur l'écran « C'est prêt »."""
    src = dossier / film.name
    shutil.copy(film, src)
    out = dossier / f"{film.stem}_restaure_equilibre.mp4"
    shutil.copy(film, out)
    win.load_file(str(src))
    return src, out


def test_nommer_le_film_restaure(fenetre, film, tmp_path, monkeypatch):
    from vhs_restore.gui import MainWindow
    ouvrir, attendre = fenetre
    win = ouvrir()
    src, out = _restaure(win, film, tmp_path)
    attendre(win)
    out.with_suffix(".wav").write_bytes(b"RIFF son")
    win._export_done(out)
    assert not win.s_fini.isHidden() and not win.s_nommer.isHidden() and win.s_nommer.text() == "Nommer ce film"
    assert win.nommer_btn.isEnabled()
    monkeypatch.setattr(MainWindow, "_demander_nom", lambda self, cible, est_photo: ("Noël 1988", "1988-12-25"))
    avant = hashlib.sha256(src.read_bytes()).hexdigest()
    win.s_nommer.click()
    attendre(win)
    nouveau = tmp_path / "Noël 1988.mp4"
    assert nouveau.is_file() and not out.exists() and (tmp_path / "Noël 1988.wav").is_file()
    assert win._fini_fichier == nouveau and "Noël 1988.mp4" in win.s_fini_texte.text()
    assert not win.s_fini.isHidden()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == avant          # l'original n'est pas touché


def test_nommer_sans_resultat_ne_demande_rien(fenetre, film, tmp_path, monkeypatch):
    from vhs_restore.gui import MainWindow
    ouvrir, attendre = fenetre
    win = ouvrir()
    _restaure(win, film, tmp_path)
    attendre(win)
    assert not win.nommer_btn.isEnabled()                                 # rien de restauré : pas de nom
    demande = []
    monkeypatch.setattr(MainWindow, "_demander_nom", lambda *a: demande.append(a))
    win.nommer_resultat()
    assert not demande and "Restaurez d'abord" in win.status.text()


def test_fenetre_de_nom_verifie_le_nom_et_la_date(fenetre, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QLabel, QLineEdit
    ouvrir, _ = fenetre
    win = ouvrir()
    vus = []

    def exec_(dlg):
        nom, date = dlg.findChildren(QLineEdit)
        erreur = next(l for l in dlg.findChildren(QLabel) if l.objectName() == "note")
        nom.setText(" ?? ")
        dlg._verifier()
        vus.append((dlg.result(), erreur.text()))
        nom.setText("Noël 1988")
        date.setText("31/02/1988")
        dlg._verifier()
        vus.append((dlg.result(), erreur.text()))
        date.setText("25/12/1988")
        dlg._verifier()
        return dlg.result()
    monkeypatch.setattr(QDialog, "exec", exec_)
    assert win._demander_nom(tmp_path / "film.mp4", False) == ("Noël 1988", "1988-12-25")
    assert vus[0][0] != QDialog.Accepted and "Tapez un nom" in vus[0][1]
    assert vus[1][0] != QDialog.Accepted and "Date non comprise" in vus[1][1]


def test_copie_legere_depuis_c_est_pret(fenetre, film, tmp_path, monkeypatch):
    from vhs_restore.gui import MainWindow
    ouvrir, attendre = fenetre
    win = ouvrir()
    _src, out = _restaure(win, film, tmp_path)
    attendre(win)
    win._export_done(out)
    monkeypatch.setattr(MainWindow, "_choisir_copie", lambda self, cible: "legere")
    win.s_partager.click()
    attendre(win)
    copie = tmp_path / f"{out.stem} - copie légère.mp4"
    assert copie.is_file() and out.is_file()
    assert "Copie légère prête" in win.s_fini_texte.text() and copie.name in win.s_fini_texte.text()
    assert not win.s_fini.isHidden() and win._fini_fichier == out          # le film restauré reste le résultat


@pytest.fixture(scope="module")
def cassette(tmp_path_factory):
    """Neige 2 s, Noël 4 s, écran bleu 3 s, vacances 3 s, noir 2 s."""
    d = tmp_path_factory.mktemp("cassette")
    f = d / "cassette 1988.mp4"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x240:r=25:d=2,noise=alls=100:allf=t+u",
       "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=4",
       "-f", "lavfi", "-i", "color=c=0x1030c8:s=320x240:r=25:d=3",
       "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=3,hue=s=0",
       "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=2",
       "-f", "lavfi", "-i", "sine=f=300:sample_rate=48000:d=14",
       "-filter_complex", "[0:v][1:v][2:v][3:v][4:v]concat=n=5:v=1:a=0,format=yuv420p[v]",
       "-map", "[v]", "-map", "5:a", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-shortest", str(f))
    return f


def test_separer_une_cassette_en_films(fenetre, cassette, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from vhs_restore.gui import MainWindow
    ouvrir, attendre = fenetre
    monkeypatch.setattr(partage, "FILM_MIN", 1.0)                         # films de quelques secondes
    src = tmp_path / cassette.name
    shutil.copy(cassette, src)
    avant = hashlib.sha256(src.read_bytes()).hexdigest()
    noms = []
    monkeypatch.setattr(MainWindow, "_demander_noms_films",
                        lambda self, cible, films, duree: noms.append(len(films)) or ["Noël 1988", ""])
    win = ouvrir()
    win.load_file(str(src))
    attendre(win)
    win.separer_btn.click()
    attendre(win)
    attendre(win)
    assert noms == [2]
    assert (tmp_path / "Noël 1988.mp4").is_file() and (tmp_path / "cassette 1988 - film 2.mp4").is_file()
    assert "séparé en 2 films" in win.s_fini_texte.text() and not win.s_fini.isHidden()
    assert win.s_voir.text() == "Regarder le premier film"
    assert win.s_nommer.isHidden() and win.s_separer.isHidden()             # déjà nommés, déjà séparés
    assert hashlib.sha256(src.read_bytes()).hexdigest() == avant            # la cassette entière reste

    # depuis « Retirer les passages vides » : la question propose aussi de séparer ; rien n'est écrasé
    vus = []

    def exec_(box):
        vus.append(box.text())
        return 0
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda box: next((b for b in box.buttons() if b.text().startswith("Séparer en")), None))
    win2 = ouvrir()
    win2.load_file(str(src))
    attendre(win2)
    win2.retirer_vides()
    attendre(win2)
    attendre(win2)
    assert "séparent 2 films" in vus[0]
    assert (tmp_path / "Noël 1988 (2).mp4").is_file() and (tmp_path / "Noël 1988.mp4").is_file()


def test_pas_de_coupure_le_dit(fenetre, film, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    ouvrir, attendre = fenetre
    vus = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda _p, _t, texte: vus.append(texte)))
    win = ouvrir()
    src = tmp_path / film.name
    shutil.copy(film, src)
    win.load_file(str(src))
    attendre(win)
    win.separer_films()
    attendre(win)
    attendre(win)
    assert vus and "Aucune coupure nette" in vus[0] and "d'un seul tenant" in vus[0]
    assert sorted(p.name for p in tmp_path.iterdir()) == [film.name]


def test_photo_seulement_nommer(fenetre, tmp_path):
    ouvrir, _ = fenetre
    win = ouvrir()
    p = tmp_path / "IMG_0001_restaure_equilibre.png"
    ff("-f", "lavfi", "-i", "color=c=red:s=64x48", "-frames:v", "1", "-update", "1", str(p))
    win._montrer_fini("Votre photo restaurée est prête.", tmp_path, p, "photo")
    assert win.s_nommer.text() == "Nommer cette photo" and not win.s_nommer.isHidden()
    for b in (win.s_partager, win.s_separer, win.s_vides, win.s_montage):
        assert b.isHidden()
