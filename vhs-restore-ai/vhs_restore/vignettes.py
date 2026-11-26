"""Petites images du film pour la barre, et image du moment.

FFmpeg seulement. L'extraction est appelée depuis un fil à part (pas le
fil des restaurations) : l'écran reste utilisable. Aucune image n'est
écrite à côté du film.
"""
from __future__ import annotations

import atexit
import subprocess
import threading
from pathlib import Path

from .dvd import input_args
from .probe import MediaInfo
from .tools import _NO_WINDOW, ff_input

PAS_PX = 90
MAX_CACHE = 128
HAUTEUR_VIGNETTE = 72
HAUTEUR_MOMENT = 180

_EN_COURS: list[subprocess.Popen] = []
_VERROU = threading.Lock()


def tuer_extractions() -> None:
    """Tue les FFmpeg d'images encore ouverts (fermeture, annulation, sortie de Python)."""
    with _VERROU:
        procs = list(_EN_COURS)
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.kill()
        except OSError:
            pass


atexit.register(tuer_extractions)


def instants(duree: float, largeur: int, pas: int = PAS_PX, *, debut: float = 0.0) -> list[float]:
    """Une image tous les `pas` pixels, au milieu de chaque tranche.

    Un film sans durée, ou une barre trop étroite, ne donne aucune image
    (la barre reste utilisable). Un film très court n'en demande pas plus
    qu'il n'a de secondes.
    """
    duree = float(duree or 0)
    if duree <= 0 or largeur < 40:
        return []
    n = max(1, int(largeur // pas))
    if duree < 20:
        n = min(n, max(1, int(duree)))
    return [round(debut + duree * (i + 0.5) / n, 3) for i in range(n)]


def _pair(n: int) -> int:
    n = max(2, int(n))
    return n - (n % 2)


def taille(info: MediaInfo, hauteur: int) -> tuple[int, int]:
    """Largeur × hauteur d'affichage. Le 4:3 d'une VHS (pixels 16/15) reste 4:3."""
    try:
        dar = float(info.dar)
    except (TypeError, ValueError, ZeroDivisionError):
        dar = 0.0
    if dar <= 0:
        dar = 4 / 3
    h = _pair(hauteur)
    return _pair(h * dar), h


def filtre(info: MediaInfo, largeur: int, hauteur: int) -> str:
    """Désentrelace seulement une image vraiment entrelacée, puis cadre au format d'affichage."""
    parts: list[str] = []
    if info.scan == "tff":
        parts.append("bwdif=mode=send_frame:parity=tff")
    elif info.scan == "bff":
        parts.append("bwdif=mode=send_frame:parity=bff")
    # scale tient compte du SAR : 720×576 en 16/15 donne bien du 4:3
    parts.append(
        f"scale={int(largeur)}:{int(hauteur)}:force_original_aspect_ratio=decrease:flags=fast_bilinear")
    parts.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
    parts.append("setsar=1")
    return ",".join(parts)


def entree(info: MediaInfo) -> list[str]:
    """Tout le titre DVD (plusieurs VOB), sinon le fichier. Les « % » d'une image sont neutralisés."""
    if len(tuple(info.parts)) > 1:
        return input_args(info)
    return ff_input(info.path)


def commande(ffmpeg: str, info: MediaInfo, instant: float, dest: Path,
             largeur: int, hauteur: int) -> list[str]:
    """Saut rapide : -ss avant -i, une seule image, pas de son."""
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-ss", f"{max(0.0, float(instant)):.3f}",
            *entree(info),
            "-frames:v", "1", "-an",
            "-vf", filtre(info, largeur, hauteur),
            str(dest)]


def extraire(ffmpeg: str, info: MediaInfo, instant: float, dest: Path,
             largeur: int, hauteur: int, annuler: threading.Event | None = None,
             processus: list | None = None) -> bool:
    """Écrit une image. False si on a annulé, ou si FFmpeg n'a rien produit.

    `processus` reçoit le Popen en cours : l'appelant peut le tuer pour que
    la dernière demande gagne sans attendre la précédente.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if annuler is not None and annuler.is_set():
        return False
    try:
        proc = subprocess.Popen(
            commande(ffmpeg, info, instant, dest, largeur, hauteur),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW)
    except OSError:
        return False
    with _VERROU:
        _EN_COURS.append(proc)
    if processus is not None:
        processus[:] = [proc]
    try:
        while proc.poll() is None:
            if annuler is not None and annuler.is_set():
                proc.kill()
                proc.wait(2)
                return False
            try:
                proc.wait(0.05)
            except subprocess.TimeoutExpired:
                continue
        return proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0
    finally:
        with _VERROU:
            if proc in _EN_COURS:
                _EN_COURS.remove(proc)
        if processus is not None and processus[:1] == [proc]:
            processus.clear()
