"""États de l'interface : ce que l'analyse de bugs a trouvé, pour que ça ne revienne pas.

- le fichier restauré va à côté de SON original (pas dans le dossier du premier fichier ouvert),
  sauf si l'utilisateur a choisi un dossier exprès ;
- pendant un traitement, les réglages sont grisés (ils ont déjà été lus) ;
- en mode Photo, les réglages propres aux films sont cachés ;
- « Écouter » est grisé pour un film sans son.
"""
import dataclasses
import shutil
import threading

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from conftest import ff  # noqa: E402
from vhs_restore.gui import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait(app, win):
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(5):
        app.processEvents()


@pytest.fixture()
def deux_dossiers(tmp_path, samples):
    a, b = tmp_path / "cassettes du salon", tmp_path / "photos de mamie"
    a.mkdir()
    b.mkdir()
    film = a / samples["pal_tff"].name
    shutil.copy(samples["pal_tff"], film)
    img = b / "mariage 1962.jpg"
    ff("-f", "lavfi", "-i", "mandelbrot=size=320x240", "-frames:v", "1", "-vf", "format=gray", str(img))
    return film, img


def test_sortie_a_cote_de_chaque_original(app, tools, deux_dossiers, tmp_path, monkeypatch):
    film, img = deux_dossiers
    win = MainWindow(tools)
    win.load_file(str(film))
    wait(app, win)
    assert win.out_edit.text() == str(film.parent)
    win.load_file(str(img))
    wait(app, win)
    assert win.out_edit.text() == str(img.parent)          # avant : resté sur le dossier du film
    choisi = tmp_path / "choisi"
    choisi.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(choisi)))
    win._choose_outdir()
    win.load_file(str(film))
    wait(app, win)
    assert win.out_edit.text() == str(choisi)              # un choix exprès est gardé
    win.close()


def test_reglages_grises_pendant_un_traitement(app, tools, samples):
    win = MainWindow(tools)
    win.load_file(str(samples["pal_tff"]))
    wait(app, win)
    stop = threading.Event()
    win._launch(lambda c, p: stop.wait(20), lambda r: None)
    app.processEvents()
    try:
        for wd in (win.profile_buttons["maximum"], win.audio_check, win.cast_check, win.res_combo,
                   win.source_combo, win.offset_spin, win.trim_start, win.out_edit, win._out_btn,
                   win.s_advice, win.drop):
            assert not wd.isEnabled(), wd
        assert win.cancel_btn.isEnabled() and win.s_cancel.isEnabled()
        win.load_file(str(samples["prog"]))                 # glissé pendant le traitement
        assert "en cours" in win.status.text()
    finally:
        stop.set()
        wait(app, win)
    assert win.profile_buttons["maximum"].isEnabled() and win.audio_check.isEnabled()
    win.close()


def test_photo_cache_les_reglages_de_film(app, tools, samples, deux_dossiers):
    _film, img = deux_dossiers
    win = MainWindow(tools)
    win.show()
    win.set_advanced(True)
    win.load_file(str(img))
    wait(app, win)
    page = win.pages.widget(1).widget()
    for wd in (win._card_son, win.deint_combo, win.tape_check, win.hq_check, win.stab_check,
               win.mask_spin, win.chroma_spin, win.start_spin, win.trim_start, win.source_combo):
        assert not wd.isVisibleTo(page), wd
    for wd in (win.cast_check, win.ai_check, win.profile_buttons["fidele"], win.run_btn):
        assert wd.isVisibleTo(page), wd
    win.load_file(str(samples["pal_tff"]))                   # retour à un film : tout réapparaît
    wait(app, win)
    for wd in (win._card_son, win.deint_combo, win.hq_check, win.start_spin, win.trim_start, win.source_combo):
        assert wd.isVisibleTo(page), wd
    win.close()


def test_ecouter_grise_pour_un_film_sans_son(app, tools, samples):
    win = MainWindow(tools)
    win.load_file(str(samples["prog"]))                       # « progressif sans son »
    wait(app, win)
    assert not win.info.has_audio
    win.preview = object()                                    # un aperçu existe
    win._update_state()
    assert win.play_btn.isEnabled()
    assert not win.hear_orig_btn.isEnabled() and not win.s_hear_new.isEnabled()
    win.info = dataclasses.replace(win.info, has_audio=True, audio_silent=False)
    win._update_state()
    assert win.hear_orig_btn.isEnabled()
    win.close()
