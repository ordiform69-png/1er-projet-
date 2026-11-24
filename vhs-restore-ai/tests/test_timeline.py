"""Timeline : petites images sur la barre, image du moment, écran jamais bloqué."""
import time
from fractions import Fraction
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QPoint  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from vhs_restore.gui import BarreFilm, MainWindow  # noqa: E402
from vhs_restore.probe import MediaInfo  # noqa: E402
from vhs_restore import vignettes  # noqa: E402


def _info(path: Path, **kw) -> MediaInfo:
    base = dict(duration=8, width=160, height=120, sar=Fraction(1), dar=Fraction(4, 3),
                scan="progressive")
    base.update(kw)
    return MediaInfo(path=path, **base)


def _teinte(path: Path) -> str:
    img = QImage(str(path))
    c = img.pixelColor(img.width() // 2, img.height() // 2)
    r, g, b = c.red(), c.green(), c.blue()
    if r > 180 and g > 180 and b < 80:
        return "jaune"
    if r > 180 and g < 100 and b < 100:
        return "rouge"
    if g > 160 and r < 120 and b < 120:
        return "vert"
    if b > 160 and r < 100 and g < 120:
        return "bleu"
    return f"{r},{g},{b}"


def test_instants_suivent_la_largeur_pas_la_duree():
    court = vignettes.instants(8, 400)
    long = vignettes.instants(7200, 400)
    assert len(court) == len(long) == 400 // vignettes.PAS_PX
    assert court[0] < court[-1]
    assert vignettes.instants(0, 800) == []
    assert vignettes.instants(4, 800)  # très court : au moins une image, pas de plantage
    assert len(vignettes.instants(4, 800)) <= 4


def test_filtre_entrelace_et_format():
    progressif = _info(Path("a.mpg"), scan="progressive", dar=Fraction(4, 3))
    assert "bwdif" not in vignettes.filtre(progressif, 96, 72)
    tff = _info(Path("a.mpg"), scan="tff", width=720, height=576, sar=Fraction(16, 15), dar=Fraction(4, 3))
    f = vignettes.filtre(tff, *vignettes.taille(tff, 72))
    assert "bwdif=mode=send_frame:parity=tff" in f
    assert "setsar=1" in f
    w, h = vignettes.taille(tff, 72)
    assert h == 72 and abs(w / h - 4 / 3) < 0.05
    cmd = vignettes.commande("ffmpeg", tff, 12.5, Path("out.png"), w, h)
    assert cmd.index("-ss") < cmd.index("-i")
    assert "-an" in cmd and "1" in cmd


def test_dvd_couvre_tout_le_titre(tmp_path):
    a, b = tmp_path / "VTS_01_1.VOB", tmp_path / "VTS_01_2.VOB"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    info = _info(a, parts=(a, b))
    args = vignettes.entree(info)
    assert args[:3] == ["-f", "concat", "-safe"]
    assert "0" in args and "-i" in args


def test_vignettes_dans_l_ordre(tmp_path, tools):
    film = tmp_path / "bandes.mpg"
    ff = tools.ffmpeg.path
    import subprocess
    r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=red:s=160x120:r=25:d=2",
                        "-f", "lavfi", "-i", "color=c=lime:s=160x120:r=25:d=2",
                        "-f", "lavfi", "-i", "color=c=blue:s=160x120:r=25:d=2",
                        "-f", "lavfi", "-i", "color=c=yellow:s=160x120:r=25:d=2",
                        "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0",
                        "-c:v", "mpeg2video", str(film)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
    info = _info(film, duration=8)
    moments = vignettes.instants(8, 360)          # 4 images, centres 1, 3, 5, 7 s
    assert len(moments) == 4
    vues = []
    for i, t in enumerate(moments):
        dest = tmp_path / f"v{i}.png"
        assert vignettes.extraire(ff, info, t, dest, 96, 72)
        vues.append(_teinte(dest))
    assert vues == ["rouge", "vert", "bleu", "jaune"], vues


def _ouvrir(tools, samples, nom="long"):
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.load_file(str(samples[nom]))
    for _ in range(600):
        app.processEvents()
        if win.info is not None and (win.worker is None or not win.worker.isRunning()):
            break
        time.sleep(0.05)
    assert win.worker is None or not win.worker.isRunning()
    assert win.info is not None
    return app, win


def test_clic_pendant_les_images(tools, samples, monkeypatch):
    """L'extraction ne passe pas par le fil de restauration : un clic répond tout de suite."""
    def lent(*_a, **_k):
        time.sleep(0.4)
        return False
    monkeypatch.setattr(vignettes, "extraire", lent)
    app, win = _ouvrir(tools, samples)
    try:
        assert win.worker is None or not win.worker.isRunning()
        barre = win.findChild(BarreFilm)
        assert barre is win.barre and barre.duree > 0
        QTest.mouseClick(barre, Qt.LeftButton, Qt.NoModifier,
                         QPoint(max(8, barre.width() // 2), max(8, barre.height() // 2)))
        app.processEvents()
        assert "Vous êtes à" in win.status.text(), win.status.text()
    finally:
        win.close()
        app.processEvents()


def test_changer_de_film_efface_le_dossier(tools, samples, monkeypatch):
    def noter(*_a, **_k):
        return False

    monkeypatch.setattr(vignettes, "extraire", noter)
    app, win = _ouvrir(tools, samples)
    try:
        dossier = win._dossier_images
        assert dossier is not None and dossier.is_dir()
        assert dossier.parent != samples["long"].parent
        win.load_file(str(samples["pal_tff"]))
        for _ in range(600):
            app.processEvents()
            if (win.worker is None or not win.worker.isRunning()) and win.info is not None \
                    and win.info.path.name == samples["pal_tff"].name:
                break
            time.sleep(0.05)
        for _ in range(60):
            if not dossier.exists():
                break
            time.sleep(0.05)
        assert not dossier.exists()
    finally:
        win.close()
        app.processEvents()


def test_deux_barres_meme_coupe(tools, samples, monkeypatch):
    monkeypatch.setattr(vignettes, "extraire", lambda *_a, **_k: False)
    app, win = _ouvrir(tools, samples)
    win._coupes = [(10.0, 25.0)]
    win._rafraichir_barre()
    assert win.barre.coupes == [(10.0, 25.0)]
    assert win.barre_avancee.coupes == win.barre.coupes
    assert win.barre_avancee is not win.barre
    win.close()


def test_derniere_demande_gagne(tools, samples, monkeypatch):
    vus = []

    def note(_ff, _info, instant, dest, *_a, **_k):
        vus.append(instant)
        img = QImage(8, 8, QImage.Format_RGB32)
        img.fill(Qt.red)
        img.save(str(dest))
        time.sleep(0.05)
        return True

    monkeypatch.setattr(vignettes, "extraire", note)
    app, win = _ouvrir(tools, samples)
    win._demander_moment()
    win.start_spin.setValue(40)
    win._demander_moment()
    for _ in range(80):
        app.processEvents()
        if "40" in win.s_moment.accessibleName() or "40" in win.s_moment_heure.text():
            break
        time.sleep(0.05)
    texte = win.s_moment.accessibleName() + " " + win.s_moment_heure.text()
    assert "40" in texte, (texte, vus)
    win.close()


def test_trio_visible_sans_defilement_horizontal(tools, samples, monkeypatch):
    monkeypatch.setattr(vignettes, "extraire", lambda *_a, **_k: False)
    app, win = _ouvrir(tools, samples)
    win.resize(1280, 641)
    win.show()
    app.processEvents()
    zone = win.pages.widget(0)
    zone.widget().layout().activate()
    zone.ensureWidgetVisible(win.s_couper, 0, 12)
    app.processEvents()
    vue = zone.viewport().rect()
    for w in (win.s_moment, win.barre, win.s_couper):
        coin = w.mapTo(zone.viewport(), w.rect().topLeft())
        assert coin.x() >= -2
        assert coin.x() + w.width() <= vue.width() + 2
    haut = win.s_moment.mapTo(zone.viewport(), QPoint(0, 0)).y()
    bas = win.s_couper.mapTo(zone.viewport(), QPoint(0, win.s_couper.height())).y()
    assert 0 <= haut < bas <= vue.height() + 2
    assert zone.horizontalScrollBar().maximum() == 0
    win.close()
