"""Vérifications des traitements IA réellement effectués."""

import pytest

from test_calage_apercu_export import _ecarts, reperes
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import PROFILES


def test_deepfilter_conserve_les_reperes(reperes, tools, tmp_path):
    if not tools.deepfilter.ok:
        pytest.skip("DeepFilterNet absent")
    info = analyze(reperes, tools)
    s = pipeline.Settings(PROFILES["maximum"])
    wav = pipeline._try_deepfilter(info, s, tools, tmp_path, 0, 8, None)
    assert wav is not None
    import subprocess
    film = tmp_path / "repere.mkv"
    subprocess.run([tools.ffmpeg.path, "-v", "error", "-i", str(reperes), "-i", str(wav),
                    "-map", "0:v", "-map", "1:a", "-c:v", "ffv1", "-c:a", "copy", "-t", "8", str(film)], check=True)
    # Même conteneur et horloge vidéo pour les deux pistes.
    avant = tmp_path / "source.mkv"
    subprocess.run([tools.ffmpeg.path, "-v", "error", "-i", str(reperes), "-i",
                    str(tmp_path / "son_source.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "ffv1", "-c:a", "copy", "-t", "8", str(avant)], check=True)
    ref, traite = _ecarts(avant), _ecarts(film)
    communs = ref.keys() & traite.keys()
    assert len(communs) >= 2
    assert max(abs(traite[t] - ref[t]) for t in communs) <= 5


@pytest.mark.parametrize("absent", [True, False], ids=["absent", "en-erreur"])
def test_repli_visible_dans_apercu_et_bilan(absent, tools, samples, tmp_path, monkeypatch):
    from dataclasses import replace
    import sys
    from test_apercu_perime import wait
    from PySide6.QtWidgets import QApplication, QMessageBox
    from vhs_restore.gui import MainWindow
    from vhs_restore.tools import Tool

    app = QApplication.instance() or QApplication([])
    # Python quitte en erreur sur les options du binaire DeepFilterNet.
    outils = replace(tools, deepfilter=Tool("DeepFilterNet", None if absent else sys.executable))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    win = MainWindow(outils)
    try:
        win.load_file(str(samples["pal_tff"]))
        wait(app, win)
        win.profile_buttons["maximum"].setChecked(True)
        win.ai_check.setChecked(False)
        win.audio_check.setChecked(True)
        win.out_edit.setText(str(tmp_path))
        win.start_preview()
        wait(app, win)
        message = "DeepFilterNet indisponible. Le nettoyage habituel a été utilisé."
        assert message in win.status.text()
        win.start_export()
        wait(app, win)
        assert message in win.s_fini_texte.text()
    finally:
        win.close()
