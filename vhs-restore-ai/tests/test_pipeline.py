import hashlib
import threading
import time
from fractions import Fraction

import pytest

from conftest import probe_json
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import PROFILES
from vhs_restore.tools import Cancelled, ToolError, detect_tools


@pytest.fixture(scope="module")
def pal(samples, tools):
    return analyze(samples["pal_tff"], tools)


def S(key="equilibre", **kw):
    return pipeline.Settings(PROFILES[key], **kw)


def _vstream(path):
    d = probe_json(path)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = [s for s in d["streams"] if s["codec_type"] == "audio"]
    return d, v, a


def test_filter_order(pal):
    chain = pipeline.filter_chain(pal, S("maximum", resolution="1080"))
    names = [f.split("=")[0] for f in chain.split(",")]
    assert names == ["bwdif", "removegrain", "hqdn3d", "eq", "scale", "cas", "setsar", "format"]
    assert "parity=tff" in chain and "send_field" in chain


def test_fidele_is_light(pal):
    chain = pipeline.filter_chain(pal, S("fidele"))
    assert "eq=" not in chain and "cas" not in chain and "scale" not in chain
    assert chain.startswith("bwdif")


def test_no_deinterlace_unless_known(pal):
    import dataclasses
    unknown = dataclasses.replace(pal, scan="unknown")
    assert "bwdif" not in pipeline.filter_chain(unknown, S())
    assert "bwdif" in pipeline.filter_chain(unknown, S(scan="bff"))
    assert "bwdif" not in pipeline.filter_chain(pal, S(scan="progressive"))
    assert pipeline.output_fps(pal, S()) == 50
    assert pipeline.output_fps(pal, S(scan="progressive")) == 25


def test_sizes_and_rules(pal):
    assert pipeline.target_size(pal, S()) == (720, 576, Fraction(16, 15))
    assert pipeline.target_size(pal, S(resolution="1080")) == (1440, 1080, 1)
    assert pipeline.target_size(pal, S(resolution="2160", use_ai=True)) == (2880, 2160, 1)
    assert pipeline.target_size(pal, S(dar=Fraction(16, 9), resolution="1080"))[0] == 1920
    with pytest.raises(ToolError):
        pipeline.target_size(pal, S(resolution="2160"))
    assert "cas" not in pipeline.filter_chain(pal, S("maximum", use_ai=True))
    assert pipeline.effective_resolution(S(use_ai=True)) == "1080"


def test_export_fullhd(pal, tools, tmp_path):
    src_hash = hashlib.sha256(pal.path.read_bytes()).hexdigest()
    s = S(resolution="1080")
    out = pipeline.export(pal, s, pipeline.unique_output_path(pal, s, tmp_path), tools)
    d, v, a = _vstream(out)
    assert (v["width"], v["height"]) == (1440, 1080)
    assert v["display_aspect_ratio"] == "4:3"
    assert v["avg_frame_rate"] == "50/1"
    # 4 s x 50 images (une par trame). L'AVI MPEG-2 de test démarre sa vidéo à 0,04 s :
    # FFmpeg duplique 1 image source au début pour rester calé sur le son (=> 202).
    assert 200 <= int(v["nb_read_frames"]) <= 202
    assert a and abs(float(d["format"]["duration"]) - 4.0) < 0.15
    assert abs(float(a[0]["duration"]) - float(v["duration"])) < 0.1
    assert hashlib.sha256(pal.path.read_bytes()).hexdigest() == src_hash  # original intact
    assert not list(tmp_path.glob("*.partiel.mp4"))


def test_export_source_resolution_keeps_43(pal, tools, tmp_path):
    out = pipeline.export(pal, S("fidele"), tmp_path / "o.mp4", tools)
    _, v, _ = _vstream(out)
    assert (v["width"], v["height"]) == (720, 576)
    assert v["sample_aspect_ratio"] == "16:15" and v["display_aspect_ratio"] == "4:3"


def test_progressive_without_audio(samples, tools, tmp_path):
    i = analyze(samples["prog"], tools)
    out = pipeline.export(i, S(), tmp_path / "p.mp4", tools)
    d, v, a = _vstream(out)
    assert not a and v["avg_frame_rate"] == "30000/1001"


def test_unique_name_never_overwrites(pal, tmp_path):
    s = S()
    first = pipeline.unique_output_path(pal, s, tmp_path)
    first.write_bytes(b"x")
    second = pipeline.unique_output_path(pal, s, tmp_path)
    assert second != first and "(2)" in second.name
    with pytest.raises(ToolError):
        pipeline.export(pal, s, pal.path, detect_tools())


def test_bad_output_dir(pal, tools, tmp_path):
    with pytest.raises(ToolError):
        pipeline.export(pal, S(), tmp_path / "absent" / "o.mp4", tools)


def test_cancel_cleans_up(samples, tools, tmp_path):
    i = analyze(samples["long"], tools)
    cancel = threading.Event()
    threading.Timer(1.5, cancel.set).start()
    t0 = time.time()
    with pytest.raises(Cancelled):
        pipeline.export(i, S("maximum"), tmp_path / "c.mp4", tools, cancel=cancel)
    assert time.time() - t0 < 10
    assert list(tmp_path.iterdir()) == []


def test_progress_reported(pal, tools, tmp_path):
    seen = []
    pipeline.export(pal, S(), tmp_path / "g.mp4", tools, progress=lambda f, m: seen.append(f))
    assert seen and seen[-1] == 1.0 and all(0 <= f <= 1 for f in seen)


def test_preview(pal, tools, tmp_path):
    r = pipeline.make_preview(pal, S(), tools, tmp_path / "apercu", start=1, duration=2)
    assert len(r.stills) == 3 and all(p.is_file() for p in r.stills)
    _, v, a = _vstream(r.compare)
    assert (v["width"], v["height"]) == (1440, 540)   # 2 x 720 (540 lignes en 4:3)
    assert a
    assert abs(float(v["duration"]) - 2.0) < 0.15


def test_ai_path_with_fake_engine(pal, fake_ai, tmp_path, monkeypatch):
    work = tmp_path / "travail"
    work.mkdir()
    monkeypatch.setenv("VHSRA_TMP", str(work))
    monkeypatch.setattr(pipeline, "AI_CHUNK_FRAMES", 37)   # plusieurs paquets, dernier incomplet
    seen = []
    out = pipeline.export(pal, S("maximum", use_ai=True), tmp_path / "ia.mp4", fake_ai,
                          progress=lambda f, m: seen.append(m), start=0.5, duration=2)
    d, v, a = _vstream(out)
    assert (v["width"], v["height"]) == (1440, 1080) and v["display_aspect_ratio"] == "4:3"
    assert int(v["nb_read_frames"]) == 100 and v["avg_frame_rate"] == "50/1"
    assert a and abs(float(a[0]["duration"]) - float(v["duration"])) < 0.1
    assert any("IA" in m for m in seen)
    assert list(work.iterdir()) == []                      # temporaires supprimés


def test_ai_missing_engine(pal, tools, tmp_path):
    import dataclasses
    from vhs_restore.tools import Tool
    t = dataclasses.replace(tools, realesrgan=Tool("Real-ESRGAN"))
    with pytest.raises(ToolError, match="Real-ESRGAN"):
        pipeline.export(pal, S(use_ai=True), tmp_path / "x.mp4", t)
    assert list(tmp_path.iterdir()) == []


def test_preview_aligned_when_video_starts_after_audio(tools, tmp_path):
    """Cas réel (MPEG de graveur DVD) : l'image commence ~0,9 s après le son. Les deux
    moitiés de l'aperçu doivent montrer le même instant (réglage quasi neutre -> PSNR élevé)."""
    import re
    import shutil
    import subprocess
    from vhs_restore.profiles import profile_for
    src = tmp_path / "graveur dvd.mpg"
    subprocess.run([shutil.which("ffmpeg"), "-loglevel", "error", "-itsoffset", "0.9", "-f", "lavfi", "-i",
                    "testsrc2=size=352x240:rate=30000/1001", "-f", "lavfi", "-i", "sine=sample_rate=48000",
                    "-t", "12", "-map", "0:v", "-map", "1:a", "-c:v", "mpeg2video", "-g", "15", "-bf", "2",
                    "-b:v", "4M", "-c:a", "mp2", "-f", "dvd", str(src)], check=True)
    info = analyze(src, tools)
    s = pipeline.Settings(profile_for("fidele", "film"), source="film", scan="progressive")
    r = pipeline.make_preview(info, s, tools, tmp_path / "ap", start=4, duration=4)
    out = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(r.compare), "-lavfi",
                          "[0:v]split[a][b];[a]crop=iw/2:ih:0:0[l];[b]crop=iw/2:ih:iw/2:0[r];[l][r]psnr",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    assert float(re.findall(r"average:([\d.]+)", out)[-1]) > 30


def test_exports_concurrents_et_temoins(pal, tools, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    dst = tmp_path / "famille.mp4"
    temoins = [dst.with_suffix(".wav"), tmp_path / "famille.partiel.mp4"]
    for path in temoins:
        path.write_bytes(b"archive")
    s = replace(S(), audio_copy="wav")
    with ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(pipeline.export, pal, s, dst, tools, duration=0.5) for _ in range(2)]
        films = {job.result() for job in jobs}
    assert len(films) == 2
    assert all(p.is_file() and p.with_suffix(".wav").is_file() for p in films)
    assert all(p.read_bytes() == b"archive" for p in temoins)


def test_vitesse_ia_mesuree_avant_choix(pal, tools, tmp_path, monkeypatch):
    from dataclasses import replace
    import threading
    horloge = [0.0]
    class Moteur:
        def __init__(self, outil):
            pass
        def upscale_dir(self, src, dst, cancel):
            horloge[0] += 4 + 30 * len(list(src.glob("*.png")))
    monkeypatch.setattr(pipeline, "RealEsrganUpscaler", Moteur)
    from types import SimpleNamespace
    monkeypatch.setattr(pipeline, "time", SimpleNamespace(monotonic=lambda: horloge[0]))
    estimations = []
    def choisir(secondes, en_4k, inconnue):
        estimations.append(secondes)
        return "sans"
    s = replace(S(), use_ai=True)
    choix = pipeline.essayer_ia(pal, s, tools, 10, choisir, threading.Event(), None)
    assert s.use_ai and not choix.use_ai
    attendu = 10 * float(pipeline.output_fps(pal, s)) * 30
    assert abs(estimations[0] / attendu - 1) < 0.2
