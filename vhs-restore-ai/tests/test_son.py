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
    # afftdn retarde le son de 25 ms : retiré en échantillons (48 kHz), horloge reculée (n°21, A2)
    recale = ["atrim=start_sample=1200", "asetpts=PTS-0.025/TB", "apad=pad_dur=0.025"]
    assert pipeline.audio_filters(mono, S("fidele")) == ["afftdn=nr=4:nf=-50:tn=1", *recale]
    eq = pipeline.audio_filters(mono, S())
    assert eq[0] == "adeclick" and eq[1].startswith("afftdn=nr=10") and eq[2:5] == recale
    assert eq[5].startswith("dynaudnorm")
    assert pipeline.audio_filters(mono, S(restore_audio=False)) == []
    assert pipeline.audio_filters(dataclasses.replace(mono, audio_silent=True), S()) == []
    assert pipeline.audio_filters(dataclasses.replace(mono, has_audio=False), S()) == []
    assert not any("bandreject" in f for f in pipeline.audio_filters(mono, S()))   # jamais par défaut
    hum = pipeline.audio_filters(mono, S(audio_mains_hz=50))
    for f_hz in (50, 100, 150, 200):
        assert f"bandreject=f={f_hz}:t=q:w=30" in hum
    hum60 = pipeline.audio_filters(mono, S(audio_mains_hz=60))
    for f_hz in (60, 120, 180, 240):
        assert f"bandreject=f={f_hz}:t=q:w=30" in hum60


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


def test_son_apres_cinq_minutes(tmp_path, tools):
    src = tmp_path / "tard.mkv"
    ff("-f", "lavfi", "-i", "color=s=128x96:r=1", "-f", "lavfi", "-i", "sine=r=8000",
       "-af", "adelay=301000:all=1", "-t", "303", "-c:v", "ffv1", "-c:a", "flac", str(src))
    info = analyze(src, tools)
    assert info.has_audio and not info.audio_silent


def test_harmoniques_du_ronflement(tools, tmp_path):
    """50, 150 et 200 Hz baissent ; une voix à 300 Hz bouge de moins de 1 dB."""
    from vhs_restore.audio_check import _levels
    src = tmp_path / "ronflement.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=160x120:r=25:d=3",
       "-filter_complex",
       "sine=f=50:sample_rate=48000:d=3,volume=0.2[a];"
       "sine=f=150:sample_rate=48000:d=3,volume=0.2[b];"
       "sine=f=200:sample_rate=48000:d=3,volume=0.2[c];"
       "sine=f=300:sample_rate=48000:d=3,volume=0.2[d];"
       "[a][b][c][d]amix=inputs=4:duration=first:normalize=0,"
       "pan=stereo|c0=c0|c1=c0[a]",
       "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
       "-c:a", "pcm_s16le", str(src))
    info = analyze(src, tools)
    sans = pipeline.export(info, S("fidele", restore_audio=False),
                           tmp_path / "sans.mp4", tools)
    avec = pipeline.export(info, S("fidele", restore_audio=False, audio_mains_hz=50),
                           tmp_path / "avec.mp4", tools)

    def rms(path, hz):
        return _levels(tools.ffmpeg.path, path,
                       f"pan=mono|c0=0.5*c0+0.5*c1,bandpass=f={hz}:width_type=h:w=8,")[0]["RMS level dB"]

    for hz in (150, 200):
        baisse = rms(sans, hz) - rms(avec, hz)
        assert baisse > 12, (hz, baisse)
    voix = rms(avec, 300) - rms(sans, 300)
    assert abs(voix) < 1, voix
