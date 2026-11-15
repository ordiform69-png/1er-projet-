"""Poussières et rayures (Analog Repair, facultatif) : le risque principal est d'effacer
un objet réel qui bouge vite (il n'est présent qu'une image à chaque endroit, comme
une poussière). Film de synthèse : grain, balle rapide (30 px/image), grand objet lent,
poussières d'une seule image. Comparaison image par image avec le même film sans poussière."""
import dataclasses
import shutil
import subprocess
import threading

import pytest

from conftest import ff, probe_json
from vhs_restore import dust, pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for
from vhs_restore.tools import Cancelled, ToolError

np = pytest.importorskip("numpy")
pytestmark = pytest.mark.skipif(not dust.available(), reason="module poussières non installé")

W, H, N = 720, 540, 54                          # 3 s à 18 i/s
SPECKS = [(10, 100, 100), (20, 400, 330), (30, 600, 120), (40, 250, 450), (25, 520, 470)]  # (image, x, y)
BALL_Y, BIG_Y, DARK_Y = 200, 300, 60


def ball_x(n):
    return (40 + n * 30) % 640


def dark_x(n):
    return (600 - n * 35) % 640


@pytest.fixture(scope="module")
def films(tmp_path_factory):
    d = tmp_path_factory.mktemp("poussières en mouvement")
    clean = d / "propre.mkv"
    ff("-filter_complex",
       f"color=c=0x8090a0:s={W}x{H}:r=18[bg];color=c=white:s=24x24:r=18[ball];"
       f"color=c=0x503020:s=90x150:r=18[big];color=c=black:s=18x18:r=18[dark];"
       f"[bg][big]overlay=x='100+n*4':y={BIG_Y}[t];[t][ball]overlay=x='mod(40+n*30,640)':y={BALL_Y}[u];"
       f"[u][dark]overlay=x='mod(600-n*35+6400,640)':y={DARK_Y},format=yuv420p,noise=c0s=10:allf=t[v]",
       "-map", "[v]", "-frames:v", str(N), "-c:v", "ffv1", str(clean))
    boxes = ",".join(f"drawbox=x={x}:y={y}:w=7:h=7:color=black:t=fill:enable='eq(n\\,{n})'"
                     for n, x, y in SPECKS)
    dusty = d / "poussiéreux.mkv"
    ff("-i", str(clean), "-vf", boxes, "-c:v", "ffv1", str(dusty))
    return clean, dusty


def gray(path):
    raw = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(path), "-vf",
                          f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(float)


def test_dust_removed_motion_kept(films, tools, tmp_path):
    clean, dusty = films
    info = analyze(dusty, tools)
    assert info.suggested_source == "film"
    s = pipeline.Settings(profile_for("fidele", "film"), source="film", dust=True, crf=10)
    out = pipeline.export(info, s, tmp_path / "o.mp4", tools)
    ref, src, res = gray(clean), gray(dusty), gray(out)
    assert len(res) == N

    def err(frames, n, x, y, w, h):
        return float(np.abs(frames[n, y:y + h, x:x + w] - ref[n, y:y + h, x:x + w]).mean())
    before = [err(src, n, x, y, 7, 7) for n, x, y in SPECKS]
    after = [err(res, n, x, y, 7, 7) for n, x, y in SPECKS]
    ball = [err(res, n, ball_x(n) + 4, BALL_Y + 4, 16, 16) for n in range(2, N - 2)]
    big = [err(res, n, 110 + n * 4, BIG_Y + 10, 60, 120) for n in range(2, N - 2)]
    dark = [err(res, n, dark_x(n) + 3, DARK_Y + 3, 12, 12) for n in range(2, N - 2)]
    print(f"\nécart avec le film propre : poussières {np.mean(before):.0f} -> {np.mean(after):.0f} ; "
          f"balle claire rapide {np.mean(ball):.1f} (max {max(ball):.1f}) ; balle sombre rapide "
          f"{np.mean(dark):.1f} (max {max(dark):.1f}) ; grand objet {np.mean(big):.1f}")
    assert np.mean(after) < 0.3 * np.mean(before)           # poussières très atténuées
    assert max(ball) < 25 and max(dark) < 25 and np.mean(big) < 10   # objets en mouvement intacts


def test_pipeline_integration(films, tools, tmp_path):
    clean, dusty = films
    info = analyze(dusty, tools)
    s = pipeline.Settings(profile_for("equilibre", "film"), source="film", dust=True,
                          resolution="1080")
    assert "_poussieres" in pipeline.unique_output_path(info, s, tmp_path).name
    r = pipeline.make_preview(info, s, tools, tmp_path / "ap", start=0.5, duration=2)
    d = probe_json(r.restored)
    v = next(x for x in d["streams"] if x["codec_type"] == "video")
    assert (v["width"], v["height"], v["display_aspect_ratio"]) == (1440, 1080, "4:3")
    assert v["avg_frame_rate"] == "18/1" and int(v["nb_read_frames"]) == 36
    with pytest.raises(ToolError, match="pellicules"):
        pipeline.export(info, dataclasses.replace(s, source="video"), tmp_path / "x.mp4", tools)
    with pytest.raises(ToolError, match="pas installé"):
        pipeline.export(info, s, tmp_path / "y.mp4", dataclasses.replace(tools, dust=False))


def test_keeps_sar_and_sound(samples, tools, tmp_path):
    """Analog Repair perd le rapport de pixel ; notre chaîne le rétablit."""
    src = tmp_path / "pellicule pixels 16-15.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=18,setsar=16/15", "-f", "lavfi", "-i",
       "sine=sample_rate=48000", "-t", "3", "-c:v", "ffv1", "-c:a", "flac", str(src))
    info = analyze(src, tools)
    out = pipeline.export(info, pipeline.Settings(profile_for("fidele", "film"), source="film", dust=True),
                          tmp_path / "o.mp4", tools)
    d = probe_json(out)
    v = next(x for x in d["streams"] if x["codec_type"] == "video")
    a = [x for x in d["streams"] if x["codec_type"] == "audio"]
    assert v["display_aspect_ratio"] == "4:3" and v["sample_aspect_ratio"] == "16:15"
    assert a and abs(float(a[0]["duration"]) - float(v["duration"])) < 0.15


def test_cancel(samples, tools, tmp_path, monkeypatch):
    work = tmp_path / "travail"
    work.mkdir()
    monkeypatch.setenv("VHSRA_TMP", str(work))
    info = analyze(samples["long"], tools)
    c = threading.Event()
    threading.Timer(2.0, c.set).start()
    with pytest.raises(Cancelled):
        pipeline.export(info, pipeline.Settings(profile_for("fidele", "film"), source="film", dust=True),
                        tmp_path / "c.mp4", tools, cancel=c)
    assert list(work.iterdir()) == [] and not list(tmp_path.glob("*.mp4"))
