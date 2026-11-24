"""Photos : redresser puis enlever le bord ; tours de 90° ; EXIF une seule fois."""
import struct
import subprocess
from pathlib import Path

from conftest import ff
from vhs_restore import photo, pipeline
from vhs_restore.profiles import profile_for


def _jpeg_orientation(src: Path, dest: Path, orientation: int) -> None:
    """Pose l'orientation EXIF (1, 3, 6, 8) sans réencoder les pixels."""
    data = src.read_bytes()
    assert data[:2] == b"\xff\xd8"
    # TIFF little-endian, un seul IFD, tag Orientation
    tiff = struct.pack("<HHIH", 0x4949, 42, 8, 1)
    tiff += struct.pack("<HHII", 0x0112, 3, 1, orientation)
    tiff += struct.pack("<I", 0)
    payload = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    dest.write_bytes(data[:2] + app1 + data[2:])


def _photo_bord_incline(dest: Path) -> None:
    ff("-f", "lavfi", "-i", "testsrc2=size=400x300:rate=1", "-frames:v", "1",
       "-vf", "pad=480:380:40:40:white,rotate=4*PI/180:fillcolor=white:ow=iw:oh=ih",
       str(dest))


def _photo_droite(dest: Path) -> None:
    ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=1", "-frames:v", "1", str(dest))


def test_bord_blanc_et_inclinaison(tools, tmp_path):
    src = tmp_path / "incline.png"
    _photo_bord_incline(src)
    a = photo.analyser_scanner(src, tools)
    assert a.cocher and a.border == "white"
    assert 2.5 <= abs(a.tilt) <= 6.0
    info = photo.analyze_photo(src, tools)
    s = pipeline.Settings(profile_for("fidele"), redresser=True)
    out = photo.restore_photo(info, s, tmp_path / "out.png", tools)
    residuel = photo.analyser_scanner(out, tools)
    assert abs(residuel.tilt) < 0.5
    assert residuel.border == "" or not residuel.cocher


def test_photo_droite_inchangee(tools, tmp_path):
    src = tmp_path / "droite.png"
    _photo_droite(src)
    a = photo.analyser_scanner(src, tools)
    assert not a.cocher and abs(a.tilt) < 0.5
    info = photo.analyze_photo(src, tools)
    avant = src.read_bytes()
    s = pipeline.Settings(profile_for("fidele"), redresser=False)
    out = photo.restore_photo(info, s, tmp_path / "out.png", tools)
    assert src.read_bytes() == avant
    # même dimensions
    assert photo.analyze_photo(out, tools).width == 320


def test_exif_orientation_6_pas_double(tools, tmp_path):
    """Orientation 6 = 90° horaire. Appliquée une fois, pas deux."""
    base = tmp_path / "base.jpg"
    ff("-f", "lavfi", "-i", "testsrc2=size=200x100:rate=1", "-frames:v", "1",
       "-q:v", "2", str(base))
    marque = tmp_path / "ori6.jpg"
    _jpeg_orientation(base, marque, 6)
    info = photo.analyze_photo(marque, tools)
    s = pipeline.Settings(profile_for("fidele"), redresser=False, photo_quarts=0)
    out0 = photo.restore_photo(info, s, tmp_path / "sans.png", tools)
    i0 = photo.analyze_photo(out0, tools)
    assert (i0.width, i0.height) == (100, 200)          # orientation 6 appliquée une fois
    s2 = pipeline.Settings(profile_for("fidele"), redresser=False, photo_quarts=1)
    out1 = photo.restore_photo(info, s2, tmp_path / "gauche.png", tools)
    i1 = photo.analyze_photo(out1, tools)
    assert (i1.width, i1.height) == (200, 100)          # un tour de plus, pas deux
    s3 = pipeline.Settings(profile_for("fidele"), redresser=False, photo_quarts=3)
    out2 = photo.restore_photo(info, s3, tmp_path / "droite.png", tools)
    i2 = photo.analyze_photo(out2, tools)
    assert (i2.width, i2.height) == (200, 100)
