"""Préparer un rapport pour mon fils : un zip sur le Bureau, sans film ni photo."""
from __future__ import annotations

import platform
import zipfile
from datetime import date
from pathlib import Path

MEDIAS = {".mp4", ".mkv", ".avi", ".mov", ".mpg", ".mpeg", ".jpg", ".jpeg", ".png",
          ".tif", ".tiff", ".bmp", ".webp", ".wav", ".mp3"}


def dossier_rapport() -> tuple[Path, str]:
    """Bureau, sinon Documents, sinon le dossier du logiciel. Le message dit où."""
    home = Path.home()
    bureau = home / "Desktop"
    if not bureau.is_dir():
        bureau = home / "Bureau"
    if bureau.is_dir() and _accessible(bureau):
        return bureau, "Le rapport est sur le Bureau. Envoyez-le à votre fils (par e-mail ou WhatsApp)."
    docs = home / "Documents"
    if docs.is_dir() and _accessible(docs):
        return docs, ("Le Bureau n'est pas disponible. Le rapport est dans le dossier Documents. "
                      "Envoyez-le à votre fils (par e-mail ou WhatsApp).")
    ici = Path.cwd()
    return ici, (f"Le rapport est dans le dossier du logiciel : {ici}. "
                 "Envoyez-le à votre fils (par e-mail ou WhatsApp).")


def _accessible(d: Path) -> bool:
    try:
        t = d / ".vhsra_test"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return True
    except OSError:
        return False


def preparer_rapport(journaux: list[Path], capture: Path | None, version: str,
                     outils: str, derniere_erreur: str = "") -> tuple[Path, str]:
    dossier, message = dossier_rapport()
    nom = f"Rapport VHS Restore AI - {date.today().isoformat()}.zip"
    dest = dossier / nom
    n = 2
    while dest.exists():
        dest = dossier / f"Rapport VHS Restore AI - {date.today().isoformat()} ({n}).zip"
        n += 1
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("version.txt", f"version: {version}\nsysteme: {platform.platform()}\n")
        z.writestr("outils.txt", outils or "outils non renseignés")
        if derniere_erreur:
            z.writestr("derniere_erreur.txt", derniere_erreur[-8000:])
        for j in journaux:
            if j.is_file() and j.suffix.lower() not in MEDIAS:
                data = j.read_bytes()[-1_000_000:]
                z.writestr(j.name, data)
        if capture and capture.is_file() and capture.suffix.lower() == ".png":
            z.writestr("fenetre.png", capture.read_bytes())
    return dest, message


def zip_sans_media(chemin: Path) -> bool:
    with zipfile.ZipFile(chemin) as z:
        return all(Path(n).suffix.lower() not in MEDIAS or n == "fenetre.png" for n in z.namelist())
