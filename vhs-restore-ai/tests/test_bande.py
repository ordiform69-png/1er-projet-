"""Bande VHS (Analog Repair, cases désactivées par défaut) et RNNoise (opt-in).
Pas d'appel au moteur poussières : il n'est pas requis pour ces contrôles."""
import dataclasses
from fractions import Fraction
from pathlib import Path

import pytest

from vhs_restore import pipeline
from vhs_restore.probe import MediaInfo
from vhs_restore.profiles import profile_for
from vhs_restore.tools import ToolError


def clip(tmp_path: Path) -> MediaInfo:
    p = tmp_path / "cassette.mp4"
    p.write_bytes(b"x")
    return MediaInfo(path=p, duration=4, width=720, height=576, fps=Fraction(25),
                     sar=Fraction(16, 15), dar=Fraction(4, 3), scan="progressive",
                     has_audio=True, audio_silent=False)


def S(key="equilibre", **kw):
    return pipeline.Settings(profile_for(key, kw.get("source", "video")), **kw)


def test_tape_names_and_not_on_film(tmp_path):
    info = clip(tmp_path)
    name = pipeline.unique_output_path(
        info, S(tape_noise=True, chroma_repair=True, dropouts=True), tmp_path).name
    assert "_bande" in name and "_couleur" in name and "_decrochages" in name
    assert not pipeline._tape_job(S(source="film", tape_noise=True, chroma_repair=True, dropouts=True))
    assert pipeline._tape_job(S(tape_noise=True))
    plain, tape = pipeline.disk_needs(info, S()), pipeline.disk_needs(info, S(tape_noise=True))
    assert plain[1] == 0 and tape[1] > 0
    interlaced = dataclasses.replace(info, scan="tff")
    assert pipeline.disk_needs(interlaced, S(tape_noise=True))[1] > tape[1]


def test_tape_refuses_without_module(tmp_path, tools):
    info = clip(tmp_path)
    bare = dataclasses.replace(tools, dust=False)
    with pytest.raises(ToolError, match="pas installé"):
        pipeline.export(info, S(tape_noise=True), tmp_path / "o.mp4", bare)
    assert not (tmp_path / "o.mp4").exists()
    assert list(tmp_path.glob("*.partiel*")) == []


def test_rnnoise_is_opt_in():
    info = MediaInfo(path=Path("a.mp4"), has_audio=True, duration=2, fps=Fraction(25))
    model = "/tmp/modele.rnnn"
    off = pipeline.audio_filters(info, S(), rnnoise=model)
    assert off[1].startswith("afftdn=nr=10")
    on = pipeline.audio_filters(info, S(use_rnnoise=True), rnnoise=model)
    assert on[0] == "adeclick" and "arnndn=m=/tmp/modele.rnnn:mix=0.35" in on[1]
    mx = pipeline.audio_filters(info, S("maximum", use_rnnoise=True), rnnoise=model)
    assert "mix=0.55" in mx[1]
    # Fidèle reste afftdn, même case cochée. DeepFilterNet déjà passé : pas de second souffle.
    assert pipeline.audio_filters(info, S("fidele", use_rnnoise=True), rnnoise=model) == \
        ["afftdn=nr=4:nf=-50:tn=1"]
    assert not any(f.startswith("arnndn") or f.startswith("afftdn")
                   for f in pipeline.audio_filters(info, S("maximum", use_rnnoise=True),
                                                   rnnoise=model, skip_afftdn=True)
                   if not f.startswith("adeclick") and not f.startswith("dynaudnorm"))
    assert pipeline._ff_filter_path(r"C:\Users\a b\m.rnnn") == "C\\:/Users/a b/m.rnnn"
