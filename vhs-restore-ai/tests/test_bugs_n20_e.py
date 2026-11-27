"""Bugs n°20, agent E : fin du travail, arrêt, erreurs, copies à partager.

Chaque test décrit le comportement attendu et échoue sur le code actuel
(`xfail` strict). Les films sont fabriqués dans le dossier temporaire du test :
rien n'est écrit dans le dépôt.

La couleur et le format se jugent sur la recette du film réaliste de la demande
(plan qui se déplace, bruit, lumière variable, entrelacé), avec une durée plus
courte que 120 s pour que le test reste lançable. `setsar=1` est le cas d'une
capture SD dont le fichier n'annonce pas le format : le reste du logiciel
suppose alors le 4:3.
"""
import json
import os
import subprocess
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore import estimation, partage, pipeline
from vhs_restore.probe import MediaInfo, analyze
from vhs_restore.profiles import profile_for
from vhs_restore.tools import Cancelled


def _recette(duree: float, sar: str) -> str:
    return (
        f"testsrc2=s=1440x1152:r=50:d={duree},"
        "crop=720:576:x='min(t*6\\,720)':y='min(t*4\\,576)',"
        "eq=brightness='0.03*sin(2*PI*t/7)':eval=frame,"
        f"noise=alls=8:allf=t,interlace,format=yuv422p,setsar={sar}"
    )


def _film_realiste(dest: Path, duree: float, sar: str = "16/15") -> None:
    """Même chaîne que la demande, durée raccourcie. Conteneur MKV : le ffv1 garde le 4:2:2."""
    ff("-f", "lavfi", "-i", _recette(duree, sar),
       "-f", "lavfi", "-i", f"sine=f=440:sample_rate=48000:d={duree}",
       "-c:v", "ffv1", "-c:a", "pcm_s16le", "-shortest", str(dest))


def _sonde(ffprobe: str, chemin: Path) -> dict:
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,channels", "-of", "json", str(chemin)],
        capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _fenetre(tmp_path: Path, duree: float, restauration_s: float, cle: str = "equilibre"):
    from types import SimpleNamespace as N
    info = MediaInfo(path=tmp_path / "cassette.mkv", width=720, height=576,
                     fps=Fraction(25), duration=duree, has_audio=True)
    return N(info=info, preview=N(restauration_s=restauration_s, duration=10.0), is_photo=False,
             trim_start=N(value=lambda: 0.0), trim_end=N(value=lambda: 0.0), _coupes=[],
             out_edit=N(text=lambda: str(tmp_path)),
             settings=lambda: pipeline.Settings(profile_for(cle, "video"), source="video"))


@pytest.mark.xfail(strict=True, reason="capture SD sans format : la copie sort en 5:4, l'analyse dit 4:3")
def test_copie_sd_sans_sar_reste_en_4_3(tools, tmp_path):
    """Une capture 720×576 dont le fichier dit « pixels carrés » est un 4:3 pour l'analyse.
    La copie légère et celle pour la télévision doivent garder ce 4:3, le son, et toute la durée."""
    src = tmp_path / "capture.mkv"
    _film_realiste(src, 4, sar="1")
    info = analyze(src, tools)
    assert info.dar == Fraction(4, 3), info.dar
    attendu = [("legere", (640, 480)), ("tele", (768, 576))]
    mesures = []
    for cle, _taille in attendu:
        dossier = tmp_path / cle
        dossier.mkdir()
        out = partage.faire_copie(tools.ffmpeg.path, tools.ffprobe.path, src, cle, dossier=dossier)
        d = _sonde(tools.ffprobe.path, out)
        v = next(s for s in d["streams"] if s["codec_type"] == "video")
        a = next(s for s in d["streams"] if s["codec_type"] == "audio")
        mesures.append({"cle": cle, "taille": (v["width"], v["height"]),
                        "son": a.get("channels"), "duree": round(float(d["format"]["duration"]), 3)})
    assert [(m["cle"], m["taille"]) for m in mesures] == attendu, mesures
    assert all(m["son"] == 2 and abs(m["duree"] - 4) < 0.25 for m in mesures), mesures


@pytest.mark.xfail(strict=True, reason="un écart fixe de durée est annoncé comme une dérive en ms par minute")
def test_avertissement_derive_ne_transforme_pas_un_decalage_fixe(tools, tmp_path):
    """Film de 20 s dont le son est simplement plus court d'une demi-seconde (pas une accélération).
    L'avertissement ne doit pas parler de millisecondes par minute, ni de « lèvres »."""
    src = tmp_path / "decal.mp4"
    # Pas de -shortest : les deux pistes gardent leur durée (20 s et 19,5 s).
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=20",
       "-f", "lavfi", "-i", "sine=f=440:sample_rate=48000:d=19.5",
       "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(src))
    info = analyze(src, tools)
    textes = "\n".join(info.warnings)
    assert "ms par minute" not in textes and "lèvres" not in textes, textes


@pytest.mark.xfail(strict=True, reason="Arrêter au 2e film laisse le 1er sur le disque")
def test_arreter_la_separation_ne_laisse_pas_de_film(tools, tmp_path):
    """Deux morceaux. On arrête dès que le second commence : aucun fichier ne doit rester."""
    src = tmp_path / "cassette.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=14,noise=alls=10:allf=t",
       "-f", "lavfi", "-i", "sine=f=330:d=14",
       "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src))
    dossier = tmp_path / "sorties"
    dossier.mkdir()
    cancel = threading.Event()

    def progres(_f, message):
        if "Film 2" in message:
            cancel.set()

    with pytest.raises(Cancelled):
        partage.separer(tools.ffmpeg.path, src, [(0.0, 2.0), (2.0, 14.0)],
                        ["Noël 1988", "Vacances"], True, dossier=dossier, cancel=cancel,
                        progress=progres, duree=14.0)
    assert list(dossier.glob("*.mp4")) == []


def test_duree_annoncee_film_de_trois_heures_nest_pas_trop_courte(tmp_path):
    """Film de 3 h, aperçu de 10 s chronométré à 2,5 s, profil Équilibré.

    2,5 × (10 800 / 10) × 1,75 = 4 725 s, soit 1 h 19. Le texte dit « environ 1 heure ».
    À 1 h 29 (5 399 s) c'est encore « environ 1 heure », puis 1 h 30 devient « environ 2 heures ».
    """
    w = _fenetre(tmp_path, duree=3 * 3600, restauration_s=2.5)
    estime, _place = estimation.calcul(w)
    texte = estimation.annonce(w)
    assert 4700 < estime < 4800, estime
    assert "environ 1 heure sur cet ordinateur" not in texte, (round(estime), texte)
    assert estimation.phrase_temps(5399) != "environ 1 heure"


@pytest.mark.xfail(strict=True, reason="durée inconnue : la barre est déjà à 100 % dès la première image")
def test_progression_duree_inconnue_ne_saute_pas_a_100(tools, tmp_path):
    """Un conteneur sans durée (ici forcée à 0, comme certains VOB) ne doit pas afficher 100 % tout de suite."""
    src = tmp_path / "sans_duree.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=3",
       "-f", "lavfi", "-i", "sine=d=3",
       "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src))
    info = analyze(src, tools)
    info.duration = 0
    s = pipeline.Settings(profile_for("fidele", "video"), source="video", preset="ultrafast",
                          restore_audio=False)
    valeurs = []
    pipeline.export(info, s, tmp_path / "restaure.mp4", tools,
                    progress=lambda f, m: valeurs.append((f, m)))
    avant_la_fin = [f for f, m in valeurs if not str(m).startswith("Terminé")]
    assert avant_la_fin and avant_la_fin[0] < 0.5, valeurs


@pytest.mark.xfail(strict=True, reason="un fichier .reserve oublié fait choisir le nom (2)")
def test_verrou_perime_ne_renomme_pas_la_sortie(tmp_path):
    """Après une coupure, le verrou peut rester sans qu'aucun film existe. Le prochain essai
    doit reprendre le nom prévu, pas « (2) »."""
    from vhs_restore.tools import reserver_sorties
    cible = tmp_path / "vacances_restaure_equilibre.mp4"
    verrou = cible.with_name("." + cible.name + ".reserve")
    verrou.write_text("reste d'un travail interrompu", encoding="utf-8")
    with reserver_sorties(cible, lambda _p: []) as obtenu:
        assert obtenu.name == cible.name
        assert not cible.exists()


def test_nommer_le_meme_nom_garde_le_fichier(tools, tmp_path):
    """Ajouter seulement la date ne doit pas changer « Noël 1988.mp4 » en « Noël 1988 (2).mp4 »."""
    src = tmp_path / "Noël 1988.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=160x120:r=25:d=1",
       "-f", "lavfi", "-i", "sine=d=1",
       "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src))
    out = partage.nommer(tools.ffmpeg.path, src, "Noël 1988", "25/12/1988")
    assert out.name == "Noël 1988.mp4"
    assert out.is_file() and not (tmp_path / "Noël 1988 (2).mp4").exists()


@pytest.mark.xfail(strict=True, reason="Arrêter le travail laisse la copie de lecture FFmpeg en cours")
def test_arreter_coupe_aussi_la_copie_de_lecture(tools, tmp_path):
    """Film entrelacé : une copie de lecture démarre toute seule. « Arrêter » doit la couper aussi."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import MainWindow

    src = tmp_path / "entrelace.mkv"
    _film_realiste(src, 8)
    info = analyze(src, tools)
    assert info.scan in ("tff", "bff"), info.scan
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    try:
        win.info = info
        win._planifier_copie()
        limite = time.monotonic() + 15
        proc = None
        while time.monotonic() < limite:
            app.processEvents()
            job = getattr(win, "_copie", None)
            if job is not None and job.procs and job.procs[0].poll() is None:
                proc = job.procs[0]
                break
            time.sleep(0.05)
        assert proc is not None and proc.poll() is None
        win._launch(lambda cancel, _p: cancel.wait(30), lambda _r: None, job="export")
        time.sleep(0.2)
        app.processEvents()
        assert win._busy()
        win.cancel(confirmer=False)
        fin = time.monotonic() + 8
        while win._busy() and time.monotonic() < fin:
            app.processEvents()
            time.sleep(0.05)
        assert not win._busy()
        assert proc.poll() is not None
        assert win._copie is None or win._copie.annuler.is_set()
    finally:
        job = getattr(win, "_copie", None)
        if job is not None:
            job.stop()
            job.fil.join(5)
        win.close()


@pytest.mark.xfail(strict=True, reason="la copie WAV du son n'envoie aucun avancement, seulement 99 %")
def test_copie_du_son_fait_avancer_la_barre(tools, tmp_path, monkeypatch):
    """Le son d'un film long est recopié en WAV sans ligne de progression : la barre reste à 99 %."""
    src = tmp_path / "film.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=160x120:r=25:d=2",
       "-f", "lavfi", "-i", "sine=d=2",
       "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src))
    info = analyze(src, tools)
    vu = {}
    reel = pipeline.run

    def wrap(cmd, **kw):
        vu["ligne"] = kw.get("on_line")
        vu["suivi"] = "-progress" in cmd
        return reel(cmd, **kw)

    monkeypatch.setattr(pipeline, "run", wrap)
    s = pipeline.Settings(profile_for("fidele", "video"), source="video", audio_copy="wav")
    pipeline._write_audio_copy(src, info, s, tools, None, lambda f, m: vu.setdefault("fractions", []).append(f))
    assert vu.get("suivi") and vu.get("ligne") is not None, vu
    assert max(vu.get("fractions") or [0]) >= 1.0


def test_message_ffmpeg_incomplet_est_lisible():
    """Si un filtre manque, l'homme de 76 ans doit lire quoi faire, pas « bwdif, hqdn3d »."""
    pytest.importorskip("PySide6")
    code = r"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMessageBox
from vhs_restore.tools import detect_tools
import vhs_restore.gui as gui

outils = detect_tools()
outils.missing_filters = ["bwdif", "hqdn3d"]
gui.detect_tools = lambda: outils
boite = {}

def critical(*args, **kwargs):
    boite["args"] = args

gui.QMessageBox.critical = critical
QApplication.exec = lambda self: 0
gui.main()
texte = " ".join(str(a) for a in boite.get("args", ()))
assert "bwdif" not in texte and "hqdn3d" not in texte, texte
assert "incomplet" in texte.lower() or "réinstallez" in texte.lower(), texte
"""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=90, cwd=str(Path(__file__).resolve().parents[1]), env=env)
    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]
