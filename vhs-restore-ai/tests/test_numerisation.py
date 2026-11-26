"""Contrôle de la numérisation : une copie déjà abîmée est signalée, une copie sans perte ne l'est pas.

Les phrases disent quoi faire. Rien n'est bloquant et le moteur de restauration ne change pas.
"""
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore.advice import (PHRASE_COMPRESSEE, PHRASE_LIGNES, PHRASE_NOIRS, PHRASE_TRAITEE,
                                advise, conseils_numerisation, ligne_assistant)
from vhs_restore.probe import (MediaInfo, _is_crushed, _levels_of, analyze, bits_per_pixel,
                               doubled_line_share, is_low_bitrate_copy, judge_capture, line_shift_stats,
                               video_bitrate_bps)

EXACTE_COMPRESSEE = (
    "Cette copie est déjà compressée : les détails perdus ne reviendront pas. "
    "Si vous avez encore la cassette, une nouvelle numérisation sans compression "
    "donnera un meilleur résultat."
)
CLES_CORRECTION = {"hum", "channel", "clip", "wind", "levels", "cast", "edges"}


def _barre(largeur: int, hauteur: int, decalage) -> bytes:
    """Image grise avec une barre claire. `decalage(y)` la déplace, pour les lignes qui tremblent."""
    buf = bytearray(largeur * hauteur)
    for y in range(hauteur):
        dec = decalage(y)
        for x in range(largeur):
            buf[y * largeur + x] = 220 if abs((x - dec) - largeur // 2) < 3 else 30
    return bytes(buf)


def test_phrase_compressee_exacte():
    assert PHRASE_COMPRESSEE == EXACTE_COMPRESSEE


def test_sans_perte_jamais_compressee():
    for codec in ("ffv1", "huffyuv", "ffvhuff", "rawvideo", "pcm_s16le"):
        assert not is_low_bitrate_copy(codec, 0.01), codec
    assert not is_low_bitrate_copy("dvvideo", 2.4)          # DV : débit large, pas « faible »
    assert not is_low_bitrate_copy("mpeg2video", 0.77)      # 8 Mbit/s en 720×576×25
    assert not is_low_bitrate_copy("h264", None)            # débit inconnu : pas d'alerte
    assert not is_low_bitrate_copy("prores", 0.05)          # codec non jugé : pas d'alerte
    assert is_low_bitrate_copy("mpeg2video", 0.07)
    assert is_low_bitrate_copy("h264", 0.10)
    assert bits_per_pixel(8_000_000, 720, 576, 25) == pytest.approx(8_000_000 / (720 * 576 * 25))


def test_debit_video_retire_le_son_pcm():
    # le flux vidéo est connu : on ne retire rien
    assert video_bitrate_bps(500_000, 2_000_000, 0, 2.0, "pcm_s16le", 48000, 2) == 500_000
    # sinon le fichier entier, moins le PCM stéréo 16 bits (1 536 000 bit/s)
    assert video_bitrate_bps(0, 2_000_000, 0, 2.0, "pcm_s16le", 48000, 2) == 2_000_000 - 1_536_000


def test_pellicule_progressive_n_est_pas_une_copie_reduite():
    film = MediaInfo(Path("super8.mkv"), codec="ffv1", width=720, height=540,
                     fps=Fraction(18), scan="progressive")
    film.bits_per_pixel = 0.05
    judge_capture(film, doubled=True, jitter=True)
    assert conseils_numerisation(film) == []
    copie = MediaInfo(Path("reduit.mkv"), codec="ffv1", width=640, height=360,
                      fps=Fraction(25), scan="progressive")
    judge_capture(copie)
    assert copie.already_scaled and copie.already_deinterlaced and not copie.low_bitrate
    assert conseils_numerisation(copie) == [PHRASE_TRAITEE]


def test_lignes_doublees_et_tremblement_sur_image_synthetique():
    largeur, hauteur = 160, 64
    plat = bytes(largeur * hauteur)                     # tout noir : pas assez de détail
    assert doubled_line_share(plat, largeur, hauteur) is None
    assert line_shift_stats(plat, largeur, hauteur) is None
    droite = _barre(largeur, hauteur, lambda _y: 0)
    assert doubled_line_share(droite, largeur, hauteur) == 1.0
    calme = line_shift_stats(droite, largeur, hauteur)
    assert calme is not None and calme[0] < 0.5 and calme[1] < 0.5
    melange = bytearray(droite)
    # une paire sur deux n'est plus une copie : sous le seuil
    for y in range(0, hauteur, 4):
        for x in range(largeur):
            melange[y * largeur + x] = (x * 3) % 256
    assert doubled_line_share(bytes(melange), largeur, hauteur) < 0.92
    tremble = _barre(largeur, hauteur, lambda y: 6 if (y // 2) % 2 == 0 else -6)
    stats = line_shift_stats(tremble, largeur, hauteur)
    assert stats is not None and stats[0] >= 1.2 and stats[1] >= 1.0 and stats[2] >= 0.25
    info = MediaInfo(Path("tbc.mkv"), codec="ffv1", width=720, height=576, fps=Fraction(25), scan="tff")
    judge_capture(info, jitter=True)
    assert conseils_numerisation(info) == [PHRASE_LIGNES]
    assert ligne_assistant(info)


def test_noirs_ecrases_ou_scene_sombre():
    def image(valeur_sombre: int, part: float) -> bytes:
        largeur, hauteur = 80, 40
        buf = bytearray([128]) * (largeur * hauteur)
        n = int(largeur * hauteur * part)
        for i in range(n):
            buf[i] = valeur_sombre
        # le centre seul est mesuré : remplir tout le cadre
        return bytes(buf)

    ecrase = image(0, 0.30)
    niveaux = _levels_of(ecrase, 80, 40)
    assert niveaux is not None and _is_crushed(niveaux[0], niveaux[1], niveaux[2])
    # pente : autant de pixels dans le voisinage que dans le pic
    pente = bytearray([128]) * (80 * 40)
    for i, pix in enumerate(pente):
        if i % 5 == 0:
            pente[i] = 0
        elif i % 5 == 1:
            pente[i] = 8
    niveaux = _levels_of(bytes(pente), 80, 40)
    assert niveaux is not None and not _is_crushed(niveaux[0], niveaux[1], niveaux[2])
    noir = bytes(80 * 40)
    niveaux = _levels_of(noir, 80, 40)
    assert niveaux is not None and not _is_crushed(niveaux[0], niveaux[1], niveaux[2])


@pytest.fixture(scope="module")
def copies(tmp_path_factory, tools):
    d = tmp_path_factory.mktemp("numerisation")
    faible = d / "faible.mpg"
    ff("-f", "lavfi", "-i",
       "testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,setfield=tff",
       "-t", "2", "-c:v", "mpeg2video", "-b:v", "700k", "-flags", "+ilme+ildct",
       "-pix_fmt", "yuv420p", str(faible))
    reduite = d / "reduite.mkv"
    # 640×480 progressif (mesure idet fiable), puis réduit : une copie déjà désentrelacée et rapetissée.
    ff("-f", "lavfi", "-i", "testsrc2=size=640x480:rate=25,scale=640:360:flags=bilinear,setfield=prog",
       "-t", "2", "-c:v", "ffv1", str(reduite))
    ecrasee = d / "ecrasee.mkv"
    ff("-f", "lavfi", "-i",
       "testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,setfield=tff,"
       "format=yuv422p,lutyuv=y='if(lt(val,90),0,val)'",
       "-t", "2", "-c:v", "ffv1", "-pix_fmt", "yuv422p", str(ecrasee))
    normale = d / "normale.mkv"
    ff("-f", "lavfi", "-i",
       "testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,setfield=tff,format=yuv422p",
       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
       "-t", "2", "-c:v", "ffv1", "-pix_fmt", "yuv422p", "-c:a", "pcm_s16le", "-ac", "2",
       str(normale))
    return {nom: analyze(chemin, tools) for nom, chemin in (
        ("faible", faible), ("reduite", reduite), ("ecrasee", ecrasee), ("normale", normale))}


def test_mpeg2_faible_debit(copies):
    info = copies["faible"]
    assert info.low_bitrate and info.bits_per_pixel is not None and info.bits_per_pixel < 0.25
    assert EXACTE_COMPRESSEE in conseils_numerisation(info)
    assert {a.key for a in advise(info)} <= CLES_CORRECTION


def test_copie_reduite_en_progressif(copies):
    info = copies["reduite"]
    assert info.codec == "ffv1" and not info.low_bitrate
    assert info.already_scaled and info.scan == "progressive"
    assert PHRASE_TRAITEE in conseils_numerisation(info)
    assert EXACTE_COMPRESSEE not in conseils_numerisation(info)


def test_noirs_ecrases(copies):
    info = copies["ecrasee"]
    assert info.codec == "ffv1" and info.pix_fmt == "yuv422p" and not info.low_bitrate
    assert info.crushed_blacks
    assert PHRASE_NOIRS in conseils_numerisation(info)


def test_ffv1_422_normale_rien(copies):
    info = copies["normale"]
    assert info.codec == "ffv1" and info.pix_fmt == "yuv422p"
    assert info.scan in ("tff", "bff") and info.height == 576
    assert "pcm" in info.audio_desc
    assert conseils_numerisation(info) == []
    assert ligne_assistant(info) == ""
    assert not any((info.low_bitrate, info.already_deinterlaced, info.already_scaled,
                    info.doubled_lines, info.crushed_blacks, info.crushed_whites, info.line_jitter))


@pytest.mark.assistant
def test_affichage_une_ligne_sans_bloquer(copies, tools):
    """Détails du fichier, conseils des réglages libres, une ligne à l'étape 1. Fenêtre 1280 × 641."""
    pytest.importorskip("PySide6")
    import time
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    try:
        win.show()
        win.resize(1280, 641)
        win.set_taille_texte(100, annoncer=False)
        win.load_file(str(copies["faible"].path))
        fin = time.monotonic() + 180
        while time.monotonic() < fin:
            app.processEvents()
            time.sleep(0.02)
            if win.worker is not None and win.worker.isRunning():
                continue
            if win.assistant._en_cours or win.info is None:
                continue
            if "Préparation" in win.assistant.note_rendu.text():
                continue
            for _ in range(8):
                app.processEvents()
            break
        assert win.info is not None and EXACTE_COMPRESSEE in win.info_labels["Numérisation"].text()
        # pendant l'assistant, « Qualité » est cachée : le texte est prêt, il s'affiche en réglages libres
        assert not win.note_numerisation.isHidden() and EXACTE_COMPRESSEE in win.note_numerisation.text()
        ligne = win.assistant._ligne_num
        assert ligne.isVisible() and ligne.text() == "Des détails sont déjà perdus. Ouvrez « Détails du fichier »."
        assert ligne.height() <= ligne.fontMetrics().height() + 8
        assert win.assistant.suivant.isEnabled()
        assert (win.width(), win.height()) == (1280, 641)
        assert win.assistant.pages_zone.verticalScrollBar().maximum() == 0
        from PySide6.QtWidgets import QScrollArea
        for zone in win.findChildren(QScrollArea):
            if zone.isVisible():
                assert zone.horizontalScrollBar().maximum() == 0
        win.libre.click()
        for _ in range(8):
            app.processEvents()
        assert win.options.isVisible() and win.note_numerisation.isVisible()
        assert EXACTE_COMPRESSEE in win.note_numerisation.text()
        assert (win.width(), win.height()) == (1280, 641)
    finally:
        win.close()
