"""Bugs n°20, agent D (Windows, fichiers, disque). Rien n'est corrigé dans vhs_restore/.

Chaque test décrit le comportement attendu après correction. Aujourd'hui le défaut
existe encore : le test échoue, d'où xfail(strict=True).
"""
from __future__ import annotations

import inspect
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from vhs_restore import ergonomie, gui, installer, tools as tools_mod
from vhs_restore.pipeline import check_fat32, systeme_de_fichiers
from vhs_restore.probe import MediaInfo
from vhs_restore.profiles import profile_for
from vhs_restore.pipeline import Settings


def test_verrou_reserve_orphelin_ne_bloque_pas_le_nom(tmp_path):
    """Un arrêt brutal laisse « .noel.mp4.reserve ». Le film n'existe pas, le nom doit rester disponible."""
    dest = tmp_path / "noel.mp4"
    (tmp_path / ".noel.mp4.reserve").touch()
    with tools_mod.reserver_sorties(dest, lambda _c: []) as choisi:
        assert choisi == dest


def test_verifier_chemin_annonce_la_longueur_reelle(tmp_path, monkeypatch):
    """Windows : on refuse dès 250 caractères. Le nombre annoncé doit être celui du chemin résolu."""
    monkeypatch.setattr(tools_mod, "IS_WIN", True)
    long = tmp_path
    while len(str(long / "sortie.mp4")) < 260:
        long = long / ("dossier" * 8)
    long.mkdir(parents=True)
    monkeypatch.chdir(long)
    rel = Path("sortie.mp4")
    assert len(str(rel)) < 20
    assert len(str(rel.resolve())) >= 250
    with pytest.raises(tools_mod.ToolError) as exc:
        tools_mod.verifier_chemin(rel)
    n = len(str(rel.resolve()))
    assert f"{n} caractères" in str(exc.value)


def test_disque_plein_ffmpeg_explique_la_place():
    """FFmpeg, en cours de route, dit « No space left on device ». Le père doit lire que le disque est plein."""
    clair, _ = ergonomie.expliquer(
        "FFmpeg (export) a échoué (code 1).\n"
        "Error while writing video frame: No space left on device"
    )
    bas = clair.lower()
    assert "place" in bas or "disque" in bas
    assert "n'est plus là" not in bas


@pytest.mark.xfail(strict=True, reason="FFmpeg lancé comme dans tools.run() survit à la mort du processus père")
def test_ffmpeg_meurt_avec_le_processus_qui_l_a_lance(tools):
    """Même Popen que tools.run (CREATE_NO_WINDOW, pas d'objet Job, pas de PDEATHSIG).

    Sous Windows, « Fin de tâche » sur l'exe laisse FFmpeg écrire et verrouiller le résultat.
    Ici : le père fait os._exit sans terminate() ; FFmpeg ne doit plus être vivant.
    """
    ffmpeg = tools.ffmpeg.path
    code = r"""
import os, sys, subprocess
flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
proc = subprocess.Popen(
    [sys.argv[1], "-hide_banner", "-nostdin", "-loglevel", "error",
     "-f", "lavfi", "-i", "nullsrc=s=64x64:r=1", "-f", "null", "-"],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    creationflags=flags,
)
os.write(1, str(proc.pid).encode("ascii"))
os.fsync(1)
os._exit(0)
"""
    aide = subprocess.run(
        [sys.executable, "-c", code, ffmpeg],
        capture_output=True, timeout=10, check=True,
    )
    pid = int(aide.stdout.decode().strip())
    try:
        time.sleep(0.4)
        encore = True
        try:
            os.kill(pid, 0)
        except OSError:
            encore = False
        assert encore is False
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def test_atexit_efface_les_dossiers_temporaires_de_la_fenetre(tools):
    """Fermeture par interruption (Ctrl+C, fin du processus) : closeEvent peut ne pas passer.

    Les dossiers vhsrestore_apercu_* et vhsrestore_lumiere_* doivent partir avec atexit.
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    if getattr(gui._eteindre_a_la_sortie, "_fait", False):
        del gui._eteindre_a_la_sortie._fait
    win = gui.MainWindow(tools)
    apercu = Path(win.preview_dir)
    lum = Path(win.lumiere.dossier)
    assert apercu.is_dir() and lum.is_dir()
    try:
        gui._eteindre_a_la_sortie()
        assert not apercu.exists()
        assert not lum.exists()
    finally:
        if hasattr(gui._eteindre_a_la_sortie, "_fait"):
            del gui._eteindre_a_la_sortie._fait
        try:
            win.lumiere.fermer()
        except Exception:
            pass
        shutil.rmtree(apercu, ignore_errors=True)
        shutil.rmtree(lum, ignore_errors=True)
        try:
            win.close()
        except Exception:
            pass


def test_extraction_7z_demande_l_utf8_comme_la_liste():
    """Un dossier d'installation avec accent (C:\\Users\\Gérard\\…) : 7-Zip sous Windows
    interprète -o… selon la page de code s'il n'a pas -sccUTF-8."""
    source = inspect.getsource(installer._extraire_7z)
    # La commande « l » l'a déjà ; la commande « x » doit l'avoir aussi.
    assert source.count("-sccUTF-8") >= 2


@pytest.mark.xfail(strict=True, reason="un lecteur réseau dont on ne lit pas le format échappe au contrôle FAT32")
def test_fat32_reseau_inconnu_est_traite_comme_un_risque(monkeypatch, tmp_path):
    """systeme_de_fichiers renvoie "" si GetVolumeInformationW échoue (lecteur réseau).

    Un film de 3 h peut alors dépasser 4 Go sur un partage FAT32, sans avertissement.
    On doit refuser, ou au moins prévenir, plutôt que de laisser passer.
    """
    info = MediaInfo(path=tmp_path / "cassette.mpg", has_audio=True, duration=3 * 3600,
                     width=720, height=576)
    s = Settings(profile_for("equilibre"))
    monkeypatch.setattr("vhs_restore.pipeline.systeme_de_fichiers", lambda _p: "")
    # Aujourd'hui check_fat32 laisse passer si le format est inconnu.
    # Après correction : un doute sur le format d'un gros fichier doit avertir.
    with pytest.raises(tools_mod.ToolError, match="FAT32|4 Go|réseau"):
        check_fat32(info, s, tmp_path)
