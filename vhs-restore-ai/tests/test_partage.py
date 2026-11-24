"""Après la restauration : copie à partager, cassette séparée en films, film nommé."""
import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore import partage, vides
from vhs_restore.tools import ToolError


def _sonde(tools, chemin):
    r = subprocess.run([tools.ffprobe.path, "-v", "error", "-show_entries",
                        "format=duration:format_tags=title,date:stream=codec_type,codec_name,profile,level,width,"
                        "height,avg_frame_rate,sample_aspect_ratio,channels", "-of", "json", str(chemin)],
                       capture_output=True, text=True)
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def restaure(tmp_path_factory):
    """Un film « restauré » typique : 720 × 576, pixels 16:15 (4:3), 50 i/s, son stéréo, 6 s."""
    d = tmp_path_factory.mktemp("partage")
    f = d / "Noël chez mémé_restaure_equilibre.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=50", "-f", "lavfi", "-i", "sine=f=440:sample_rate=48000",
       "-t", "6", "-vf", "setsar=16/15", "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-ac", "2", str(f))
    return f


@pytest.mark.parametrize("cle,taille,fps,niveau", [("legere", (640, 480), "25/1", 30), ("tele", (768, 576), "50/1", 32)])
def test_copies_a_partager(tools, restaure, cle, taille, fps, niveau):
    avant = hashlib.sha256(restaure.read_bytes()).hexdigest()
    out = partage.faire_copie(tools.ffmpeg.path, tools.ffprobe.path, restaure, cle)
    d = _sonde(tools, out)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next(s for s in d["streams"] if s["codec_type"] == "audio")
    assert (v["width"], v["height"]) == taille and v["avg_frame_rate"] == fps
    assert v["sample_aspect_ratio"] in ("1:1", "N/A") and v["level"] == niveau
    assert a["codec_name"] == "aac" and a["channels"] == 2
    assert abs(float(d["format"]["duration"]) - 6) < 0.2
    assert out.name == restaure.stem + partage.COPIES[cle].suffixe + ".mp4"
    assert hashlib.sha256(restaure.read_bytes()).hexdigest() == avant          # le film restauré est intact
    out2 = partage.faire_copie(tools.ffmpeg.path, tools.ffprobe.path, restaure, cle)
    assert out2 != out and out.is_file() and "(2)" in out2.name               # jamais d'écrasement
    assert not list(restaure.parent.glob("*.partiel*")) and not list(restaure.parent.glob(".*reserve"))


def test_copie_tele_tient_sur_une_cle_fat32():
    """Film de 3 h : le débit est plafonné pour rester sous 4 Go ; un film court garde 8 Mbit/s."""
    long = partage.InfosVideo(3 * 3600, 720, 576, Fraction(50), Fraction(4, 3), True)
    court = partage.InfosVideo(600, 720, 576, Fraction(50), Fraction(4, 3), True)
    tele = partage.COPIES["tele"]
    assert (partage.debit_video(long, tele) + 192_000) * long.duree / 8 < 4e9
    assert partage.debit_video(court, tele) == tele.debit_max
    assert partage.taille_copie(long, partage.COPIES["legere"]) == (640, 480)
    petit = partage.InfosVideo(60, 320, 240, Fraction(25), Fraction(4, 3), True)
    assert partage.taille_copie(petit, tele) == (320, 240)                    # jamais agrandi


@pytest.mark.parametrize("texte,attendu", [
    ("Noël 1988", "Noël 1988"), ("  Vacances : été 1990 / Bretagne?  ", "Vacances été 1990 Bretagne"),
    ("CON", "CON (film)"), ("fin...", "fin"), ("", ""), ("a" * 200, "a" * 80)])
def test_nom_de_fichier_windows(texte, attendu):
    assert partage.nom_de_fichier(texte) == attendu


@pytest.fixture(scope="module")
def cassette(tmp_path_factory):
    """Neige 2 s, Noël 4 s, écran bleu 3 s, vacances 3 s, noir 2 s."""
    d = tmp_path_factory.mktemp("cassette")
    f = d / "cassette 1988.mp4"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x240:r=25:d=2,noise=alls=100:allf=t+u",
       "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=4",
       "-f", "lavfi", "-i", "color=c=0x1030c8:s=320x240:r=25:d=3",
       "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=3,hue=s=0",
       "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=2",
       "-f", "lavfi", "-i", "sine=f=300:sample_rate=48000:d=14",
       "-filter_complex", "[0:v][1:v][2:v][3:v][4:v]concat=n=5:v=1:a=0,format=yuv420p[v]",
       "-map", "[v]", "-map", "5:a", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-shortest", str(f))
    return f


def test_separer_une_cassette(tools, cassette):
    avant = hashlib.sha256(cassette.read_bytes()).hexdigest()
    passages, duree = vides.detecter_tout(tools.ffmpeg.path, cassette, 14.0)
    films = partage.films_separables(vides.a_garder(passages, duree), duree, film_min=1.0)
    assert len(films) == 2
    sortis = partage.separer(tools.ffmpeg.path, cassette, films, ["Noël 1988", "Vacances: été"], True, duree=duree)
    assert [p.name for p in sortis] == ["Noël 1988.mp4", "Vacances été.mp4"]
    for p, attendu in zip(sortis, (4.0, 3.0)):
        d = _sonde(tools, p)
        assert abs(float(d["format"]["duration"]) - attendu) < 0.4, (p.name, d["format"]["duration"])
        assert {s["codec_type"] for s in d["streams"]} == {"video", "audio"}
    assert _sonde(tools, sortis[0])["format"]["tags"]["title"] == "Noël 1988"
    assert hashlib.sha256(cassette.read_bytes()).hexdigest() == avant             # l'original reste entier
    assert partage.films_separables(vides.a_garder(passages, duree), duree) == []   # 20 s minimum par défaut


def test_nommer_un_film(tools, restaure, tmp_path):
    src = tmp_path / "DVD_041544_0_restaure_equilibre.mp4"
    src.write_bytes(restaure.read_bytes())
    wav = src.with_suffix(".wav")
    wav.write_bytes(b"RIFF son")
    (tmp_path / "Noël 1988.mp4").write_bytes(b"un autre film")                   # déjà pris : pas écrasé
    out = partage.nommer(tools.ffmpeg.path, src, "Noël 1988", "1988-12-25", annexes=[wav])
    assert out.name == "Noël 1988 (2).mp4" and not src.exists()
    assert (tmp_path / "Noël 1988.mp4").read_bytes() == b"un autre film"
    assert out.with_suffix(".wav").read_bytes() == b"RIFF son" and not wav.exists()
    tags = _sonde(tools, out)["format"]["tags"]
    assert tags["title"] == "Noël 1988" and tags["date"].startswith("1988")
    assert abs(float(_sonde(tools, out)["format"]["duration"]) - 6) < 0.2         # recopié tel quel


def test_nommer_protege_l_original(tools, tmp_path):
    src = tmp_path / "Noël.mp4"
    src.write_bytes(b"original")
    with pytest.raises(ToolError, match="origine"):
        partage.nommer(tools.ffmpeg.path, src, "Noël 1988", original=src)
    with pytest.raises(ToolError, match="vide"):
        partage.nommer(tools.ffmpeg.path, src, "  ?? ")
    assert src.read_bytes() == b"original"


def test_nommer_une_photo(tools, tmp_path):
    src = tmp_path / "IMG_0001_restaure_equilibre.png"
    ff("-f", "lavfi", "-i", "color=c=red:s=64x48", "-frames:v", "1", "-update", "1", str(src))
    out = partage.nommer(tools.ffmpeg.path, src, "Mamie au jardin")
    assert out == tmp_path / "Mamie au jardin.png" and out.is_file() and not src.exists()


@pytest.mark.parametrize("texte,attendu", [
    ("", ""), ("1988", "1988"), ("12/1988", "1988-12"), ("25/12/1988", "1988-12-25"), ("25.12.1988", "1988-12-25"),
    ("1988-12-25", "1988-12-25"), (" 5 / 7 / 1990 ", "1990-07-05"), ("31/02/1988", None), ("1700", None),
    ("Noël", None)])
def test_date_comprise(texte, attendu):
    assert partage.date_iso(texte) == attendu


def test_separer_refuse_s_il_manque_de_la_place(tools, cassette, tmp_path, monkeypatch):
    class _Usage:
        free = 1_000
    monkeypatch.setattr(partage.shutil, "disk_usage", lambda _p: _Usage())
    with pytest.raises(ToolError, match="Espace disque insuffisant"):
        partage.separer(tools.ffmpeg.path, cassette, [(2.0, 6.0), (9.0, 12.0)], ["a", "b"], True,
                        dossier=tmp_path, duree=14.0)
    assert list(tmp_path.iterdir()) == []
