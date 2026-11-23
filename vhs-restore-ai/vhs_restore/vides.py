"""Passages vides d'une cassette : neige, écran bleu, noir, image grise.

Une cassette commence et finit souvent par de la neige ou un écran bleu, et contient parfois
des « trous » entre deux enregistrements. Le logiciel les repère et propose une **copie** du film
sans ces passages. Le fichier d'origine n'est jamais modifié ; rien n'est retiré sans accord.

Mesure (calibrée sur des passages de synthèse et deux vrais films) : 4 images par seconde,
réduites à 48×36 (moyenne par zone), écart entre zones sombres et claires (YHIGH − YLOW de
signalstats). Neige (capture 320 ou 720 de large) : 5 à 11 ; écran bleu, noir : 0. Images
réelles : 74 (VHS 1988) à 123. Un passage est « vide » si l'écart reste ≤ 20 pendant au moins
2 secondes. Une scène très sombre ou un mur
blanc filmé de près peuvent être pris pour un passage vide : la liste est toujours montrée avant.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .tools import Cancelled, ToolError, run

Progress = Callable[[float, str], None]

PAS = 0.25            # secondes entre deux mesures (4 images par seconde)
ECART_MAX = 20.0      # écart sombre / clair au-delà duquel il y a une vraie image
DUREE_MIN = 2.0       # un passage plus court n'est pas proposé
TROU_MAX = 0.5        # une image « pleine » isolée n'interrompt pas un passage vide


@dataclass
class Passage:
    debut: float
    fin: float
    genre: str            # « écran noir » | « écran bleu ou coloré » | « neige ou écran gris »

    @property
    def duree(self) -> float:
        return self.fin - self.debut


def _hms(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def decrire(p: Passage) -> str:
    return f"de {_hms(p.debut)} à {_hms(p.fin)} : {p.genre} ({_hms(p.duree)})"


def _genre(mesures: list[dict]) -> str:
    haut = sorted(m["YHIGH"] for m in mesures)[len(mesures) // 2]
    sat = sorted(m["SATAVG"] for m in mesures)[len(mesures) // 2]
    if haut < 45:
        return "écran noir"
    if sat > 20:
        return "écran bleu ou coloré"
    return "neige ou écran gris"


def regrouper(mesures: list[dict], duree_totale: float) -> list[Passage]:
    """Mesures (t, YLOW, YHIGH, SATAVG) -> passages vides d'au moins DUREE_MIN secondes."""
    passages: list[Passage] = []
    groupe: list[dict] = []
    dernier_vide = None
    for m in mesures:
        vide = m["YHIGH"] - m["YLOW"] <= ECART_MAX
        if vide:
            if groupe and dernier_vide is not None and m["t"] - dernier_vide > TROU_MAX + PAS:
                passages.append(_fermer(groupe))
                groupe = []
            groupe.append(m)
            dernier_vide = m["t"]
    if groupe:
        passages.append(_fermer(groupe))
    out = []
    for p in passages:
        p.fin = min(p.fin, duree_totale) if duree_totale else p.fin
        if p.duree >= DUREE_MIN:
            out.append(p)
    # tout le film « vide » : sans doute une erreur de mesure, rien n'est proposé
    if duree_totale and sum(p.duree for p in out) > duree_totale - 1.0:
        return []
    return out


def _fermer(groupe: list[dict]) -> Passage:
    return Passage(groupe[0]["t"], groupe[-1]["t"] + PAS, _genre(groupe))


def detecter(ffmpeg: str, path: Path, duree: float, *, cancel: threading.Event | None = None,
             progress: Progress | None = None) -> list[Passage]:
    """Lit tout le film (vite : petites images) et renvoie les passages vides."""
    mesures: list[dict] = []
    courant: dict = {}

    def ligne(l: str) -> None:
        nonlocal courant
        m = re.search(r"pts_time:([\d.]+)", l)
        if m:
            if courant:
                mesures.append(courant)
            courant = {"t": float(m.group(1))}
            if progress and duree:
                progress(min(0.99, courant["t"] / duree), "Recherche des passages vides…")
            return
        m = re.search(r"signalstats\.(YLOW|YHIGH|SATAVG)=([\d.]+)", l)
        if m and courant is not None:
            courant[m.group(1)] = float(m.group(2))

    run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:v:0", "-vf",
         f"fps={1 / PAS:g},scale=48:36:flags=area,signalstats,metadata=print",
         "-an", "-f", "null", "-"], cancel=cancel, on_line=ligne, what="FFmpeg (passages vides)")
    if courant:
        mesures.append(courant)
    mesures = [m for m in mesures if {"YLOW", "YHIGH", "SATAVG"} <= m.keys()]
    return regrouper(mesures, duree)


def a_garder(passages: list[Passage], duree: float) -> list[tuple[float, float]]:
    """Intervalles conservés, dans l'ordre."""
    garde, t = [], 0.0
    for p in sorted(passages, key=lambda x: x.debut):
        if p.debut - t > 0.05:
            garde.append((t, p.debut))
        t = max(t, p.fin)
    if duree - t > 0.05:
        garde.append((t, duree))
    return garde


def sortie_sans_vides(src: Path) -> Path:
    base = f"{src.stem}_sans_vides"
    cand, n = src.with_name(f"{base}.mp4"), 2
    while cand.exists():
        cand, n = src.with_name(f"{base} ({n}).mp4"), n + 1
    return cand


def retirer(ffmpeg: str, src: Path, dst: Path, passages: list[Passage], duree: float, avec_son: bool, *,
            cancel: threading.Event | None = None, progress: Progress | None = None) -> Path:
    """Copie du film sans les passages vides (réencodée en haute qualité, x264 CRF 16).
    Le fichier d'origine n'est pas modifié ; le résultat n'apparaît qu'une fois complet."""
    src, dst = Path(src), Path(dst)
    if dst.resolve() == src.resolve():
        raise ToolError("La copie ne peut pas remplacer le fichier d'origine.")
    garde = a_garder(passages, duree)
    if not garde:
        raise ToolError("Il ne resterait rien du film : rien n'a été retiré.")
    parts, labels = [], ""
    for i, (a, b) in enumerate(garde):
        parts.append(f"[0:v:0]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        labels += f"[v{i}]"
        if avec_son:
            parts.append(f"[0:a:0]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
            labels += f"[a{i}]"
    parts.append(f"{labels}concat=n={len(garde)}:v=1:a={1 if avec_son else 0}[v]" + ("[a]" if avec_son else ""))
    total = sum(b - a for a, b in garde)
    partiel = dst.with_name(dst.stem + ".partiel.mp4")

    def ligne(l: str) -> None:
        if progress and l.startswith("out_time_us="):
            try:
                t = int(l.split("=", 1)[1]) / 1e6
            except ValueError:
                return
            progress(min(0.99, t / max(total, 0.001)), "Copie sans les passages vides…")

    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning", "-progress", "pipe:1",
           "-nostats", "-i", str(src), "-filter_complex", ";".join(parts), "-map", "[v]"]
    if avec_son:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(partiel)]
    try:
        run(cmd, cancel=cancel, on_line=ligne, what="FFmpeg (copie sans passages vides)")
        partiel.replace(dst)
    except BaseException:
        partiel.unlink(missing_ok=True)
        raise
    if progress:
        progress(1.0, "Terminé")
    return dst


__all__ = ["Cancelled", "Passage", "a_garder", "decrire", "detecter", "regrouper", "retirer", "sortie_sans_vides"]
