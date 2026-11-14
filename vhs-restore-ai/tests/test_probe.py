from fractions import Fraction

import pytest

from vhs_restore.probe import analyze, decide_scan, guess_standard, parse_idet
from vhs_restore.tools import ToolError


def test_pal_interlaced(samples, tools):
    i = analyze(samples["pal_tff"], tools)
    assert (i.width, i.height) == (720, 576)
    assert i.fps == 25
    assert i.scan == "tff" and "mesuré" in i.scan_source
    assert i.dar == Fraction(4, 3) and i.sar == Fraction(16, 15)
    assert i.standard == "625/25"
    assert i.has_audio
    assert "été" in i.summary()["Fichier"]


def test_progressive_no_audio(samples, tools):
    i = analyze(samples["prog"], tools)
    assert i.scan == "progressive"
    assert i.standard == "525/30"
    assert not i.has_audio
    assert i.dar == Fraction(4, 3)


def test_sd_without_sar_assumes_43_with_warning(samples, tools):
    i = analyze(samples["sd_nosar"], tools)
    assert i.dar == Fraction(4, 3)
    assert "supposé" in i.dar_source and i.warnings


def test_errors(samples, tools, tmp_path):
    with pytest.raises(ToolError):
        analyze(samples["corrupt"], tools)
    with pytest.raises(ToolError):
        analyze(tmp_path / "absent.avi", tools)


def test_parse_idet():
    txt = ("[Parsed_idet_0 @ 0x1] Single frame detection: TFF: 1 BFF: 0 Progressive: 2 Undetermined: 3\n"
           "[Parsed_idet_0 @ 0x1] Multi frame detection: TFF:    90 BFF:     2 Progressive:     1 Undetermined:     7\n")
    assert parse_idet(txt) == {"tff": 90, "bff": 2, "progressive": 1, "undetermined": 7}
    assert parse_idet("rien") == {}


@pytest.mark.parametrize("idet,meta,expected", [
    ({"tff": 300, "bff": 5, "progressive": 10, "undetermined": 100}, "unknown", "tff"),
    ({"tff": 2, "bff": 280, "progressive": 4, "undetermined": 10}, "tt", "bff"),        # contenu > drapeau
    ({"tff": 3, "bff": 2, "progressive": 400, "undetermined": 5}, "tt", "progressive"),
    ({"tff": 5, "bff": 5, "progressive": 6, "undetermined": 500}, "unknown", "unknown"),  # jamais supposé
    ({"tff": 5, "bff": 5, "progressive": 6, "undetermined": 500}, "bb", "bff"),           # repli métadonnées
    ({}, "unknown", "unknown"),
])
def test_decide_scan(idet, meta, expected):
    assert decide_scan(idet, meta)[0] == expected


def test_guess_standard():
    assert guess_standard(576, Fraction(25))[0] == "625/25"
    assert guess_standard(480, Fraction(30000, 1001))[0] == "525/30"
    assert guess_standard(576, Fraction(30000, 1001))[0] == "inconnu"
    assert guess_standard(1080, Fraction(24))[0] == "inconnu"
