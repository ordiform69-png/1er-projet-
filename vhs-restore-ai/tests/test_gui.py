import dataclasses

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from vhs_restore.gui import MainWindow  # noqa: E402
from vhs_restore.tools import Tool  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait(app, win):
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(5):
        app.processEvents()


def test_window_flow(app, tools, samples, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)   # pas de fenêtre modale en test
    t = dataclasses.replace(tools, realesrgan=Tool("Real-ESRGAN"))
    win = MainWindow(t)
    assert not win.run_btn.isEnabled() and not win.ai_check.isEnabled()
    win.load_file(str(samples["pal_tff"]))
    wait(app, win)
    assert win.info is not None
    assert "TFF" in win.info_labels["Balayage"].text()
    assert win.run_btn.isEnabled() and win.preview_btn.isEnabled()
    assert win.settings().profile.key == "equilibre"
    win.profile_buttons["maximum"].setChecked(True)
    assert win.settings().resolution == "1080" and not win.settings().use_ai
    expected = "qtgmc" if t.qtgmc_available else "bwdif"
    assert win.settings().deinterlacer == expected
    assert win.deint_combo.model().item(1).isEnabled() == t.qtgmc_available
    assert win.stab_check.isEnabled() == t.stab_available and not win.settings().stabilize
    win.stab_check.setChecked(True)
    assert win.settings().stabilize == t.stab_available
    win.stab_check.setChecked(False)
    assert not win.settings().denoise_hq
    win.hq_check.setChecked(True)
    assert win.settings().denoise_hq
    win.hq_check.setChecked(False)
    win.profile_buttons["fidele"].setChecked(True)
    win.start_spin.setValue(0)
    win.start_preview()
    wait(app, win)
    assert win.preview is not None and win.compare.before is not None
    win.out_edit.setText(str(tmp_path))
    win.start_export()
    wait(app, win)
    assert win.status.text().startswith("Terminé")
    assert len(list(tmp_path.glob("*_restaure_fidele.mp4"))) == 1
    win.close()


def test_bad_file_shows_error(app, tools, samples, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()) or 0)
    win = MainWindow(tools)
    win.load_file(str(samples["corrupt"]))
    wait(app, win)
    assert shown and win.info is None and not win.run_btn.isEnabled()
    assert "abîmé" in shown[0] and "Traceback" not in shown[0]
    win.close()


def test_source_selector(app, tools, samples):
    win = MainWindow(tools)
    win.load_file(str(samples["film18"]))
    wait(app, win)
    win.sections["Régler l'image"][0].click()
    assert win.source_combo.currentData() is None and win.source() == "film"   # suggestion
    assert win.cadence_combo.isVisibleTo(win) and not win.deint_combo.isEnabled()
    assert win.flicker_check.isVisibleTo(win)
    assert win.dust_check.isVisibleTo(win) and win.dust_check.isEnabled() == tools.dust_available
    win.dust_check.setChecked(True)
    assert win.settings().dust == tools.dust_available
    assert "muet" in win.warn_label.text()
    win.cadence_combo.setCurrentIndex(win.cadence_combo.findData(24))
    s = win.settings()
    assert s.source == "film" and s.playback_fps == 24 and s.profile.denoise == (1.0, 3.0, 1.0, 3.0)
    win.source_combo.setCurrentIndex(win.source_combo.findData("video"))       # correction manuelle
    s = win.settings()
    assert s.source == "video" and s.playback_fps is None and not s.deflicker
    assert not win.cadence_combo.isVisibleTo(win) and not win.flicker_check.isVisibleTo(win)
    assert not win.dust_check.isVisibleTo(win) and not win.settings().dust
    win.close()


def test_simple_mode(app, tools, samples, tmp_path, monkeypatch):
    import shutil
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    win = MainWindow(tools)
    assert win.gauche.currentIndex() == 0 and win.choisir.isVisibleTo(win)
    assert win.s_choose.isEnabled() and not win.s_run.isEnabled() and not win.s_cancel.isEnabled()
    src = tmp_path / "films"
    src.mkdir()
    shutil.copy(samples["film18"], src)
    win.load_file(str(src / samples["film18"].name))
    wait(app, win)
    assert "pellicule" in win.s_info.text() and "muet" in win.s_info.text()
    assert win.s_run.isEnabled() and win.s_preview.isEnabled()
    win.s_preview.click()
    wait(app, win)
    assert win.s_compare.before is not None and win.compare.before is not None
    win.s_run.click()
    wait(app, win)
    assert win.s_status.text().startswith("Terminé") and len(list(src.glob("*_film.mp4"))) == 1
    win.restore_folder(src)
    wait(app, win)
    assert win.s_status.text().startswith("Terminé : 1 fichier")
    assert len(list((src / "Films restaurés").glob("*.mp4"))) == 1
    assert win.s_fini.isVisibleTo(win) and not win.options.isVisibleTo(win)
    win.close()


def test_read_only_source_uses_fallback(app, tools, samples, tmp_path, monkeypatch):
    from pathlib import Path
    from vhs_restore import pipeline
    fb = tmp_path / "Films restaurés"
    monkeypatch.setenv("VHSRA_SORTIE", str(fb))
    src_dir = samples["film18"].parent
    real = pipeline.is_writable
    monkeypatch.setattr(pipeline, "is_writable", lambda d: Path(d) != src_dir and real(d))
    win = MainWindow(tools)
    win.out_edit.setText("")
    win.load_file(str(samples["film18"]))
    wait(app, win)
    assert win.out_edit.text() == str(fb) and "ne peut pas être modifié" in win.warn_label.text()
    win.close()


def test_advice_checkbox(app, tools, samples, tmp_path):
    from conftest import ff
    src = tmp_path / "son d'un seul côté.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-filter_complex",
       "sine=f=440:sample_rate=48000[t];anullsrc=r=48000:cl=mono[s];[t][s]join=inputs=2:channel_layout=stereo[a]",
       "-map", "0:v", "-map", "[a]", "-t", "3", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(src))
    win = MainWindow(tools)
    win.load_file(str(src))
    wait(app, win)
    win.sections["Qualité"][0].click()
    assert win.s_advice.isVisibleTo(win) and win.s_advice.isChecked()     # défauts repérés : cochée d'office
    assert "seul côté" in win.s_info.text() and "côté gauche" in win.s_info.toolTip()   # simple / détail
    assert win.settings().audio_channel_fix == "left"             # corrigé d'office
    win.s_advice.setChecked(False)
    assert win.settings().audio_channel_fix == ""                 # décochée : film tel quel
    win.load_file(str(samples["film18"]))                         # film muet : aucun conseil
    wait(app, win)
    assert not win.s_advice.isVisibleTo(win) and win.settings().audio_channel_fix == ""
    win.close()


def test_photo_mode(app, tools, tmp_path, monkeypatch):
    from conftest import ff
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()) or 0)
    src = tmp_path / "carte postale.jpg"
    ff("-f", "lavfi", "-i", "mandelbrot=size=320x240", "-frames:v", "1", "-vf", "format=gray", "-q:v", "20", str(src))
    win = MainWindow(tools)
    win.out_edit.setText(str(tmp_path))
    win.load_file(str(src))
    wait(app, win)
    assert win.is_photo and "Photo noir et blanc" in win.s_info.text()
    win.s_preview.click()
    wait(app, win)
    assert win.s_compare.before is not None and win.status.text().startswith("Aperçu prêt")
    win.s_run.click()
    wait(app, win)
    assert list(tmp_path.glob("carte postale_restaure_*.png"))
    assert "photo restaurée" in win.s_fini_texte.text()
    assert win.s_voir.text() == "Voir la photo" and not win.s_fini.isHidden()
    win.close()


def test_choix_ia_explicite(app, tools, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    import threading
    win = MainWindow(tools)
    def repondre(box):
        boutons = {b.text(): b for b in box.buttons()}
        assert set(boutons) == {"Continuer avec l'IA", "Continuer sans l'IA", "Annuler"}
        assert "Full HD" in box.text()
        boutons["Continuer sans l'IA"].click()
    monkeypatch.setattr(QMessageBox, "exec", repondre)
    reponse, pret = [], threading.Event()
    win._question_vitesse((15000, True, False, reponse, pret))
    assert reponse == ["sans"] and pret.is_set()
    win.close()
