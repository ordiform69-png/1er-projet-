#!/usr/bin/env python3
"""Temps d'une restauration : en une fois, puis par parties (n°19).

Films 720×576 entrelacés avec son, FFV1 4:2:2 et MPEG-2 4:2:0, hors dépôt.
Par défaut : film de 3 min, parties forcées à 60 s (sous le seuil de production).
Avec --production --duree 1500 : constantes de production (parties 600 s,
seuil 1200 s, chauffe 8 s) sur un film de 25 min.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PARIS = timezone(timedelta(hours=1), name="Europe/Paris")
DUREE_DEFAUT = 180.0
# Pour la mesure par parties d'un film de 3 min (sous le seuil de production
# de 20 min). On impose trois parties de 60 s, chauffe de production (8 s).
PARTIE_MESURE = 60.0
CHAUFFE_MESURE = 8.0
SEUIL_MESURE = 1.0
VF = (
    "testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,"
    "setfield=tff,setsar=16/15"
)
AF = "sine=frequency=440:sample_rate=48000"

# vhs-restore-ai/ à partir de ce fichier (partage-grok/mesures-n19/)
ROOT = Path(__file__).resolve().parents[2]


def maintenant() -> str:
    return datetime.now(PARIS).strftime("%Y-%m-%d %H:%M:%S Europe/Paris (UTC+1)")


def _meminfo() -> dict:
    mem = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith(("MemTotal:", "MemAvailable:", "MemFree:", "Cached:", "SwapTotal:", "SwapFree:")):
                mem[line.split(":")[0]] = int(line.split()[1])
    except OSError:
        pass
    return mem


def _disque(chemin: Path) -> dict:
    try:
        u = shutil.disk_usage(chemin)
    except OSError:
        return {"chemin": str(chemin), "erreur": "indisponible"}
    return {
        "chemin": str(chemin),
        "total_gio": round(u.total / 1024 ** 3, 2),
        "utilise_gio": round(u.used / 1024 ** 3, 2),
        "libre_gio": round(u.free / 1024 ** 3, 2),
    }


def ressource(chemins: list[Path] | None = None) -> dict:
    mem = _meminfo()
    out = {
        "quand": maintenant(),
        "ram_totale_mio": round(mem.get("MemTotal", 0) / 1024, 1),
        "ram_dispo_mio": round(mem.get("MemAvailable", 0) / 1024, 1),
        "ram_libre_mio": round(mem.get("MemFree", 0) / 1024, 1),
        "swap_totale_mio": round(mem.get("SwapTotal", 0) / 1024, 1),
        "swap_libre_mio": round(mem.get("SwapFree", 0) / 1024, 1),
        "disques": [_disque(p) for p in (chemins or [Path("/"), Path("/tmp"), Path("/workspace")])],
    }
    return out


class Surveillance:
    """Échantillonne RAM et disque pendant un export (toutes les 5 s)."""

    def __init__(self, chemins: list[Path], periode: float = 5.0):
        self.chemins = chemins
        self.periode = periode
        self._stop = threading.Event()
        self.echantillons: list[dict] = []
        self.ram_dispo_min_mio: float | None = None
        self.disque_libre_min_gio: dict[str, float] = {}
        self._th: threading.Thread | None = None

    def _prise(self) -> None:
        r = ressource(self.chemins)
        self.echantillons.append(r)
        d = r["ram_dispo_mio"]
        if self.ram_dispo_min_mio is None or d < self.ram_dispo_min_mio:
            self.ram_dispo_min_mio = d
        for disc in r["disques"]:
            libre = disc.get("libre_gio")
            if libre is None:
                continue
            cle = disc["chemin"]
            if cle not in self.disque_libre_min_gio or libre < self.disque_libre_min_gio[cle]:
                self.disque_libre_min_gio[cle] = libre

    def _boucle(self) -> None:
        self._prise()
        while not self._stop.wait(self.periode):
            self._prise()

    def __enter__(self) -> "Surveillance":
        self._th = threading.Thread(target=self._boucle, name="surveillance-n19", daemon=True)
        self._th.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._th is not None:
            self._th.join(timeout=self.periode + 2)
        if not self.echantillons:
            self._prise()

    def resume(self) -> dict:
        return {
            "nb_echantillons": len(self.echantillons),
            "ram_dispo_min_mio": self.ram_dispo_min_mio,
            "ram_dispo_debut_mio": self.echantillons[0]["ram_dispo_mio"] if self.echantillons else None,
            "ram_dispo_fin_mio": self.echantillons[-1]["ram_dispo_mio"] if self.echantillons else None,
            "disque_libre_min_gio": self.disque_libre_min_gio,
            "debut": self.echantillons[0]["quand"] if self.echantillons else None,
            "fin": self.echantillons[-1]["quand"] if self.echantillons else None,
        }


def materiel() -> dict:
    cpu = "?"
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    mem = _meminfo()
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
        "ressources": ressource(),
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


def nom_film(duree: float, kind: str) -> str:
    return f"film-{int(round(duree))}s-{kind}.mkv"


def fabriquer(ffmpeg: str, dossier: Path, duree: float) -> dict[str, Path]:
    dossier.mkdir(parents=True, exist_ok=True)
    films = {}
    f422 = dossier / nom_film(duree, "ffv1-422")
    ff(ffmpeg, "-f", "lavfi", "-i", VF, "-f", "lavfi", "-i", AF,
       "-t", f"{duree:.3f}", "-c:a", "pcm_s16le",
       "-pix_fmt", "yuv422p", "-c:v", "ffv1", str(f422))
    films["ffv1_422"] = f422
    f420 = dossier / nom_film(duree, "mpeg2-420")
    ff(ffmpeg, "-f", "lavfi", "-i", VF, "-f", "lavfi", "-i", AF,
       "-t", f"{duree:.3f}", "-c:a", "pcm_s16le",
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


def _mediane(murs: list[float]) -> float:
    return float(statistics.median(murs))


def mesurer_une_fois(cle: str, src: Path, work: Path, n_runs: int, duree: float,
                     chemins_surv: list[Path]) -> dict:
    detect_tools, analyze, profile_for, pipeline = _prep()
    from vhs_restore import reprise
    tools = detect_tools()
    t_an0 = time.perf_counter()
    info = analyze(src, tools)
    t_analyze = time.perf_counter() - t_an0
    s = reglages(pipeline, profile_for)
    chaine = pipeline.filter_chain(info, s)
    # Sur un film >= SEUIL (20 min), pipeline.export emprunte tout seul le
    # chemin par parties. Pour mesurer vraiment « en une fois », on relève
    # le seuil le temps de l'export, sans toucher au moteur committé.
    seuil_prod = float(reprise.SEUIL)
    local = work / "localapp"
    local.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(local)
    runs = []
    for i in range(n_runs):
        dest = work / f"une-fois-{cle}-{i + 1}.mp4"
        ancien = reprise.SEUIL
        reprise.SEUIL = float(info.duration) + 1.0
        try:
            with Surveillance(chemins_surv) as surv:
                t0 = time.perf_counter()
                pipeline.export(info, s, dest, tools)
                wall = time.perf_counter() - t0
        finally:
            reprise.SEUIL = ancien
        taille = dest.stat().st_size if dest.is_file() else 0
        dest.unlink(missing_ok=True)
        runs.append({
            "run": i + 1, "wall_s": wall, "s_par_minute": wall / duree * 60.0,
            "sortie_octets": taille, "ressources": surv.resume(),
        })
        print(f"  {cle} une-fois run {i + 1}/{n_runs}: {wall:.3f} s "
              f"→ {wall / duree * 60:.2f} s/min "
              f"(RAM dispo min {surv.ram_dispo_min_mio} Mio)", flush=True)
    murs = [r["wall_s"] for r in runs]
    mid = _mediane(murs)
    return {
        "film": str(src), "cle": cle, "mode": "une-fois",
        "duree_s": info.duration, "pix_fmt": info.pix_fmt, "scan": info.scan,
        "chaine": chaine, "analyze_s": t_analyze, "runs": runs,
        "mediane_wall_s": mid, "mediane_s_par_minute": mid / duree * 60.0,
        "seuil_production_s": seuil_prod,
        "seuil_force_une_fois_s": float(info.duration) + 1.0,
    }


def mesurer_parties(cle: str, src: Path, work: Path, n_runs: int, duree: float,
                    production: bool, chemins_surv: list[Path]) -> dict:
    detect_tools, analyze, profile_for, pipeline = _prep()
    from vhs_restore import reprise
    tools = detect_tools()
    t_an0 = time.perf_counter()
    info = analyze(src, tools)
    t_analyze = time.perf_counter() - t_an0
    s = reglages(pipeline, profile_for)
    if production:
        # Constantes de production, non forcées (DUREE_PARTIE=600, SEUIL=1200, CHAUFFE=8).
        partie = float(reprise.DUREE_PARTIE)
        seuil = float(reprise.SEUIL)
        chauffe = float(reprise.CHAUFFE)
    else:
        # Film de 3 min < seuil de 20 min : on force le découpage pour mesurer les raccords.
        # API réelle (R1) : pipeline.export s'appuie sur reprise.DUREE_PARTIE / SEUIL / CHAUFFE.
        reprise.DUREE_PARTIE = PARTIE_MESURE
        reprise.SEUIL = SEUIL_MESURE
        reprise.CHAUFFE = CHAUFFE_MESURE
        partie = PARTIE_MESURE
        seuil = SEUIL_MESURE
        chauffe = CHAUFFE_MESURE
    local = work / "localapp"
    local.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(local)
    # Découpage attendu du film complet (pas de passages exclus dans cette mesure).
    decoupage = reprise.decouper([(0.0, float(info.duration))])
    runs = []
    for i in range(n_runs):
        dest = work / f"parties-{cle}-{i + 1}.mp4"
        with Surveillance(chemins_surv) as surv:
            t0 = time.perf_counter()
            pipeline.export(info, s, dest, tools)
            wall = time.perf_counter() - t0
        taille = dest.stat().st_size if dest.is_file() else 0
        dest.unlink(missing_ok=True)
        runs.append({
            "run": i + 1, "wall_s": wall, "s_par_minute": wall / duree * 60.0,
            "sortie_octets": taille, "ressources": surv.resume(),
        })
        print(f"  {cle} parties run {i + 1}/{n_runs}: {wall:.3f} s "
              f"→ {wall / duree * 60:.2f} s/min "
              f"(RAM dispo min {surv.ram_dispo_min_mio} Mio)", flush=True)
    murs = [r["wall_s"] for r in runs]
    mid = _mediane(murs)
    return {
        "film": str(src), "cle": cle, "mode": "parties",
        "duree_s": info.duration, "pix_fmt": info.pix_fmt, "scan": info.scan,
        "duree_partie_s": partie, "seuil_s": seuil, "chauffe_s": chauffe,
        "production": production, "decoupage": decoupage,
        "analyze_s": t_analyze, "runs": runs,
        "mediane_wall_s": mid, "mediane_s_par_minute": mid / duree * 60.0,
    }


def ecrire(data: dict, outdir: Path, nom: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / f"resultats-{nom}.json"
    txt_path = outdir / f"resultats-{nom}.txt"
    csv_path = outdir / f"resultats-{nom}.csv"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str),
                         encoding="utf-8")
    lignes = [
        f"Temps de restauration n°19 — mode {data.get('mode', nom)}",
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
        if bloc.get("duree_partie_s") is not None:
            lignes.append(
                f"  constantes : partie={bloc.get('duree_partie_s')} s, "
                f"seuil={bloc.get('seuil_s')} s, chauffe={bloc.get('chauffe_s')} s, "
                f"production={bloc.get('production')}, découpage={bloc.get('decoupage')}"
            )
        for r in bloc["runs"]:
            res = r.get("ressources") or {}
            extra = ""
            if res.get("ram_dispo_min_mio") is not None:
                extra = (f" | RAM dispo min {res['ram_dispo_min_mio']} Mio "
                         f"(début {res.get('ram_dispo_debut_mio')}, fin {res.get('ram_dispo_fin_mio')})")
            lignes.append(f"  run {r['run']}: {r['wall_s']:.3f} s → {r['s_par_minute']:.2f} s/min{extra}")
            rows.append({"mode": data.get("mode", nom), "film": cle, "run": r["run"],
                         "wall_s": r["wall_s"], "s_par_minute": r["s_par_minute"],
                         "pix_fmt": bloc.get("pix_fmt")})
        lignes.append(
            f"  médiane : {bloc['mediane_wall_s']:.3f} s "
            f"({bloc['mediane_s_par_minute']:.2f} s de calcul par minute de film)"
        )
        rows.append({"mode": data.get("mode", nom), "film": cle, "run": "mediane",
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
    ap.add_argument("--duree", type=float, default=DUREE_DEFAUT,
                    help="durée du film de synthèse, en secondes (défaut 180)")
    ap.add_argument("--production", action="store_true",
                    help="par parties : constantes de production, sans forçage")
    ap.add_argument("--etiquette", default="",
                    help="préfixe des fichiers résultats (ex. production → resultats-production-une-fois)")
    args = ap.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg introuvable", file=sys.stderr)
        return 2
    if args.fabriquer:
        print(f"Fabrication des films {args.duree:.0f} s…", flush=True)
        films = fabriquer(ffmpeg, args.films_dir, args.duree)
        for k, p in films.items():
            print(f"  {k}: {p} ({p.stat().st_size} octets)")
        return 0
    if not args.mode:
        print("--mode une-fois|parties requis (sauf --fabriquer)", file=sys.stderr)
        return 2
    films = {
        "ffv1_422": args.films_dir / nom_film(args.duree, "ffv1-422"),
        "mpeg2_420": args.films_dir / nom_film(args.duree, "mpeg2-420"),
    }
    for p in films.values():
        if not p.is_file():
            print(f"film manquant : {p} (lancez --fabriquer --duree {args.duree})", file=sys.stderr)
            return 2
    work = args.workdir / args.mode
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    chemins_surv = [Path("/"), Path("/tmp"), Path("/workspace"), args.films_dir, work]
    racine_git = ROOT.parent
    br = subprocess.run(["git", "-C", str(racine_git), "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True, text=True)
    etiquette = args.etiquette.strip("-_ ")
    nom = f"{etiquette}-{args.mode}" if etiquette else args.mode
    data = {
        "mode": args.mode,
        "etiquette": etiquette or None,
        "production": bool(args.production),
        "duree_demandee_s": args.duree,
        "date": maintenant(),
        "sha": sha_depot(racine_git),
        "branche": br.stdout.strip() if br.returncode == 0 else "?",
        "materiel": materiel(),
        "methode": "voir METHODE.md"
                    + (" — constantes de production, film 25 min" if args.production else ""),
        "ressources_debut": ressource(chemins_surv),
        "films": {},
    }
    print(f"Mode {args.mode} — SHA {data['sha']} ({data['branche']}) — "
          f"durée {args.duree}s production={args.production}", flush=True)
    print(f"  RAM dispo {data['ressources_debut']['ram_dispo_mio']} Mio, "
          f"disques {[d.get('libre_gio') for d in data['ressources_debut']['disques']]}",
          flush=True)
    if args.mode == "une-fois":
        fn = lambda cle, src, w, n: mesurer_une_fois(cle, src, w, n, args.duree, chemins_surv)
    else:
        fn = lambda cle, src, w, n: mesurer_parties(
            cle, src, w, n, args.duree, args.production, chemins_surv)
    for cle, src in films.items():
        print(f"Mesure {cle}…", flush=True)
        data["films"][cle] = fn(cle, src, work, args.runs)
    data["ressources_fin"] = ressource(chemins_surv)
    ecrire(data, args.outdir, nom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
