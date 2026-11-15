"""Conseils de l'analyse (son) : détection, aucune fausse alerte, et correction réelle
mesurée dans le fichier exporté. Échantillons de synthèse."""
import dataclasses

import pytest

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.advice import advise, apply
from vhs_restore.audio_check import _levels, measure
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for

AUDIO = {
    "gauche_muet": ("sine=f=440:sample_rate=48000[t];anullsrc=r=48000:cl=mono[s];"
                    "[s][t]join=inputs=2:channel_layout=stereo"),
    "phase": "sine=f=440:sample_rate=48000,pan=stereo|c0=c0|c1=c0,aeval=exprs=val(0)|-val(1):channel_layout=stereo",
    "sature": "sine=f=440:sample_rate=48000,volume=20,pan=stereo|c0=c0|c1=c0",
    "ronflement": ("anoisesrc=c=pink:a=0.05:r=48000[n];sine=f=50:sample_rate=48000,volume=0.3[h];"
                   "[n][h]amix=inputs=2:duration=first,pan=stereo|c0=c0|c1=c0"),
    "propre": "anoisesrc=c=pink:a=0.1:r=48000,pan=stereo|c0=c0|c1=c0",
}


@pytest.fixture(scope="module")
def films(tmp_path_factory, tools):
    d = tmp_path_factory.mktemp("conseils son")
    out = {}
    for name, graph in AUDIO.items():
        p = d / f"{name}.mkv"
        ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-filter_complex", f"{graph}[a]",
           "-map", "0:v", "-map", "[a]", "-t", "4", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(p))
        out[name] = analyze(p, tools)
    return out


def test_detection_and_advice(films):
    assert films["gauche_muet"].channel_issue == "left_silent"
    assert films["phase"].channel_issue == "phase"
    assert films["sature"].clipped > 0.01
    assert films["ronflement"].hum_hz == 50
    assert advise(films["propre"]) == []                                  # aucune fausse alerte
    assert advise(dataclasses.replace(films["sature"], audio_silent=True)) == []
    keys = {k: [a.key for a in advise(f)] for k, f in films.items()}
    assert keys["gauche_muet"] == ["channel"] and keys["sature"] == ["clip"] and keys["ronflement"] == ["hum"]
    s = apply(pipeline.Settings(profile_for("equilibre", "video")), advise(films["gauche_muet"]))
    assert s.audio_channel_fix == "right"


def test_nothing_applied_by_default(films):
    s = pipeline.Settings(profile_for("equilibre", "video"))
    for f in films.values():
        chain = pipeline.audio_filters(f, s)
        assert not any(x.startswith(("pan=", "aeval", "adeclip", "bandreject")) for x in chain)


@pytest.mark.parametrize("name", ["gauche_muet", "phase", "sature", "ronflement"])
def test_fix_really_repairs(films, tools, tmp_path, name):
    info = films[name]
    base = pipeline.Settings(profile_for("fidele", "video"), restore_audio=False)
    out = pipeline.export(info, apply(base, advise(info)), tmp_path / "o.mp4", tools)
    after = measure(tools.ffmpeg.path, out, 2)
    if name == "gauche_muet":
        levels = [c["RMS level dB"] for c in _levels(tools.ffmpeg.path, out, "")]
        assert len(levels) == 2 and min(levels) > -30                     # son des deux côtés
    elif name == "phase":
        assert after.channel_issue == ""
    elif name == "sature":
        assert after.clipped < info.clipped / 2
    else:
        assert after.hum_hz == 0
