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
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[2]))
    win = MainWindow(tools)
    win.load_file(str(samples["corrupt"]))
    wait(app, win)
    assert shown and win.info is None and not win.run_btn.isEnabled()
    win.close()


def test_source_selector(app, tools, samples):
    win = MainWindow(tools)
    win.load_file(str(samples["film18"]))
    wait(app, win)
    assert win.source_combo.currentData() is None and win.source() == "film"   # suggestion
    assert win.cadence_combo.isVisibleTo(win) and not win.deint_combo.isEnabled()
    assert win.flicker_check.isVisibleTo(win)
    assert "muet" in win.warn_label.text()
    win.cadence_combo.setCurrentIndex(win.cadence_combo.findData(24))
    s = win.settings()
    assert s.source == "film" and s.playback_fps == 24 and s.profile.denoise == (1.0, 3.0, 1.0, 3.0)
    win.source_combo.setCurrentIndex(win.source_combo.findData("video"))       # correction manuelle
    s = win.settings()
    assert s.source == "video" and s.playback_fps is None and not s.deflicker
    assert not win.cadence_combo.isVisibleTo(win) and not win.flicker_check.isVisibleTo(win)
    win.close()
