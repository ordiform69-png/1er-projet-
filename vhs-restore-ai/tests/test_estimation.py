"""Durée gardée, extrapolation, et phrase de place avant de lancer."""
import pytest

from vhs_restore import estimation


def test_duree_gardee_deduit_debut_fin_et_coupes():
    assert estimation.duree_gardee(100, 0, 0, []) == 100
    # fenêtre 10 s → 80 s, moins le passage 30 s → 40 s
    assert estimation.duree_gardee(100, 10, 80, [(30, 40)]) == 60
    # coupe hors de la fenêtre : elle ne change rien
    assert estimation.duree_gardee(100, 0, 50, [(80, 90)]) == 50
    # deux coupes qui se touchent ne sont comptées qu'une fois
    assert estimation.duree_gardee(100, 0, 0, [(10, 20), (15, 25)]) == 85
    # moins d'une demi-seconde : ignorée
    assert estimation.duree_gardee(100, 0, 0, [(10, 10.2)]) == 100


def test_extrapoler_depuis_dix_secondes():
    assert estimation.extrapoler(2.5, 10, 60) == 15
    assert estimation.extrapoler(0, 10, 60) == 0
    assert estimation.extrapoler(4, 0, 60) == 0


def test_phrase_duree_et_place():
    assert estimation.phrase_temps(7200) == "environ 2 heures"
    assert estimation.phrase_temps(30) == "moins d'une minute"
    texte = estimation.phrase(7200, 6e9, 120e9)
    assert texte == ("Durée estimée : environ 2 heures sur cet ordinateur. "
                     "Il faut environ 6 Go ; il en reste 120 Go.")
    manque = estimation.phrase(7200, 6e9, 2e9)
    assert manque.startswith("Il manque de la place")
    assert "Durée estimée" in manque
    assert manque.index("Il manque") < manque.index("Durée estimée")
    assert "Il faut environ 0,1 Go" in estimation.phrase(30, 2e6, 120e9)     # jamais « 0 Go »


def fenetre_factice(tmp_path, cle, restauration_s=3.0, duree=3600.0):
    """Le strict nécessaire de la fenêtre pour estimation.annonce."""
    from fractions import Fraction
    from types import SimpleNamespace as N
    from vhs_restore import pipeline
    from vhs_restore.probe import MediaInfo
    from vhs_restore.profiles import profile_for
    info = MediaInfo(path=tmp_path / "cassette.mkv", width=720, height=576, fps=Fraction(25), duration=duree,
                     has_audio=True)
    return N(info=info, preview=N(restauration_s=restauration_s, duration=10.0), is_photo=False,
             trim_start=N(value=lambda: 0), trim_end=N(value=lambda: 0), _coupes=[],
             out_edit=N(text=lambda: str(tmp_path)),
             settings=lambda: pipeline.Settings(profile_for(cle, "video"), source="video"))


def test_la_duree_tient_compte_de_l_encodage_final(tmp_path):
    """L'aperçu encode en « veryfast », la restauration en « medium » : sans facteur, la durée
    annoncée était 1,6 à 2,3 fois trop courte (mesuré)."""
    for cle, attendu in (("fidele", 3 * 360 * 2.2), ("equilibre", 3 * 360 * 1.75), ("maximum", 3 * 360 * 1.65)):
        estime, place = estimation.calcul(fenetre_factice(tmp_path, cle))
        assert abs(estime - attendu) < 1, (cle, estime)
        assert place is not None and place[1] > 0
    temps, place = estimation.lignes(fenetre_factice(tmp_path, "equilibre"))
    assert temps == "Durée estimée : environ 32 minutes sur cet ordinateur."
    assert place.startswith("Il faut environ") and "il en reste" in place
    assert estimation.annonce(fenetre_factice(tmp_path, "equilibre")) == temps + " " + place


def test_estimation_contre_duree_reelle(tools, tmp_path):
    """Film de synthèse SD de 60 s avec son : l'estimation n'est jamais nettement trop courte."""
    import time
    from conftest import ff
    from vhs_restore import pipeline
    from vhs_restore.probe import analyze
    from vhs_restore.profiles import profile_for
    f = tmp_path / "cassette.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=s=720x576:r=25:d=60,noise=alls=12:allf=t,interlace,setsar=16/15",
       "-f", "lavfi", "-i", "sine=f=300:sample_rate=48000:d=60", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(f))
    info = analyze(f, tools)
    s = pipeline.Settings(profile_for("equilibre", info.suggested_source), source=info.suggested_source)
    p = pipeline.make_preview(info, s, tools, tmp_path / "apercu", 20)
    estime = estimation.extrapoler(p.restauration_s, p.duration, 60) * estimation.facteur("equilibre")
    t0 = time.monotonic()
    pipeline.export(info, s, tmp_path / "restaure.mp4", tools)
    reel = time.monotonic() - t0
    assert 0.7 * reel <= estime <= 2.5 * reel, (estime, reel)


def test_reglages_libres_annoncent_la_duree(tools, tmp_path):
    """Réglages libres : pas de résumé d'assistant, la durée et la place vont dans la ligne d'état."""
    import time
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from conftest import ff
    from vhs_restore.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    f = tmp_path / "film.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=30", "-f", "lavfi", "-i", "sine=d=30",
       "-c:v", "libx264", "-c:a", "aac", str(f))
    win = MainWindow(tools)
    try:
        win.show()
        win.load_file(str(f))
        fin = time.monotonic() + 120
        while (win.info is None or (win.worker is not None and win.worker.isRunning())) and time.monotonic() < fin:
            app.processEvents()
            time.sleep(0.02)
        assert not win.assistant.actif                     # écran complet (tests hors assistant)
        win.start_preview()
        while (win.worker is not None and win.worker.isRunning()) or win.preview is None:
            app.processEvents()
            time.sleep(0.02)
            assert time.monotonic() < fin
        for _ in range(10):
            app.processEvents()
        texte = win.status.text()
        assert texte.startswith("Aperçu prêt") and "Durée estimée" in texte and "Il faut environ" in texte, texte
    finally:
        win.close()
