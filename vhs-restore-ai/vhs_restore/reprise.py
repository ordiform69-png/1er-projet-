"""Reprise d'une restauration interrompue, par parties.

Un film gardé de 20 minutes ou plus, sans IA, sans poussières, sans réparation
de bande, sans changement de cadence et sans stabilisation, est restauré par
parties de 10 minutes. Chaque partie commence quelques secondes plus tôt
(image et son) : ces images de chauffe sont retirées, les raccords ne se voient
pas et ne s'entendent pas. Les parties restent dans le profil de l'utilisateur,
jamais à côté de la cassette. Une partie ne compte que si elle est complète.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import time
from fractions import Fraction
from pathlib import Path

from .tools import ToolError, effacer, run_capture

# Réglables. Les tests raccourcissent ces trois valeurs.
DUREE_PARTIE = 600.0          # 10 minutes
SEUIL = 1200.0                # film gardé : 20 minutes ou plus
CHAUFFE = 8.0                 # secondes lues avant chaque raccord, puis retirées
VERSION = 1                   # changer invalide les parties déjà écrites
AGE_JOURS = 30

_EPS = 1e-3


def possible(s, duree: float, *, cadence: bool, bande: bool) -> bool:
    """Vrai seulement quand couper le film en parties ne change pas le résultat.

    La stabilisation mesure tout le film d'un coup : on ne la découpe pas.
    La cadence de tournage non plus. L'IA, les poussières et la réparation de
    bande gardent leur chemin d'aujourd'hui.
    """
    if duree < float(SEUIL):
        return False
    if cadence or bande:
        return False
    if s.use_ai or s.dust or s.stabilize:
        return False
    return True


def intervalles(info, start, duration, passages) -> list[tuple[float, float]]:
    """Intervalles gardés, en secondes de la source. Un film entier : un seul."""
    if passages is not None and len(passages) >= 2:
        return [(float(a), float(b)) for a, b in passages]
    a = float(start or 0.0)
    if duration is not None:
        b = a + float(duration)
    else:
        b = float(info.duration or 0.0)
    if b - a < _EPS:
        return []
    return [(a, b)]


def decouper(passages: list[tuple[float, float]],
             duree_partie: float | None = None,
             chauffe: float | None = None) -> list[tuple[float, float]]:
    """Découpe chaque passage gardé. Les trous ne sont jamais traversés.

    Les parties font au plus `duree_partie`, sauf la dernière d'un passage
    quand elle est plus courte que la chauffe : elle rejoint la précédente
    (une partie plus brève que la chauffe ne ferait pas un raccord utile).
    """
    duree = float(DUREE_PARTIE if duree_partie is None else duree_partie)
    seuil_reste = float(CHAUFFE if chauffe is None else chauffe)
    if duree <= _EPS:
        raise ToolError("La durée d'une partie doit être positive.")
    parties: list[tuple[float, float]] = []
    for a0, b0 in passages:
        a, b = float(a0), float(b0)
        if b - a < _EPS:
            continue
        locales: list[tuple[float, float]] = []
        curseur = a
        while b - curseur > _EPS:
            fin = min(curseur + duree, b)
            if fin - curseur <= _EPS:
                break
            locales.append((curseur, fin))
            curseur = fin
        if len(locales) >= 2 and (locales[-1][1] - locales[-1][0]) < seuil_reste:
            locales[-2] = (locales[-2][0], locales[-1][1])
            locales.pop()
        parties.extend(locales)
    return parties


def chauffe_partie(debut: float, passages: list[tuple[float, float]],
                   chauffe: float | None = None) -> float:
    """Chauffe réelle : pas avant le début du passage gardé, jamais dans un trou."""
    largeur = float(CHAUFFE if chauffe is None else chauffe)
    for a, b in passages:
        if a - _EPS <= debut < b - _EPS:
            return min(largeur, max(0.0, float(debut) - float(a)))
    return 0.0


def racine() -> Path:
    """%LOCALAPPDATA%\\VHSRestoreAI\\reprise, ou ~/.local/share sous Linux."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return Path(base) / "VHSRestoreAI" / "reprise"


def _chemin_source(info) -> str:
    return str(Path(info.path).resolve())


def _empreinte(path: Path) -> dict:
    st = Path(path).stat()
    return {"chemin": str(Path(path).resolve()), "taille": int(st.st_size), "date": int(st.st_mtime_ns)}


def _sources(info) -> list[dict]:
    chemins = list(info.parts) if getattr(info, "parts", None) else [info.path]
    return [_empreinte(Path(p)) for p in chemins]


def _canon(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _canon(dataclasses.asdict(obj))
    if isinstance(obj, Fraction):
        return f"{obj.numerator}/{obj.denominator}"
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (tuple, list)):
        return [_canon(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): _canon(v) for k, v in obj.items()}
    return obj


def _signature_scenes(info) -> list:
    out = []
    for sc in tuple(getattr(info, "scenes", ()) or ()):
        out.append({
            "debut": round(float(sc.debut), 6),
            "fin": round(float(sc.fin), 6),
            "noir": round(float(sc.noir), 6),
            "blanc": round(float(sc.blanc), 6),
            "gains": [round(float(g), 6) for g in sc.gains],
            "franche": bool(sc.franche),
            "rvb": [round(float(v), 6) for v in getattr(sc, "rvb", (0.0, 0.0, 0.0))],
        })
    return out


def calculer_cle(info, s, passages: list[tuple[float, float]]) -> str:
    """Empreinte du film, des réglages (scènes comprises) et du découpage."""
    charge = {
        "version": VERSION,
        "source": _sources(info),
        "reglages": _canon(s),
        "scenes": _signature_scenes(info),
        "passages": [[round(float(a), 6), round(float(b), 6)] for a, b in passages],
        "duree_partie": round(float(DUREE_PARTIE), 6),
        "chauffe": round(float(CHAUFFE), 6),
    }
    brut = json.dumps(charge, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def fichier(dossier: Path, index: int) -> Path:
    return dossier / f"partie-{index:04d}.mp4"


def temoin(dossier: Path, index: int) -> Path:
    return dossier / f"partie-{index:04d}.temoin"


def ecrire_temoin(path: Path, duree: float) -> None:
    """Écrit la durée attendue une fois la partie renommée à son nom définitif."""
    path.write_text(f"{float(duree):.9f}\n", encoding="utf-8")


def lire_temoin(path: Path) -> float | None:
    try:
        ligne = path.read_text(encoding="utf-8").strip().splitlines()[0]
        return float(ligne)
    except (OSError, ValueError, IndexError):
        return None


def _lire_manifeste(dossier: Path) -> dict | None:
    try:
        return json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _ecrire_manifeste(dossier: Path, info) -> None:
    premier = _sources(info)[0]
    data = {"version": VERSION, "chemin": premier["chemin"], "taille": premier["taille"],
            "date": premier["date"]}
    tmp = dossier / "manifeste.json.partiel"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, dossier / "manifeste.json")


def _activite(dossier: Path) -> float:
    dernier = dossier.stat().st_mtime
    try:
        for enfant in dossier.iterdir():
            try:
                dernier = max(dernier, enfant.stat().st_mtime)
            except OSError:
                pass
    except OSError:
        pass
    return dernier


def _a_nous(dossier: Path) -> bool:
    if (dossier / "manifeste.json").is_file():
        return True
    nom = dossier.name
    return len(nom) == 64 and all(c in "0123456789abcdef" for c in nom)


def menage(rac: Path, *, garder: str | None, chemin: str | None) -> None:
    """Efface les dossiers de plus de 30 jours, et ceux du même film sous une autre clé."""
    if not rac.is_dir():
        return
    limite = time.time() - AGE_JOURS * 86400
    for dossier in list(rac.iterdir()):
        if not dossier.is_dir() or not _a_nous(dossier):
            continue
        try:
            vieux = _activite(dossier) < limite
        except OSError:
            vieux = False
        manifeste = _lire_manifeste(dossier)
        meme_film = bool(chemin and manifeste and manifeste.get("chemin") == chemin
                         and dossier.name != garder)
        if vieux or meme_film:
            shutil.rmtree(dossier, ignore_errors=True)


def retirer_source(info) -> None:
    """Une restauration qui ne reprend pas efface les parties de ce film."""
    rac = racine()
    if not rac.is_dir():
        return
    menage(rac, garder=None, chemin=_chemin_source(info))


def preparer(info, s, passages: list[tuple[float, float]]) -> Path:
    """Dossier de la clé. L'ancienne clé du même film est effacée."""
    cle = calculer_cle(info, s, passages)
    rac = racine()
    rac.mkdir(parents=True, exist_ok=True)
    menage(rac, garder=cle, chemin=_chemin_source(info))
    dossier = rac / cle
    dossier.mkdir(parents=True, exist_ok=True)
    _ecrire_manifeste(dossier, info)
    for reste in dossier.glob("*.partiel*"):
        effacer(reste)
    return dossier


def supprimer(dossier: Path) -> None:
    shutil.rmtree(dossier, ignore_errors=True)


def oublier_partie(dossier: Path, index: int) -> None:
    """Une partie incomplète ou douteuse ne doit jamais être réutilisée."""
    effacer(fichier(dossier, index))
    effacer(temoin(dossier, index))
    for reste in dossier.glob(f"partie-{index:04d}*.partiel*"):
        effacer(reste)
    for reste in dossier.glob("vhs-*.partiel*"):
        effacer(reste)


def sonder(ffprobe: str, fichier_partie: Path, duree: float, fps: float, attend_son: bool) -> bool:
    """ffprobe : durée à une image près, image présente, son présent s'il est attendu."""
    if not ffprobe or not fichier_partie.is_file() or fichier_partie.stat().st_size < 32:
        return False
    try:
        r = run_capture([ffprobe, "-v", "error", "-show_entries",
                         "stream=codec_type,duration:format=duration", "-of", "json",
                         str(fichier_partie)], timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0 or not (r.stdout or "").strip():
        return False
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False
    streams = data.get("streams") or []
    video = next((flux for flux in streams if flux.get("codec_type") == "video"), None)
    if video is None:
        return False
    if attend_son and not any(flux.get("codec_type") == "audio" for flux in streams):
        return False
    brut = video.get("duration") or (data.get("format") or {}).get("duration")
    if brut in (None, "", "N/A"):
        brut = (data.get("format") or {}).get("duration")
    try:
        mesure = float(brut)
    except (TypeError, ValueError):
        return False
    tolerance = (1.0 / float(fps) if fps else 0.04) + 1e-3
    return abs(mesure - float(duree)) <= tolerance


def partie_valide(ffprobe: str, fichier_partie: Path, chemin_temoin: Path,
                  duree: float, fps: float, attend_son: bool) -> bool:
    """Faite seulement si le témoin annonce la durée prévue et que ffprobe confirme."""
    annoncee = lire_temoin(chemin_temoin)
    if annoncee is None or abs(annoncee - float(duree)) > 1e-3:
        return False
    return sonder(ffprobe, fichier_partie, duree, fps, attend_son)


def verifier_place(besoins: list[tuple[Path, float]]) -> None:
    """Place pour les parties encore à écrire et pour le résultat, avant de commencer.

    Deux dossiers sur le même disque : les besoins s'additionnent.
    """
    racines: dict[int, tuple[Path, float, float]] = {}
    for dossier, octets in besoins:
        if octets <= 0:
            continue
        dossier = Path(dossier)
        try:
            dev = os.stat(dossier).st_dev
        except OSError:
            continue
        libre = shutil.disk_usage(dossier).free
        ancien = racines.get(dev)
        if ancien is None:
            racines[dev] = (dossier, float(octets), libre)
        else:
            racines[dev] = (ancien[0], ancien[1] + float(octets), min(ancien[2], libre))
    for dossier, besoin, libre in racines.values():
        if libre < besoin * 1.1:
            raise ToolError(
                f"Espace disque insuffisant dans {dossier} : il faut environ "
                f"{besoin / 1e9:.1f} Go, il en reste {libre / 1e9:.1f} Go. Libérez de la place "
                "ou choisissez un autre dossier de sortie (disque externe, par exemple).")
