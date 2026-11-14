"""Restauration d'un dossier entier (mode simple)."""
import shutil

import pytest

from conftest import probe_json
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
    res = pipeline.restore_folder(tmp_path, tools, auto)
    assert res.out_dir == tmp_path / "Films restaurés"
    names = sorted(p.name for p in res.done)
    assert len(names) == 2 and any("_film" in n for n in names)
    assert [e[0] for e in res.errors] == ["abîmé.avi"]
    film = next(p for p in res.done if "_film" in p.name)
    v = next(x for x in probe_json(film)["streams"] if x["codec_type"] == "video")
    assert v["avg_frame_rate"] == "18/1"                     # pellicule non désentrelacée
    again = pipeline.restore_folder(tmp_path, tools, auto)    # les sorties ne sont pas retraitées
    assert len(again.done) == 2 and all("(2)" in p.name for p in again.done)


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
