"""Durée, place et outils annoncés avant de lancer."""
from pathlib import Path

from vhs_restore import ergonomie, estimation, pipeline
from vhs_restore.probe import MediaInfo
from vhs_restore.profiles import profile_for


def _info():
    return MediaInfo(Path("film.avi"), duration=3600, width=720, height=576, scan="tff")


def _reglages(cle="equilibre", **kw):
    return pipeline.Settings(profile_for(cle, "video"), **kw)


def test_phrase_deux_heures():
    assert estimation.phrase_temps(7200) == (
        "Environ 2 heures sur cet ordinateur. "
        "Vous pouvez faire autre chose pendant ce temps.")
    assert estimation.phrase_temps(90 * 60) == (
        "Environ 1 heure et 30 minutes sur cet ordinateur. "
        "Vous pouvez faire autre chose pendant ce temps.")
    assert "minutes" in estimation.phrase_temps(12 * 60)


def test_extrapolation_de_l_apercu():
    assert estimation.secondes(4, 10, 7200) == 2880
    assert estimation.secondes(0, 10, 100) is None
    assert estimation.secondes(4, 0, 100) is None


def test_place_et_outils(tmp_path):
    info = _info()
    phrase, assez = estimation.phrase_place(info, _reglages(), tmp_path, 3600)
    assert "dossier choisi" in phrase and "Go" in phrase
    assert assez
    manquant = MediaInfo(Path("x.avi"), duration=0, width=0, height=0)
    assert estimation.phrase_place(manquant, _reglages(), tmp_path, None) == ("", True)
    outils = estimation.phrases_outils(info, _reglages("maximum"), qtgmc=False, ia=False)
    assert any("désentrelacement le plus fin" in ligne for ligne in outils)
    assert any("intelligence artificielle" in ligne for ligne in outils)
    assert estimation.phrases_outils(info, _reglages("fidele"), qtgmc=False, ia=False) == []
    assert "veille" in ergonomie.PHRASE_PATIENCE
