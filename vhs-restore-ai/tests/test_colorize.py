"""Colorisation facultative des photos noir et blanc.

Sans le modèle (130 Mo, non livré dans le dépôt), un faux modèle renvoie une couleur
constante : on vérifie tout le reste (luminance gardée, copie EN PLUS, noir et blanc conservé,
original intact, rien d'écrasé). Avec VHSRA_DDCOLOR pointant vers le vrai modèle, un test
supplémentaire vérifie que l'IA ajoute bien de la couleur.
"""
import dataclasses
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from conftest import ff  # noqa: E402
from vhs_restore import colorize, photo, pipeline  # noqa: E402
from vhs_restore.profiles import profile_for  # noqa: E402
from vhs_restore.tools import Tool, ToolError  # noqa: E402


class _FakeInput:
    name = "input"


class _FakeSession:
    """Couleur constante (a=20, b=-30 : un bleu-violet) à la place de l'IA."""

    def get_inputs(self):
        return [_FakeInput()]

    def run(self, _out, feeds):
        x = feeds["input"]
        assert x.shape == (1, 3, 512, 512) and x.dtype == np.float32
        ab = np.empty((1, 2, 512, 512), dtype=np.float32)
        ab[:, 0], ab[:, 1] = 20.0, -30.0
        return [ab]


@pytest.fixture()
def fake_model(tmp_path, monkeypatch, tools):
    m = tmp_path / "modele.onnx"
    m.write_bytes(b"faux")
    monkeypatch.setattr(colorize, "_session", lambda _p: _FakeSession())
    monkeypatch.setattr(colorize, "_check_model", lambda _p: None)
    t = dataclasses.replace(tools, colorizer=Tool("Colorisation (DDColor)", str(m), "test"))
    return t


@pytest.fixture(scope="module")
def nb_photo(tmp_path_factory):
    d = tmp_path_factory.mktemp("photos noir et blanc")
    p = d / "grand-père 1952.jpg"
    ff("-f", "lavfi", "-i", "mandelbrot=size=600x400", "-frames:v", "1", "-vf", "format=gray", "-q:v", "6", str(p))
    c = d / "couleur.jpg"
    ff("-f", "lavfi", "-i", "mandelbrot=size=600x400", "-frames:v", "1", "-q:v", "6", str(c))
    return {"nb": p, "couleur": c}


def raw(path, fmt):
    r = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(path), "-f", "rawvideo",
                        "-pix_fmt", fmt, "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.uint8)


def L_of_rgb(rgb):
    """L de Lab d'une image sRGB 0..255 (H×W×3)."""
    c = rgb.astype(np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    y = 0.212671 * lin[..., 0] + 0.715160 * lin[..., 1] + 0.072169 * lin[..., 2]
    return np.where(y > 0.008856, 116.0 * np.cbrt(y) - 16.0, 903.3 * y)


def settings(**kw):
    return dataclasses.replace(pipeline.Settings(profile_for("equilibre")), **kw)


def test_gris_sans_couleur_reste_identique():
    g = np.linspace(0, 1, 256, dtype=np.float32)[None, :]
    rgb = colorize.lab_to_rgb(colorize.gray_to_L(g), np.zeros_like(g), np.zeros_like(g))
    assert np.abs(rgb - g[..., None]).max() < 1.0 / 255


def test_copie_coloree_garde_le_dessin(nb_photo, fake_model, tmp_path):
    src = tmp_path / "nb.png"
    ff("-i", str(nb_photo["nb"]), "-vf", "format=gray", str(src))
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    out = colorize.colorize(src, tmp_path / "c.png", fake_model.ffmpeg.path, fake_model.ffprobe.path,
                            Path(fake_model.colorizer.path))
    rgb = raw(out, "rgb24").reshape(400, 600, 3)
    gray = raw(src, "gray").reshape(400, 600)
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
    # même luminance (CIE L) pixel par pixel, hors pixels rognés aux extrêmes
    mid = (gray > 40) & (gray < 215)
    dL = np.abs(L_of_rgb(rgb) - L_of_rgb(np.repeat(gray[..., None], 3, axis=2)))
    assert np.percentile(dL[mid], 99) < 1.5
    # et bien de la couleur : bleu au-dessus du rouge (b négatif)
    assert (rgb[..., 2].astype(int) - rgb[..., 0].astype(int))[mid].mean() > 10


def test_photo_nb_copie_en_plus(nb_photo, fake_model, tmp_path):
    info = photo.analyze_photo(nb_photo["nb"], fake_model)
    before = hashlib.sha256(nb_photo["nb"].read_bytes()).hexdigest()
    s = settings(colorize=True)
    out = photo.restore_photo(info, s, photo.output_path(info, s, tmp_path), fake_model)
    col = photo.colorized_path(out)
    assert out.is_file() and col.is_file() and col.name.endswith("_colorisee_ia.png")
    assert photo.analyze_photo(out, fake_model).black_and_white          # le noir et blanc est gardé
    assert not photo.analyze_photo(col, fake_model).black_and_white
    assert hashlib.sha256(nb_photo["nb"].read_bytes()).hexdigest() == before
    # nouveau passage : les deux noms précédents sont évités, rien n'est écrasé
    out2 = photo.output_path(info, s, tmp_path)
    assert out2 != out and not photo.colorized_path(out2).exists()


def test_rien_par_defaut_ni_pour_une_photo_couleur(nb_photo, fake_model, tmp_path):
    info = photo.analyze_photo(nb_photo["nb"], fake_model)
    out = photo.restore_photo(info, settings(), tmp_path / "a.png", fake_model)
    assert not photo.colorized_path(out).exists()
    cinfo = photo.analyze_photo(nb_photo["couleur"], fake_model)
    out = photo.restore_photo(cinfo, settings(colorize=True), tmp_path / "b.png", fake_model)
    assert not photo.colorized_path(out).exists()


def test_non_installee_ou_nom_pris(nb_photo, tools, fake_model, tmp_path):
    info = photo.analyze_photo(nb_photo["nb"], tools)
    absent = dataclasses.replace(tools, colorizer=Tool("Colorisation (DDColor)"))
    with pytest.raises(ToolError, match="Colorisation"):
        photo.restore_photo(info, settings(colorize=True), tmp_path / "x.png", absent)
    assert not (tmp_path / "x.png").exists()
    pris = tmp_path / "y_colorisee_ia.png"
    pris.write_bytes(b"photo de l'utilisateur")
    out = photo.restore_photo(info, settings(colorize=True), tmp_path / "y.png", fake_model)
    assert out.name == "y (2).png" and photo.colorized_path(out).is_file()
    assert pris.read_bytes() == b"photo de l'utilisateur"


def test_apercu_montre_la_version_coloree(nb_photo, fake_model, tmp_path):
    info = photo.analyze_photo(nb_photo["nb"], fake_model)
    r = photo.make_photo_preview(info, settings(colorize=True), fake_model, tmp_path / "ap")
    assert r.restored.name.endswith("_colorisee_ia.png")
    r2 = photo.make_photo_preview(info, settings(colorize=True), fake_model, tmp_path / "ap")   # relance
    assert r2.restored == r.restored


def test_modele_absent_ou_abime(tmp_path, monkeypatch):
    monkeypatch.setenv("VHSRA_DDCOLOR", str(tmp_path / "absent.onnx"))
    monkeypatch.setattr(colorize, "TOOLS_DIR", tmp_path)
    assert not colorize.detect().ok
    bad = tmp_path / "abime.onnx"
    bad.write_bytes(b"pas un modele")
    with pytest.raises(ToolError, match="abîmé"):
        colorize._check_model(bad)


@pytest.mark.skipif(not os.environ.get("VHSRA_DDCOLOR"), reason="modèle DDColor non fourni (VHSRA_DDCOLOR)")
def test_vrai_modele_ajoute_de_la_couleur(tmp_path, tools):
    model = Path(os.environ["VHSRA_DDCOLOR"])
    src = tmp_path / "nb.png"
    ff("-f", "lavfi", "-i", "testsrc2=size=640x480", "-frames:v", "1", "-vf", "format=gray", str(src))
    out = colorize.colorize(src, tmp_path / "c.png", tools.ffmpeg.path, tools.ffprobe.path, model)
    rgb = raw(out, "rgb24").reshape(480, 640, 3).astype(int)
    sat = (rgb.max(axis=2) - rgb.min(axis=2)).mean()
    assert sat > 8, f"pas de couleur ajoutée (écart moyen {sat:.1f})"
