"""Temps restant, début/fin de l'export, bouton « Vérifier l'installation »."""
from fractions import Fraction

import pytest

from conftest import probe_json
from vhs_restore import pipeline
from vhs_restore.eta import Eta, describe
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for
from vhs_restore.tools import ToolError


# ---------------------------------------------------------------- temps restant
def test_describe():
    assert describe(30) == "moins d'une minute restante"
    assert describe(60) == "environ 1 min restante"
    assert describe(25 * 60) == "environ 25 min restantes"
    assert describe(80 * 60) == "environ 1 h 20 restantes"
    assert describe(120 * 60) == "environ 2 h restantes"


def test_eta_waits_then_estimates():
    t = [0.0]
    eta = Eta(clock=lambda: t[0])
    assert eta.update(0.01) == ""                 # trop tôt : rien
    t[0] = 8
    assert eta.update(0.10) == ""                 # moins de 10 s : rien
    t[0] = 60
    assert eta.update(0.25) == "environ 3 min restantes"   # 25 % en 1 min -> 3 min
    t[0] = 120
    assert eta.update(1.0) == ""                  # terminé : rien


# ---------------------------------------------------------------- début et fin
def test_trim_window(samples, tools):
    info = analyze(samples["pal_tff"], tools)       # 4 s
    assert pipeline.trim_window(info, 0, 0) == (None, None)
    assert pipeline.trim_window(info, 1, 0) == (1.0, pytest.approx(3.0))
    assert pipeline.trim_window(info, 0, 2.5) == (None, 2.5)
    assert pipeline.trim_window(info, 1, 99) == (1.0, pytest.approx(3.0))   # fin ramenée au film
    with pytest.raises(ToolError, match="après le début"):
        pipeline.trim_window(info, 2, 2.2)
    with pytest.raises(ToolError, match="après la fin"):
        pipeline.trim_window(info, 5, 0)


def _v_a(path):
    d = probe_json(path)
    v = next(x for x in d["streams"] if x["codec_type"] == "video")
    a = [x for x in d["streams"] if x["codec_type"] == "audio"]
    return v, a


def test_trimmed_export(samples, tools, tmp_path):
    info = analyze(samples["pal_tff"], tools)
    start, length = pipeline.trim_window(info, 1, 3.5)
    out = pipeline.export(info, pipeline.Settings(profile_for("equilibre", "video")), tmp_path / "t.mp4",
                          tools, start=start, duration=length)
    v, a = _v_a(out)
    assert abs(float(v["duration"]) - 2.5) < 0.1 and a and abs(float(a[0]["duration"]) - 2.5) < 0.1


def test_trimmed_film_with_shooting_rate(samples, tools, tmp_path):
    info = analyze(samples["film18_son"], tools)            # 6 s à 18 i/s
    start, length = pipeline.trim_window(info, 1, 4)         # 3 s du fichier
    s = pipeline.Settings(profile_for("fidele", "film"), source="film", playback_fps=Fraction(24))
    out = pipeline.export(info, s, tmp_path / "f.mp4", tools, start=start, duration=length)
    v, a = _v_a(out)
    assert int(v["nb_read_frames"]) == 54 and abs(float(v["duration"]) - 2.25) < 0.1   # 3 s x 18 i/s à 24 i/s
    assert a and abs(float(a[0]["duration"]) - float(v["duration"])) < 0.1


# ---------------------------------------------------------------- interface
def test_gui_trim_and_check(tools, samples, tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from vhs_restore.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.detailedText()) or 0)

    def wait(win):
        while win.worker is not None and win.worker.isRunning():
            app.processEvents()
            win.worker.wait(20)
        for _ in range(5):
            app.processEvents()
    win = MainWindow(tools)
    win.out_edit.setText(str(tmp_path))
    win.load_file(str(samples["pal_tff"]))
    wait(win)
    assert win.trim_start.value() == 0 and win.trim_end.value() == 0      # tout garder par défaut
    win.trim_start.setValue(1.0)
    win.trim_end.setValue(3.0)
    win.start_export()
    wait(win)
    out = next(tmp_path.glob("*.mp4"))
    v, _ = _v_a(out)
    assert abs(float(v["duration"]) - 2.0) < 0.1
    win.check_install()
    wait(win)
    assert win.status.text().startswith("Installation vérifiée") and "RÉSULTAT : OK" in shown[-1]
    win.close()
