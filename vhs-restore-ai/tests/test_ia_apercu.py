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
