"""Décalage de couleur VHS : un glissement de synthèse est annulé.
L'alignement se mesure sur le plan de chrominance (PSNR), pas seulement sur le filtre."""
import re
import subprocess
import dataclasses

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for


def u_psnr(ffmpeg, path, reference):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-i", str(reference), "-lavfi",
                        "[0:v]extractplanes=u[a];[1:v]extractplanes=u[b];[a][b]psnr",
                        "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"average:([\d.]+|inf)", r.stderr)
    assert m, r.stderr[-400:]
    return 99.0 if m[-1] == "inf" else float(m[-1])


def test_shift_cancelled_edges_realign(tools, tmp_path):
    ref = tmp_path / "net.mkv"
    ff("-f", "lavfi", "-i", "color=c=0x808080:s=320x240,drawbox=x=80:y=40:w=40:h=160:color=red@1:t=fill",
       "-frames:v", "5", "-c:v", "ffv1", str(ref))
    bad = tmp_path / "decale.mkv"
    ff("-i", str(ref), "-vf", "chromashift=cbh=4:crh=4", "-c:v", "ffv1", str(bad))
    info = analyze(bad, tools)
    bare = dataclasses.replace(profile_for("fidele", "video"), denoise=None)
    plain = pipeline.Settings(bare, restore_audio=False, preset="ultrafast", scan="progressive")
    assert pipeline.filter_chain(info, plain).count("chromashift") == 0
    out = pipeline.export(info, dataclasses.replace(plain, chroma_shift=-4), tmp_path / "o.mp4", tools)
    assert u_psnr(tools.ffmpeg.path, bad, ref) < 40          # le décalage se voit
    assert u_psnr(tools.ffmpeg.path, out, ref) > 50          # la correction le retire
    d = subprocess.run([tools.ffprobe.path, "-v", "error", "-select_streams", "v", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(out)],
                       capture_output=True, text=True, check=True).stdout.strip()
    assert d == "320,240"
