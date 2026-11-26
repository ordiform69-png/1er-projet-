"""Court aperçu des images réellement gardées de part et d’autre d’une coupe."""
from __future__ import annotations

import threading
from pathlib import Path
from uuid import uuid4

from . import pipeline
from .dvd import input_args, lecture_dvd
from .probe import MediaInfo
from .profiles import profile_for
from .tools import AAC, Toolset, effacer, ff_input, finaliser, run, verifier_chemin

Plages = tuple[tuple[float, float], ...]
CONTEXTE = 3.0


def extrait(duree: float, debut: float, fin: float, coupes: list[tuple[float, float]], ici: float) -> Plages:
    """Choisit le raccord le plus proche du curseur, ou la borne extérieure."""
    if duree <= 0:
        return ()
    gardes = pipeline.passages_gardes(duree, debut, fin, coupes)
    choix: list[tuple[float, Plages]] = []
    premier, dernier = gardes[0], gardes[-1]
    if premier[0] > 0:
        a, b = premier
        choix.append((abs(ici - a), ((a, min(b, a + 2 * CONTEXTE)),)))
    for (a, b), (c, d) in zip(gardes, gardes[1:]):
        plages = ((max(a, b - CONTEXTE), b), (c, min(d, c + CONTEXTE)))
        choix.append((min(abs(ici - b), abs(ici - c)), plages))
    if dernier[1] < duree:
        a, b = dernier
        choix.append((abs(ici - b), ((max(a, b - 2 * CONTEXTE), b),)))
    return min(choix, key=lambda item: item[0])[1] if choix else ()


@lecture_dvd
def fabriquer(info: MediaInfo, outils: Toolset, dossier: Path, plages: Plages,
              cancel: threading.Event | None = None) -> Path:
    """Enchaîne les deux côtés sans modifier le film ni appliquer de restauration."""
    duree = sum(fin - debut for debut, fin in plages)
    dossier.mkdir(parents=True, exist_ok=True)
    final = dossier / f"coupe-{uuid4().hex[:12]}.mp4"
    partiel = final.with_suffix(".partiel.mp4")
    verifier_chemin(info.path, origine=True)
    verifier_chemin(partiel)
    pipeline.check_fat32(info, pipeline.Settings(profile_for("fidele")), dossier, duration=duree)
    for ancien in dossier.glob("coupe-*.mp4"):
        effacer(ancien)
    cmd = [outils.ffmpeg.path, "-hide_banner", "-nostdin", "-loglevel", "error"]
    entree = input_args(info) if len(info.parts) > 1 else ff_input(info.path)
    rapport = float(info.dar) if info.dar > 0 else 4 / 3
    hauteur = max(2, int(min(info.height or 540, 540, 960 / rapport)) // 2 * 2)
    largeur = max(2, int(hauteur * rapport) // 2 * 2)
    cadence = str(info.fps or 25)
    desentrelacer = f"bwdif=mode=send_frame:parity={info.scan}," if info.scan in ("tff", "bff") else ""
    filtres, entrees = [], []
    for i, (debut, fin) in enumerate(plages):
        longueur = f"{fin - debut:.3f}"
        cmd += ["-ss", f"{debut:.3f}", "-t", longueur, *entree]
        filtres.append(
            f"[{i}:v:0]{desentrelacer}fps={cadence},scale={largeur}:{hauteur}:flags=fast_bilinear,"
            f"setsar=1,format=yuv420p,trim=duration={longueur},setpts=PTS-STARTPTS[v{i}]")
        entrees.append(f"[v{i}]")
        if info.has_audio:
            filtres.append(f"[{i}:a:0]aresample=48000:async=1:first_pts=0,"
                           f"apad=whole_dur={longueur},atrim=duration={longueur},asetpts=PTS-STARTPTS[a{i}]")
            entrees.append(f"[a{i}]")
    son = int(info.has_audio)
    filtres.append(f"{''.join(entrees)}concat=n={len(plages)}:v=1:a={son}[image]" + ("[son]" if son else ""))
    cmd += ["-filter_complex_threads", "1", "-filter_complex", ";".join(filtres),
            "-map", "[image]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-threads", "2"]
    if son:
        cmd += ["-map", "[son]", *AAC, "-b:a", "160k"]
    try:
        run(cmd + ["-movflags", "+faststart", str(partiel)], cancel=cancel, what="FFmpeg (vérifier la coupe)")
        finaliser(partiel, final)
    finally:
        effacer(partiel)
    return final
