"""DVD VIDEO_TS : plusieurs VOB d'un titre = un seul film. Menus ignorés."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ff, probe_json
from vhs_restore import dvd, pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for
from vhs_restore.tools import ToolError


def test_grouping_ignores_menus(tmp_path):
    d = tmp_path / "VIDEO_TS"
    d.mkdir()
    for name in ("VIDEO_TS.VOB", "VTS_01_0.VOB", "VTS_01_2.VOB", "VTS_01_1.VOB", "VTS_02_1.VOB", "film.mp4"):
        (d / name).write_bytes(b"x")
    titles = dvd.titles_in(d)
    assert [[p.name for p in t] for t in titles] == [["VTS_01_1.VOB", "VTS_01_2.VOB"], ["VTS_02_1.VOB"]]
    assert [p.name for p in dvd.parts_for(d / "VTS_01_2.VOB")] == ["VTS_01_1.VOB", "VTS_01_2.VOB"]
    assert dvd.parts_for(d / "film.mp4") == [d / "film.mp4"]
    with pytest.raises(ToolError, match="menu"):
        dvd.open_media(d / "VTS_01_0.VOB", None)


@pytest.fixture(scope="module")
def video_ts(tmp_path_factory):
    """Un film de 6 s coupé en 3 VOB, plus un menu et un second titre."""
    root = tmp_path_factory.mktemp("dvd")
    full = root / "entier.mpg"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25,setsar=16/15",
       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
       "-t", "6", "-c:v", "mpeg2video", "-g", "12", "-bf", "2", "-b:v", "2M",
       "-c:a", "mp2", "-f", "dvd", str(full))
    d = root / "VIDEO_TS"
    d.mkdir()
    ff("-i", str(full), "-c", "copy", "-f", "segment", "-segment_time", "2",
       "-reset_timestamps", "1", str(d / "piece%d.vob"))
    pieces = sorted(d.glob("piece*.vob"))
    assert len(pieces) >= 2
    for i, p in enumerate(pieces, start=1):
        p.rename(d / f"VTS_01_{i}.VOB")
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25", "-f", "lavfi", "-i", "sine=frequency=880",
       "-t", "1", "-c:v", "mpeg2video", "-c:a", "mp2", "-f", "dvd", str(d / "VTS_01_0.VOB"))
    ff("-f", "lavfi", "-i", "color=c=black:s=720x576:r=25", "-f", "lavfi", "-i", "sine=frequency=100",
       "-t", "1", "-c:v", "mpeg2video", "-c:a", "mp2", "-f", "dvd", str(d / "VIDEO_TS.VOB"))
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25", "-f", "lavfi", "-i", "sine=frequency=330",
       "-t", "2", "-c:v", "mpeg2video", "-c:a", "mp2", "-f", "dvd", str(d / "VTS_02_1.VOB"))
    return root, full


def _frames(path):
    v = next(s for s in probe_json(path)["streams"] if s["codec_type"] == "video")
    return int(v["nb_read_frames"]), float(v["duration"])


def _silence_gaps(path):
    err = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(path), "-af",
                          "silencedetect=n=-40dB:d=0.15", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return re.findall(r"silence_end: ([\d.]+)", err)


def test_one_film_per_title(video_ts, tools, tmp_path):
    root, full = video_ts
    d = root / "VIDEO_TS"
    before = sorted(p.name for p in d.iterdir())
    info = dvd.open_media(d / "VTS_01_2.VOB", tools)
    whole = analyze(full, tools)
    assert len(info.parts) == len(list(d.glob("VTS_01_[1-9].VOB")))
    assert info.output_stem == "VTS_01"
    assert abs(info.duration - whole.duration) < 0.25
    assert "menus" in info.warnings[0]
    s = pipeline.Settings(profile_for("fidele", "video"), source="video", scan="progressive",
                          preset="ultrafast", restore_audio=True)
    joined = pipeline.export(info, s, tmp_path / "titre.mp4", tools)
    single = pipeline.export(whole, s, tmp_path / "entier.mp4", tools)
    jf, jd = _frames(joined)
    sf, sd = _frames(single)
    assert abs(jf - sf) <= 2                      # pas de morceau répété ni sauté à la jonction
    assert abs(jd - sd) < 0.2
    assert _silence_gaps(joined) == []           # le son continu n'a pas de trou
    assert sorted(p.name for p in d.iterdir()) == before   # le DVD n'est pas modifié
    # aperçu : les deux moitiés restent le même instant (le cas du graveur DVD)
    prev = pipeline.make_preview(info, pipeline.Settings(profile_for("fidele", "film"), source="film",
                                                         scan="progressive"), tools,
                                 tmp_path / "ap", start=1.5, duration=2)
    err = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(prev.compare), "-lavfi",
                          "[0:v]split[a][b];[a]crop=iw/2:ih:0:0[l];[b]crop=iw/2:ih:iw/2:0[r];[l][r]psnr",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    assert float(re.findall(r"average:([\d.]+)", err)[-1]) > 30


def test_folder_one_output_per_title(video_ts, tools, tmp_path, monkeypatch):
    root, _full = video_ts
    src = tmp_path / "disque"
    shutil.copytree(root / "VIDEO_TS", src / "VIDEO_TS")   # comme un DVD : le film est dans VIDEO_TS
    fb = tmp_path / "sortie"
    monkeypatch.setenv("VHSRA_SORTIE", str(fb))
    real = pipeline.is_writable
    monkeypatch.setattr(pipeline, "is_writable", lambda folder: Path(folder) != src and "VIDEO_TS" not in
                        Path(folder).parts and real(folder))
    names_before = sorted(p.name for p in (src / "VIDEO_TS").iterdir())
    res = pipeline.restore_folder(src, tools, lambda info: pipeline.Settings(
        profile_for("fidele", "video"), source="video", scan="progressive", preset="ultrafast"))
    assert res.fallback and len(res.done) == 2 and not res.errors
    stems = sorted(p.name for p in res.done)
    assert any(n.startswith("VTS_01_restaure_") for n in stems)
    assert any(n.startswith("VTS_02_restaure_") for n in stems)
    assert sorted(p.name for p in (src / "VIDEO_TS").iterdir()) == names_before
