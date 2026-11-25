"""Plafonds de fidélité des conseils d'image. Cas réel (VHS de 1988, très verte, niveaux
84-163) : sans limite, la correction faisait virer l'image au magenta, noirs bouchés."""
import json
import re
import shutil
import subprocess

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.advice import advise, apply
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for


def test_caps():
    assert pipeline.safe_gains((1.56, 0.84, 0.85)) == (1.18, 0.85, 0.85)
    lo, hi = pipeline.safe_levels(84 / 255, 163 / 255)
    assert abs(1 / (hi - lo) - pipeline.MAX_CONTRAST) < 1e-6        # contraste x1,6 au plus
    assert pipeline.safe_levels(0.1, 0.9) == (0.1, 0.9)               # plage déjà large : inchangée


def rgb_means(path):
    t = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(path), "-vf",
                        "format=rgb24,extractplanes=r+g+b[r][g][b];[r]signalstats,metadata=print:key=lavfi.signalstats.YAVG[r2];"
                        "[g]signalstats,metadata=print:key=lavfi.signalstats.YAVG[g2];"
                        "[b]signalstats,metadata=print:key=lavfi.signalstats.YAVG[b2];[r2][g2][b2]hstack=3",
                        "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True).stderr
    vals = [float(v) for v in re.findall(r"YAVG=([\d.]+)", t)[:3]]
    return vals


def test_green_flat_vhs_is_not_overcorrected(tools, tmp_path):
    src = tmp_path / "vhs verte et terne.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25,colorchannelmixer=rr=0.3:gg=0.95:bb=0.85,"
       "colorlevels=romin=0.33:gomin=0.33:bomin=0.33:romax=0.64:gomax=0.64:bomax=0.64,setsar=16/15",
       "-t", "1", "-c:v", "ffv1", str(src))
    info = analyze(src, tools)
    tips = advise(info)
    assert {a.key for a in tips} >= {"cast"}
    s = apply(pipeline.Settings(profile_for("fidele", "video"), source="video", scan="progressive"), tips)
    out = pipeline.export(info, s, tmp_path / "o.mp4", tools)
    r0, g0, _ = rgb_means(src)
    r1, g1, _ = rgb_means(out)
    assert g0 - r0 > 20                       # très vert au départ
    # atténué, jamais inversé (pas de magenta). La balance ramène les moyennes au même niveau :
    # à 1/255 près, l'écart restant n'est que du bruit d'arrondi (avant les niveaux à moitié :
    # +0,03 ; après : −0,4, image grise). Un vrai virage au magenta se mesure en dizaines.
    assert -1 < g1 - r1 < g0 - r0
