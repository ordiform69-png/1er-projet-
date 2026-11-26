"""Reprise d'une restauration : parties, chauffe, témoin, raccords.

Constantes raccourcies dans les tests qui restaurent vraiment : parties de 20 s,
seuil 30 s, chauffe 3 s. Le film de synthèse dure 80 s.
"""
import dataclasses
import os
import shutil
import subprocess
import threading
import time
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import ff, probe_json
from vhs_restore import pipeline, reprise
from vhs_restore.probe import MediaInfo, analyze
from vhs_restore.profiles import PROFILES, profile_for
from vhs_restore.scenes import Scene
from vhs_restore.tools import AAC, Cancelled, ToolError


def _suite(cmd, suite) -> bool:
    suite = list(suite)
    for i in range(len(cmd) - len(suite) + 1):
        if list(cmd[i:i + len(suite)]) == suite:
            return True
    return False


def _ss(cmd) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-ss"]


# ---------------------------------------------------------------- découpage


def test_decoupage_parties_coupes_et_reste():
    """20 s au plus, un reste plus court que la chauffe rejoint la précédente,
    une coupe au milieu n'est pas traversée."""
    plein = reprise.decouper([(0, 80)], 20, 3)
    assert plein == [(0, 20), (20, 40), (40, 60), (60, 80)]
    assert all(b - a <= 20 for _, (a, b) in enumerate(plein))

    avec_trou = reprise.decouper([(0, 50), (70, 100)], 20, 3)
    assert avec_trou == [(0, 20), (20, 40), (40, 50), (70, 90), (90, 100)]
    assert all(b <= 50 or a >= 70 for a, b in avec_trou)

    court = reprise.decouper([(0, 42)], 20, 3)
    assert court == [(0, 20), (20, 42)]
    assert reprise.chauffe_partie(0, [(0, 42)], 3) == 0
    assert reprise.chauffe_partie(20, [(0, 42)], 3) == 3

    gardes = [(0, 25), (40, 70)]
    assert reprise.chauffe_partie(40, gardes, 3) == 0
    assert reprise.chauffe_partie(60, gardes, 3) == 3


def test_possible_seulement_quand_cest_sur():
    s = pipeline.Settings(PROFILES["fidele"])
    assert reprise.possible(s, 1200, cadence=False, bande=False)
    assert not reprise.possible(s, 1199, cadence=False, bande=False)
    assert not reprise.possible(dataclasses.replace(s, use_ai=True), 4000, cadence=False, bande=False)
    assert not reprise.possible(dataclasses.replace(s, dust=True), 4000, cadence=False, bande=False)
    assert not reprise.possible(dataclasses.replace(s, stabilize=True), 4000, cadence=False, bande=False)
    assert not reprise.possible(s, 4000, cadence=True, bande=False)
    assert not reprise.possible(s, 4000, cadence=False, bande=True)


def test_cle_change_avec_reglages_scenes_et_passages(tmp_path, monkeypatch):
    film = tmp_path / "cassette.mp4"
    film.write_bytes(b"abcdef")
    info = MediaInfo(path=film, duration=3600)
    s = pipeline.Settings(PROFILES["fidele"])
    base = [(0.0, 3600.0)]
    cle = reprise.calculer_cle(info, s, base)
    assert reprise.calculer_cle(info, s, base) == cle
    assert reprise.calculer_cle(info, dataclasses.replace(s, crf=19), base) != cle
    assert reprise.calculer_cle(info, s, [(0.0, 60.0), (120.0, 3600.0)]) != cle
    scenes = (
        Scene(0, 10, 0.2, 0.6, (1.1, 1.0, 0.9), True, (140, 100, 80)),
        Scene(10, 3600, 0.05, 0.9, (0.9, 1.0, 1.1), True, (80, 100, 140)),
    )
    assert reprise.calculer_cle(dataclasses.replace(info, scenes=scenes), s, base) != cle
    monkeypatch.setattr(reprise, "DUREE_PARTIE", 300.0)
    assert reprise.calculer_cle(info, s, base) != cle
    monkeypatch.setattr(reprise, "DUREE_PARTIE", 600.0)
    monkeypatch.setattr(reprise, "CHAUFFE", 4.0)
    assert reprise.calculer_cle(info, s, base) != cle


def test_menage_autre_cle_et_trente_jours(tmp_path, monkeypatch):
    rac = tmp_path / "reprise"
    rac.mkdir()
    monkeypatch.setattr(reprise, "racine", lambda: rac)
    film = tmp_path / "cassette.mp4"
    film.write_bytes(b"abcdef")
    info = MediaInfo(path=film, duration=3600)
    ancienne = rac / ("ab" * 32)
    ancienne.mkdir()
    (ancienne / "manifeste.json").write_text(
        '{"version": 1, "chemin": "%s", "taille": 6, "date": 1}' % str(film.resolve()),
        encoding="utf-8")
    (ancienne / "partie-0001.mp4").write_bytes(b"partie")
    vieux = rac / ("cd" * 32)
    vieux.mkdir()
    (vieux / "manifeste.json").write_text('{"version": 1, "chemin": "/ailleurs", "taille": 1, "date": 1}',
                                         encoding="utf-8")
    passe = time.time() - 31 * 86400
    os.utime(vieux, (passe, passe))
    os.utime(vieux / "manifeste.json", (passe, passe))

    dossier = reprise.preparer(info, pipeline.Settings(PROFILES["fidele"]), [(0.0, 3600.0)])
    assert dossier.is_dir() and (dossier / "manifeste.json").is_file()
    assert not ancienne.exists()
    assert not vieux.exists()
    assert dossier.name != ancienne.name


def test_place_disque_insuffisante(tmp_path, monkeypatch):
    class Usage:
        def __init__(self, libre):
            self.free = libre

    (tmp_path / "sous").mkdir()
    monkeypatch.setattr(reprise.shutil, "disk_usage", lambda _p: Usage(5_000))
    with pytest.raises(ToolError, match="Espace disque insuffisant"):
        reprise.verifier_place([(tmp_path, 3_000), (tmp_path / "sous", 3_000)])
    monkeypatch.setattr(reprise.shutil, "disk_usage", lambda _p: Usage(20_000))
    reprise.verifier_place([(tmp_path, 3_000), (tmp_path / "sous", 3_000)])


# ---------------------------------------------------------------- pièges de la commande


def _info_long(samples, tools):
    info = analyze(samples["pal_tff"], tools)
    return dataclasses.replace(info, duration=3600, scan="tff", scenes=(
        Scene(0, 30, 0.2, 0.6, (1.18, 1.0, 0.85), True, (150, 100, 80)),
        Scene(30, 3600, 0.16, 0.55, (0.85, 1.0, 1.18), True, (80, 100, 150)),
    ))


def _reglages_piege():
    return pipeline.Settings(PROFILES["fidele"], level_black=0.2, level_white=0.8,
                             audio_offset_ms=100, audio_drift_ms_per_min=600)


def _capturer(monkeypatch):
    commandes = []

    def faux(cmd, **_k):
        commandes.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"x")
        return []

    monkeypatch.setattr(pipeline, "run", faux)
    return commandes


def test_commande_chauffe_scenes_son_images_aac(samples, tools, tmp_path, monkeypatch):
    """La chauffe est en temps source : scènes, dérive, -frames:v et AAC."""
    info = _info_long(samples, tools)
    s = _reglages_piege()
    commandes = _capturer(monkeypatch)
    pipeline._export(info, s, tmp_path / "partie.mp4", tools, morceau=True, _partie=True,
                     chauffe=3, start=20, duration=20)
    cmd = commandes[-1]
    assert _suite(cmd, AAC)
    assert _ss(cmd)[0] == "17.000"
    vf = cmd[cmd.index("-vf") + 1]
    assert "trim=start_frame=150" in vf
    assert "PTS+17.000000" in vf and "PTS+20" not in vf
    assert cmd[cmd.index("-frames:v") + 1] == "1000"
    af = cmd[cmd.index("-af") + 1]
    assert "apad=whole_dur=20.000000000" in af
    assert "atrim=duration=20.000000000" in af
    assert "atrim=start=3.000000000" in af
    assert af.index("atrim=start=") < af.index("apad=")
    vitesse = pipeline._tempo_factor(info, s, drift=True)
    attendu = (17 - 0.1) * vitesse
    assert _ss(cmd)[1] == f"{attendu:.3f}"
    assert abs(attendu - 17.07) < 0.05
    assert abs(attendu - (20 - 0.1) * vitesse) > 1


def test_commande_sans_chauffe_inchangee(samples, tools, tmp_path, monkeypatch):
    info = _info_long(samples, tools)
    s = _reglages_piege()
    commandes = _capturer(monkeypatch)
    pipeline._export(info, s, tmp_path / "morceau.mp4", tools, morceau=True, start=20, duration=20)
    cmd = commandes[-1]
    assert _suite(cmd, AAC)
    assert "trim=start_frame" not in cmd[cmd.index("-vf") + 1]
    assert _ss(cmd)[0] == "20.000"
    assert cmd[cmd.index("-frames:v") + 1] == "1000"
    af = cmd[cmd.index("-af") + 1]
    assert "apad=whole_dur=20.000000000" in af and "atrim=duration=20.000000000" in af
    assert "atrim=start=" not in af


def test_film_court_ou_ia_ne_cree_pas_de_dossier(samples, tools, tmp_path, monkeypatch):
    local = tmp_path / "loc"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    info = analyze(samples["prog"], tools)
    pipeline.export(info, pipeline.Settings(PROFILES["fidele"]), tmp_path / "court.mp4", tools)
    assert not (local / "VHSRestoreAI" / "reprise").exists()

    monkeypatch.setattr(reprise, "SEUIL", 1.0)
    assert not reprise.possible(pipeline.Settings(PROFILES["fidele"], use_ai=True),
                                info.duration, cadence=False, bande=False)
    if not tools.stab_available:
        with pytest.raises(ToolError):
            pipeline.export(info, pipeline.Settings(PROFILES["fidele"], stabilize=True),
                            tmp_path / "stab.mp4", tools)
        assert not (local / "VHSRestoreAI" / "reprise").exists()


# ---------------------------------------------------------------- film de 80 s


@pytest.fixture(scope="module")
def film_80(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("film80")
    chemin = dossier / "vacances.mp4"
    # Bip court autour de chaque seconde + 0,25 s, pas sur les raccords entiers.
    son = "aevalsrc=0.7*sin(2*PI*880*t)*gte(sin(2*PI*t)\\,0.97):s=48000"
    ff("-f", "lavfi", "-i", "testsrc2=size=160x120:rate=25",
       "-f", "lavfi", "-i", son, "-t", "80", "-frames:v", "2000",
       "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", "-pix_fmt", "yuv420p",
       "-c:a", "pcm_s16le", str(chemin))
    return chemin


def _locaux(monkeypatch, tmp_path):
    local = tmp_path / "loc"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(reprise, "DUREE_PARTIE", 20.0)
    monkeypatch.setattr(reprise, "SEUIL", 30.0)
    monkeypatch.setattr(reprise, "CHAUFFE", 3.0)
    return local


def _scenes_80():
    # La coupure de scène tombe dans la chauffe de la partie qui commence à 20 s.
    return (
        Scene(0, 21.5, 0.2, 0.6, (1.18, 1.0, 0.85), True, (150, 100, 80)),
        Scene(21.5, 80, 0.16, 0.55, (0.85, 1.0, 1.18), False, (80, 100, 150)),
    )


def _info_80(chemin, tools):
    info = analyze(chemin, tools)
    return dataclasses.replace(info, scenes=_scenes_80(), scan="progressive")


def _reglages_80():
    return pipeline.Settings(profile_for("fidele", "video"), preset="ultrafast", crf=4,
                             level_black=0.2, level_white=0.8, scan="progressive")


def _image(ffmpeg, chemin, numero):
    r = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(chemin), "-vf", f"select=eq(n\\,{numero})",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:"],
        capture_output=True, check=True)
    if not r.stdout:
        raise RuntimeError(f"image {numero} absente")
    return r.stdout


def _ecart(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a) / 255


def _pcm(ffmpeg, chemin) -> bytes:
    r = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(chemin), "-vn", "-ac", "1", "-ar", "48000",
         "-f", "s16le", "pipe:"],
        capture_output=True, check=True)
    return r.stdout


def _creneaux(pcm: bytes, pas: int = 480) -> list[float]:
    """Instants des bips : énergie forte, pas plus d'un par demi-seconde."""
    import array
    vals = array.array("h")
    vals.frombytes(pcm[:len(pcm) // 2 * 2])
    energie = []
    for i in range(0, len(vals) - pas, pas):
        energie.append(sum(abs(int(v)) for v in vals[i:i + pas]) / pas)
    seuil = max(energie) * 0.45 if energie else 0
    instants = []
    dernier = -1.0
    for i, e in enumerate(energie):
        t = i * pas / 48000
        if e >= seuil and t - dernier > 0.4:
            instants.append(t)
            dernier = t
    return instants


def _saut(pcm: bytes, instant: float, demi: int = 240) -> int:
    import array
    vals = array.array("h")
    vals.frombytes(pcm[:len(pcm) // 2 * 2])
    i = int(round(instant * 48000))
    a, b = max(1, i - demi), min(len(vals) - 1, i + demi)
    return max(abs(int(vals[k]) - int(vals[k - 1])) for k in range(a, b))


def test_meme_resultat_que_d_une_fois(film_80, tools, tmp_path, monkeypatch):
    """Même nombre d'images, bips calés, raccords proches, pas de claquement."""
    _locaux(monkeypatch, tmp_path)
    info = _info_80(film_80, tools)
    s = _reglages_80()
    monkeypatch.setattr(reprise, "SEUIL", 1e9)
    une = pipeline.export(info, s, tmp_path / "une.mp4", tools)
    monkeypatch.setattr(reprise, "SEUIL", 30.0)
    parties = pipeline.export(info, s, tmp_path / "parties.mp4", tools)
    rac = tmp_path / "loc" / "VHSRestoreAI" / "reprise"
    assert not rac.exists() or not any(p for p in rac.iterdir() if p.is_dir())

    du, vu, au = _flux(une)
    dp, vp, ap = _flux(parties)
    assert int(vu["nb_read_frames"]) == int(vp["nb_read_frames"]) == 2000
    assert abs(float(ap[0]["duration"]) - float(vp["duration"])) < 0.02
    assert abs(float(au[0]["duration"]) - float(vu["duration"])) < 0.02

    ffmpeg = tools.ffmpeg.path
    for numero in (499, 500, 550, 999, 1000, 1499, 1500):
        ecart = _ecart(_image(ffmpeg, une, numero), _image(ffmpeg, parties, numero))
        assert ecart < 2 / 255, (numero, ecart)

    pu, pp = _pcm(ffmpeg, une), _pcm(ffmpeg, parties)
    bu, bp = _creneaux(pu), _creneaux(pp)
    assert len(bu) >= 70 and len(bu) == len(bp)
    for a, b in zip(bu, bp):
        assert abs(a - b) < 0.04, (a, b)
    for instant in (20, 40, 60):
        assert _saut(pp, instant) <= max(1500, _saut(pu, instant) * 4)


def test_reprise_partie_abimee_et_menage(film_80, tools, tmp_path, monkeypatch):
    """Arrêt après deux parties, une partie abîmée est refaite, le dossier disparaît."""
    local = _locaux(monkeypatch, tmp_path)
    info = _info_80(film_80, tools)
    s = _reglages_80()
    vrai = pipeline._export
    etat = {"n": 0}

    def compte(*args, **kwargs):
        if kwargs.get("_partie"):
            etat["n"] += 1
            if etat["n"] > 2:
                raise Cancelled("Annulé.")
        return vrai(*args, **kwargs)

    monkeypatch.setattr(pipeline, "_export", compte)
    with pytest.raises(Cancelled):
        pipeline.export(info, s, tmp_path / "incomplet.mp4", tools)
    monkeypatch.setattr(pipeline, "_export", vrai)

    rac = local / "VHSRestoreAI" / "reprise"
    dossiers = [p for p in rac.iterdir() if p.is_dir()]
    assert len(dossiers) == 1
    dossier = dossiers[0]
    assert reprise.fichier(dossier, 1).is_file() and reprise.temoin(dossier, 1).is_file()
    assert reprise.fichier(dossier, 2).is_file() and reprise.temoin(dossier, 2).is_file()
    assert not reprise.fichier(dossier, 3).exists()
    assert not list(dossier.glob("*.partiel*"))

    reprise.fichier(dossier, 2).write_bytes(b"partie incomplete")
    messages = []
    out = pipeline.export(info, s, tmp_path / "repris.mp4", tools,
                          progress=lambda _f, m: messages.append(m))
    assert any(m.startswith("Reprise : 1 partie sur") and "déjà faite." in m for m in messages)
    assert not any(rac.iterdir())
    d, v, a = _flux(out)
    assert int(v["nb_read_frames"]) == 2000
    assert a and abs(float(a[0]["duration"]) - float(v["duration"])) < 0.02


def test_reglages_changes_effacent_l_ancien_dossier(film_80, tools, tmp_path, monkeypatch):
    local = _locaux(monkeypatch, tmp_path)
    info = _info_80(film_80, tools)
    s = _reglages_80()
    vrai = pipeline._export
    etat = {"n": 0}

    def stop(*args, **kwargs):
        if kwargs.get("_partie"):
            etat["n"] += 1
            if etat["n"] > 1:
                raise Cancelled("Annulé.")
        return vrai(*args, **kwargs)

    monkeypatch.setattr(pipeline, "_export", stop)
    with pytest.raises(Cancelled):
        pipeline.export(info, s, tmp_path / "a.mp4", tools)
    monkeypatch.setattr(pipeline, "_export", vrai)
    rac = local / "VHSRestoreAI" / "reprise"
    ancienne = next(p for p in rac.iterdir() if p.is_dir())
    etat["n"] = 0
    monkeypatch.setattr(pipeline, "_export", stop)
    with pytest.raises(Cancelled):
        pipeline.export(info, dataclasses.replace(s, crf=8), tmp_path / "b.mp4", tools)
    assert not ancienne.exists()
    restants = [p for p in rac.iterdir() if p.is_dir()]
    assert len(restants) == 1 and restants[0] != ancienne


def test_dvd_en_plusieurs_morceaux(tools, tmp_path, monkeypatch):
    """Les parties de 20 s se font dans le film réuni, chauffe comprise, à travers les VOB."""
    local = _locaux(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=size=160x120:rate=25",
       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
       "-t", "40", "-frames:v", "1000", "-c:v", "libx264", "-preset", "ultrafast",
       "-c:a", "pcm_s16le", str(source))
    dossier = tmp_path / "VIDEO_TS"
    dossier.mkdir()
    v1, v2 = dossier / "VTS_01_1.VOB", dossier / "VTS_01_2.VOB"
    ff("-i", str(source), "-t", "20", "-c:v", "mpeg2video", "-b:v", "2M", "-c:a", "mp2",
       "-f", "vob", str(v1))
    ff("-ss", "20", "-i", str(source), "-c:v", "mpeg2video", "-b:v", "2M", "-c:a", "mp2",
       "-f", "vob", str(v2))
    from vhs_restore.dvd import open_media
    info = open_media(v1, tools)
    assert len(info.parts) == 2 and info.duration >= 30
    messages = []
    out = pipeline.export(info, _reglages_80(), tmp_path / "dvd.mp4", tools,
                          progress=lambda _f, m: messages.append(m))
    assert any(m.startswith("Partie ") for m in messages)
    rac = local / "VHSRestoreAI" / "reprise"
    assert not rac.exists() or not any(p for p in rac.iterdir() if p.is_dir())
    _d, v, a = _flux(out)
    assert a and int(v["nb_read_frames"]) >= 900


def _flux(path):
    d = probe_json(path)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = [s for s in d["streams"] if s["codec_type"] == "audio"]
    return d, v, a
