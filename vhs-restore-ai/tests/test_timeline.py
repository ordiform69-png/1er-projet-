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
    assert win._barres() == [win.barre]
    assert win.barre.coupes == win._coupes
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
        if "40" in win.s_compare.accessibleDescription() or "40" in win.s_moment_heure.text():
            break
        time.sleep(0.05)
    texte = win.s_compare.accessibleDescription() + " " + win.s_moment_heure.text()
    assert "40" in texte, (texte, vus)
    win.close()


def test_trio_visible_sans_defilement_horizontal(tools, samples, monkeypatch):
    monkeypatch.setattr(vignettes, "extraire", lambda *_a, **_k: False)
    app, win = _ouvrir(tools, samples)
    try:
        for pct in (100, 150):
            win.resize(1280, 641)
            win.show()
            win.set_taille_texte(pct, annoncer=False)
            app.processEvents()
            bouton, zone = win.sections["Couper le film"]
            if not bouton.isChecked():
                bouton.click()
            app.processEvents()
            zone.ensureWidgetVisible(win.s_couper)
            app.processEvents()
            for w in (win.s_compare, win.barre, win.s_couper):
                assert w.isVisible()
                assert win.rect().contains(w.mapTo(win, w.rect().topLeft()))
                assert win.rect().contains(w.mapTo(win, w.rect().bottomRight()))
            assert win.s_compare.height() >= 180
            assert zone.horizontalScrollBar().maximum() == 0
    finally:
        win.close()


def test_apercu_avance_recoit_limage_du_moment(tools, samples, tmp_path):
    app, win = _ouvrir(tools, samples)
    try:
        img = tmp_path / "moment.png"
        qimg = QImage(16, 12, QImage.Format_RGB32)
        qimg.fill(Qt.red)
        qimg.save(str(img))
        win.preview = None
        win._moment_pret(12, str(img), win._gen_images)
        vue = win.compare
        assert vue._moment is not None and not vue._moment.isNull()
        assert vue.before is None
        assert "12" in vue._moment_texte
    finally:
        win.close()


def test_cinq_films_effacent_les_dossiers(tools, samples, monkeypatch):
    def lent(*args, **kwargs):
        annuler = args[6] if len(args) > 6 else kwargs.get("annuler")
        for _ in range(40):
            if annuler is not None and annuler.is_set():
                return False
            time.sleep(0.02)
        return False

    monkeypatch.setattr(vignettes, "extraire", lent)
    app, win = _ouvrir(tools, samples)
    dossiers = []
    try:
        for nom in ("pal_tff", "prog", "long", "pal_tff", "prog"):
            if win._dossier_images is not None:
                dossiers.append(win._dossier_images)
            win.load_file(str(samples[nom]))
            for _ in range(400):
                app.processEvents()
                if (win.worker is None or not win.worker.isRunning()) and win.info is not None \
                        and win.info.path.name == samples[nom].name:
                    break
                time.sleep(0.02)
    finally:
        if win._dossier_images is not None:
            dossiers.append(win._dossier_images)
        win.close()
        app.processEvents()
    for _ in range(80):
        if dossiers and all(not d.exists() for d in dossiers):
            break
        time.sleep(0.05)
        app.processEvents()
    assert dossiers and all(not d.exists() for d in dossiers), [str(d) for d in dossiers if d.exists()]


def test_sortie_sans_close_ne_plante_pas(samples):
    """Une fenêtre qui n'appelle pas close() ne doit pas tuer le processus (code 134)."""
    import os
    import subprocess
    import sys
    script = r"""
import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from vhs_restore.gui import MainWindow
from vhs_restore.tools import detect_tools
app = QApplication([])
win = MainWindow(detect_tools())
win.load_file(sys.argv[1])
for _ in range(500):
    app.processEvents()
    if win.info is not None and (win.worker is None or not win.worker.isRunning()):
        break
    time.sleep(0.02)
# vignettes peut-être encore en cours : on ne ferme pas
"""
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    r = subprocess.run([sys.executable, "-c", script, str(samples["long"])],
                       cwd=str(Path(__file__).resolve().parent.parent),
                       env=env, capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stderr[-1500:]
    assert "QThread" not in r.stderr
    assert "QThread" not in r.stdout


def test_zoom_et_clavier_sur_trois_heures():
    app = QApplication.instance() or QApplication([])
    barre = BarreFilm()
    barre.resize(540, 64)
    barre.fps = 25
    barre.definir(10_800, 5_400, 0, 0, [(5_399, 5_401), (6_500, 6_502)])
    curseur = barre.position
    for _ in range(16):
        barre.zoomer(1)
    a, b = barre._fenetre()
    assert (a, b) == pytest.approx((5_399, 5_401))
    assert barre._temps(barre._x_de(curseur)) == pytest.approx(curseur)
    assert barre.coupes == [(5_399, 5_401), (6_500, 6_502)]
    assert barre._bord_sous(barre._x_de(6_500)) is None

    positions = []
    barre.clique.connect(positions.append)
    QTest.keyClick(barre, Qt.Key_Left)
    QTest.keyClick(barre, Qt.Key_Right, Qt.ShiftModifier)
    QTest.keyClick(barre, Qt.Key_Right, Qt.ControlModifier)
    assert positions == pytest.approx([5_399, 5_410, 5_400.040])
    barre.zoomer()
    assert barre._fenetre() == (0, 10_800)
    app.processEvents()


@pytest.mark.parametrize("mode", ["clair", "sombre"])
def test_passages_bleus_opaques_sur_les_vignettes(mode):
    from PySide6.QtGui import QColor, QPixmap
    from vhs_restore import theme, vides

    app = QApplication.instance() or QApplication([])
    ancien = theme.MODE
    theme.set_mode(mode)
    barre = BarreFilm()
    try:
        barre.resize(400, 64)
        barre.definir(100, 5, 0, 0, [(55, 65)])
        barre.passages_vides = (vides.Passage(20, 50, "neige ou écran gris"),
                                vides.Passage(50, 85, "écran noir"))
        barre.choisir_passage(barre.passages_vides[0])
        vignette = QPixmap(160, 120)
        vignette.fill(QColor("red"))
        barre.vider_images(4, dict.fromkeys(range(4), vignette))
        image = barre.grab().toImage()
        r = barre._zone()
        for temps, bleu in ((24, "#104596"), (75, "#2165c3")):
            x = round(barre._x_de(temps))
            assert image.pixelColor(x, r.top()) == QColor(bleu)
            assert image.pixelColor(x, r.bottom()) == QColor(bleu)
        assert image.pixelColor(int(barre._x_de(20)), r.center().y()) == QColor("#dbeaff")
        assert image.pixelColor(round(barre._x_de(60)), r.top() + 9) != QColor("#2165c3")
        assert any(image.pixelColor(x, y) == QColor("white")
                   for x in range(round(barre._x_de(26)), round(barre._x_de(44)))
                   for y in range(r.top() + 3, r.bottom() - 2))
    finally:
        barre.close()
        theme.set_mode(ancien)
        app.processEvents()


def test_passage_vide_propose_puis_enleve_et_annule(tools, tmp_path):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QPushButton

    from vhs_restore import vides

    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    try:
        win.info = _info(tmp_path / "Film.mpg", duration=300, fps=Fraction(25))
        win.info.scenes = [SimpleNamespace(debut=0), SimpleNamespace(debut=63.0)]
        win._rafraichir_barre()
        win.barre.resize(500, 64)
        assert win.barre.aimanter(63.2) == 63.0
        assert win.barre.aimanter(65.0) == 65.0

        neige = vides.Passage(60, 63, "neige ou écran gris")
        win.assistant._vides_trouves(([neige], 300))
        assert win.barre.passage_vide is neige
        assert win._coupes == []
        assert win.trim_start.value() == win.trim_end.value() == 0
        enlever = next(b for b in win.findChildren(QPushButton) if b.text() == "Enlever")
        enlever.click()
        assert win._coupes == [(60, 63)]
        assert win.barre.passage_vide is None
        win.s_passage_annuler.click()
        assert win._coupes == []
        assert win.barre.passage_vide is neige
    finally:
        win.close()
        app.processEvents()


def test_vignettes_memorisees_au_retour_au_film_entier(tools, monkeypatch, tmp_path):
    from PySide6.QtGui import QPixmap

    from vhs_restore import gui

    class FabFactice:
        fils = ()

        def __init__(self, *args):
            lots.append((args[3], args[-1]))

        def stop(self):
            pass

        def demander(self, *args):
            pass

    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    lots = []
    monkeypatch.setattr(gui, "_Fab", FabFactice)
    try:
        win.info = _info(tmp_path / "Film.mpg", duration=120)
        win._rafraichir_barre()
        win._lancer_images()
        initial, remis = lots[-1]
        assert initial and not remis
        pixmap = QPixmap(8, 8)
        pixmap.fill(Qt.red)
        win._cache_vignettes.update(dict.fromkeys(initial, pixmap))
        win._lancer_images()
        assert len(lots) == 1

        win.barre.zoomer(1)
        win._lancer_images()
        assert lots[-1][0] != initial
        win.barre.zoomer()
        win._lancer_images()
        assert lots[-1] == (initial, frozenset(range(len(initial))))
        assert all(not p.isNull() for p in win.barre._vignettes)
    finally:
        win.close()
        app.processEvents()
