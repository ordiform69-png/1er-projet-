"""Installation des outils facultatifs depuis l'application (clic sur un voyant ○).

Les fichiers viennent de leurs publications officielles, à une version figée, et leur
empreinte SHA-256 est vérifiée avant installation : un fichier abîmé ou différent est refusé.
Ils sont rangés dans le profil de l'utilisateur (tools.user_tools_dir()), pour servir encore
après une mise à jour du logiciel. Rien n'est installé à moitié : le téléchargement se fait
dans un dossier temporaire, puis le dossier final est mis en place d'un coup.

QTGMC n'est pas installable ainsi (il faut Python et VapourSynth) ; FFmpeg est livré avec
l'application.

Montage : LosslessCut (GPL-2.0, couper et assembler sans perte) et Shotcut (GPL-3.0, montage
complet) sont des programmes séparés, lancés avec le film restauré. LosslessCut n'est publié pour
Windows qu'en archive 7z : le petit extracteur officiel de 7-Zip (7zr.exe, LGPL) est alors
installé d'abord, de la même façon. Empreintes relevées sur les fichiers publiés (nov. 2026).
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .tools import IS_WIN, Cancelled, ToolError, run, user_tools_dir

Progress = Callable[[float, str], None]


@dataclass(frozen=True)
class Paquet:
    key: str
    name: str
    url: str
    sha256: str
    size_mb: int
    folder: str            # sous-dossier de user_tools_dir()
    kind: str              # "zip" ou "7z" (contenu extrait), ou "file" (fichier seul)
    file_name: str         # fichier attendu une fois installé
    windows_only: bool = True


PAQUETS: dict[str, Paquet] = {
    "realesrgan": Paquet(
        "realesrgan", "Real-ESRGAN",
        "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
        "realesrgan-ncnn-vulkan-20220424-windows.zip",
        "abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d", 45,
        "realesrgan", "zip", "realesrgan-ncnn-vulkan.exe"),
    "deepfilter": Paquet(
        "deepfilter", "DeepFilterNet",
        "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/"
        "deep-filter-0.5.6-x86_64-pc-windows-msvc.exe",
        "75e11fa16445f560cb6b021521ddb89e89270d13b83089705d98776f58fd7915", 27,
        "deepfilter", "file", "deep-filter.exe"),
    "colorisation": Paquet(
        "colorisation", "Colorisation (DDColor)",
        "https://huggingface.co/edgetools/ddcolor/resolve/4755ae9f1f7a35a9e7693b96c2a88f3432cb6ab0/"
        "ddcolor-tiny-fp16.onnx",
        "2653da00dc15e54a45e5200b61dbf82ee9ceaf56b02bb9b9657569ac775e82e6", 130,
        "ddcolor", "file", "ddcolor-tiny-fp16.onnx", windows_only=False),
    "sevenzip": Paquet(
        "sevenzip", "7-Zip (extracteur)", "https://www.7-zip.org/a/7zr.exe",
        "256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282", 1,
        "7zip", "file", "7zr.exe"),
    "losslesscut": Paquet(
        "losslesscut", "LosslessCut",
        "https://github.com/mifi/lossless-cut/releases/download/v3.70.2/LosslessCut-win-x64.7z",
        "1740c5f17b952c04cf1b1612cf32f56c68a88105c045199526c7ea9678d309b0", 152,
        "losslesscut", "7z", "LosslessCut.exe"),
    "shotcut": Paquet(
        "shotcut", "Shotcut",
        "https://github.com/mltframework/shotcut/releases/download/v26.8.1/shotcut-win64-26.8.1.zip",
        "b0148856de01b39add4bf4d6a813bfbc554b4663b65e3ca25cb2589f47555a6a", 225,
        "shotcut", "zip", "shotcut.exe"),
}


def can_install(key: str) -> bool:
    p = PAQUETS.get(key)
    return p is not None and (IS_WIN or not p.windows_only)


def _download(url: str, dest: Path, expected_sha: str, cancel: threading.Event | None,
              progress: Progress | None, label: str) -> None:
    """Téléchargement avec 3 essais, progression, annulation et vérification SHA-256."""
    last: Exception | None = None
    for essai in range(1, 4):
        try:
            h = hashlib.sha256()
            req = urllib.request.Request(url, headers={"User-Agent": "VHSRestoreAI"})
            with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as out:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress and total:
                        progress(0.9 * done / total, f"Téléchargement de {label} "
                                                     f"({done // 1_000_000} / {total // 1_000_000} Mo)…")
            if total and done != total:       # connexion coupée en route : on réessaie (OSError)
                raise ConnectionError(f"téléchargement interrompu ({done // 1_000_000} / {total // 1_000_000} Mo)")
            if h.hexdigest() != expected_sha:
                raise ToolError(f"Le fichier téléchargé pour {label} n'est pas le bon (empreinte différente). "
                                "Rien n'a été installé. Réessayez plus tard.")
            return
        except (Cancelled, ToolError):
            raise
        except OSError as exc:            # réseau coupé, site indisponible…
            last = exc
            if essai < 3:
                for _ in range(10 * essai):
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    time.sleep(0.5)
    raise ToolError(f"Téléchargement impossible de {label} : {last}. Vérifiez la connexion Internet.")


def _extraire_7z(archive: Path, dest: Path, base: Path, cancel: threading.Event | None,
                 progress: Progress | None) -> None:
    """Extrait une archive 7z avec 7zr.exe (installé d'abord s'il manque)."""
    outil = base / PAQUETS["sevenzip"].folder / PAQUETS["sevenzip"].file_name
    if not outil.is_file():
        install("sevenzip", cancel=cancel, root=base,
                progress=(lambda f, m: progress(0.9, "Installation de l'extracteur 7-Zip…")) if progress else None)
    run([str(outil), "x", str(archive), f"-o{dest}", "-y", "-bso0", "-bsp0"], cancel=cancel,
        what="7-Zip (extraction)")


def install(key: str, *, cancel: threading.Event | None = None, progress: Progress | None = None,
            root: Path | None = None) -> Path:
    """Télécharge, vérifie et installe l'outil `key`. Renvoie le chemin du fichier installé."""
    p = PAQUETS.get(key)
    if p is None:
        raise ToolError(f"Outil inconnu : {key}")
    if p.windows_only and not IS_WIN:
        raise ToolError(f"{p.name} ne s'installe automatiquement que sous Windows.")
    base = Path(root) if root else user_tools_dir()
    base.mkdir(parents=True, exist_ok=True)
    final = base / p.folder
    work = Path(tempfile.mkdtemp(prefix=f"vhsra_{p.key}_", dir=base))
    try:
        dl = work / ({"zip": "paquet.zip", "7z": "paquet.7z"}.get(p.kind) or p.file_name)
        _download(p.url, dl, p.sha256, cancel, progress, p.name)
        if progress:
            progress(0.93, f"Installation de {p.name}…")
        staged = work / "installe"
        staged.mkdir()
        if p.kind == "7z":
            _extraire_7z(dl, staged, base, cancel, progress)
            for f in staged.rglob("*"):                   # aucun fichier ne doit sortir du dossier
                if not str(f.resolve()).startswith(str(staged.resolve())):
                    raise ToolError(f"Archive de {p.name} refusée (chemin suspect).")
            found = next(staged.rglob(p.file_name), None)
            if found is None:
                raise ToolError(f"{p.file_name} introuvable dans l'archive de {p.name}.")
            staged = found.parent
        elif p.kind == "zip":
            with zipfile.ZipFile(dl) as z:
                for m in z.infolist():                    # pas de chemin qui sorte du dossier
                    target = (staged / m.filename).resolve()
                    if not str(target).startswith(str(staged.resolve())):
                        raise ToolError(f"Archive de {p.name} refusée (chemin suspect).")
                z.extractall(staged)
            found = next(staged.rglob(p.file_name), None)
            if found is None:
                raise ToolError(f"{p.file_name} introuvable dans l'archive de {p.name}.")
            staged = found.parent
        else:
            shutil.move(str(dl), staged / p.file_name)
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if final.exists():
            shutil.rmtree(final)
        shutil.move(str(staged), final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(1.0, f"{p.name} installé.")
    return final / p.file_name
