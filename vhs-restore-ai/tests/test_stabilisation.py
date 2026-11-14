"""Stabilisation vid.stab (2 passes). Mesure objective : différence moyenne entre
images successives d'une scène fixe filmée « en tremblant » (plus petite = plus stable)."""
import dataclasses
import re
import shutil
import subprocess
import threading
import time

import pytest

from conftest import probe_json
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import PROFILES
from vhs_restore.tools import Cancelled, ToolError


def S(key="fidele", **kw):
    return pipeline.Settings(PROFILES[key], **kw)


@pytest.fixture()
def stools(tools):
    if not tools.stab_available:
        pytest.skip("FFmpeg sans libvidstab")
    return tools


@pytest.fixture(scope="module")
def shaky(samples, tools):
    return dataclasses.replace(analyze(samples["shaky"], tools), scan="progressive")


def jitter(path) -> float:
    """Moyenne de la luminance de la différence entre images successives (zone centrale)."""
    r = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(path), "-vf",
                        "crop=iw*0.6:ih*0.6,tblend=all_mode=difference,signalstats,"
                        "metadata=print:key=lavfi.signalstats.YAVG", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    vals = [float(x) for x in re.findall(r"YAVG=([\d.]+)", r.stderr)]
    return sum(vals) / len(vals)


def test_filters_and_order(shaky, tools):
    chain = pipeline.filter_chain(shaky, S("equilibre", stabilize=True))
    names = [f.split("=")[0] for f in chain.split(",")]
    assert names[:3] == ["vidstabtransform", "removegrain", "hqdn3d"]
    assert "input=transforms.trf" in chain and "crop=black" in chain and "maxshift=29" in chain
    assert "smoothing=8" in chain                                     # 25p : ±0,3 s
    det = pipeline.stab_detect_filters(shaky, S(stabilize=True))
    assert det[-1].startswith("vidstabdetect=result=transforms.trf")
    pal_i = dataclasses.replace(shaky, scan="tff")
    t = pipeline.stab_transform_filter(pal_i, S(stabilize=True))
    assert "smoothing=15" in t                                        # 50p après désentrelacement
    assert pipeline.filter_chain(pal_i, S(stabilize=True)).startswith("bwdif")


def test_missing_vidstab_is_explicit(shaky, tools, tmp_path):
    t = dataclasses.replace(tools, vidstab=False)
    with pytest.raises(ToolError, match="libvidstab"):
        pipeline.export(shaky, S(stabilize=True), tmp_path / "x.mp4", t)
    assert list(tmp_path.iterdir()) == []


def test_stabilization_reduces_shake(shaky, stools, tmp_path, monkeypatch):
    work = tmp_path / "travail"
    work.mkdir()
    monkeypatch.setenv("VHSRA_TMP", str(work))
    ref = pipeline.export(shaky, S(), tmp_path / "ref.mp4", stools)
    seen = []
    stab = pipeline.export(shaky, S(stabilize=True), tmp_path / "stab.mp4", stools,
                           progress=lambda f, m: seen.append(m))
    j_ref, j_stab = jitter(ref), jitter(stab)
    print(f"tremblement moyen : sans {j_ref:.2f}, avec {j_stab:.2f}")
    assert j_stab < 0.6 * j_ref
    d = probe_json(stab)
    v = next(x for x in d["streams"] if x["codec_type"] == "video")
    a = [x for x in d["streams"] if x["codec_type"] == "audio"]
    assert (v["width"], v["height"], v["display_aspect_ratio"]) == (720, 576, "4:3")
    assert int(v["nb_read_frames"]) == int(probe_json(ref)["streams"][0]["nb_read_frames"])
    assert a and abs(float(a[0]["duration"]) - float(v["duration"])) < 0.1
    assert any("Stabilisation" in m for m in seen)
    assert list(work.iterdir()) == []                                 # transforms.trf supprimé
    assert "_stab" in pipeline.unique_output_path(shaky, S(stabilize=True), tmp_path).name


def test_stabilized_excerpt_and_preview(shaky, stools, tmp_path):
    r = pipeline.make_preview(shaky, S("equilibre", resolution="1080", stabilize=True), stools,
                              tmp_path / "ap", start=1, duration=3)
    v = next(x for x in probe_json(r.restored)["streams"] if x["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1440, 1080) and abs(float(v["duration"]) - 3) < 0.1


def test_stab_cancel_during_analysis(samples, stools, tmp_path, monkeypatch):
    work = tmp_path / "travail"
    work.mkdir()
    monkeypatch.setenv("VHSRA_TMP", str(work))
    info = analyze(samples["long"], stools)
    cancel = threading.Event()
    threading.Timer(1.5, cancel.set).start()
    t0 = time.time()
    with pytest.raises(Cancelled):
        pipeline.export(info, S(stabilize=True), tmp_path / "c.mp4", stools, cancel=cancel)
    assert time.time() - t0 < 10
    assert list(work.iterdir()) == [] and not list(tmp_path.glob("*.mp4"))


def test_stab_with_ai(shaky, stools, fake_ai, tmp_path, monkeypatch):
    t = dataclasses.replace(fake_ai, vidstab=True)
    work, out = tmp_path / "travail", tmp_path / "sortie"
    work.mkdir()
    out.mkdir()
    monkeypatch.setenv("VHSRA_TMP", str(work))
    res = pipeline.export(shaky, S("maximum", use_ai=True, stabilize=True), out / "sa.mp4", t,
                          start=0, duration=1)
    v = next(x for x in probe_json(res)["streams"] if x["codec_type"] == "video")
    # 25 images + 1 éventuellement dupliquée au début (vidéo de l'AVI MPEG-2 décalée sur le son,
    # comportement identique sans stabilisation)
    assert (v["width"], v["height"]) == (1440, 1080) and 25 <= int(v["nb_read_frames"]) <= 26
    assert list(work.iterdir()) == []
