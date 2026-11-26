#!/usr/bin/env python3
"""Mesures reproductibles « avant / après » pour la demande n°17 (qualité de restauration).

Ne modifie ni le moteur ni les tests. Aucune dépendance nouvelle : bibliothèque
standard, FFmpeg déjà requis, et le paquet vhs_restore du dépôt.

Usage (depuis n'importe quel répertoire) :

    python3 mesurer.py --phase avant
    python3 mesurer.py --phase apres

Les films de synthèse sont régénérés à l'identique à chaque run (recettes
figées ci-dessous). Les résultats bruts sont écrits à côté de ce script, ou
dans --outdir. Les fichiers vidéo restent dans --workdir (non versionnés).
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # vhs-restore-ai/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vhs_restore import pipeline  # noqa: E402
from vhs_restore.advice import advise, apply  # noqa: E402
from vhs_restore.probe import MediaInfo, analyze  # noqa: E402
from vhs_restore.profiles import profile_for  # noqa: E402
from vhs_restore.tools import detect_tools  # noqa: E402

# --- Films de synthèse figés (demande n°17, agents A et B) -------------------
# Trois scènes, PAL 720×576, 25 im/s, au moins 2 s chacune. L'aperçu à 20 s
# tombe dans la scène 2 (10–26 s si on compte 8+16+8 : 8–24 s).
LARGEUR, HAUTEUR, CADENCE = 720, 576, 25
DUREE_S1, DUREE_S2, DUREE_S3 = 8.0, 16.0, 8.0
# Recettes lavfi : même base testsrc2, puis dominante et niveaux.
# Réglées pour que l'analyse isolée conseille niveaux+dominante sur S1 et S3,
# et rien sur S2 (copie « normale », plage déjà ouverte, pas de dominante).
RECETTE_S1 = (
    "testsrc2=size=720x576:rate=25,setsar=16/15,"
    "colorchannelmixer=rr=1.20:gg=0.92:bb=0.55,"
    "colorlevels=romin=0.16:gomin=0.16:bomin=0.16:"
    "romax=0.48:gomax=0.48:bomax=0.48"
)
RECETTE_S2 = "testsrc2=size=720x576:rate=25,setsar=16/15"
RECETTE_S3 = (
    "testsrc2=size=720x576:rate=25,setsar=16/15,"
    "colorchannelmixer=rr=0.55:gg=0.92:bb=1.20,"
    "colorlevels=romin=0.52:gomin=0.52:bomin=0.52:"
    "romax=0.90:gomax=0.90:bomax=0.90"
)
SCENES = (
    {"id": "1", "nom": "sombre et orangée", "duree": DUREE_S1, "recette": RECETTE_S1, "debut": 0.0},
    {"id": "2", "nom": "normale", "duree": DUREE_S2, "recette": RECETTE_S2, "debut": DUREE_S1},
    {"id": "3", "nom": "claire et bleutée", "duree": DUREE_S3, "recette": RECETTE_S3,
     "debut": DUREE_S1 + DUREE_S2},
)
DUREE_FILM = DUREE_S1 + DUREE_S2 + DUREE_S3  # 32 s
DUREE_RAMPE = 4.0
# Rampe de gris 16 bits, 720 valeurs distinctes, écrasée dans 48–176 / 255
# (déclenche le conseil « niveaux » : hi−lo < 140, lo > 35, hi < 190).
RAMPE_YMIN, RAMPE_YMAX = 48, 176
LUMIERE_GAMMA = 2  # cran utilisateur : gamma = 1 + 0,10 × 2 = 1,2 via eq (8 bits)
NB_RUNS_TEMPS = 3
# Recette agent B (recette-agent-B.md / tests/test_precision.py) : rampe déjà en
# 10 bits, une seule image, niveaux forcés 0,2–0,75, lumière +2. Distincte de la
# rampe 16 bits grise ci-dessus. Y en codes 10 bits, chroma neutre.
RAMPE_B_Y0, RAMPE_B_Y1, RAMPE_B_CHROMA = 180, 700, 512
RAMPE_B_NOIR, RAMPE_B_BLANC = 0.2, 0.75
PARIS = timezone(timedelta(hours=1), name="Europe/Paris")  # heure d'hiver 2026-11


def ff(ffmpeg: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and r.returncode:
        raise RuntimeError(f"ffmpeg a échoué ({r.returncode}) : {r.stderr[-1200:]}\n{args}")
    return r


def maintenant() -> str:
    return datetime.now(PARIS).strftime("%Y-%m-%d %H:%M:%S Europe/Paris (UTC+1)")


def materiel() -> dict:
    cpu = "?"
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        cpu = platform.processor() or "?"
    mem = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith(("MemTotal:", "MemAvailable:")):
                mem[line.split(":")[0]] = int(line.split()[1])  # kB
    except OSError:
        pass
    ffv = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    premiere = (ffv.stdout or ffv.stderr).splitlines()[0] if ffv.stdout or ffv.stderr else "?"
    return {
        "cpu": cpu,
        "coeurs": os.cpu_count(),
        "ram_totale_mio": round(mem.get("MemTotal", 0) / 1024, 1),
        "ram_dispo_mio": round(mem.get("MemAvailable", 0) / 1024, 1),
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "ffmpeg": premiere,
        "hostname": platform.node(),
    }


def sha_depot(racine: Path) -> str:
    r = subprocess.run(
        ["git", "-C", str(racine), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else "?"


def ecrire_rampe_16b(dest_raw: Path, n_images: int) -> None:
    """Rampe horizontale gray16le, une valeur distincte par colonne, Y dans [48, 176]/255."""
    ymin = int(round(RAMPE_YMIN * 65535 / 255))
    ymax = int(round(RAMPE_YMAX * 65535 / 255))
    row = bytearray()
    for x in range(LARGEUR):
        v = ymin + int(round(x * (ymax - ymin) / (LARGEUR - 1)))
        row += v.to_bytes(2, "little")
    frame = bytes(row) * HAUTEUR
    with dest_raw.open("wb") as f:
        for _ in range(n_images):
            f.write(frame)


def ecrire_rampe_b_10b(dest: Path) -> None:
    """Une image yuv420p10le : Y = 180 + arrondi(x × 520 / 719), U = V = 512."""
    row = bytearray()
    for x in range(LARGEUR):
        v = RAMPE_B_Y0 + int(round(x * (RAMPE_B_Y1 - RAMPE_B_Y0) / (LARGEUR - 1)))
        row += v.to_bytes(2, "little")
    y = bytes(row) * HAUTEUR
    chroma = (RAMPE_B_CHROMA.to_bytes(2, "little") * (LARGEUR // 2)) * (HAUTEUR // 2)
    dest.write_bytes(y + chroma + chroma)


def _info_rampe_b(path: Path) -> MediaInfo:
    return MediaInfo(path=path, width=LARGEUR, height=HAUTEUR, fps=Fraction(25),
                     duration=1 / CADENCE, dar=Fraction(4, 3), sar=Fraction(1),
                     scan="progressive", pix_fmt="yuv420p10le")


def reglages_rampe_b() -> pipeline.Settings:
    """Niveaux forcés 0,2 / 0,75, lumière +2, profil Fidèle nu (recette B)."""
    return dataclasses.replace(
        reglages_nu(), lumiere=LUMIERE_GAMMA,
        level_black=RAMPE_B_NOIR, level_white=RAMPE_B_BLANC,
    )


def _ligne_gray_ffmpeg(ffmpeg: str, raw: bytes, vf: str) -> list[int]:
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "yuv420p10le",
         "-s", f"{LARGEUR}x{HAUTEUR}", "-i", "pipe:0",
         "-vf", vf + ("" if vf.endswith("format=gray") or ",format=gray" in vf
                      else ",format=gray"),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        input=raw, capture_output=True,
    )
    if r.returncode or len(r.stdout) < LARGEUR * HAUTEUR:
        raise RuntimeError(f"rampe B ffmpeg a échoué : {(r.stderr or b'')[-800:]!r}")
    offset = (HAUTEUR // 2) * LARGEUR
    return list(r.stdout[offset:offset + LARGEUR])


def mesurer_degrades_b(ffmpeg: str, work: Path, tools) -> tuple[dict, list[int], list[int], list[int]]:
    """Rampe 10 bits de l'agent B : référence 8 bits, chaîne moteur, export livré.

    Sur la base 8 bits, colorlevels/eq appliqués directement à du yuv420p10le
    écrasent l'image (1 niveau). La référence de B convertit d'abord en
    format=yuv420p, puis applique les mêmes colorlevels et eq=gamma=1.2.
    C'est cette référence (117 niveaux, saut max 5, mesuré par B en FFmpeg 6.1)
    que l'on compare à la chaîne moteur et au MP4 livré.
    """
    work.mkdir(parents=True, exist_ok=True)
    raw_path = work / "rampe-B.yuv"
    ecrire_rampe_b_10b(raw_path)
    raw = raw_path.read_bytes()
    src = work / "rampe-B.mkv"
    ff(ffmpeg, "-f", "rawvideo", "-pix_fmt", "yuv420p10le",
       "-s", f"{LARGEUR}x{HAUTEUR}", "-r", str(CADENCE),
       "-i", str(raw_path), "-frames:v", "1",
       "-c:v", "ffv1", "-pix_fmt", "yuv420p10le", str(src))

    s = reglages_rampe_b()
    info_construit = _info_rampe_b(raw_path)
    chaine_moteur = pipeline.filter_chain(info_construit, s)
    niveaux = next((f for f in chaine_moteur.split(",") if f.startswith("colorlevels=")), None)
    if niveaux is None:
        raise RuntimeError(f"pas de colorlevels dans la chaîne moteur : {chaine_moteur}")
    chaine_ref_8b = (
        f"format=yuv420p,{niveaux},eq=contrast=1:saturation=1:gamma=1.2,format=yuv420p"
    )

    ligne_ref = _ligne_gray_ffmpeg(ffmpeg, raw, chaine_ref_8b)
    ligne_moteur = _ligne_gray_ffmpeg(ffmpeg, raw, chaine_moteur)

    info_fichier = analyze(src, tools)
    chaine_export = pipeline.filter_chain(info_fichier, s)
    out_mp4 = pipeline.export(info_fichier, s, work / "rampe-B-restauree.mp4", tools)
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(out_mp4),
         "-frames:v", "1", "-an", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
    )
    if r.returncode or len(r.stdout) < LARGEUR * HAUTEUR:
        raise RuntimeError(f"extraction MP4 rampe B échouée : {(r.stderr or b'')[-400:]!r}")
    offset = (HAUTEUR // 2) * LARGEUR
    ligne_mp4 = list(r.stdout[offset:offset + LARGEUR])

    def bloc(ligne, chaine=None, extra=None):
        d = {**stats_marches(ligne), "unite": "0-255", "moyenne_ligne": (sum(ligne) / len(ligne)) if ligne else None}
        if chaine is not None:
            d["chaine"] = chaine
        if extra:
            d.update(extra)
        return d

    data = {
        "recette": "agent-B",
        "description": "yuv420p10le, 1 image 720×576, Y 180–700, U=V=512, niveaux forcés 0,2/0,75, lumière +2",
        "reference_8bits": bloc(ligne_ref, chaine_ref_8b),
        "chaine_moteur_sur_10bits": bloc(ligne_moteur, chaine_moteur),
        "fichier_livre_mp4": bloc(ligne_mp4, chaine_export),
        "pix_fmt_source": info_fichier.pix_fmt,
        "color_range": info_fichier.color_range,
        "level_black": RAMPE_B_NOIR,
        "level_white": RAMPE_B_BLANC,
        "lumiere_cran": LUMIERE_GAMMA,
    }
    return data, ligne_ref, ligne_moteur, ligne_mp4


def fabriquer_sources(ffmpeg: str, work: Path) -> dict[str, Path]:
    chemins: dict[str, Path] = {}
    for sc in SCENES:
        p = work / f"scene-{sc['id']}.mkv"
        ff(ffmpeg, "-f", "lavfi", "-i", sc["recette"], "-t", f"{sc['duree']:.3f}",
           "-c:v", "ffv1", str(p))
        chemins[f"scene-{sc['id']}"] = p
    film = work / "film-3scenes.mkv"
    # Filtre concat (une piste FFV1 continue). Le démultiplexeur concat, lui,
    # sautait la scène 2 pendant l'analyse du moteur (-frames:v 600 ne lisait
    # que 400 images, scènes 1 et 3) : ce n'est pas un fichier réel.
    ff(ffmpeg,
       "-i", str(chemins["scene-1"]),
       "-i", str(chemins["scene-2"]),
       "-i", str(chemins["scene-3"]),
       "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,setsar=16/15",
       "-c:v", "ffv1", str(film))
    chemins["film"] = film

    n = int(DUREE_RAMPE * CADENCE)
    raw = work / "rampe.gray16le"
    ecrire_rampe_16b(raw, n)
    rampe = work / "rampe-gris.mkv"
    ff(ffmpeg,
       "-f", "rawvideo", "-pix_fmt", "gray16le",
       "-s:v", f"{LARGEUR}x{HAUTEUR}", "-r", str(CADENCE),
       "-i", str(raw), "-frames:v", str(n),
       "-c:v", "ffv1", "-pix_fmt", "gray16le", str(rampe))
    raw.unlink(missing_ok=True)
    chemins["rampe"] = rampe
    return chemins


def mediane(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    return s[len(s) // 2]


def _fenetre(start: float, n_images: int) -> str:
    """trim + setpts : fenêtre précise à l'image (FFV1 et H.264)."""
    dur = n_images / CADENCE + 0.04
    return f"trim=start={start:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS"


def signalstats(ffmpeg: str, path: Path, start: float, n_images: int = 8) -> dict[str, float | None]:
    vf = (
        _fenetre(start, n_images) + ","
        "signalstats,metadata=print:key=lavfi.signalstats.YLOW,"
        "metadata=print:key=lavfi.signalstats.YHIGH,"
        "metadata=print:key=lavfi.signalstats.YAVG,"
        "metadata=print:key=lavfi.signalstats.UAVG,"
        "metadata=print:key=lavfi.signalstats.VAVG,"
        "metadata=print:key=lavfi.signalstats.SATAVG"
    )
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path), "-an",
         "-vf", vf, "-frames:v", str(n_images), "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode:
        raise RuntimeError(f"signalstats a échoué : {r.stderr[-800:]}")
    out: dict[str, float | None] = {}
    for key in ("YLOW", "YHIGH", "YAVG", "UAVG", "VAVG", "SATAVG"):
        vals = [float(x) for x in re.findall(rf"signalstats\.{key}=([\d.]+)", r.stderr)]
        out[key.lower()] = mediane(vals)
    return out


def rgb_moy(ffmpeg: str, path: Path, start: float, n_images: int = 8) -> tuple[float, float, float] | None:
    vf = _fenetre(start, n_images) + ",scale=32:32,format=rgb24"
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path),
         "-map", "0:v:0", "-vf", vf,
         "-frames:v", str(n_images), "-an", "-f", "rawvideo", "-"],
        capture_output=True, timeout=60,
    )
    data = r.stdout or b""
    if r.returncode or len(data) < 32 * 32 * 3:
        return None
    n = len(data) // 3
    return (sum(data[0::3]) / n, sum(data[1::3]) / n, sum(data[2::3]) / n)


def mesures_image(ffmpeg: str, path: Path, start: float) -> dict:
    sig = signalstats(ffmpeg, path, start)
    rgb = rgb_moy(ffmpeg, path, start)
    span = None if rgb is None else max(rgb) - min(rgb)
    u, v = sig.get("uavg"), sig.get("vavg")
    chroma = None if u is None or v is None else abs(u - 128.0) + abs(v - 128.0)
    return {
        **{k: sig.get(k) for k in ("ylow", "yhigh", "yavg", "uavg", "vavg", "satavg")},
        "r": None if rgb is None else rgb[0],
        "g": None if rgb is None else rgb[1],
        "b": None if rgb is None else rgb[2],
        "span_rgb": span,
        "ecart_chroma": chroma,
        "ouverture": None if sig.get("ylow") is None or sig.get("yhigh") is None
        else sig["yhigh"] - sig["ylow"],
        "debut_mesure_s": start,
    }


def profil_nu():
    """Fidèle, sans débruitage ni netteté : isole niveaux + dominante."""
    return dataclasses.replace(profile_for("fidele", "video"), denoise=None, sharpen=0.0, despeckle=False)


def reglages_nu(scan: str = "progressive") -> pipeline.Settings:
    return pipeline.Settings(
        profil_nu(), source="video", scan=scan, restore_audio=False,
        preset="ultrafast", crf=18, resolution="source",
        use_ai=False, stabilize=False, denoise_hq=False,
    )


def reglages_restauration() -> pipeline.Settings:
    """Réglages typiques pour le temps au minute : profil Équilibré, cadence source."""
    return pipeline.Settings(
        profile_for("equilibre", "video"), source="video", scan="progressive",
        restore_audio=False, preset="medium", crf=18, resolution="source",
        use_ai=False, stabilize=False, denoise_hq=False,
    )


def resume_analyse(info, conseils) -> dict:
    return {
        "duree_s": info.duration,
        "largeur": info.width,
        "hauteur": info.height,
        "level_low": info.level_low,
        "level_high": info.level_high,
        "cast_rgb": list(info.cast_rgb) if info.cast_rgb else None,
        "conseils": [{"key": a.key, "fix": a.fix} for a in conseils],
    }


def ligne_rampe(ffmpeg: str, path: Path, start: float, pix_fmt: str = "gray") -> list[int]:
    """Luminance de la ligne centrale (ligne 288, paire, compatible 4:2:0) d'une image."""
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path),
         "-vf", _fenetre(start, 1),
         "-frames:v", "1", "-an", "-f", "rawvideo", "-pix_fmt", pix_fmt, "-"],
        capture_output=True, timeout=60,
    )
    if r.returncode or not r.stdout:
        raise RuntimeError(f"extraction de ligne échouée : {(r.stderr or b'')[-400:]!r}")
    data = r.stdout
    if pix_fmt == "gray16le":
        row_bytes = LARGEUR * 2
        offset = (HAUTEUR // 2) * row_bytes
        strip = data[offset:offset + row_bytes]
        return [int.from_bytes(strip[i:i + 2], "little") for i in range(0, len(strip), 2)]
    offset = (HAUTEUR // 2) * LARGEUR
    return list(data[offset:offset + LARGEUR])


def stats_marches(valeurs: list[int]) -> dict:
    if not valeurs:
        return {"n_pixels": 0, "niveaux_distincts": 0, "saut_max": None,
                "saut_moyen_non_nul": None, "n_sauts_non_nuls": 0,
                "ymin": None, "ymax": None}
    sauts = [abs(valeurs[i] - valeurs[i - 1]) for i in range(1, len(valeurs))]
    non_nuls = [s for s in sauts if s > 0]
    return {
        "n_pixels": len(valeurs),
        "niveaux_distincts": len(set(valeurs)),
        "saut_max": max(sauts) if sauts else 0,
        "saut_moyen": (sum(sauts) / len(sauts)) if sauts else 0,
        "saut_moyen_non_nul": (sum(non_nuls) / len(non_nuls)) if non_nuls else 0,
        "n_sauts_non_nuls": len(non_nuls),
        "ymin": min(valeurs),
        "ymax": max(valeurs),
    }


def dump_filtre(ffmpeg: str, src: Path, chaine: str, dest_raw: Path) -> None:
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(src),
         "-vf", _fenetre(DUREE_RAMPE / 2, 1) + "," + chaine,
         "-frames:v", "1", "-an",
         "-f", "rawvideo", "-pix_fmt", "gray", str(dest_raw)],
        capture_output=True, text=True,
    )
    if r.returncode:
        raise RuntimeError(f"dump filtre échoué : {r.stderr[-800:]}")


def ecrire_csv(path: Path, lignes: list[dict]) -> None:
    if not lignes:
        return
    cols: list[str] = []
    for row in lignes:
        for k in row:
            if k not in cols:
                cols.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for row in lignes:
            w.writerow({k: _csv(v) for k, v in row.items()})


def _csv(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6f}".rstrip("0").rstrip(".")
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v


def texte_resume(data: dict) -> str:
    lignes = [
        f"Mesures « {data['phase']} » — demande n°17",
        f"Date : {data['date']}",
        f"Dépôt SHA : {data['sha']}",
        f"Branche : {data.get('branche', '')}",
        f"Matériel : {data['materiel']['cpu']}, {data['materiel']['coeurs']} cœurs, "
        f"RAM {data['materiel']['ram_totale_mio']} Mio "
        f"(dispo {data['materiel']['ram_dispo_mio']} Mio), {data['materiel']['os']}",
        f"FFmpeg : {data['materiel']['ffmpeg']}",
        f"Python : {data['materiel']['python']}",
        "",
        "=== Écart à la cible par scène ===",
        "Film : 3 scènes PAL 720×576 25 im/s, durée 8+16+8 = 32 s (FFV1).",
        "Correction unique = analyse du film entier + conseils (niveaux à moitié, safe_levels, safe_gains).",
        "Cible / oracle = la même correction, mesurée et appliquée à la scène seule.",
        "Cible idéale (repère) : YLOW=16, YHIGH=235 (plage TV ouverte), span RVB = 0, écart chroma = 0.",
        "",
    ]
    for sc in data["scenes"]:
        lignes.append(f"Scène {sc['id']} — {sc['nom']} (t={sc['debut']:.1f}–{sc['debut']+sc['duree']:.1f} s)")
        for etape, lab in (("source", "source"),
                           ("unique", "après correction unique (tout le film)"),
                           ("oracle", "cible : correction de la scène seule")):
            m = sc[etape]
            lignes.append(
                f"  {lab}: YLOW={_n(m['ylow'])} YHIGH={_n(m['yhigh'])} ouverture={_n(m['ouverture'])} "
                f"YAVG={_n(m['yavg'])} R,G,B=({_n(m['r'])}, {_n(m['g'])}, {_n(m['b'])}) "
                f"span_rvb={_n(m['span_rgb'])} écart_chroma={_n(m['ecart_chroma'])}"
            )
        u, o = sc["unique"], sc["oracle"]
        lignes.append(
            f"  écart unique vs oracle : "
            f"ΔYLOW={_d(u['ylow'], o['ylow'])} ΔYHIGH={_d(u['yhigh'], o['yhigh'])} "
            f"Δouverture={_d(u['ouverture'], o['ouverture'])} "
            f"Δspan_rvb={_d(u['span_rgb'], o['span_rgb'])} "
            f"Δchroma={_d(u['ecart_chroma'], o['ecart_chroma'])}"
        )
        lignes.append(
            f"  écart unique vs idéal (16/235, span 0) : "
            f"ΔYLOW={_d(u['ylow'], 16)} ΔYHIGH={_d(u['yhigh'], 235)} "
            f"span_rvb={_n(u['span_rgb'])} chroma={_n(u['ecart_chroma'])}"
        )
        lignes.append("")
    an = data["analyse_film"]
    lignes += [
        "Analyse du film entier (moteur actuel, une mesure pour tout le film) :",
        f"  YLOW={an['level_low']} YHIGH={an['level_high']} cast_rgb={an['cast_rgb']}",
        f"  conseils={an['conseils']}",
        f"  (durée {an['duree_s']} s < 60 s : l'échantillon commence à t=0, "
        f"IDET_FRAMES=600 images ≈ 24 s, soit scènes 1 et 2 pour les niveaux — "
        f"médiane ; 8 images au début pour la dominante).",
        "",
        "=== Marches dans les dégradés ===",
        f"Rampe de gris 16 bits, {LARGEUR} colonnes, Y source dans "
        f"[{RAMPE_YMIN}, {RAMPE_YMAX}]/255, {DUREE_RAMPE:.0f} s, plus gamma cran {LUMIERE_GAMMA} "
        f"(eq, 8 bits) et niveaux conseillés.",
    ]
    for nom, bloc in data["degrades"].items():
        if not isinstance(bloc, dict) or "niveaux_distincts" not in bloc:
            continue
        lignes.append(
            f"  {nom}: niveaux distincts={bloc['niveaux_distincts']}/{bloc['n_pixels']}, "
            f"saut max={bloc['saut_max']}, saut moyen (non nul)={_n(bloc.get('saut_moyen_non_nul'))}, "
            f"Y {bloc['ymin']}–{bloc['ymax']}"
        )
    if data.get("degrades_B"):
        b = data["degrades_B"]
        lignes += [
            "",
            "=== Marches dans les dégradés — recette agent B ===",
            f"Rampe yuv420p10le, 1 image, Y codes 10 bits {RAMPE_B_Y0}–{RAMPE_B_Y1}, "
            f"U=V={RAMPE_B_CHROMA}, niveaux forcés {RAMPE_B_NOIR}/{RAMPE_B_BLANC}, "
            f"lumière +{LUMIERE_GAMMA} (gamma 1,2).",
        ]
        for nom, lab in (
            ("reference_8bits", "référence 8 bits (format=yuv420p + colorlevels + eq)"),
            ("chaine_moteur_sur_10bits", "chaîne moteur appliquée au 10 bits"),
            ("fichier_livre_mp4", "fichier livré (pipeline.export, MP4 8 bits)"),
        ):
            bloc = b.get(nom) or {}
            if "niveaux_distincts" not in bloc:
                continue
            lignes.append(
                f"  {lab}: niveaux distincts={bloc['niveaux_distincts']}/{bloc['n_pixels']}, "
                f"saut max={bloc['saut_max']}, saut moyen (non nul)={_n(bloc.get('saut_moyen_non_nul'))}, "
                f"moyenne={_n(bloc.get('moyenne_ligne'))}, Y {bloc['ymin']}–{bloc['ymax']}"
            )
            if bloc.get("chaine"):
                lignes.append(f"    chaîne : {bloc['chaine']}")

    t = data["temps"]
    lignes += [
        "",
        "=== Temps de restauration par minute de film ===",
        f"Extrait : film 3 scènes, {t['duree_extrait_s']} s, 720×576, 25 im/s, FFV1 → H.264.",
        f"Réglages : profil {t['profil']}, scan={t['scan']}, preset={t['preset']}, crf={t['crf']}, "
        f"résolution={t['resolution']}, débruitage du profil, pas d'IA ni de stabilisation, pas de son.",
        f"Conseils du film appliqués : {t['conseils']}",
        f"Chaîne : {t['chaine']}",
    ]
    for i, run in enumerate(t["runs"], 1):
        lignes.append(
            f"  run {i}: {run['wall_s']:.3f} s d'horloge "
            f"→ {run['s_par_minute']:.2f} s de calcul par minute de film "
            f"({run['facteur']:.2f}× le temps réel)"
        )
    lignes.append(
        f"  médiane : {t['mediane_s_par_minute']:.2f} s de calcul par minute de film "
        f"(médiane des durées d'horloge {t['mediane_wall_s']:.3f} s "
        f"pour {t['duree_extrait_s']} s d'extrait)."
    )
    lignes.append("")
    return "\n".join(lignes)


def _n(v, q=3):
    if v is None:
        return "?"
    if isinstance(v, float):
        return f"{v:.{q}f}".rstrip("0").rstrip(".")
    return str(v)


def _d(a, b, q=3):
    if a is None or b is None:
        return "?"
    return _n(a - b, q)


def main() -> int:
    ici = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Mesures qualité n°17 (avant / après)")
    ap.add_argument("--phase", choices=("avant", "apres"), default="avant")
    ap.add_argument("--workdir", type=Path, default=Path("/tmp/mesures-n17"))
    ap.add_argument("--outdir", type=Path, default=ici)
    ap.add_argument("--runs", type=int, default=NB_RUNS_TEMPS)
    ap.add_argument("--seulement-degrades-B", action="store_true",
                    help="N'ajoute que la rampe 10 bits de l'agent B, sans refaire scènes/temps/rampe E.")
    args = ap.parse_args()
    if args.seulement_degrades_B:
        return _ajouter_degrades_b(args, ici)
    work = args.workdir / args.phase
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    tools = detect_tools()
    if not tools.ffmpeg.path:
        print("ffmpeg introuvable", file=sys.stderr)
        return 2
    ffmpeg = tools.ffmpeg.path
    racine_git = ROOT.parent
    sha = sha_depot(racine_git)
    br = subprocess.run(["git", "-C", str(racine_git), "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True, text=True)
    branche = br.stdout.strip() if br.returncode == 0 else "?"

    print(f"Phase {args.phase} — SHA {sha} ({branche})")
    print("Génération des films de synthèse…")
    chemins = fabriquer_sources(ffmpeg, work)

    print("Analyse du film entier et de chaque scène (source)…")
    info_film = analyze(chemins["film"], tools)
    conseils_film = advise(info_film)
    s_unique = apply(reglages_nu(), conseils_film)

    scenes_out = []
    for sc in SCENES:
        mid = sc["debut"] + sc["duree"] / 2
        src = mesures_image(ffmpeg, chemins["film"], mid)
        info_sc = analyze(chemins[f"scene-{sc['id']}"], tools)
        conseils_sc = advise(info_sc)
        s_oracle = apply(reglages_nu(), conseils_sc)
        out_oracle = pipeline.export(
            info_sc, s_oracle, work / f"oracle-scene-{sc['id']}.mp4", tools,
        )
        oracle = mesures_image(ffmpeg, out_oracle, sc["duree"] / 2)
        scenes_out.append({
            "id": sc["id"], "nom": sc["nom"], "debut": sc["debut"], "duree": sc["duree"],
            "milieu_s": mid, "recette": sc["recette"],
            "analyse_isolee": resume_analyse(info_sc, conseils_sc),
            "chaine_oracle": pipeline.filter_chain(info_sc, s_oracle),
            "source": src, "oracle": oracle, "unique": None,  # rempli après l'export unique
        })

    print("Export avec la correction unique du film entier (profil nu)…")
    t0 = time.perf_counter()
    out_unique = pipeline.export(info_film, s_unique, work / "film-unique.mp4", tools)
    duree_unique = time.perf_counter() - t0
    print(f"  export unique (nu) : {duree_unique:.2f} s")
    for i, sc in enumerate(SCENES):
        mid = sc["debut"] + sc["duree"] / 2
        scenes_out[i]["unique"] = mesures_image(ffmpeg, out_unique, mid)

    print("Mesure des marches (rampe + niveaux + gamma)…")
    info_rampe = analyze(chemins["rampe"], tools)
    conseils_rampe = advise(info_rampe)
    s_rampe = apply(reglages_nu(), conseils_rampe)
    s_rampe = dataclasses.replace(s_rampe, lumiere=LUMIERE_GAMMA)
    chaine_rampe = pipeline.filter_chain(info_rampe, s_rampe)
    out_rampe = pipeline.export(info_rampe, s_rampe, work / "rampe-restauree.mp4", tools)
    mid_r = DUREE_RAMPE / 2
    ligne_src16 = ligne_rampe(ffmpeg, chemins["rampe"], mid_r, "gray16le")
    # Source 16 bits ramenée sur 8 bits par simple division, sans tramage, pour référence.
    ligne_src8 = [v // 257 for v in ligne_src16]
    ligne_mp4 = ligne_rampe(ffmpeg, out_rampe, mid_r, "gray")
    dump_path = work / "rampe-filtre.gray"
    dump_filtre(ffmpeg, chemins["rampe"], chaine_rampe, dump_path)
    data_dump = dump_path.read_bytes()
    offset = (HAUTEUR // 2) * LARGEUR
    ligne_filtre = list(data_dump[offset:offset + LARGEUR])

    degrades = {
        "source_16bits": {**stats_marches(ligne_src16), "unite": "0-65535"},
        "source_divisee_8bits": {**stats_marches(ligne_src8), "unite": "0-255"},
        "apres_filtres_avant_x264": {**stats_marches(ligne_filtre), "unite": "0-255",
                                      "chaine": chaine_rampe},
        "fichier_livre_mp4": {**stats_marches(ligne_mp4), "unite": "0-255",
                              "chaine": chaine_rampe},
        "analyse_rampe": resume_analyse(info_rampe, conseils_rampe),
        "lumiere_cran": LUMIERE_GAMMA,
        "gamma": 1 + pipeline.PAS_LUMIERE * pipeline.cran(LUMIERE_GAMMA),
    }

    print("Mesure des marches (rampe 10 bits, recette agent B)…")
    degrades_b, ligne_b_ref, ligne_b_moteur, ligne_b_mp4 = mesurer_degrades_b(
        ffmpeg, work / "rampe-B", tools)

    print(f"Temps de restauration ({args.runs} runs, profil équilibré)…")
    s_temps = apply(reglages_restauration(), conseils_film)
    chaine_temps = pipeline.filter_chain(info_film, s_temps)
    runs = []
    for i in range(args.runs):
        dest = work / f"film-temps-{i + 1}.mp4"
        t0 = time.perf_counter()
        pipeline.export(info_film, s_temps, dest, tools)
        wall = time.perf_counter() - t0
        facteur = wall / DUREE_FILM
        runs.append({
            "wall_s": wall,
            "duree_extrait_s": DUREE_FILM,
            "s_par_minute": wall / DUREE_FILM * 60.0,
            "facteur": facteur,
        })
        print(f"  run {i + 1}/{args.runs}: {wall:.3f} s → {runs[-1]['s_par_minute']:.2f} s/min")
        dest.unlink(missing_ok=True)

    murs = sorted(r["wall_s"] for r in runs)
    mid = murs[len(murs) // 2]
    temps = {
        "duree_extrait_s": DUREE_FILM,
        "profil": "equilibre",
        "scan": "progressive",
        "preset": "medium",
        "crf": 18,
        "resolution": "source",
        "conseils": [{"key": a.key, "fix": a.fix} for a in conseils_film],
        "chaine": chaine_temps,
        "runs": runs,
        "mediane_wall_s": mid,
        "mediane_s_par_minute": mid / DUREE_FILM * 60.0,
    }

    data = {
        "phase": args.phase,
        "date": maintenant(),
        "sha": sha,
        "branche": branche,
        "demande": "n°17",
        "materiel": materiel(),
        "methode": "voir METHODE.md à côté de ce fichier",
        "analyse_film": resume_analyse(info_film, conseils_film),
        "chaine_unique_nu": pipeline.filter_chain(info_film, s_unique),
        "scenes": scenes_out,
        "degrades": degrades,
        "degrades_B": degrades_b,
        "temps": temps,
        "export_unique_nu_s": duree_unique,
    }

    suffixe = args.phase
    json_path = outdir / f"resultats-{suffixe}.json"
    txt_path = outdir / f"resultats-{suffixe}.txt"
    csv_scenes = outdir / f"resultats-{suffixe}-scenes.csv"
    csv_degrades = outdir / f"resultats-{suffixe}-degrades.csv"
    csv_temps = outdir / f"resultats-{suffixe}-temps.csv"
    csv_ligne = outdir / f"rampe-ligne-{suffixe}.csv"

    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    txt_path.write_text(texte_resume(data), encoding="utf-8")

    rows_sc = []
    for sc in scenes_out:
        for etape in ("source", "unique", "oracle"):
            row = {"phase": args.phase, "scene": sc["id"], "nom": sc["nom"],
                   "debut_s": sc["debut"], "duree_s": sc["duree"], "etape": etape}
            row.update(sc[etape])
            rows_sc.append(row)
    ecrire_csv(csv_scenes, rows_sc)

    rows_deg = []
    for nom in ("source_16bits", "source_divisee_8bits", "apres_filtres_avant_x264", "fichier_livre_mp4"):
        row = {"phase": args.phase, "mesure": nom}
        row.update({k: v for k, v in degrades[nom].items() if k != "chaine"})
        rows_deg.append(row)
    ecrire_csv(csv_degrades, rows_deg)
    ecrire_csv(csv_temps, [{"phase": args.phase, "run": i + 1, **r} for i, r in enumerate(runs)]
               + [{"phase": args.phase, "run": "mediane", "wall_s": temps["mediane_wall_s"],
                   "duree_extrait_s": DUREE_FILM,
                   "s_par_minute": temps["mediane_s_par_minute"],
                   "facteur": temps["mediane_wall_s"] / DUREE_FILM}])

    with csv_ligne.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["x", "source_16bits", "source_divisee_8bits",
                    "apres_filtres_avant_x264", "fichier_livre_mp4"])
        for x in range(LARGEUR):
            w.writerow([x, ligne_src16[x], ligne_src8[x], ligne_filtre[x], ligne_mp4[x]])

    csv_degrades_b = outdir / f"resultats-{suffixe}-degrades-B.csv"
    csv_ligne_b = outdir / f"rampe-ligne-{suffixe}-B.csv"
    _ecrire_fichiers_b(csv_degrades_b, csv_ligne_b, args.phase, degrades_b,
                       ligne_b_ref, ligne_b_moteur, ligne_b_mp4)

    print()
    print(texte_resume(data))
    print("Fichiers écrits :")
    for pth in (json_path, txt_path, csv_scenes, csv_degrades, csv_temps, csv_ligne,
                csv_degrades_b, csv_ligne_b):
        print(f"  {pth}")
    return 0


def _ecrire_fichiers_b(csv_degrades_b: Path, csv_ligne_b: Path, phase: str, degrades_b: dict,
                       ligne_ref: list[int], ligne_moteur: list[int], ligne_mp4: list[int]) -> None:
    rows = []
    for nom in ("reference_8bits", "chaine_moteur_sur_10bits", "fichier_livre_mp4"):
        row = {"phase": phase, "recette": "agent-B", "mesure": nom}
        row.update({k: v for k, v in degrades_b[nom].items() if k != "chaine"})
        rows.append(row)
    ecrire_csv(csv_degrades_b, rows)
    with csv_ligne_b.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["x", "reference_8bits", "chaine_moteur_sur_10bits", "fichier_livre_mp4"])
        for x in range(LARGEUR):
            w.writerow([x, ligne_ref[x], ligne_moteur[x], ligne_mp4[x]])


def _ajouter_degrades_b(args, ici: Path) -> int:
    """Ajoute la mesure recette B aux résultats existants, sans refaire le reste."""
    tools = detect_tools()
    if not tools.ffmpeg.path:
        print("ffmpeg introuvable", file=sys.stderr)
        return 2
    ffmpeg = tools.ffmpeg.path
    outdir = args.outdir
    work = args.workdir / f"{args.phase}-rampe-B"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    print(f"Phase {args.phase} — seulement dégradés recette B")
    degrades_b, ligne_ref, ligne_moteur, ligne_mp4 = mesurer_degrades_b(ffmpeg, work, tools)

    json_path = outdir / f"resultats-{args.phase}.json"
    txt_path = outdir / f"resultats-{args.phase}.txt"
    if json_path.is_file():
        data = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        racine_git = ROOT.parent
        br = subprocess.run(["git", "-C", str(racine_git), "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True)
        data = {"phase": args.phase, "date": maintenant(), "sha": sha_depot(racine_git),
                "branche": br.stdout.strip() if br.returncode == 0 else "?",
                "materiel": materiel(), "degrades": {}, "scenes": [], "temps": {}}
    data["degrades_B"] = degrades_b
    data["date_degrades_B"] = maintenant()
    data["sha_degrades_B"] = sha_depot(ROOT.parent)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # Ajouter la section B au texte, sans écraser les notes déjà présentes.
    b_txt_lines = [
        "",
        f"=== Marches dans les dégradés — recette agent B (ajout {data['date_degrades_B']}, SHA {data['sha_degrades_B']}) ===",
        f"Rampe yuv420p10le, 1 image, Y codes 10 bits {RAMPE_B_Y0}–{RAMPE_B_Y1}, "
        f"U=V={RAMPE_B_CHROMA}, niveaux forcés {RAMPE_B_NOIR}/{RAMPE_B_BLANC}, "
        f"lumière +{LUMIERE_GAMMA} (gamma 1,2). Moteur encore à la base 8 bits.",
    ]
    for nom, lab in (
        ("reference_8bits", "référence 8 bits (format=yuv420p + colorlevels + eq)"),
        ("chaine_moteur_sur_10bits", "chaîne moteur appliquée au 10 bits"),
        ("fichier_livre_mp4", "fichier livré (pipeline.export, MP4 8 bits)"),
    ):
        bloc = degrades_b[nom]
        b_txt_lines.append(
            f"  {lab}: niveaux distincts={bloc['niveaux_distincts']}/{bloc['n_pixels']}, "
            f"saut max={bloc['saut_max']}, saut moyen (non nul)={_n(bloc.get('saut_moyen_non_nul'))}, "
            f"moyenne={_n(bloc.get('moyenne_ligne'))}, Y {bloc['ymin']}–{bloc['ymax']}"
        )
        if bloc.get("chaine"):
            b_txt_lines.append(f"    chaîne : {bloc['chaine']}")
    b_txt_lines.append("")
    if txt_path.is_file():
        prev = txt_path.read_text(encoding="utf-8")
        if "recette agent B" in prev:
            # replace previous B section if re-run
            start = prev.find("=== Marches dans les dégradés — recette agent B")
            if start >= 0:
                prev = prev[:start].rstrip() + "\n"
        txt_path.write_text(prev.rstrip() + "\n" + "\n".join(b_txt_lines), encoding="utf-8")
    else:
        txt_path.write_text("\n".join(b_txt_lines), encoding="utf-8")

    csv_degrades_b = outdir / f"resultats-{args.phase}-degrades-B.csv"
    csv_ligne_b = outdir / f"rampe-ligne-{args.phase}-B.csv"
    _ecrire_fichiers_b(csv_degrades_b, csv_ligne_b, args.phase, degrades_b,
                       ligne_ref, ligne_moteur, ligne_mp4)
    print("\n".join(b_txt_lines))
    print("Fichiers écrits :")
    for pth in (json_path, txt_path, csv_degrades_b, csv_ligne_b):
        print(f"  {pth}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
