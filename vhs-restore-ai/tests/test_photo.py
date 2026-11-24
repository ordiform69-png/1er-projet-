"""Mode Photo : JPEG très compressé (blocs) et photo noir et blanc, de synthèse."""
import hashlib
import json
import re
import shutil
import subprocess

import pytest

from conftest import ff
from vhs_restore import pipeline, photo
from vhs_restore.profiles import profile_for
from vhs_restore.tools import ToolError


@pytest.fixture(scope="module")
def images(tmp_path_factory):
    d = tmp_path_factory.mktemp("photos de famille")
    clean = d / "propre.png"
    ff("-f", "lavfi", "-i", "mandelbrot=size=640x480", "-frames:v", "1", str(clean))
    jpeg = d / "carte postale été.jpg"
    ff("-i", str(clean), "-q:v", "28", str(jpeg))                    # compression forte : blocs 8x8
    nb = d / "photo noir et blanc.jpg"
    ff("-i", str(clean), "-vf", "format=gray", "-q:v", "10", str(nb))
    return {"clean": clean, "jpeg": jpeg, "nb": nb}


def props(p):
    s = json.loads(subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_streams", "-of", "json", str(p)],
                                  capture_output=True, text=True).stdout)["streams"][0]
    return s["width"], s["height"], s["pix_fmt"]


def psnr(a, b):
    t = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(a), "-i", str(b), "-lavfi",
                        "[0:v]format=gray[x];[1:v]format=gray,scale=640:480[y];[y][x]psnr", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return float(re.findall(r"average:([\d.]+)", t)[-1])


def test_analysis(images, tools):
    assert photo.is_photo(images["jpeg"]) and not photo.is_photo("film.avi")
    c = photo.analyze_photo(images["jpeg"], tools)
    assert (c.width, c.height) == (640, 480) and not c.black_and_white and not c.has_audio
    assert photo.analyze_photo(images["nb"], tools).black_and_white
    with pytest.raises(ToolError):
        photo.analyze_photo(images["clean"].with_name("absente.jpg"), tools)


@pytest.mark.parametrize("key,size", [("fidele", (640, 480)), ("equilibre", (640, 480)), ("maximum", (1280, 960))])
def test_profiles(images, tools, tmp_path, key, size):
    before = hashlib.sha256(images["jpeg"].read_bytes()).hexdigest()
    info = photo.analyze_photo(images["jpeg"], tools)
    s = pipeline.Settings(profile_for(key))
    out = photo.restore_photo(info, s, photo.output_path(info, s, tmp_path), tools)
    assert out.suffix == ".png" and props(out)[:2] == size
    assert hashlib.sha256(images["jpeg"].read_bytes()).hexdigest() == before          # original intact
    assert not list(tmp_path.glob("*.partiel*"))


def test_deblocking_brings_closer_to_clean(images, tools, tmp_path):
    info = photo.analyze_photo(images["jpeg"], tools)
    out = photo.restore_photo(info, pipeline.Settings(profile_for("fidele")), tmp_path / "f.png", tools)
    assert psnr(out, images["clean"]) > psnr(images["jpeg"], images["clean"])        # blocs atténués


def test_black_and_white_stays_gray(images, tools, tmp_path):
    info = photo.analyze_photo(images["nb"], tools)
    out = photo.restore_photo(info, pipeline.Settings(profile_for("equilibre")), tmp_path / "nb.png", tools)
    assert props(out)[2] == "gray"                                                    # aucune couleur ajoutée


def test_never_overwrites(images, tools, tmp_path):
    info = photo.analyze_photo(images["jpeg"], tools)
    s = pipeline.Settings(profile_for("fidele"))
    first = photo.output_path(info, s, tmp_path)
    first.write_bytes(b"x")
    assert "(2)" in photo.output_path(info, s, tmp_path).name
    with pytest.raises(ToolError):
        photo.restore_photo(info, s, images["jpeg"], tools)


def test_preview_and_folder(images, tools, tmp_path):
    info = photo.analyze_photo(images["jpeg"], tools)
    r = photo.make_photo_preview(info, pipeline.Settings(profile_for("maximum")), tools, tmp_path / "ap")
    w, h, _ = props(r.compare)
    assert (w, h) == (2560, 960)                                     # avant | après, même taille
    folder = tmp_path / "album"
    folder.mkdir()
    shutil.copy(images["jpeg"], folder)
    shutil.copy(images["nb"], folder)
    auto = lambda i: pipeline.Settings(profile_for("equilibre"))
    res = pipeline.restore_folder(folder, tools, auto)
    assert len(res.done) == 2 and all(p.suffix == ".png" for p in res.done)
    again = pipeline.restore_folder(folder, tools, auto)
    assert again.done == [] and len(again.skipped) == 2              # relance : rien n'est refait


def test_lot_homonymes_et_reglages(images, tools, tmp_path):
    import shutil
    from dataclasses import replace
    shutil.copy(images["jpeg"], tmp_path / "Noel.jpg")
    ff("-i", str(images["jpeg"]), str(tmp_path / "Noel.png"))
    def lot(decalage):
        return pipeline.restore_folder(tmp_path, tools, lambda _: replace(
            pipeline.Settings(profile_for("fidele")), audio_offset_ms=decalage))
    assert len(lot(0).done) == 2
    assert len(lot(0).skipped) == 2
    assert len(lot(100).done) == 2
