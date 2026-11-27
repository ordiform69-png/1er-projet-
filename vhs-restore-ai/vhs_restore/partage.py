"""Après la restauration : copie à partager, film séparé en plusieurs, nom et date d'un film.

Tout part d'un film **déjà restauré** (ou d'un film ouvert), et crée de **nouveaux** fichiers :
l'original n'est jamais modifié. Chaque fichier n'apparaît qu'une fois complet (`partiel_unique`
puis `finaliser`), sous un nom libre (`reserver_sorties`, jamais d'écrasement).

- **Copie légère** (pour envoyer par e-mail, WhatsApp, à un téléphone) : 640 × 480 en 4:3, 25 images
  par seconde au plus, H.264 Main 3.0, AAC 96 kbit/s stéréo : environ 5 à 8 Mo par minute.
- **Copie pour la télévision** (clé USB) : 960 × 720 au plus en 4:3 (jamais agrandi), cadence gardée (50 i/s au plus),
  H.264 High 3.2 lu par presque tous les téléviseurs, AAC 192 kbit/s stéréo. Débit plafonné pour
  qu'un film de plusieurs heures tienne sous 4 Go (clé au format FAT32).
- **Séparer en plusieurs films** : une cassette de 3 heures mélange souvent Noël, des vacances, un
  anniversaire. Les coupures (neige, écran bleu, noir) que `vides.py` repère servent de frontières ;
  chaque morceau devient un film (x264 CRF 16, son AAC 192k, comme « sans passages vides »).
- **Nommer** : « Noël 1988 » plutôt que « DVD_041544_0_restaure_equilibre.mp4 » ; le titre et la date
  sont aussi écrits **dans** le fichier (lus par les téléviseurs et les lecteurs). Le fichier est
  recopié sans recompression (`-c copy`), puis l'ancien nom est effacé : seulement pour un fichier
  créé par le logiciel, jamais pour un original.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from . import vides
from .tools import (AAC, Cancelled, FichierOccupe, ToolError, effacer, finaliser, partiel_unique, reserver_sorties,
                    run, run_capture, verifier_chemin)

Progress = Callable[[float, str], None]

FAT32_MAX = 3.6e9                 # octets : marge sous les 4 Go d'un fichier sur une clé FAT32
FILM_MIN = 20.0                   # secondes : un morceau plus court n'est pas un « film »


@dataclass(frozen=True)
class GenreCopie:
    cle: str
    libelle: str                  # pour les phrases : « copie légère »
    suffixe: str                  # ajouté au nom du fichier
    hauteur: int
    fps_max: float
    profil: str
    niveau: str
    crf: int
    debit_max: int                # bits par seconde (plafond vidéo)
    son: str


COPIES = {
    "legere": GenreCopie("legere", "copie légère", " - copie légère", 480, 30.0, "main", "3.0", 28,
                         2_000_000, "96k"),
    "tele": GenreCopie("tele", "copie pour la télévision", " - pour la télévision", 720, 50.0, "high", "3.2", 20,
                       8_000_000, "192k"),
}

_INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def nom_de_fichier(texte: str, longueur: int = 80) -> str:
    """Un nom tapé par l'utilisateur, accepté par Windows : sans « : / \\ ? * », sans point ni espace
    à la fin, pas un nom réservé (« CON »…), pas trop long. Vide si rien d'utilisable."""
    nom = _INTERDITS.sub(" ", texte or "")
    nom = re.sub(r"\s+", " ", nom).strip().rstrip(". ")[:longueur].rstrip(". ")
    if nom.split(".")[0].upper() in _RESERVES:
        nom = f"{nom} (film)"
    return nom


def date_iso(texte: str) -> str | None:
    """« 1988 », « 12/1988 », « 25/12/1988 », « 1988-12-25 » → « 1988 », « 1988-12 », « 1988-12-25 »
    (forme lue par les téléviseurs et les lecteurs). Vide → « ». Illisible → None."""
    t = texte.strip()
    if not t:
        return ""
    sep = r"\s*[/.\- ]\s*"
    for motif, ordre in ((r"(\d{4})", "a"), (rf"(\d{{1,2}}){sep}(\d{{4}})", "ma"),
                         (rf"(\d{{1,2}}){sep}(\d{{1,2}}){sep}(\d{{4}})", "jma"),
                         (r"(\d{4})-(\d{1,2})-(\d{1,2})", "amj")):
        m = re.fullmatch(motif, t)
        if not m:
            continue
        v = dict(zip(ordre, map(int, m.groups())))
        if not 1880 <= v["a"] <= 2100:
            return None
        try:
            datetime.date(v["a"], v.get("m", 1), v.get("j", 1))
        except ValueError:
            return None
        if "j" in v:
            return f"{v['a']:04d}-{v['m']:02d}-{v['j']:02d}"
        return f"{v['a']:04d}-{v['m']:02d}" if "m" in v else f"{v['a']:04d}"
    return None


@dataclass
class InfosVideo:
    duree: float
    largeur: int
    hauteur: int
    fps: Fraction
    dar: Fraction
    son: bool


def infos_video(ffprobe: str, chemin: Path) -> InfosVideo:
    r = run_capture([ffprobe, "-v", "error", "-show_entries",
                     "format=duration:stream=codec_type,width,height,avg_frame_rate,r_frame_rate,"
                     "sample_aspect_ratio,display_aspect_ratio", "-of", "json", str(chemin)], timeout=60)
    try:
        d = json.loads(r.stdout or "{}")
        v = next(s for s in d.get("streams", []) if s.get("codec_type") == "video")
    except (ValueError, StopIteration):
        raise ToolError(f"Ce film n'a pas pu être lu : {Path(chemin).name}") from None
    largeur, hauteur = int(v["width"]), int(v["height"])
    fps = Fraction(v.get("avg_frame_rate") or v.get("r_frame_rate") or "25/1")
    if fps <= 0:
        fps = Fraction(v.get("r_frame_rate") or "25/1")
    try:
        dar = Fraction(str(v.get("display_aspect_ratio", "")).replace(":", "/"))
    except (ValueError, ZeroDivisionError):
        dar = Fraction(0)
    try:
        sar = Fraction(str(v.get("sample_aspect_ratio", "1:1")).replace(":", "/"))
    except (ValueError, ZeroDivisionError):
        sar = Fraction(1)
    if sar <= 0 or sar == 1:
        from .probe import SD_SIZES
        if (largeur, hauteur) in SD_SIZES:
            # Capture SD sans format (pixels « carrés ») : 4:3, la même règle que l'analyse
            # (n°20, E1 : la copie sortait en 5:4, visages trop étroits).
            dar = Fraction(4, 3)
    if dar <= 0:
        dar = Fraction(largeur, hauteur) * (sar if sar > 0 else 1)
    try:
        duree = float(d.get("format", {}).get("duration") or 0)
    except ValueError:
        duree = 0.0
    son = any(s.get("codec_type") == "audio" for s in d.get("streams", []))
    return InfosVideo(duree, largeur, hauteur, fps, dar, son)


def _pair(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def taille_copie(infos: InfosVideo, genre: GenreCopie) -> tuple[int, int]:
    """Pixels carrés au format d'affichage du film (4:3 → 640 × 480 ou 960 × 720). Jamais agrandi."""
    h = min(genre.hauteur, _pair(infos.hauteur))
    return _pair(h * float(infos.dar)), h


def fps_copie(infos: InfosVideo, genre: GenreCopie) -> Fraction:
    """Cadence gardée ; divisée par deux si elle dépasse le plafond (50 → 25 pour la copie légère)."""
    fps = infos.fps
    while float(fps) > genre.fps_max + 0.01:
        fps = fps / 2
    return fps


def debit_video(infos: InfosVideo, genre: GenreCopie) -> int:
    """Plafond de débit vidéo. Copie pour la télévision : réduit pour un film long, afin que le
    fichier tienne sous 4 Go (clé USB FAT32) ; jamais sous 1,5 Mbit/s."""
    plafond = genre.debit_max
    if genre.cle == "tele" and infos.duree > 0:
        son = int(genre.son.rstrip("k")) * 1000
        budget = int(FAT32_MAX * 8 / infos.duree) - son
        plafond = max(1_500_000, min(plafond, budget))
    return plafond


def commande_copie(ffmpeg: str, src: Path, partiel: Path, infos: InfosVideo, genre: GenreCopie) -> list[str]:
    w, h = taille_copie(infos, genre)
    fps = fps_copie(infos, genre)
    debit = debit_video(infos, genre)
    vf = f"scale={w}:{h}:flags=lanczos,setsar=1,fps={fps.numerator}/{fps.denominator},format=yuv420p"
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning", "-progress", "pipe:1", "-nostats",
           "-i", str(src), "-map", "0:v:0", "-vf", vf,
           "-c:v", "libx264", "-preset", "medium", "-crf", str(genre.crf), "-profile:v", genre.profil,
           "-level", genre.niveau, "-maxrate", str(debit), "-bufsize", str(2 * debit), "-pix_fmt", "yuv420p"]
    if infos.son:
        cmd += ["-map", "0:a:0", *AAC, "-b:a", genre.son, "-ac", "2", "-ar", "48000"]
    return cmd + ["-map_metadata", "0", "-movflags", "+faststart", "-f", "mp4", str(partiel)]


def _suivi(total: float, progress: Progress | None, texte: str) -> Callable[[str], None]:
    def ligne(l: str) -> None:
        if progress and l.startswith("out_time_us="):
            try:
                t = int(l.split("=", 1)[1]) / 1e6
            except ValueError:
                return
            progress(min(0.99, t / max(total, 0.001)), texte)
    return ligne


def verifier_place(dossier: Path, besoin: float) -> None:
    """Refuse de commencer s'il manque de la place (estimation prudente, en octets)."""
    try:
        libre = shutil.disk_usage(dossier).free
    except OSError:
        return                                   # inconnu : FFmpeg dira s'il manque de la place
    if libre < besoin:
        raise ToolError(f"Espace disque insuffisant dans {dossier} : il faut environ {besoin / 1e9:.1f} Go, "
                        f"il en reste {libre / 1e9:.1f} Go. Libérez de la place ou choisissez un autre dossier, "
                        "puis recommencez.")


def faire_copie(ffmpeg: str, ffprobe: str, src: Path, cle: str, *, dossier: Path | None = None,
                cancel: threading.Event | None = None, progress: Progress | None = None) -> Path:
    """Copie légère ou pour la télévision, à côté du film (ou dans `dossier`), sous un nom libre."""
    genre = COPIES[cle]
    src = Path(src)
    infos = infos_video(ffprobe, src)
    d = Path(dossier) if dossier else src.parent
    voulu = d / f"{src.stem}{genre.suffixe}.mp4"
    verifier_chemin(voulu)
    verifier_place(d, (debit_video(infos, genre) + int(genre.son.rstrip("k")) * 1000) * infos.duree / 8 * 1.2)
    with reserver_sorties(voulu, lambda p: []) as dst:
        partiel = partiel_unique(dst)
        try:
            run(commande_copie(ffmpeg, src, partiel, infos, genre), cancel=cancel,
                on_line=_suivi(infos.duree, progress, f"Préparation de la {genre.libelle}…"),
                what=f"FFmpeg ({genre.libelle})")
            finaliser(partiel, dst)
        except BaseException as exc:
            if not isinstance(exc, FichierOccupe):
                effacer(partiel)
            raise
    if progress:
        progress(1.0, "Terminé")
    return dst


# ---------------------------------------------------------------- séparer une cassette
def films_separables(garde: list[tuple[float, float | None]], duree: float,
                     film_min: float = FILM_MIN) -> list[tuple[float, float | None]]:
    """Morceaux d'au moins `film_min` secondes, entre les passages vides. Moins de deux : rien à séparer."""
    films = [(a, b) for a, b in garde if ((b if b is not None else duree) - a) >= film_min]
    return films if len(films) >= 2 else []


def separer(ffmpeg: str, src: Path, films: list[tuple[float, float | None]], noms: list[str],
            avec_son: bool, *, dossier: Path | None = None, cancel: threading.Event | None = None,
            progress: Progress | None = None, duree: float = 0.0) -> list[Path]:
    """Un fichier par morceau, à côté du film (ou dans `dossier`), avec son titre dans le fichier.
    L'original reste entier."""
    src = Path(src)
    d = Path(dossier) if dossier else src.parent
    if len(noms) != len(films):
        raise ToolError("Il faut un nom par film.")
    longueurs = [((b if b is not None else max(duree, a)) - a) for a, b in films]
    total = sum(longueurs) or 1.0
    # x264 CRF 16, environ 10 Mbit/s, comme la copie « sans passages vides »
    vides.verifier_place(d / "film.mp4", max(longueurs, default=0.0))   # clé FAT32 : le plus long film
    verifier_place(d, total * 10e6 / 8 * 1.1)                           # et tous les films ensemble
    faits, sortis = 0.0, []
    for i, ((a, b), nom, longueur) in enumerate(zip(films, noms, longueurs), start=1):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        propre = nom_de_fichier(nom) or f"{src.stem} - film {i}"
        voulu = d / f"{propre}.mp4"
        verifier_chemin(voulu)

        def sous(f: float, m: str, faits=faits, longueur=longueur, i=i) -> None:
            if progress:
                progress(min(0.99, (faits + f * longueur) / total), f"Film {i} sur {len(films)} — {m}")
        with reserver_sorties(voulu, lambda p: []) as dst:
            partiel = partiel_unique(dst)
            cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning", "-progress", "pipe:1",
                   "-nostats", "-ss", f"{a:.3f}", "-i", str(src)]
            if b is not None:
                cmd += ["-t", f"{b - a:.3f}"]
            cmd += ["-map", "0:v:0", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"]
            if avec_son:
                cmd += ["-map", "0:a:0", *AAC, "-b:a", "192k"]
            cmd += ["-metadata", f"title={nom.strip() or propre}", "-movflags", "+faststart", "-f", "mp4",
                    str(partiel)]
            try:
                run(cmd, cancel=cancel, on_line=_suivi(longueur, lambda f, m: sous(f, m), "Copie…"),
                    what="FFmpeg (séparer les films)")
                finaliser(partiel, dst)
            except BaseException as exc:
                if not isinstance(exc, FichierOccupe):
                    effacer(partiel)
                raise
        sortis.append(dst)
        faits += longueur
    if progress:
        progress(1.0, "Terminé")
    return sortis


# ---------------------------------------------------------------- nommer
def nommer(ffmpeg: str, src: Path, nom: str, date: str = "", *, annexes: list[Path] | None = None,
           original: Path | None = None, cancel: threading.Event | None = None) -> Path:
    """Nouveau nom (et titre, date dans le fichier) pour un film **créé par le logiciel**.

    Le film est recopié sans recompression sous son nouveau nom (jamais par-dessus un fichier
    existant), puis l'ancien est effacé. Les copies du son (WAV, FLAC) suivent le même nom.
    Une photo (PNG) change seulement de nom. « original » : le fichier d'origine, jamais touché."""
    src = Path(src)
    if original is not None and src.resolve() == Path(original).resolve():
        raise ToolError("Le fichier d'origine n'est jamais renommé : seul un résultat du logiciel peut l'être.")
    propre = nom_de_fichier(nom)
    if not propre:
        raise ToolError("Le nom choisi est vide. Tapez par exemple « Noël 1988 ».")
    voulu = src.with_name(propre + src.suffix)
    meta = ["-metadata", f"title={nom.strip()}"]
    if date.strip():
        meta += ["-metadata", f"date={date.strip()}"]
    if voulu.resolve() == src.resolve():
        # Même nom (n°20, E8) : le fichier garde son nom. Avant : « (2) » et l'ancien nom perdu.
        if src.suffix.lower() != ".mp4":
            return src                            # photo : rien à changer
        partiel = partiel_unique(src)
        try:
            run([ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", str(src),
                 "-map", "0", "-c", "copy", "-map_metadata", "0", *meta, "-movflags", "+faststart",
                 "-f", "mp4", str(partiel)], cancel=cancel, what="FFmpeg (nommer le film)")
            os.replace(partiel, src)
        except BaseException:
            effacer(partiel)
            raise
        return src
    annexes = [Path(p) for p in (annexes or []) if Path(p).is_file()]
    with reserver_sorties(voulu, lambda p: [p.with_suffix(a.suffix) for a in annexes]) as dst:
        if src.suffix.lower() != ".mp4":         # photo : un simple changement de nom, sans écrasement
            finaliser(src, dst)
            for a in annexes:
                try:
                    a.rename(dst.with_suffix(a.suffix))
                except OSError:
                    pass
            return dst
        partiel = partiel_unique(dst)
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", str(src),
               "-map", "0", "-c", "copy", "-map_metadata", "0", *meta, "-movflags", "+faststart",
               "-f", "mp4", str(partiel)]
        try:
            run(cmd, cancel=cancel, what="FFmpeg (nommer le film)")
            finaliser(partiel, dst)
        except BaseException as exc:
            if not isinstance(exc, FichierOccupe):
                effacer(partiel)
            raise
        for a in annexes:                        # WAV / FLAC : simple changement de nom
            cible = dst.with_suffix(a.suffix)
            try:
                a.rename(cible)
            except OSError:
                pass                              # gardée sous l'ancien nom plutôt que perdue
    effacer(src)
    return dst


__all__ = ["COPIES", "date_iso", "faire_copie", "films_separables", "infos_video", "nom_de_fichier", "nommer", "separer",
           "verifier_place"]
