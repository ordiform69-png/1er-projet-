"""Changements de scène : détection FFmpeg, sans modèle, rien n'est coupé."""
import pytest

from conftest import ff
from vhs_restore import scenes

pytestmark = pytest.mark.assistant


def test_phrase_en_mots():
    assert scenes.phrase(0) == "0 secondes"
    assert scenes.phrase(1) == "1 seconde"
    assert scenes.phrase(45) == "45 secondes"
    assert scenes.phrase(60) == "1 min"
    assert scenes.phrase(80) == "1 min 20"
    assert scenes.phrase(3661) == "1 h 01"


def test_regrouper_ignore_le_bord_et_plafonne():
    assert scenes.regrouper([0.1, 3.0, 3.4, 9.0], duree=10) == [3.0, 9.0]
    beaucoup = [float(i) for i in range(2, 40, 2)]
    assert len(scenes.regrouper(beaucoup, maximum=8)) == 8
    assert scenes.regrouper(beaucoup, maximum=8)[0] == 2.0


def test_detecte_deux_changements(tools, tmp_path):
    f = tmp_path / "trois.mp4"
    ff("-f", "lavfi", "-i", "color=c=red:s=160x120:r=25:d=3",
       "-f", "lavfi", "-i", "color=c=blue:s=160x120:r=25:d=3",
       "-f", "lavfi", "-i", "testsrc2=s=160x120:r=25:d=3",
       "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p",
       "-c:v", "libx264", "-crf", "18", str(f))
    moments = scenes.detecter(tools.ffmpeg.path, f, 9.0)
    assert len(moments) == 2, moments
    assert abs(moments[0] - 3) <= 0.5 and abs(moments[1] - 6) <= 0.5
