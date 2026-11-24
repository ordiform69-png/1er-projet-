"""Restauration d'un dossier entier (mode simple)."""
import shutil
from pathlib import Path

import pytest

from conftest import probe_json
from vhs_restore.probe import analyze
from vhs_restore import pipeline
from vhs_restore.profiles import profile_for
from vhs_restore.tools import Cancelled, ToolError


def auto(info):
    src = info.suggested_source
    return pipeline.Settings(profile_for("equilibre", src), source=src, preset="ultrafast")


def test_folder(samples, tools, tmp_path):
    for name in ("pal_tff", "film18", "corrupt"):
        shutil.copy(samples[name], tmp_path)
    (tmp_path / "notes.txt").write_text("pas une vidéo")
    msgs = []
    res = pipeline.restore_folder(tmp_path, tools, auto, progress=lambda f, m: msgs.append(m))
    assert res.out_dir == tmp_path / "Films restaurés"
    names = sorted(p.name for p in res.done)
    assert len(names) == 2 and any("_film" in n for n in names)
    assert [e[0] for e in res.errors] == ["abîmé.avi"]
    assert any(m.startswith("Film ") and " sur " in m and " : " in m for m in msgs)
    film = next(p for p in res.done if "_film" in p.name)
    v = next(x for x in probe_json(film)["streams"] if x["codec_type"] == "video")
    assert v["avg_frame_rate"] == "18/1"                     # pellicule non désentrelacée
    again = pipeline.restore_folder(tmp_path, tools, auto)    # relance : rien n'est refait
    assert again.done == [] and len(again.skipped) == 2
    assert len(list(res.out_dir.glob("*.mp4"))) == 2           # aucune copie « (2) »


def test_empty_folder_and_cancel(samples, tools, tmp_path):
    with pytest.raises(ToolError, match="Aucune vidéo"):
        pipeline.restore_folder(tmp_path, tools, auto)
    shutil.copy(samples["long"], tmp_path)
    import threading
    c = threading.Event()
    threading.Timer(1.0, c.set).start()
    with pytest.raises(Cancelled):
        pipeline.restore_folder(tmp_path, tools, auto, cancel=c)
    assert list((tmp_path / "Films restaurés").iterdir()) == []


def test_read_only_source_goes_to_fallback(samples, tools, tmp_path, monkeypatch):
    """DVD ou clé protégée : simulé (les tests tournent souvent en administrateur)."""
    src, fb = tmp_path / "dvd", tmp_path / "Vidéos" / "Films restaurés"
    src.mkdir()
    shutil.copy(samples["film18"], src)
    monkeypatch.setenv("VHSRA_SORTIE", str(fb))
    real = pipeline.is_writable
    monkeypatch.setattr(pipeline, "is_writable", lambda d: Path(d) != src and real(d))
    assert pipeline.output_dir_for(src) == (fb, True)
    res = pipeline.restore_folder(src, tools, auto)
    assert res.fallback and res.out_dir == fb and len(res.done) == 1
    assert not (src / "Films restaurés").exists() and sorted(p.name for p in src.iterdir()) == \
        [samples["film18"].name]                               # rien écrit sur le « DVD »


def test_disk_space_checked_before_starting(samples, tools, tmp_path, monkeypatch):
    info = analyze(samples["film18"], tools)
    s = pipeline.Settings(profile_for("equilibre", "film"), source="film")
    final, temp = pipeline.disk_needs(info, s)
    assert final > 0 and temp == 0
    assert pipeline.disk_needs(info, pipeline.Settings(s.profile, source="film", dust=True))[1] > final
    monkeypatch.setattr(pipeline.shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(1, 1, 1000))
    with pytest.raises(ToolError, match="Espace disque insuffisant"):
        pipeline.export(info, s, tmp_path / "o.mp4", tools)
    assert list(tmp_path.iterdir()) == []


def test_delai_deuxieme_photo(tmp_path, tools, monkeypatch):
    import subprocess
    from vhs_restore import photo
    from vhs_restore.probe import MediaInfo
    def lire(path, _):
        if path.stem == "2":
            raise subprocess.TimeoutExpired("lecture", 1)
        return MediaInfo(path=path)
    for nom in ("1.png", "2.png", "3.png"):
        (tmp_path / nom).touch()
    monkeypatch.setattr(photo, "analyze_photo", lire)
    monkeypatch.setattr(photo, "restore_photo", lambda i,s,p,t,**kw: p)
    res = pipeline.restore_folder(tmp_path, tools, lambda i: pipeline.Settings(profile_for("fidele")))
    assert len(res.done) == 2 and res.done[-1].name.startswith("3")
    assert res.errors == [("2.png", "La lecture de ce fichier a pris trop de temps.")]
