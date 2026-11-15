"""Noirs gris et blancs ternes : conseil seulement si la plage est écrasée,
correction fixe mesurée dans le fichier exporté. Un film déjà ouvert n'est pas conseillé."""
import dataclasses
import re
import subprocess

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.advice import advise, apply
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for


def y_range(ffmpeg, path):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-vf",
                        "signalstats,metadata=print:key=lavfi.signalstats.YLOW,"
                        "metadata=print:key=lavfi.signalstats.YHIGH",
                        "-frames:v", "8", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    def med(key):
        vals = sorted(float(x) for x in re.findall(rf"signalstats\.{key}=([\d.]+)", r.stderr))
        assert vals, key
        return vals[len(vals) // 2]
    return med("YLOW"), med("YHIGH")


def test_crushed_levels_are_opened_correct_film_untouched(tools, tmp_path):
    normal = tmp_path / "normal.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-t", "1", "-c:v", "ffv1", str(normal))
    crush = tmp_path / "ecrase.mkv"
    # 0–255 ramené vers 40–180 : noirs gris, blancs ternes
    ff("-i", str(normal), "-vf", "lutyuv=y='clip(40+val*(180-40)/255,0,255)'",
       "-c:v", "ffv1", str(crush))
    good, bad = analyze(normal, tools), analyze(crush, tools)
    assert not any(a.key == "levels" for a in advise(good))
    tips = advise(bad)
    assert [a.key for a in tips if a.key == "levels"] == ["levels"]
    bare = dataclasses.replace(profile_for("fidele", "video"), denoise=None)
    plain = pipeline.Settings(bare, restore_audio=False, preset="ultrafast", scan="progressive")
    assert "colorlevels=" not in pipeline.filter_chain(bad, plain)
    out = pipeline.export(bad, apply(plain, tips), tmp_path / "o.mp4", tools)
    lo0, hi0 = y_range(tools.ffmpeg.path, crush)
    lo1, hi1 = y_range(tools.ffmpeg.path, out)
    assert lo1 < lo0 - 10 and hi1 > hi0 + 20          # noirs plus bas, blancs plus hauts
    assert "colorlevels=" in pipeline.filter_chain(bad, apply(plain, tips))
