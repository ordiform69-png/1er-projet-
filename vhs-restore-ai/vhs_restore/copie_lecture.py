"""Copie de lecture désentrelacée, pour le lecteur.

Seulement si le film est entrelacé (`info.scan` vaut `tff` ou `bff`). Même cadence
et mêmes instants que l'original (`bwdif` en `send_frame`), à la taille d'affichage.
Le son passe par `tools.AAC`. Aucune copie n'est écrite à côté du film.
"""
from __future__ import annotations

import atexit
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

from .probe import MediaInfo
from .tools import AAC, _NO_WINDOW, effacer
from .vignettes import entree

log = logging.getLogger("vhs_restore")

LARGEUR_MAX = 720
# Marge au-dessus d'un H.264 veryfast en 720 px, et la réécriture de faststart.
_OCTETS_PAR_SECONDE = 25_000_000 / 8 * 2

_VERROU = threading.Lock()
_PROCS: list[subprocess.Popen] = []
_DOSSIERS: set[Path] = set()


def voulu(info: MediaInfo) -> bool:
    """Vrai seulement pour un film dont l'analyse a conclu tff ou bff."""
    return getattr(info, "scan", "") in ("tff", "bff")


def _pair(n: float) -> int:
    return max(2, int(float(n) / 2.0 + 0.5) * 2)


def taille(info: MediaInfo) -> tuple[int, int]:
    """Largeur × hauteur d'affichage, 720 px de large au plus.

    Le format annoncé est gardé : une VHS 720×576 en pixels 16/15 (4:3) devient
    720×540, pas une image étirée.
    """
    try:
        dar = float(info.dar)
    except (TypeError, ValueError, ZeroDivisionError):
        dar = 0.0
    if dar <= 0:
        dar = 4 / 3
    try:
        affichage = float(info.height) * dar
    except (TypeError, ValueError):
        affichage = float(LARGEUR_MAX)
    if affichage <= 0:
        affichage = float(LARGEUR_MAX)
    largeur = min(LARGEUR_MAX, _pair(affichage))
    if largeur > LARGEUR_MAX:
        largeur = LARGEUR_MAX
    if largeur % 2:
        largeur -= 1
    return largeur, _pair(largeur / dar)


def filtre(info: MediaInfo) -> str:
    """Désentrelace sans changer la cadence, puis cadre au format d'affichage."""
    largeur, hauteur = taille(info)
    return (
        f"bwdif=mode=send_frame:parity={info.scan},"
        f"scale={largeur}:{hauteur}:flags=fast_bilinear,"
        "pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1,format=yuv420p"
    )


def besoin_octets(info: MediaInfo) -> int:
    """Place à réserver avant de commencer. 0 si la durée est inconnue."""
    try:
        duree = float(info.duration or 0)
    except (TypeError, ValueError):
        return 0
    if duree <= 0:
        return 0
    return int(duree * _OCTETS_PAR_SECONDE) + 1_048_576


def assez_de_place(info: MediaInfo, dossier: Path) -> bool:
    """Faux s'il manque de la place, ou si la place ne peut pas être lue.

    Dans les deux cas l'appelant ne fabrique pas de copie.
    """
    besoin = besoin_octets(info)
    if besoin <= 0:
        return False
    try:
        libre = shutil.disk_usage(dossier).free
    except OSError:
        return False
    return libre >= besoin


def commande(ffmpeg: str, info: MediaInfo, dest: Path) -> list[str]:
    """Tout le titre (plusieurs VOB compris), une image par image source."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           *entree(info),
           "-map", "0:v:0",
           "-vf", filtre(info),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
    if info.has_audio:
        cmd += ["-map", "0:a:0", *AAC, "-b:a", "160k"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", str(dest)]
    return cmd


def priorite_basse() -> None:
    """Le fil courant passe derrière l'interface. Sans effet si le système refuse."""
    try:
        if os.name == "nt":
            import ctypes
            noyau = ctypes.windll.kernel32
            noyau.SetThreadPriority(noyau.GetCurrentThread(), -1)
        else:
            os.nice(10)
    except (OSError, AttributeError):
        pass


def _baisser(proc: subprocess.Popen) -> None:
    if os.name == "nt" or proc.pid is None:
        return
    try:
        os.setpriority(os.PRIO_PROCESS, proc.pid, 10)
    except OSError:
        pass


def _lancer(cmd: list[str]) -> subprocess.Popen:
    drapeaux = _NO_WINDOW
    if os.name == "nt":
        drapeaux |= 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS
    proc = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=drapeaux)
    _baisser(proc)
    return proc


def tuer() -> None:
    """Tue les FFmpeg de copie encore ouverts (fermeture, annulation, sortie)."""
    with _VERROU:
        procs = list(_PROCS)
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.kill()
        except OSError:
            pass


def retenir(dossier: Path) -> None:
    _DOSSIERS.add(Path(dossier))


def oublier(dossier: Path) -> None:
    _DOSSIERS.discard(Path(dossier))


def _nettoyer_a_la_sortie() -> None:
    tuer()
    for dossier in list(_DOSSIERS):
        shutil.rmtree(dossier, ignore_errors=True)


atexit.register(_nettoyer_a_la_sortie)


def preparer(ffmpeg: str, info: MediaInfo, dest: Path, annuler: threading.Event,
             processus: list | None = None) -> bool:
    """Écrit la copie. Faux si le film n'est pas entrelacé, s'il manque de la place,
    si on annule, ou si FFmpeg échoue. N'élève pas : le lecteur reste sur l'original.
    """
    if annuler.is_set() or not voulu(info):
        return False
    dest = Path(dest)
    if not assez_de_place(info, dest.parent):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = _lancer(commande(ffmpeg, info, dest))
    except (OSError, ValueError):
        log.info("copie de lecture non lancée", exc_info=True)
        effacer(dest)
        return False
    with _VERROU:
        _PROCS.append(proc)
    if processus is not None:
        processus.append(proc)
    try:
        while proc.poll() is None:
            if annuler.is_set():
                proc.kill()
                try:
                    proc.wait(2)
                except subprocess.TimeoutExpired:
                    pass
                effacer(dest)
                return False
            try:
                proc.wait(0.05)
            except subprocess.TimeoutExpired:
                continue
        if annuler.is_set() or proc.returncode != 0:
            if proc.returncode not in (0, None) and not annuler.is_set():
                log.info("copie de lecture abandonnée (code %s)", proc.returncode)
            effacer(dest)
            return False
        if not dest.is_file() or dest.stat().st_size <= 0:
            effacer(dest)
            return False
        return True
    finally:
        with _VERROU:
            if proc in _PROCS:
                _PROCS.remove(proc)