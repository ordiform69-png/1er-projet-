"""Bords abîmés : bandes noires, même taille d'image et même 4:3.
Vidéo : gauche et droite. Pellicule : cadre des quatre côtés. Rien par défaut."""
import dataclasses
import json
import re
import subprocess

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for


def plain(source):
    bare = dataclasses.replace(profile_for("fidele", source), denoise=None)
    return pipeline.Settings(bare, source=source, restore_audio=False,
                             preset="ultrafast", scan="progressive")


def yavg(ffmpeg, path, crop):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-vf",
                        f"crop={crop},signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                        "-frames:v", "2", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    vals = [float(x) for x in re.findall(r"signalstats\.YAVG=([\d.]+)", r.stderr)]
    assert vals, r.stderr[-400:]
    return vals[-1]


def geom(ffprobe, path):
    r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v", "-show_entries",
                        "stream=width,height,display_aspect_ratio,sample_aspect_ratio",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["streams"][0]


def test_edges_black_same_size_and_dar(tools, tmp_path):
    video = tmp_path / "cassette.mkv"
    ff("-f", "lavfi", "-i", "color=c=0x808080:s=720x576:r=25,setsar=16/15",
       "-t", "0.5", "-c:v", "ffv1", str(video))
    film = tmp_path / "pellicule.mkv"
    ff("-f", "lavfi", "-i", "color=c=0x808080:s=720x540:r=18",
       "-t", "0.5", "-c:v", "ffv1", str(film))
    info_v, info_f = analyze(video, tools), analyze(film, tools)
    sv, sf = plain("video"), plain("film")

    assert "pad=" not in pipeline.filter_chain(info_v, sv)
    assert "pad=" not in pipeline.filter_chain(info_f, sf)
    assert "crop=688:576:16:0,pad=720:576:16:0:black" in pipeline.filter_chain(
        info_v, dataclasses.replace(sv, mask_sides=16))
    assert "crop=688:508:16:16,pad=720:540:16:16:black" in pipeline.filter_chain(
        info_f, dataclasses.replace(sf, mask_sides=16))

    out_v = pipeline.export(info_v, dataclasses.replace(sv, mask_sides=16), tmp_path / "v.mp4", tools)
    out_f = pipeline.export(info_f, dataclasses.replace(sf, mask_sides=16), tmp_path / "f.mp4", tools)
    bare_v = pipeline.export(info_v, sv, tmp_path / "v0.mp4", tools)

    gv, gf = geom(tools.ffprobe.path, out_v), geom(tools.ffprobe.path, out_f)
    assert (gv["width"], gv["height"], gv["display_aspect_ratio"]) == (720, 576, "4:3")
    assert gv["sample_aspect_ratio"] == "16:15"
    assert (gf["width"], gf["height"], gf["display_aspect_ratio"]) == (720, 540, "4:3")

    ffmpeg = tools.ffmpeg.path
    assert yavg(ffmpeg, bare_v, "8:576:0:0") > 80          # sans masque, le bord n'est pas noir
    assert yavg(ffmpeg, out_v, "8:576:0:0") < 25           # gauche
    assert yavg(ffmpeg, out_v, "8:576:712:0") < 25         # droite
    assert yavg(ffmpeg, out_v, "64:64:328:256") > 80       # le centre reste l'image
    assert yavg(ffmpeg, out_f, "8:540:0:0") < 25           # cadre gauche
    assert yavg(ffmpeg, out_f, "720:8:0:0") < 25           # cadre haut
    assert yavg(ffmpeg, out_f, "720:8:0:532") < 25         # cadre bas
    assert yavg(ffmpeg, out_f, "64:64:328:238") > 80
