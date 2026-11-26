"""Copie de lecture désentrelacée : stries, instants, film progressif, annulation."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
from fractions import Fraction
from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from conftest import ff
from vhs_restore import copie_lecture
from vhs_restore.dvd import input_args
from vhs_restore.gui import MainWindow
from vhs_restore.probe import MediaInfo, analyze


def attendre(app, condition, secondes=20):
    limite = time.monotonic() + secondes
    while time.monotonic() < limite:
        app.processEvents()
        if condition():
            return
        time.sleep(0.01)
    assert condition()


def _pair_image(chemin: Path) -> QImage:
    image = QImage(str(chemin))
    assert not image.isNull(), chemin
    return image


def _extraire(ffmpeg: str, source: Path, dest: Path, instant: float, filtre: str | None) -> None:
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
           "-ss", f"{instant:.3f}", "-frames:v", "1"]
    if filtre:
        cmd += ["-vf", filtre]
    cmd.append(str(dest))
    fait = subprocess.run(cmd, capture_output=True, text=True)
    assert fait.returncode == 0, fait.stderr[-500:]


def _luma(image: QImage) -> tuple[bytes, int, int, int]:
    gris = image.convertToFormat(QImage.Format.Format_Grayscale8)
    largeur, hauteur, pas = gris.width(), gris.height(), gris.bytesPerLine()
    brut = bytes(gris.constBits())
    return brut, largeur, hauteur, pas


def _ligne(brut: bytes, pas: int, largeur: int, y: int) -> bytes:
    base = y * pas
    return brut[base:base + largeur]


def ecart_lignes(image: QImage) -> tuple[float, float]:
    """Même mesure que mesure-stries-n13.py : D1 = |ligne 2k − ligne 2k+1|, D2 = |ligne 2k − ligne 2k+2|."""
    brut, largeur, hauteur, pas = _luma(image)
    lignes = [y for y in range(hauteur) if max(_ligne(brut, pas, largeur, y)) >= 128]
    assert len(lignes) >= 40, "barre blanche introuvable"
    y0, y1 = lignes[0], lignes[-1] + 1
    debut = y0 if y0 % 2 == 0 else y0 + 1
    ys = [y for y in range(debut, y1 - 2, 2) if y + 2 < y1]
    assert len(ys) >= 20
    total_1 = total_2 = nombre = 0
    for y in ys:
        a = _ligne(brut, pas, largeur, y)
        b = _ligne(brut, pas, largeur, y + 1)
        c = _ligne(brut, pas, largeur, y + 2)
        for i in range(largeur):
            total_1 += abs(a[i] - b[i])
            total_2 += abs(a[i] - c[i])
            nombre += 1
    return total_1 / nombre, total_2 / nombre


def _mae(a: QImage, b: QImage) -> float:
    a = a.convertToFormat(QImage.Format.Format_RGB888)
    b = b.convertToFormat(QImage.Format.Format_RGB888)
    assert (a.width(), a.height()) == (b.width(), b.height())
    largeur, hauteur = a.width(), a.height()
    pa, pb = a.bytesPerLine(), b.bytesPerLine()
    ba, bb = bytes(a.constBits()), bytes(b.constBits())
    total = 0
    for y in range(hauteur):
        la, lb = ba[y * pa:y * pa + largeur * 3], bb[y * pb:y * pb + largeur * 3]
        total += sum(abs(x - y_) for x, y_ in zip(la, lb))
    return total / (largeur * hauteur * 3)


def _centre_barre(image: QImage) -> float:
    """Centre des colonnes les plus claires : stable quand la barre est un aplat."""
    brut, largeur, hauteur, pas = _luma(image)
    scores = [0] * largeur
    for y in range(hauteur):
        ligne = _ligne(brut, pas, largeur, y)
        for x, valeur in enumerate(ligne):
            scores[x] += valeur
    seuil = max(scores) * 0.5
    xs = [i for i, score in enumerate(scores) if score >= seuil]
    assert xs
    return sum(xs) / len(xs)


def _ecrire_brut(chemin: Path, images: int = 50) -> None:
    """Mire du rapport : barre blanche, champ du temps 2k sur les lignes paires."""
    largeur, hauteur = 720, 576
    with chemin.open("wb") as sortie:
        for k in range(images):
            haut = bytearray(largeur * hauteur)
            bas = bytearray(largeur * hauteur)
            x_haut = (2 * k * 24) % 640
            x_bas = ((2 * k + 1) * 24) % 640
            for y in range(48, 528):
                haut[y * largeur + x_haut:y * largeur + x_haut + 32] = b"\xff" * 32
                bas[y * largeur + x_bas:y * largeur + x_bas + 32] = b"\xff" * 32
            image = haut
            for y in range(1, hauteur, 2):
                debut = y * largeur
                image[debut:debut + largeur] = bas[debut:debut + largeur]
            sortie.write(image)


def ecrire_mire(dossier: Path, ffmpeg: str) -> Path:
    brut = dossier / "mire.gray"
    dest = dossier / "mire entrelacée.avi"
    _ecrire_brut(brut)
    fait = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "gray", "-s", "720x576", "-r", "25", "-i", str(brut),
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-shortest",
         "-vf", "setfield=tff,setsar=16/15,format=yuv420p",
         "-c:v", "mpeg2video", "-b:v", "8M", "-flags", "+ildct+ilme", "-field_order", "tt",
         "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(dest)],
        capture_output=True, text=True)
    assert fait.returncode == 0, fait.stderr[-500:]
    brut.unlink(missing_ok=True)
    return dest


def ecrire_film(dossier: Path, nom: str, duree: float, *, bruit: bool = False) -> Path:
    dest = dossier / nom
    filtre = "setfield=tff,setsar=16/15,format=yuv420p"
    if bruit:
        filtre = "noise=alls=12:allf=t," + filtre
    ff("-f", "lavfi", "-i", f"testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top",
       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
       "-t", str(duree), "-vf", filtre,
       "-c:v", "mpeg2video", "-b:v", "8M", "-flags", "+ildct+ilme", "-field_order", "tt",
       "-c:a", "pcm_s16le", "-shortest", str(dest))
    return dest


def test_taille_garde_le_4_3_des_pixels_16_15():
    info = MediaInfo(path=Path("film.mpg"), width=720, height=576, dar=Fraction(4, 3), scan="tff")
    assert copie_lecture.taille(info) == (720, 540)
    large = MediaInfo(path=Path("large.mpg"), width=720, height=480, dar=Fraction(4, 3), scan="bff")
    assert copie_lecture.taille(large) == (640, 480)
    panoramique = MediaInfo(path=Path("large.mpg"), width=720, height=576, dar=Fraction(16, 9), scan="tff")
    assert copie_lecture.taille(panoramique)[0] == 720
    assert copie_lecture.taille(panoramique)[1] % 2 == 0


def test_la_commande_couvre_tout_le_titre_dvd(tmp_path):
    morceaux = (tmp_path / "VTS_01_1.VOB", tmp_path / "VTS_01_2.VOB")
    for morceau in morceaux:
        morceau.write_bytes(b"")
    info = MediaInfo(path=morceaux[0], parts=morceaux, scan="tff", height=576, dar=Fraction(4, 3),
                     fps=Fraction(25), duration=8, has_audio=True)
    cmd = copie_lecture.commande("ffmpeg", info, tmp_path / "lecture.mp4")
    assert cmd[cmd.index("-f") + 1] == "concat"
    assert "bwdif=mode=send_frame:parity=tff" in " ".join(cmd)
    assert "veryfast" in cmd and "aac" in cmd and "-aac_coder" in cmd
    assert input_args(info)[0] == "-f"


def test_pas_assez_de_place_ne_fabrique_rien(tmp_path, monkeypatch):
    info = MediaInfo(path=tmp_path / "film.mpg", scan="tff", height=576, dar=Fraction(4, 3),
                     duration=3600, fps=Fraction(25))
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: shutil._ntuple_diskusage(0, 0, 10))
    assert copie_lecture.assez_de_place(info, tmp_path) is False
    dest = tmp_path / "lecture.mp4"
    assert copie_lecture.preparer("ffmpeg", info, dest, threading.Event()) is False
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []


def test_film_progressif_sans_copie(tools, samples):
    info = analyze(samples["prog"], tools)
    assert info.scan == "progressive"
    app = QApplication.instance() or QApplication([])
    avant = set(Path(tempfile.gettempdir()).glob("vhsrestore_lecture_*"))
    statut = ""
    win = MainWindow(tools)
    try:
        win.load_file(str(samples["prog"]))
        attendre(app, lambda: win.info is not None and not (win.worker and win.worker.isRunning()))
        for _ in range(30):
            app.processEvents()
            time.sleep(0.02)
        statut = win.status.text()
        assert win._copie is None and win._dossier_copie is None and win._copie_prete is None
        assert set(Path(tempfile.gettempdir()).glob("vhsrestore_lecture_*")) == avant
        assert "Vidéo analysée" in statut
        assert "copie" not in statut.lower()
    finally:
        win.close()
        app.processEvents()


def test_sans_place_lecran_reste_utilisable(tools, samples, monkeypatch):
    monkeypatch.setattr(copie_lecture, "assez_de_place", lambda *_a, **_k: False)
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    try:
        win.load_file(str(samples["pal_tff"]))
        attendre(app, lambda: win.info is not None and not (win.worker and win.worker.isRunning()))
        for _ in range(20):
            app.processEvents()
            time.sleep(0.02)
        assert win.info.scan in ("tff", "bff")
        assert win._copie is None and win._dossier_copie is None
        assert "Vidéo analysée" in win.status.text()
        win.lire_film.click()
        attendre(app, lambda: win.lecteur.actif and win.lecteur.media is not None)
        assert Path(win.lecteur.media.source().toLocalFile()).name == samples["pal_tff"].name
    finally:
        win.close()
        app.processEvents()


@pytest.fixture(scope="module")
def mire(tmp_path_factory, tools):
    dossier = tmp_path_factory.mktemp("mire-copie")
    chemin = ecrire_mire(dossier, tools.ffmpeg.path)
    info = analyze(chemin, tools)
    assert info.scan == "tff", (info.scan, info.idet, info.field_order_meta)
    return chemin, info


def test_la_copie_nest_pas_striee_alors_que_loriginal_lest(tmp_path, tools, mire):
    chemin, info = mire
    dest = tmp_path / "lecture.mp4"
    assert copie_lecture.preparer(tools.ffmpeg.path, info, dest, threading.Event())
    instant = 0.72
    originale = tmp_path / "originale.png"
    copie = tmp_path / "copie.png"
    _extraire(tools.ffmpeg.path, chemin, originale, instant, None)
    _extraire(tools.ffmpeg.path, dest, copie, instant, None)
    d1_original, d2_original = ecart_lignes(_pair_image(originale))
    d1_copie, d2_copie = ecart_lignes(_pair_image(copie))
    print(f"STRIES original D1={d1_original:.2f} D2={d2_original:.2f} "
          f"copie D1={d1_copie:.2f} D2={d2_copie:.2f}")
    assert d1_original > 8, (d1_original, d2_original)
    assert d1_copie < 2.5, (d1_copie, d2_copie)
    assert d1_original > d1_copie * 5


def test_meme_image_aux_memes_instants(tmp_path, tools, mire):
    chemin, info = mire
    dest = tmp_path / "lecture.mp4"
    assert copie_lecture.preparer(tools.ffmpeg.path, info, dest, threading.Event())
    duree_copie = analyze(dest, tools)
    assert duree_copie.duration == pytest.approx(info.duration, abs=0.08)
    assert duree_copie.has_audio and copie_lecture.taille(info) == (duree_copie.width, duree_copie.height)
    filtre = copie_lecture.filtre(info)
    for instant in (0.24, 0.72, 1.20):
        reference = tmp_path / f"ref-{instant:.2f}.png"
        image = tmp_path / f"copie-{instant:.2f}.png"
        _extraire(tools.ffmpeg.path, chemin, reference, instant, filtre)
        _extraire(tools.ffmpeg.path, dest, image, instant, None)
        ref, cop = _pair_image(reference), _pair_image(image)
        ecart = _mae(ref, cop)
        print(f"IMAGE t={instant:.2f} mae={ecart:.2f} "
              f"centre={_centre_barre(ref):.1f}/{_centre_barre(cop):.1f}")
        assert ecart < 12, (instant, ecart)
        assert abs(_centre_barre(ref) - _centre_barre(cop)) <= 6, instant


def _job_en_cours(win) -> bool:
    job = win._copie
    return job is not None and any(proc.poll() is None for proc in job.procs)


def test_changement_de_film_arrete_et_ne_laisse_rien(tmp_path, tools, samples, monkeypatch):
    source = ecrire_film(tmp_path, "long entrelacé.avi", 40)
    commandes: list[list[str]] = []
    lancer = copie_lecture._lancer

    def noter(cmd):
        commandes.append(list(cmd))
        return lancer(cmd)

    monkeypatch.setattr(copie_lecture, "_lancer", noter)
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    dossier = None
    proc = None
    try:
        win.load_file(str(source))
        attendre(app, lambda: win.info is not None and not (win.worker and win.worker.isRunning()), 60)
        assert win.info.scan == "tff"
        attendre(app, lambda: _job_en_cours(win), 20)
        job = win._copie
        dossier = win._dossier_copie
        proc = next(item for item in job.procs if item.poll() is None)
        assert commandes, "FFmpeg n'a pas été lancé"
        ligne = " ".join(commandes[-1])
        assert "bwdif=mode=send_frame" in ligne
        assert "veryfast" in ligne and "aac" in ligne
        assert dossier is not None and dossier.is_dir()
        win.load_file(str(samples["prog"]))
        attendre(app, lambda: win.info is not None and win.info.path.name == samples["prog"].name
                 and not (win.worker and win.worker.isRunning()), 60)
        attendre(app, lambda: proc.poll() is not None and not dossier.exists(), 15)
        assert win._copie is None and win._dossier_copie is None and win._copie_prete is None
        assert not dossier.exists()
    finally:
        win.close()
        app.processEvents()
        if proc is not None and proc.poll() is None:
            proc.kill()
        if dossier is not None and dossier.exists():
            shutil.rmtree(dossier, ignore_errors=True)


def test_la_lecture_passe_sur_la_copie_sans_s_arreter(tmp_path, tools):
    source = ecrire_film(tmp_path, "lecture.mkv", 12)
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    try:
        win.load_file(str(source))
        attendre(app, lambda: win.info is not None and not (win.worker and win.worker.isRunning()), 60)
        win.lire_film.click()
        attendre(app, lambda: win.lecteur.actif and win.lecteur.joue)
        from PySide6.QtMultimedia import QMediaPlayer
        origine = source.name
        vu_original = False
        bascule = None
        position_originale = 0
        limite = time.monotonic() + 20
        while time.monotonic() < limite and bascule is None:
            app.processEvents()
            media = win.lecteur.media
            if media is None or not win.lecteur.actif:
                time.sleep(0.01)
                continue
            nom = Path(media.source().toLocalFile()).name
            joue = media.playbackState() == QMediaPlayer.PlayingState
            pos = media.position()
            if nom == origine and joue:
                vu_original = True
                position_originale = pos
            elif nom == "lecture.mp4" and vu_original and position_originale > 200 and joue:
                if abs(pos - position_originale) < 1000:
                    bascule = (position_originale, pos)
            time.sleep(0.01)
        assert vu_original and bascule is not None, (vu_original, position_originale, bascule)
        assert win.lecteur.mode == "original"
        assert win.lecteur.media.playbackState() == QMediaPlayer.PlayingState
        assert "copie" not in win.status.text().lower()
    finally:
        win.close()
        app.processEvents()


def test_vitesse_de_preparation(tmp_path, tools):
    source = ecrire_film(tmp_path, "vitesse.avi", 8, bruit=True)
    info = analyze(source, tools)
    assert info.scan == "tff"
    assert (info.width, info.height) == (720, 576)
    dest = tmp_path / "lecture.mp4"
    debut = time.perf_counter()
    assert copie_lecture.preparer(tools.ffmpeg.path, info, dest, threading.Event())
    ecoule = time.perf_counter() - debut
    images = int(round(float(info.fps) * info.duration))
    par_seconde = images / ecoule
    heure = ecoule / info.duration * 3600
    texte = (
        f"images={images} duree_s={info.duration:.3f} ecoule_s={ecoule:.3f} "
        f"images_par_seconde={par_seconde:.1f} secondes_pour_une_heure={heure:.1f} "
        f"machine={platform.platform()} processeur={platform.processor() or platform.machine()} "
        f"coeurs={os.cpu_count()} ffmpeg={tools.ffmpeg.version}"
    )
    print("VITESSE " + texte)
    Path("/tmp/vhs-vitesse-copie.txt").write_text(texte + "\n", encoding="utf-8")
    assert par_seconde > 1
