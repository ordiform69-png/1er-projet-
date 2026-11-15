"""Son (ajouté sans tests le 15/11) : profils, mono, durée, décalage, dérive, ronflement,
copie WAV/FLAC, piste silencieuse, film muet, bande noire du bas."""
import dataclasses
import json
import re
import shutil
import subprocess

import pytest

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for


@pytest.fixture(scope="module")
def mono(tmp_path_factory, tools):
    src = tmp_path_factory.mktemp("son") / "son essai été.avi"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25,setsar=16/15", "-f", "lavfi", "-i",
       "sine=frequency=440:sample_rate=48000", "-t", "4", "-c:v", "mpeg2video", "-c:a", "pcm_s16le", str(src))
    return analyze(src, tools)


def S(key="equilibre", **kw):
    return pipeline.Settings(profile_for(key, "video"), **kw)


def streams(p):
    d = json.loads(subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_streams", "-of", "json",
                                   str(p)], capture_output=True, text=True).stdout)
    return {s["codec_type"]: s for s in d["streams"]}


def onset(p):
    t = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(p), "-af",
                        "silencedetect=n=-40dB:d=0.05", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"silence_end: ([\d.]+)", t)
    return float(m[0]) if m else 0.0


def test_profiles_chains(mono):
    assert pipeline.audio_filters(mono, S("fidele")) == ["afftdn=nr=4:nf=-50:tn=1"]
    eq = pipeline.audio_filters(mono, S())
    assert eq[0] == "adeclick" and eq[1].startswith("afftdn=nr=10") and eq[2].startswith("dynaudnorm")
    assert pipeline.audio_filters(mono, S(restore_audio=False)) == []
    assert pipeline.audio_filters(dataclasses.replace(mono, audio_silent=True), S()) == []
    assert pipeline.audio_filters(dataclasses.replace(mono, has_audio=False), S()) == []
    assert not any("bandreject" in f for f in pipeline.audio_filters(mono, S()))   # jamais par défaut
    hum = pipeline.audio_filters(mono, S(audio_mains_hz=50))
    assert "bandreject=f=50:t=q:w=30" in hum and "bandreject=f=100:t=q:w=30" in hum


def test_mono_duration_and_offset(mono, tools, tmp_path):
    out = pipeline.export(mono, S(), tmp_path / "eq.mp4", tools)
    st = streams(out)
    assert st["audio"]["channels"] == 1                                    # le mono reste mono
    assert abs(float(st["audio"]["duration"]) - float(st["video"]["duration"])) < 0.1
    assert onset(out) < 0.05
    late = pipeline.export(mono, S(audio_offset_ms=300), tmp_path / "late.mp4", tools)
    assert 0.25 < onset(late) < 0.4                                         # son retardé de 300 ms


def test_drift_and_copy(mono, tools, tmp_path):
    assert pipeline.audio_filters(mono, S(audio_drift_ms_per_min=600))[-1].startswith("atempo=1.01")
    out = pipeline.export(mono, S(audio_copy="flac", audio_mains_hz=50), tmp_path / "c.mp4", tools)
    flac = out.with_suffix(".flac")
    assert flac.is_file() and streams(flac)["audio"]["codec_name"] == "flac"
    assert not list(tmp_path.glob("*.partiel*"))


def test_silent_film_stays_silent(samples, tools, tmp_path):
    info = analyze(samples["film18"], tools)
    out = pipeline.export(info, pipeline.Settings(profile_for("equilibre", "film"), source="film",
                                                  audio_copy="wav"), tmp_path / "m.mp4", tools)
    assert "audio" not in streams(out) and not out.with_suffix(".wav").exists()


def test_bottom_mask(mono):
    chain = pipeline.filter_chain(mono, S(mask_bottom=12))
    assert "crop=720:564:0:0,pad=720:576:0:0:black" in chain              # même taille d'image
    assert "pad=" not in pipeline.filter_chain(mono, S())                   # 0 ligne par défaut
