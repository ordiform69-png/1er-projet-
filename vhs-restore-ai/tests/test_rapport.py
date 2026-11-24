"""Rapport pour le fils : zip sans film ni photo, Bureau absent → Documents."""
from pathlib import Path

from vhs_restore import rapport


def test_zip_sans_media(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()
    log = tmp_path / "vhs_restore.log"
    log.write_text("erreur de test\n", encoding="utf-8")
    film = tmp_path / "film.mp4"
    film.write_bytes(b"video")
    dest, msg = rapport.preparer_rapport([log, film], None, "test", "ffmpeg: ok")
    assert dest.parent == tmp_path / "Desktop"
    assert "Bureau" in msg
    assert rapport.zip_sans_media(dest)
    noms = __import__("zipfile").ZipFile(dest).namelist()
    assert "vhs_restore.log" in noms
    assert "film.mp4" not in noms


def test_bureau_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / "Documents").mkdir()
    dest, msg = rapport.preparer_rapport([], None, "test", "ok")
    assert dest.parent == tmp_path / "Documents"
    assert "Documents" in msg
