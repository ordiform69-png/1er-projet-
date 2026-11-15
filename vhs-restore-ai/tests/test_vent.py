"""Vent et grondements : détection, rien par défaut, effet mesuré dans le fichier exporté.
Une voix de synthèse (300 Hz à 3 kHz) ne bouge pas. Bruit grave irrégulier : il baisse."""
import pytest

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.advice import advise, apply
from vhs_restore.audio_check import _levels
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for

GRAPHS = {
    "vent": ("anoisesrc=color=brown:a=0.6:r=48000[w];sine=f=1000:sample_rate=48000,volume=0.15[v];"
             "[w][v]amix=inputs=2:duration=first,pan=stereo|c0=c0|c1=c0"),
    "voix": ("sine=f=300:sample_rate=48000,volume=0.2[a];sine=f=1000:sample_rate=48000,volume=0.2[b];"
             "sine=f=3000:sample_rate=48000,volume=0.15[c];[a][b][c]amix=inputs=3:duration=first,"
             "pan=stereo|c0=c0|c1=c0"),
}


@pytest.fixture(scope="module")
def films(tmp_path_factory, tools):
    d = tmp_path_factory.mktemp("vent")
    out = {}
    for name, graph in GRAPHS.items():
        p = d / f"{name}.mkv"
        ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-filter_complex", f"{graph}[a]",
           "-map", "0:v", "-map", "[a]", "-t", "4", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(p))
        out[name] = analyze(p, tools)
    return out


def rms(ffmpeg, path, af):
    chans = _levels(ffmpeg, path, af)
    assert chans, af
    return max(c["RMS level dB"] for c in chans)


def test_advice_only_for_wind(films):
    assert films["vent"].wind and not films["voix"].wind
    assert [a.key for a in advise(films["vent"])] == ["wind"]
    assert advise(films["voix"]) == []
    s = pipeline.Settings(profile_for("fidele", "video"))
    assert "highpass=" not in ",".join(pipeline.audio_filters(films["vent"], s))
    fixed = apply(s, advise(films["vent"]))
    assert fixed.audio_highpass and "highpass=f=80:poles=1" in pipeline.audio_filters(films["vent"], fixed)


def test_rumble_down_voice_unchanged(films, tools, tmp_path):
    s = pipeline.Settings(profile_for("fidele", "video"), restore_audio=False,
                          audio_highpass=True, preset="ultrafast", scan="progressive")
    ffm = tools.ffmpeg.path
    low, voice = "lowpass=f=80,", "highpass=f=300,lowpass=f=3000,"
    before_low = rms(ffm, films["vent"].path, low)
    out = pipeline.export(films["vent"], s, tmp_path / "vent.mp4", tools)
    after_low = rms(ffm, out, low)
    assert after_low < before_low - 4          # grondement mesuré en baisse (dB)
    before_v = rms(ffm, films["voix"].path, voice)
    out_v = pipeline.export(films["voix"], s, tmp_path / "voix.mp4", tools)
    after_v = rms(ffm, out_v, voice)
    assert abs(after_v - before_v) < 1.0      # voix 300 Hz–3 kHz inchangée
