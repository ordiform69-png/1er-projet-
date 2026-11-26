#!/usr/bin/env python3
"""Temps d'une restauration de 3 minutes : en une fois, puis par parties (n°19).

Films 720×576 entrelacés avec son, FFV1 4:2:2 et MPEG-2 4:2:0, hors dépôt.
La mesure « une fois » utilise pipeline.export (disponible dès maintenant).
La mesure « parties » appelle vhs_restore.reprise.restaurer et attend R1.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PARIS = timezone(timedelta(hours=1), name="Europe/Paris")
DUREE = 180.0
# Pour la mesure par parties : un film de 3 min est sous le seuil de production
# (20 min). On impose trois parties de 60 s, chauffe de production (8 s).
PARTIE_MESURE = 60.0
CHAUFFE_MESURE = 8.0
VF = (
    "testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,"
    "setfield=tff,setsar=16/15"
)
AF = "sine=frequency=440:sample_rate=48000"

# vhs-restore-ai/ à partir de ce fichier (partage-grok/mesures-n19/)
ROOT = Path(__file__).resolve().parents[2]


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
        pass
    mem = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith(("MemTotal:", "MemAvailable:")):
                mem[line.split(":")[0]] = int(line.split()[1])
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
    }


def sha_depot(racine: Path) -> str:
    r = subprocess.run(["git", "-C", str(racine), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "?"


def ff(ffmpeg: str, *args: str) -> None:
    r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-1200:] or "ffmpeg a échoué")


def fabriquer(ffmpeg: str, dossier: Path) -> dict[str, Path]:
    dossier.mkdir(parents=True, exist_ok=True)
    films = {}
    f422 = dossier / "film-180s-ffv1-422.mkv"
    ff(ffmpeg, "-f", "lavfi", "-i", VF, "-f", "lavfi", "-i", AF,
       "-t", f"{DUREE:.3f}", "-c:a", "pcm_s16le",
       "-pix_fmt", "yuv422p", "-c:v", "ffv1", str(f422))
    films["ffv1_422"] = f422
    f420 = dossier / "film-180s-mpeg2-420.mkv"
    ff(ffmpeg, "-f", "lavfi", "-i", VF, "-f", "lavfi", "-i", AF,
       "-t", f"{DUREE:.3f}", "-c:a", "pcm_s16le",
       "-pix_fmt", "yuv420p", "-c:v", "mpeg2video",
       "-flags", "+ilme+ildct", "-b:v", "8M", str(f420))
    films["mpeg2_420"] = f420
    return films


def _prep():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from vhs_restore.tools import detect_tools
    from vhs_restore.probe import analyze
    from vhs_restore.profiles import profile_for
    from vhs_restore import pipeline
    return detect_tools, analyze, profile_for, pipeline


def reglages(pipeline, profile_for):
    return pipeline.Settings(
        profile_for("equilibre", "video"), source="video",
        restore_audio=True, preset="medium", crf=18, resolution="source",
        use_ai=False, stabilize=False, denoise_hq=False,
    )


def mesurer_une_fois(cle: str, src: Path, work: Path, n_runs: int) -> dict:
    detect_tools, analyze, profile_for, pipeline = _prep()
    tools = detect_tools()
    t_an0 = time.perf_counter()
    info = analyze(src, tools)
    t_analyze = time.perf_counter() - t_an0
    s = reglages(pipeline, profile_for)
    chaine = pipeline.filter_chain(info, s)
    runs = []
    for i in range(n_runs):
        dest = work / f"une-fois-{cle}-{i + 1}.mp4"
        t0 = time.perf_counter()
        pipeline.export(info, s, dest, tools)
        wall = time.perf_counter() - t0
        runs.append({"run": i + 1, "wall_s": wall, "s_par_minute": wall / DUREE * 60.0})
        dest.unlink(missing_ok=True)
        print(f"  {cle} une-fois run {i + 1}/{n_runs}: {wall:.3f} s "
              f"→ {wall / DUREE * 60:.2f} s/min", flush=True)
    murs = sorted(r["wall_s"] for r in runs)
    mid = murs[len(murs) // 2]
    return {
        "film": str(src), "cle": cle, "mode": "une-fois",
        "duree_s": info.duration, "pix_fmt": info.pix_fmt, "scan": info.scan,
        "chaine": chaine, "analyze_s": t_analyze, "runs": runs,
        "mediane_wall_s": mid, "mediane_s_par_minute": mid / DUREE * 60.0,
    }


def mesurer_parties(cle: str, src: Path, work: Path, n_runs: int) -> dict:
    detect_tools, analyze, profile_for, pipeline = _prep()
    try:
        from vhs_restore import reprise
    except ImportError as exc:
        raise RuntimeError(
            "vhs_restore.reprise est absent : la mesure par parties attend l'agent R1 "
            "(branche grok/reprise-moteur)."
        ) from exc
    tools = detect_tools()
    t_an0 = time.perf_counter()
    info = analyze(src, tools)
    t_analyze = time.perf_counter() - t_an0
    s = reglages(pipeline, profile_for)
    # Film de 3 min < seuil de 20 min : on force le découpage pour mesurer les raccords.
    reprise.DUREE_PARTIE = PARTIE_MESURE
    reprise.SEUIL = 1.0
    reprise.CHAUFFE = CHAUFFE_MESURE
    racine = work / "reprise-dossiers"
    racine.mkdir(parents=True, exist_ok=True)
    reprise.dossier_racine = lambda: racine
    runs = []
    for i in range(n_runs):
        dest = work / f"parties-{cle}-{i + 1}.mp4"
        t0 = time.perf_counter()
        reprise.restaurer(info, s, dest, tools)
        wall = time.perf_counter() - t0
        runs.append({"run": i + 1, "wall_s": wall, "s_par_minute": wall / DUREE * 60.0})
        dest.unlink(missing_ok=True)
        print(f"  {cle} parties run {i + 1}/{n_runs}: {wall:.3f} s "
              f"→ {wall / DUREE * 60:.2f} s/min", flush=True)
    murs = sorted(r["wall_s"] for r in runs)
    mid = murs[len(murs) // 2]
    return {
        "film": str(src), "cle": cle, "mode": "parties",
        "duree_s": info.duration, "pix_fmt": info.pix_fmt, "scan": info.scan,
        "duree_partie_s": PARTIE_MESURE, "chauffe_s": CHAUFFE_MESURE,
        "analyze_s": t_analyze, "runs": runs,
        "mediane_wall_s": mid, "mediane_s_par_minute": mid / DUREE * 60.0,
    }


def ecrire(data: dict, outdir: Path, mode: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / f"resultats-{mode}.json"
    txt_path = outdir / f"resultats-{mode}.txt"
    csv_path = outdir / f"resultats-{mode}.csv"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str),
                         encoding="utf-8")
    lignes = [
        f"Temps de restauration n°19 — mode {mode}",
        f"Date : {data['date']}",
        f"SHA : {data['sha']}",
        f"Branche : {data.get('branche', '')}",
        f"Matériel : {data['materiel']['cpu']}, {data['materiel']['coeurs']} cœurs, "
        f"RAM {data['materiel']['ram_totale_mio']} Mio "
        f"(dispo {data['materiel']['ram_dispo_mio']} Mio), {data['materiel']['os']}",
        f"FFmpeg : {data['materiel']['ffmpeg']}",
        f"Méthode : {data['methode']}",
        "",
    ]
    rows = []
    for cle, bloc in data["films"].items():
        lignes += [
            f"=== {cle} ({bloc.get('pix_fmt')}, scan={bloc.get('scan')}, "
            f"{bloc.get('duree_s')} s) ===",
            f"  analyze={bloc.get('analyze_s', 0):.3f} s",
        ]
        for r in bloc["runs"]:
            lignes.append(f"  run {r['run']}: {r['wall_s']:.3f} s → {r['s_par_minute']:.2f} s/min")
            rows.append({"mode": mode, "film": cle, "run": r["run"],
                         "wall_s": r["wall_s"], "s_par_minute": r["s_par_minute"],
                         "pix_fmt": bloc.get("pix_fmt")})
        lignes.append(
            f"  médiane : {bloc['mediane_wall_s']:.3f} s "
            f"({bloc['mediane_s_par_minute']:.2f} s de calcul par minute de film)"
        )
        rows.append({"mode": mode, "film": cle, "run": "mediane",
                     "wall_s": bloc["mediane_wall_s"],
                     "s_par_minute": bloc["mediane_s_par_minute"],
                     "pix_fmt": bloc.get("pix_fmt")})
        lignes.append("")
    txt_path.write_text("\n".join(lignes), encoding="utf-8")
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print("\n".join(lignes))
    print("Écrit :", json_path, txt_path, csv_path)


def main() -> int:
    ici = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--fabriquer", action="store_true")
    ap.add_argument("--mode", choices=("une-fois", "parties"))
    ap.add_argument("--films-dir", type=Path, default=Path("/tmp/mesures-n19/films"))
    ap.add_argument("--workdir", type=Path, default=Path("/tmp/mesures-n19/work"))
    ap.add_argument("--outdir", type=Path, default=ici)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg introuvable", file=sys.stderr)
        return 2
    if args.fabriquer:
        print("Fabrication des films 180 s…", flush=True)
        films = fabriquer(ffmpeg, args.films_dir)
        for k, p in films.items():
            print(f"  {k}: {p} ({p.stat().st_size} octets)")
        return 0
    if not args.mode:
        print("--mode une-fois|parties requis (sauf --fabriquer)", file=sys.stderr)
        return 2
    films = {
        "ffv1_422": args.films_dir / "film-180s-ffv1-422.mkv",
        "mpeg2_420": args.films_dir / "film-180s-mpeg2-420.mkv",
    }
    for p in films.values():
        if not p.is_file():
            print(f"film manquant : {p} (lancez --fabriquer)", file=sys.stderr)
            return 2
    work = args.workdir / args.mode
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    racine_git = ROOT.parent
    br = subprocess.run(["git", "-C", str(racine_git), "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True, text=True)
    data = {
        "mode": args.mode,
        "date": maintenant(),
        "sha": sha_depot(racine_git),
        "branche": br.stdout.strip() if br.returncode == 0 else "?",
        "materiel": materiel(),
        "methode": "voir METHODE.md",
        "films": {},
    }
    print(f"Mode {args.mode} — SHA {data['sha']} ({data['branche']})", flush=True)
    fn = mesurer_une_fois if args.mode == "une-fois" else mesurer_parties
    for cle, src in films.items():
        print(f"Mesure {cle}…", flush=True)
        data["films"][cle] = fn(cle, src, work, args.runs)
    ecrire(data, args.outdir, args.mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
