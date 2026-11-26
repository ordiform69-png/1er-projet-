#!/usr/bin/env python3
"""Temps de restauration selon la méthode de Claude (corrections n°17).

Films proches de vraies captures : 720×576 entrelacé, son, 60 s, sombres et
peu contrastés pour que les niveaux s'appliquent. 3 passages, médiane.
FFV1 4:2:2 et MPEG-2 4:2:0.

Usage :
  python3 mesurer_temps_claude.py --fabriquer --films-dir /tmp/mesures-n17-corr/films
  python3 mesurer_temps_claude.py --phase avant --moteur /chemin/vhs-restore-ai \\
      --films-dir /tmp/mesures-n17-corr/films --outdir ...
  python3 mesurer_temps_claude.py --phase apres --moteur /chemin/vhs-restore-ai ...
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
DUREE = 60.0
# Recette figée : PAL TFF, 720×576, noirs gris et blancs ternes (déclenche « niveaux »).
VF = (
    "testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,setfield=tff,"
    "setsar=16/15,colorlevels=romin=0.20:gomin=0.20:bomin=0.20:"
    "romax=0.52:gomax=0.52:bomax=0.52"
)
AF = "sine=frequency=440:sample_rate=48000"


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
    f422 = dossier / "sombre-60s-ffv1-422.mkv"
    ff(ffmpeg, "-f", "lavfi", "-i", VF, "-f", "lavfi", "-i", AF,
       "-t", f"{DUREE:.3f}", "-c:a", "pcm_s16le",
       "-pix_fmt", "yuv422p", "-c:v", "ffv1", str(f422))
    films["ffv1_422"] = f422
    f420 = dossier / "sombre-60s-mpeg2-420.mkv"
    ff(ffmpeg, "-f", "lavfi", "-i", VF, "-f", "lavfi", "-i", AF,
       "-t", f"{DUREE:.3f}", "-c:a", "pcm_s16le",
       "-pix_fmt", "yuv420p", "-c:v", "mpeg2video",
       "-flags", "+ilme+ildct", "-b:v", "8M", str(f420))
    films["mpeg2_420"] = f420
    return films


def charger_moteur(chemin: Path) -> None:
    sys.path.insert(0, str(chemin.resolve()))
    # evincer un vhs_restore déjà importé
    for nom in list(sys.modules):
        if nom == "vhs_restore" or nom.startswith("vhs_restore."):
            del sys.modules[nom]


def mesurer_un(phase: str, cle: str, src: Path, work: Path, tools, n_runs: int) -> dict:
    from vhs_restore.probe import analyze
    from vhs_restore.advice import advise, apply
    from vhs_restore.profiles import profile_for
    from vhs_restore import pipeline

    t_an0 = time.perf_counter()
    info = analyze(src, tools)
    t_analyze = time.perf_counter() - t_an0
    tips = advise(info)
    s = apply(pipeline.Settings(
        profile_for("equilibre", "video"), source="video",
        restore_audio=True, preset="medium", crf=18, resolution="source",
        use_ai=False, stabilize=False, denoise_hq=False,
    ), tips)
    t_att = None
    scenes_n = None
    if hasattr(info, "scenes"):
        try:
            from vhs_restore import scenes
            t0 = time.perf_counter()
            scenes.attacher(info, tools.ffmpeg.path)
            t_att = time.perf_counter() - t0
            scenes_n = len(info.scenes or ())
        except Exception as exc:
            t_att = f"echec: {exc}"
    chaine = pipeline.filter_chain(info, s)
    niveaux = "colorlevels=" in chaine or "sendcmd=" in chaine
    runs = []
    for i in range(n_runs):
        dest = work / f"{phase}-{cle}-{i + 1}.mp4"
        t0 = time.perf_counter()
        pipeline.export(info, s, dest, tools)
        wall = time.perf_counter() - t0
        runs.append({"run": i + 1, "wall_s": wall, "s_par_minute": wall / DUREE * 60.0})
        dest.unlink(missing_ok=True)
        print(f"  {cle} run {i + 1}/{n_runs}: {wall:.3f} s → {wall / DUREE * 60:.2f} s/min",
              flush=True)
    murs = sorted(r["wall_s"] for r in runs)
    mid = murs[len(murs) // 2]
    return {
        "film": str(src),
        "cle": cle,
        "duree_s": info.duration,
        "pix_fmt": info.pix_fmt,
        "scan": info.scan,
        "level_low": info.level_low,
        "level_high": info.level_high,
        "conseils": [a.key for a in tips],
        "level_black": s.level_black,
        "level_white": s.level_white,
        "niveaux_actifs": niveaux,
        "chaine": chaine,
        "analyze_s": t_analyze,
        "attacher_s": t_att,
        "n_scenes": scenes_n,
        "runs": runs,
        "mediane_wall_s": mid,
        "mediane_s_par_minute": mid / DUREE * 60.0,
    }


def main() -> int:
    ici = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--fabriquer", action="store_true")
    ap.add_argument("--phase", choices=("avant", "apres"))
    ap.add_argument("--moteur", type=Path)
    ap.add_argument("--films-dir", type=Path, default=Path("/tmp/mesures-n17-corr/films"))
    ap.add_argument("--workdir", type=Path, default=Path("/tmp/mesures-n17-corr/work"))
    ap.add_argument("--outdir", type=Path, default=ici)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg introuvable", file=sys.stderr)
        return 2

    if args.fabriquer:
        print("Fabrication des films 60 s…", flush=True)
        films = fabriquer(ffmpeg, args.films_dir)
        for k, p in films.items():
            print(f"  {k}: {p} ({p.stat().st_size} octets)")
        return 0

    if not args.phase or not args.moteur:
        print("--phase et --moteur requis (sauf --fabriquer)", file=sys.stderr)
        return 2
    charger_moteur(args.moteur)
    from vhs_restore.tools import detect_tools
    tools = detect_tools()
    films = {
        "ffv1_422": args.films_dir / "sombre-60s-ffv1-422.mkv",
        "mpeg2_420": args.films_dir / "sombre-60s-mpeg2-420.mkv",
    }
    for p in films.values():
        if not p.is_file():
            print(f"film manquant : {p}", file=sys.stderr)
            return 2
    work = args.workdir / args.phase
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    racine = args.moteur.resolve().parent
    data = {
        "phase": args.phase,
        "date": maintenant(),
        "sha": sha_depot(racine),
        "moteur": str(args.moteur.resolve()),
        "materiel": materiel(),
        "methode": "720×576 entrelacé, son, 60 s, sombre peu contrasté, niveaux appliqués, "
                   "profil Équilibré, preset medium, crf=18, 3 runs, médiane. "
                   "Horloge autour de pipeline.export seulement (analyse et attacher à part).",
        "films": {},
    }
    print(f"Phase {args.phase} — SHA {data['sha']}", flush=True)
    for cle, src in films.items():
        print(f"Mesure {cle}…", flush=True)
        data["films"][cle] = mesurer_un(args.phase, cle, src, work, tools, args.runs)

    args.outdir.mkdir(parents=True, exist_ok=True)
    json_path = args.outdir / f"resultats-corrections-temps-{args.phase}.json"
    txt_path = args.outdir / f"resultats-corrections-temps-{args.phase}.txt"
    csv_path = args.outdir / f"resultats-corrections-temps-{args.phase}.csv"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str),
                         encoding="utf-8")
    lignes = [
        f"Temps de restauration — méthode Claude — phase {args.phase}",
        f"Date : {data['date']}",
        f"SHA : {data['sha']}",
        f"Moteur : {data['moteur']}",
        f"Matériel : {data['materiel']['cpu']}, {data['materiel']['coeurs']} cœurs, "
        f"RAM {data['materiel']['ram_totale_mio']} Mio "
        f"(dispo {data['materiel']['ram_dispo_mio']} Mio), {data['materiel']['os']}",
        f"FFmpeg : {data['materiel']['ffmpeg']}",
        "",
    ]
    rows = []
    for cle, bloc in data["films"].items():
        lignes += [
            f"=== {cle} ({bloc['pix_fmt']}, scan={bloc['scan']}, "
            f"Y {bloc['level_low']}–{bloc['level_high']}) ===",
            f"  conseils={bloc['conseils']} niveaux_actifs={bloc['niveaux_actifs']} "
            f"n_scenes={bloc['n_scenes']}",
            f"  analyze={bloc['analyze_s']:.3f} s  attacher={bloc['attacher_s']}",
        ]
        for r in bloc["runs"]:
            lignes.append(f"  run {r['run']}: {r['wall_s']:.3f} s → {r['s_par_minute']:.2f} s/min")
            rows.append({"phase": args.phase, "film": cle, "run": r["run"],
                         "wall_s": r["wall_s"], "s_par_minute": r["s_par_minute"],
                         "niveaux_actifs": bloc["niveaux_actifs"], "pix_fmt": bloc["pix_fmt"]})
        lignes.append(
            f"  médiane : {bloc['mediane_wall_s']:.3f} s "
            f"({bloc['mediane_s_par_minute']:.2f} s de calcul par minute de film)"
        )
        rows.append({"phase": args.phase, "film": cle, "run": "mediane",
                     "wall_s": bloc["mediane_wall_s"],
                     "s_par_minute": bloc["mediane_s_par_minute"],
                     "niveaux_actifs": bloc["niveaux_actifs"], "pix_fmt": bloc["pix_fmt"]})
        lignes.append("")
    txt_path.write_text("\n".join(lignes), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\n".join(lignes))
    print("Écrit :", json_path, txt_path, csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
