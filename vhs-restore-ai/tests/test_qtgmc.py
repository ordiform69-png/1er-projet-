"""QTGMC via VapourSynth. Les tests « réels » demandent vspipe + plugins
(requirements-qtgmc.txt) ; sinon ils sont ignorés. Pointer VHSRA_VSPIPE vers vspipe au besoin."""
import dataclasses
import os
import stat
import sys
import threading
import time

import pytest

from conftest import probe_json
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import PROFILES
from vhs_restore.tools import Cancelled, Tool, ToolError, explain_vs_error



def S(key="equilibre", **kw):
    kw.setdefault("deinterlacer", "qtgmc")
    return pipeline.Settings(PROFILES[key], **kw)


@pytest.fixture(scope="module")
def pal(samples, tools):
    return analyze(samples["pal_tff"], tools)


@pytest.fixture()
def qtools(tools):
    if not tools.qtgmc_available:
        pytest.skip("QTGMC non installé : " + (tools.vspipe.problem or "vspipe introuvable"))
    return tools


def _streams(path):
    d = probe_json(path)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    return d, v, [s for s in d["streams"] if s["codec_type"] == "audio"]


# ------------------------------------------------------------ sans VapourSynth
def test_chain_and_command(pal, tools):
    ok = dataclasses.replace(tools, vspipe=Tool("QTGMC", "/x/vspipe", "R82"))
    chain = pipeline.filter_chain(pal, S())
    assert "bwdif" not in chain and chain.startswith("removegrain")
    args, vs, vmap, amap = pipeline.source_inputs(pal, S(), ok, start=2.0, duration=3.0)
    assert vs[0] == "/x/vspipe" and "-c" in vs and vs[-1] == "-"
    assert f"src={pal.path}" in vs and "tff=1" in vs and "first=50" in vs and "count=75" in vs
    assert args[args.index("-f") + 1] == "yuv4mpegpipe" and (vmap, amap) == ("0:v:0", "1:a:0?")
    assert pipeline.source_inputs(pal, S(scan="bff"), ok, None, None)[1][6] == "tff=0"


def test_progressive_or_bwdif_does_not_use_vapoursynth(pal, tools):
    assert pipeline.source_inputs(pal, S(scan="progressive"), tools, None, None)[1] is None
    assert pipeline.source_inputs(pal, S(deinterlacer="bwdif"), tools, None, None)[1] is None
    assert "bwdif" in pipeline.filter_chain(pal, S(deinterlacer="bwdif"))


def test_missing_qtgmc_is_explicit(pal, tools, tmp_path):
    t = dataclasses.replace(tools, vspipe=Tool("QTGMC"))
    with pytest.raises(ToolError, match="QTGMC"):
        pipeline.export(pal, S(), tmp_path / "x.mp4", t)
    assert list(tmp_path.iterdir()) == []


def test_explain_vs_error():
    assert "mvu" in explain_vs_error("AttributeError: No attribute with the name mvu exists.")
    assert "vsdeinterlace" in explain_vs_error("ModuleNotFoundError: No module named 'vsdeinterlace'")
    assert explain_vs_error("ligne 1\nderniere ligne") == "derniere ligne"


@pytest.mark.skipif(os.name == "nt", reason="faux exécutable POSIX")
def test_failing_vspipe_reports_cause(pal, tools, tmp_path):
    fake = tmp_path / "vspipe"
    fake.write_text(f"#!{sys.executable}\nimport sys\n"
                    "sys.stderr.write('AttributeError: No attribute with the name mvu exists.\\n')\nsys.exit(1)\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    t = dataclasses.replace(tools, vspipe=Tool("QTGMC", str(fake), "fake"))
    out = tmp_path / "sortie"
    out.mkdir()
    with pytest.raises(ToolError, match="plugin VapourSynth manquant"):
        pipeline.export(pal, S(), out / "x.mp4", t)
    assert list(out.iterdir()) == []


# ------------------------------------------------------------ vrai QTGMC
def test_real_qtgmc_export(pal, qtools, tmp_path):
    out = pipeline.export(pal, S(resolution="1080"), tmp_path / "q.mp4", qtools)
    d, v, a = _streams(out)
    assert (v["width"], v["height"], v["display_aspect_ratio"]) == (1440, 1080, "4:3")
    assert v["avg_frame_rate"] == "50/1" and 200 <= int(v["nb_read_frames"]) <= 202
    assert a and abs(float(a[0]["duration"]) - float(v["duration"])) < 0.1


def test_real_qtgmc_excerpt_matches_bwdif_timing(pal, qtools, tmp_path):
    q = pipeline.export(pal, S(), tmp_path / "q.mp4", qtools, start=1.0, duration=2.0)
    _, v, a = _streams(q)
    assert int(v["nb_read_frames"]) == 100 and v["display_aspect_ratio"] == "4:3"
    assert abs(float(v["duration"]) - 2.0) < 0.05 and abs(float(a[0]["duration"]) - 2.0) < 0.1


def test_real_qtgmc_preview(pal, qtools, tmp_path):
    r = pipeline.make_preview(pal, S(), qtools, tmp_path / "ap", start=0.5, duration=2)
    _, v, _ = _streams(r.compare)
    assert (v["width"], v["height"]) == (1440, 540) and len(r.stills) == 3


def test_real_qtgmc_cancel(samples, qtools, tmp_path):
    import dataclasses as dc
    info = dc.replace(analyze(samples["long"], qtools), scan="tff")  # forcé : source progressive
    cancel = threading.Event()
    threading.Timer(3, cancel.set).start()
    t0 = time.time()
    with pytest.raises(Cancelled):
        pipeline.export(info, S(), tmp_path / "c.mp4", qtools, cancel=cancel)
    assert time.time() - t0 < 15 and list(tmp_path.iterdir()) == []


def test_real_qtgmc_with_ai(pal, qtools, fake_ai, tmp_path, monkeypatch):
    t = dataclasses.replace(fake_ai, vspipe=qtools.vspipe)
    work, out = tmp_path / "travail", tmp_path / "sortie"
    work.mkdir()
    out.mkdir()
    monkeypatch.setenv("VHSRA_TMP", str(work))
    res = pipeline.export(pal, S("maximum", use_ai=True), out / "qa.mp4", t, start=0, duration=1)
    _, v, a = _streams(res)
    assert (v["width"], v["height"]) == (1440, 1080) and int(v["nb_read_frames"]) == 50 and a
    assert list(work.iterdir()) == []                       # temporaires supprimés


def test_real_qtgmc_with_stabilization(pal, qtools, tmp_path, monkeypatch):
    if not qtools.stab_available:
        pytest.skip("FFmpeg sans libvidstab")
    work, out = tmp_path / "travail", tmp_path / "sortie"
    work.mkdir()
    out.mkdir()
    monkeypatch.setenv("VHSRA_TMP", str(work))
    res = pipeline.export(pal, S(stabilize=True), out / "qs.mp4", qtools, start=1, duration=2)
    _, v, a = _streams(res)
    assert int(v["nb_read_frames"]) == 100 and v["display_aspect_ratio"] == "4:3" and a
    assert list(work.iterdir()) == []
