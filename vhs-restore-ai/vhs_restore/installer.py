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

import json
import hashlib
import os
import re
import ssl
import stat
import subprocess
from pathlib import PureWindowsPath
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .tools import _NO_WINDOW, IS_WIN, Cancelled, ToolError, run, terminate, user_tools_dir

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


_manifeste = Path(__file__).with_name("paquets.json")
PAQUETS = {p["key"]: Paquet(**p) for p in json.loads(_manifeste.read_text(encoding="utf-8"))}


def can_install(key: str) -> bool:
    p = PAQUETS.get(key)
    return key != "ffmpeg" and p is not None and (IS_WIN or not p.windows_only)


def _curl_windows() -> str | None:
    """curl.exe, livré avec Windows 10 (depuis 2018) et 11. Il vérifie les certificats comme le
    navigateur : magasin de Windows, qui va chercher lui-même un certificat racine manquant."""
    if not IS_WIN:
        return None
    racine = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    chemin = Path(racine) / "System32" / "curl.exe"
    return str(chemin) if chemin.is_file() else None


def _certificat_refuse(exc: BaseException) -> bool:
    """[SSL: CERTIFICATE_VERIFY_FAILED] : Python ne trouve pas un certificat que Windows, lui,
    sait aller chercher (constaté chez l'utilisateur : « unable to get issuer certificate »)."""
    raison = getattr(exc, "reason", None)
    return (isinstance(exc, ssl.SSLCertVerificationError) or isinstance(raison, ssl.SSLCertVerificationError)
            or "CERTIFICATE_VERIFY_FAILED" in str(exc))


def _empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _download_curl(curl: str, url: str, dest: Path, cancel: threading.Event | None,
                   progress: Progress | None, label: str, taille_mo: int) -> None:
    """Le même téléchargement par curl.exe de Windows. OSError si curl échoue."""
    options = ["--location", "--fail", "--silent", "--show-error", "--retry", "3", "--retry-delay", "2",
               "--connect-timeout", "30", "--user-agent", "VHSRestoreAI", "--output", str(dest), url]
    # révocation « au mieux », comme les navigateurs ; un curl trop ancien ne connaît pas l'option
    for essai in (["--ssl-revoke-best-effort"], []):
        dest.unlink(missing_ok=True)
        proc = subprocess.Popen([curl, *essai, *options], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=_NO_WINDOW)
        try:
            while proc.poll() is None:
                if cancel is not None and cancel.is_set():
                    terminate(proc)
                    raise Cancelled()
                if progress and taille_mo:
                    fait = dest.stat().st_size if dest.exists() else 0
                    progress(0.9 * min(1.0, fait / (taille_mo * 1_000_000)),
                             f"Téléchargement de {label} ({fait // 1_000_000} / {taille_mo} Mo)…")
                time.sleep(0.25)
        finally:
            if proc.poll() is None:
                terminate(proc)
        erreur = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace").strip()
        if proc.returncode == 0:
            return
        if proc.returncode != 2 or not essai:             # 2 : option inconnue (curl ancien)
            raise OSError(f"curl {proc.returncode} : {erreur[-300:] or 'échec'}")


def _download(url: str, dest: Path, expected_sha: str, cancel: threading.Event | None,
              progress: Progress | None, label: str, taille_mo: int = 0) -> None:
    """Téléchargement avec 3 essais, progression, annulation et vérification SHA-256.

    Certificat refusé par Python (ou réseau en échec) : le même fichier par curl.exe de
    Windows, avec la même vérification d'empreinte."""
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
            if _certificat_refuse(exc):
                break                     # réessayer ne change rien : on passe par Windows
            if essai < 3:
                for _ in range(10 * essai):
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    time.sleep(0.5)
    curl = _curl_windows()
    if curl is not None:
        try:
            _download_curl(curl, url, dest, cancel, progress, label, taille_mo)
        except OSError as exc:
            log_curl = exc
        else:
            if _empreinte(dest) != expected_sha:
                raise ToolError(f"Le fichier téléchargé pour {label} n'est pas le bon (empreinte différente). "
                                "Rien n'a été installé. Réessayez plus tard.")
            return
    else:
        log_curl = None
    if last is not None and _certificat_refuse(last):
        raise ToolError(f"Téléchargement impossible de {label} : le certificat de sécurité du site n'a pas pu "
                        "être vérifié sur cet ordinateur. Votre connexion n'est pas en cause. Réessayez plus "
                        "tard ; si cela continue, un antivirus qui filtre les connexions sécurisées peut en être "
                        f"la cause.\n(Détail : {last}" + (f" ; {log_curl}" if log_curl else "") + ")")
    raise ToolError(f"Téléchargement impossible de {label} : {last}"
                    + (f" ; {log_curl}" if log_curl else "") + ". Vérifiez la connexion Internet.")


def _membre(dest, nom):
    relatif = PureWindowsPath(nom)
    if (not relatif.parts or relatif.anchor or ".." in relatif.parts
            or any(":" in p or p.rstrip(" .") != p or PureWindowsPath(p).is_reserved()
                   for p in relatif.parts)):
        raise ToolError("Archive refusée (chemin suspect).")
    cible = dest.joinpath(*relatif.parts).resolve()
    if not cible.is_relative_to(dest.resolve()):
        raise ToolError("Archive refusée (chemin suspect).")


def _verifier_liste_7z(texte, dest):
    membres = 0
    for bloc in re.split(r"\n\s*\n", texte.strip()):
        champs = dict(l.split(" = ", 1) for l in bloc.splitlines() if " = " in l)
        if "Path" not in champs:
            raise ToolError("Impossible de vérifier le contenu de l’archive.")
        _membre(dest, champs["Path"])
        attributs = champs.get("Attributes", "")
        if (any(champs.get(k) for k in ("Symbolic Link", "Hard Link", "Reparse Point"))
                or re.search(r"(?:^|\s)l[rwx-]{9}", attributs)
                or "L" in attributs.split(" ")[0]):
            raise ToolError("Archive refusée (lien suspect).")
        membres += 1
    if not membres:
        raise ToolError("L’archive est vide.")


def _extraire_7z(archive: Path, dest: Path, base: Path, cancel: threading.Event | None,
                 progress: Progress | None) -> None:
    """Extrait une archive 7z avec 7zr.exe (installé d'abord s'il manque)."""
    outil = base / PAQUETS["sevenzip"].folder / PAQUETS["sevenzip"].file_name
    if not outil.is_file():
        install("sevenzip", cancel=cancel, root=base,
                progress=(lambda f, m: progress(0.9, "Installation de l'extracteur 7-Zip…")) if progress else None)
    lignes = []
    run([str(outil), "l", "-slt", "-ba", "-sccUTF-8", str(archive)], cancel=cancel,
        on_line=lignes.append, what="Vérification de l’archive")
    _verifier_liste_7z("\n".join(lignes), dest)
    # -sccUTF-8 comme pour la liste (n°20, D6) : un profil Windows accentué (« Hélène »)
    run([str(outil), "x", str(archive), f"-o{dest}", "-y", "-bso0", "-bsp0", "-sccUTF-8"], cancel=cancel,
        what="7-Zip (extraction)")


def _poser_installation(staged: Path, final: Path, nom: str) -> None:
    """Remplace l'installation précédente. Si le programme est ouvert, on ne l'efface pas."""
    ancien = final.with_name(final.name + ".ancien")
    deplace = False
    if final.exists():
        if ancien.exists():
            shutil.rmtree(ancien, ignore_errors=True)
        try:
            final.rename(ancien)
        except OSError:
            # Constaté chez l'utilisateur, ordinateur tout juste allumé : ce n'est pas forcément
            # un programme ouvert. Un antivirus qui bloque le fichier donne la même erreur.
            raise ToolError(
                f"Windows refuse de remplacer l'installation précédente de {nom}. Le plus souvent, "
                "l'antivirus de Windows bloque ce fichier : ouvrez « Sécurité Windows », puis "
                "« Protection contre les virus et menaces », puis « Historique de protection ». "
                f"Sinon, {nom} est peut-être ouvert : fermez-le ou redémarrez l'ordinateur, "
                "puis recommencez l'installation. Rien n'a été désinstallé.") from None
        deplace = True
    try:
        shutil.move(str(staged), final)
    except Exception:
        if deplace and ancien.exists() and not final.exists():
            try:
                ancien.rename(final)
            except OSError:
                pass
        raise
    if deplace and ancien.exists():
        shutil.rmtree(ancien, ignore_errors=True)


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
        _download(p.url, dl, p.sha256, cancel, progress, p.name, p.size_mb)
        if progress:
            progress(0.93, f"Installation de {p.name}…")
        staged = work / "installe"
        staged.mkdir()
        if p.kind == "7z":
            _extraire_7z(dl, staged, base, cancel, progress)
            for f in staged.rglob("*"):                   # aucun fichier ne doit sortir du dossier
                if f.is_symlink() or not f.resolve().is_relative_to(staged.resolve()):
                    raise ToolError(f"Archive de {p.name} refusée (chemin suspect).")
            found = next(staged.rglob(p.file_name), None)
            if found is None:
                raise ToolError(f"{p.file_name} introuvable dans l'archive de {p.name}.")
            staged = found.parent
        elif p.kind == "zip":
            with zipfile.ZipFile(dl) as z:
                for m in z.infolist():                    # pas de chemin qui sorte du dossier
                    _membre(staged, m.filename)
                    if stat.S_ISLNK(m.external_attr >> 16) or m.external_attr & 0x400:
                        raise ToolError(f"Archive de {p.name} refusée (lien suspect).")
                z.extractall(staged)
            found = next(staged.rglob(p.file_name), None)
            if found is None:
                raise ToolError(f"{p.file_name} introuvable dans l'archive de {p.name}.")
            staged = found.parents[len(Path(p.file_name).parts) - 1]
            if key == "ffmpeg" and not (staged / "bin/ffprobe.exe").is_file():
                raise ToolError("FFprobe manque dans le paquet téléchargé.")
        else:
            shutil.move(str(dl), staged / p.file_name)
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        _poser_installation(staged, final, p.name)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(1.0, f"{p.name} installé.")
    return final / p.file_name


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Installer les outils vérifiés de VHS Restore AI.")
    parser.add_argument("dossier", type=Path)
    parser.add_argument("outils", nargs="+", choices=PAQUETS)
    args = parser.parse_args()
    for cle in args.outils:
        print(f"Installation de {PAQUETS[cle].name}…", flush=True)
        print(install(cle, root=args.dossier.resolve()))
