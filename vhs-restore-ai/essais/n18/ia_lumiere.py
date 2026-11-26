"""Essai n°18, agent F1 : lumière et couleurs réglées par IAT, comparées à la méthode actuelle.

Une commande :   python essais/n18/ia_lumiere.py
                 python essais/n18/ia_lumiere.py --extraits <dossier>    (vrais extraits, sans origine)
                 python essais/n18/ia_lumiere.py --verifier              (contrôles de calcul seulement)

Compare, scène par scène :
  (0) entree        : l'image dégradée, sans correction (repère)
  (1) actuelle      : niveaux + dominante du logiciel, mesurés UNE fois pour tout le film
                      (vhs_restore/probe.py, advice.py, pipeline._cast_filter / _levels_filter,
                      appelés tels quels ; le logiciel n'est pas modifié)
  (2) iat_global    : matrice 3 x 3 + gamma d'IAT estimés sur 3 à 5 images de la scène, appliqués
                      à toute la scène par FFmpeg (colorchannelmixer + lutrgb)
  (3) iat_complet   : IAT complet image par image (référence, trop lent pour un film entier)
Chaque méthode AVEC les plafonds du logiciel (safe_levels / safe_gains) et SANS plafond.
Mesures : PSNR, ΔE2000 moyen (écart à l'image d'origine), temps sur processeur.
Dépendances : numpy, onnxruntime (CPUExecutionProvider), FFmpeg. Pas de torch ici.
Résultats : CSV (--csv), images avant / après hors dépôt (--images).
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import f1_banc as banc  # noqa: E402
import f1_iat as iat    # noqa: E402

COLONNES = ["banc", "scene", "methode", "plafond", "poids", "images", "images_analyse",
            "psnr_db", "delta_e2000", "luma_moy", "ecretes_pct", "ecart_entree_de2000",
            "temps_analyse_ms_par_image", "temps_application_ms_par_image", "temps_total_ms_par_image",
            "film_2h_minutes", "coeurs", "gamma", "matrice", "dispersion_matrice", "dispersion_gamma",
            "filtres", "remarque"]
IMAGES_2H = 2 * 3600 * 25          # film PAL de 2 heures, 25 images/s
NON = "non mesuré"


# ------------------------------------------------------------------ méthode actuelle (logiciel)
def logiciel():
    return iat._logiciel()


@contextlib.contextmanager
def sans_plafond():
    """Retire safe_levels / safe_gains le temps d'un appel (le fichier du logiciel n'est pas touché)."""
    p = logiciel()
    sl, sg = p.safe_levels, p.safe_gains
    p.safe_levels, p.safe_gains = (lambda lo, hi: (lo, hi)), (lambda g: tuple(g))
    try:
        yield
    finally:
        p.safe_levels, p.safe_gains = sl, sg


def mesure_film_actuelle(images: list) -> tuple[dict, float]:
    """Ce que mesure le logiciel, une fois pour le film :
    - niveaux : médiane de YLOW / YHIGH de signalstats sur l'échantillon (probe.parse_signals),
      après passage en YUV 4:2:0 comme un fichier de capture ;
    - dominante : moyennes R, G, B sur 8 images réduites à 32 x 32 (comme probe.rgb_mean ; ici
      8 images réparties sur le film au lieu des 8 premières après le tiers) -> probe.cast_gains ;
    - seuils de déclenchement de advice.py (l. 44-59)."""
    from vhs_restore import probe
    t0 = time.perf_counter()
    h, w, _ = images[0].shape
    r = subprocess.run([banc.ffmpeg(), "-hide_banner", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", f"{w}x{h}", "-r", "25", "-i", "-", "-vf",
                        "format=yuv420p,signalstats,metadata=print:key=lavfi.signalstats.YLOW,"
                        "metadata=print:key=lavfi.signalstats.YHIGH", "-f", "null", "-"],
                       input=b"".join(i.tobytes() for i in images), capture_output=True)
    sig = probe.parse_signals(r.stderr.decode(errors="replace"))
    idx = np.linspace(0, len(images) - 1, min(8, len(images))).round().astype(int)
    petites, _ = banc.filtrer([images[i] for i in idx], "scale=32:32")
    rgb = tuple(float(np.mean([p[..., c].mean() for p in petites])) for c in range(3))
    dt = time.perf_counter() - t0
    lo, hi = sig.get("level_low"), sig.get("level_high")
    m = {"level_low": lo, "level_high": hi, "cast_rgb": rgb, "niveaux": False, "dominante": False}
    if lo is not None and hi is not None and hi - lo < 140 and lo > 35 and hi < 190:
        m.update(niveaux=True, level_black=lo / 255.0, level_white=hi / 255.0)
    if max(rgb) - min(rgb) > 15:
        m.update(dominante=True, gains=probe.cast_gains(rgb))
    return m, dt


def filtres_actuelle(m: dict, plafond: bool) -> str:
    from vhs_restore.profiles import profile_for
    p = logiciel()
    kw = {}
    if m["niveaux"]:
        kw.update(level_black=m["level_black"], level_white=m["level_white"])
    if m["dominante"]:
        kw.update(gain_r=m["gains"][0], gain_g=m["gains"][1], gain_b=m["gains"][2])
    s = p.Settings(profile=profile_for("equilibre", "video"), **kw)
    with (contextlib.nullcontext() if plafond else sans_plafond()):
        f = [x for x in (p._cast_filter(s), p._levels_filter(s)) if x]   # ordre de pre_filters
    return ",".join(f)


# ------------------------------------------------------------------ mesures
def stats(sortie: list, entree: list, origine: list | None) -> dict:
    d = {}
    if origine is not None:
        d["psnr_db"] = f"{np.mean([banc.psnr(a, b) for a, b in zip(sortie, origine)]):.3f}"
        d["delta_e2000"] = f"{np.mean([banc.delta_e2000(a, b) for a, b in zip(sortie, origine)]):.3f}"
    else:
        d["psnr_db"] = d["delta_e2000"] = NON + " (pas d'image d'origine)"
    luma = [0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2] for a in sortie]
    d["luma_moy"] = f"{np.mean([l.mean() for l in luma]):.2f}"
    d["ecretes_pct"] = f"{100 * np.mean([((a <= 2) | (a >= 253)).mean() for a in sortie]):.3f}"
    d["ecart_entree_de2000"] = f"{np.mean([banc.delta_e2000(a, b) for a, b in zip(sortie, entree)]):.3f}"
    return d


def temps(analyse_s: float, appli_s: float, n: int) -> dict:
    a, b = 1000 * analyse_s / n, 1000 * appli_s / n
    return {"temps_analyse_ms_par_image": f"{a:.2f}", "temps_application_ms_par_image": f"{b:.2f}",
            "temps_total_ms_par_image": f"{a + b:.2f}", "film_2h_minutes": f"{(a + b) * IMAGES_2H / 60000:.1f}"}


def fmt_m(M) -> str:
    return " ".join(f"{x:.5f}" for x in np.asarray(M).reshape(-1))


def choisir(n: int, k: int) -> list[int]:
    k = max(3, min(5, k, n)) if n >= 3 else n
    return [int(i) for i in np.linspace(0, n - 1, k + 2)[1:-1].round()] if n > k else list(range(n))


# ------------------------------------------------------------------ essai
def essai(nom_banc: str, scenes: list, a, sortie_csv: Path, dossier_img: Path) -> list[dict]:
    lignes = []
    base = {"banc": nom_banc, "coeurs": banc.coeurs()}

    def ajoute(**kw):
        l = dict(base)
        l.update(kw)
        lignes.append(l)

    # (1) méthode actuelle : une mesure pour tout le film (toutes les scènes à la suite)
    film = [im for s in scenes for im in s.degradees]
    m_act, t_act = mesure_film_actuelle(film)
    f_act = {pl: filtres_actuelle(m_act, pl) for pl in (True, False)}
    print(f"méthode actuelle : {json.dumps({k: v for k, v in m_act.items()}, default=str)}")

    modeles = {}
    for p in a.poids:
        try:
            modeles[p] = (iat.IATGlobal(p, a.threads), iat.IATComplet(p, a.threads))
        except (FileNotFoundError, RuntimeError) as e:
            print(f"IAT {p} : {e}")
            modeles[p] = None

    for s in scenes:
        n = len(s.degradees)
        vignettes = {"entree": s.degradees[0]}
        if s.originales is not None:
            vignettes = {"origine": s.originales[0], **vignettes}
        ajoute(scene=s.nom, methode="entree", plafond="-", poids="-", images=n, images_analyse=0,
               remarque=s.remarque, **stats(s.degradees, s.degradees, s.originales))
        for pl in (True, False):
            vf = f_act[pl]
            out, dt = banc.filtrer(s.degradees, vf) if vf else (s.degradees, 0.0)
            ajoute(scene=s.nom, methode="actuelle", plafond="oui" if pl else "non", poids="-", images=n,
                   images_analyse=len(film), filtres=vf or "(aucun : seuils non atteints)",
                   remarque="mesure unique sur tout le film ; temps d'analyse réparti sur toutes ses images",
                   **stats(out, s.degradees, s.originales), **temps(t_act * n / len(film), dt, n))
            vignettes[f"actuelle_{'plaf' if pl else 'brut'}"] = out[0]
        idx = choisir(n, a.images_par_scene)
        for p, mod in modeles.items():
            if mod is None:
                for meth in ("iat_global", "iat_complet"):
                    ajoute(scene=s.nom, methode=meth, plafond="-", poids=p, images=n, psnr_db=NON,
                           delta_e2000=NON, remarque="ONNX absent : lancer iat_export_onnx.py")
                continue
            g_mod, c_mod = mod
            t0 = time.perf_counter()
            est = [g_mod.estimer(s.degradees[i]) for i in idx]
            t_est = time.perf_counter() - t0
            M, g, dM, dg = iat.combiner(est)
            for pl in (True, False):
                M2, g2 = iat.plafonner(M, g) if pl else (M, g)
                vf = iat.filtres_ffmpeg(M2, g2)
                out, dt = banc.filtrer(s.degradees, vf)
                ajoute(scene=s.nom, methode="iat_global", plafond="oui" if pl else "non", poids=p, images=n,
                       images_analyse=len(idx), gamma=f"{g2:.5f}", matrice=fmt_m(M2),
                       dispersion_matrice=f"{dM:.5f}", dispersion_gamma=f"{dg:.5f}", filtres=vf,
                       remarque=f"médiane de {len(idx)} images (n° {idx}) ; brut : gamma {g:.4f}, matrice {fmt_m(M)}",
                       **stats(out, s.degradees, s.originales), **temps(t_est, dt, n))
                vignettes[f"iat_global_{p}_{'plaf' if pl else 'brut'}"] = out[0]
            # (3) complet, image par image
            brut, plaf, t_inf, t_rec = [], [], 0.0, 0.0
            for im in s.degradees:
                t0 = time.perf_counter()
                mul, add, Mi, gi = c_mod.sorties(im)
                t1 = time.perf_counter()
                brut.append(c_mod.recomposer(im, mul, add, Mi, gi))
                t_rec += time.perf_counter() - t1
                Mp, gp = iat.plafonner(Mi, gi)
                plaf.append(c_mod.recomposer(im, mul, add, Mp, gp))
                t_inf += t1 - t0
            for pl, out in ((False, brut), (True, plaf)):
                ajoute(scene=s.nom, methode="iat_complet", plafond="oui (partie globale)" if pl else "non",
                       poids=p, images=n, images_analyse=n,
                       remarque="partie locale (mul, add par pixel) jamais plafonnée : le logiciel n'a pas "
                                "d'équivalent" if pl else "IAT.forward exact",
                       **stats(out, s.degradees, s.originales), **temps(t_inf, t_rec, n))
                vignettes[f"iat_complet_{p}_{'plaf' if pl else 'brut'}"] = out[0]
        if dossier_img:
            mosaique(vignettes, dossier_img / f"{s.nom}.png")
    return lignes


def mosaique(v: dict, chemin: Path) -> None:
    """Une ligne de vignettes (moitié de la taille) : origine | entrée | méthodes. Hors dépôt."""
    ims = [im[::2, ::2] for im in v.values()]
    banc.png(np.concatenate(ims, axis=1), chemin)
    chemin.with_suffix(".txt").write_text(" | ".join(v.keys()) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ extraits réels
VIDEOS = {".mp4", ".mkv", ".avi", ".mov", ".mpg", ".mpeg", ".vob", ".ts", ".m2ts", ".dv", ".m4v", ".wmv"}


def scenes_extrait(f: Path, par_scene: int, max_scenes: int) -> list:
    """Coupes par scdet (FFmpeg), puis quelques images par scène (720 x 576). Sans origine connue."""
    ffprobe = str(Path(banc.ffmpeg()).with_name("ffprobe" + Path(banc.ffmpeg()).suffix))
    try:
        duree = float(subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                                      "-of", "csv=p=0", str(f)], capture_output=True, text=True).stdout.strip())
    except (ValueError, OSError):
        duree = 30.0
    r = subprocess.run([banc.ffmpeg(), "-hide_banner", "-nostdin", "-i", str(f), "-map", "0:v:0",
                        "-vf", "scdet=threshold=10,metadata=print:key=lavfi.scd.time", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    coupes = sorted({float(x) for x in re.findall(r"lavfi\.scd\.time=([\d.]+)", r.stderr)})
    bornes = [0.0] + [c for c in coupes if 0.5 < c < duree - 0.5] + [duree]
    scenes = []
    for i, (t0, t1) in enumerate(zip(bornes[:-1], bornes[1:])):
        if t1 - t0 < 0.4 or len(scenes) >= max_scenes:
            continue
        ts = np.linspace(t0, t1, par_scene + 2)[1:-1]
        ims = []
        for t in ts:
            ims += banc.lire(["-ss", f"{t:.3f}", "-i", str(f), "-map", "0:v:0"], 1)
        if ims:
            scenes.append(banc.Scene(f"{f.stem}#{i + 1}({t0:.1f}-{t1:.1f}s)", ims, None,
                                     f"extrait réel {f.name}, {len(ims)} images échantillonnées"))
    return scenes


# ------------------------------------------------------------------ vérifications
def verifier(a) -> int:
    """Contrôles de calcul (pas des résultats d'essai) :
    1. ΔE2000 sur les paires de référence de Sharma et al. ;
    2. filtres FFmpeg (colorchannelmixer + lutrgb) = formule d'IAT calculée en numpy ;
    3. méthode actuelle avec plafond = chaîne du logiciel (pipeline.pre_filters)."""
    ok = True
    for l1, l2, att in (((50, 2.6772, -79.7751), (50, 0, -82.7485), 2.0425),
                        ((50, -1.0, 2.0), (50, 0, 0), 2.3669),
                        ((2.0776, 0.0795, -1.135), (0.9033, -0.0636, -0.5514), 0.9082)):
        v = float(banc.delta_e2000_lab(np.array(l1, float), np.array(l2, float)))
        ok &= abs(v - att) < 1e-3
        print(f"ΔE2000 {v:.4f} (attendu {att})")
    img = banc.lire(["-f", "lavfi", "-i", banc.SYNTHESE["mire_animee"]], 1)[0]
    M = np.array([[1.10, -0.05, 0.02], [0.03, 0.95, 0.01], [-0.02, 0.04, 1.05]])
    for g in (0.8, 1.0, 1.3):
        ff = banc.filtrer([img], iat.filtres_ffmpeg(M, g))[0][0].astype(int)
        npy = iat.appliquer_global_numpy(img, M, g).astype(int)
        e = np.abs(ff - npy)
        print(f"FFmpeg contre numpy, gamma {g} : écart max {e.max()}, moyen {e.mean():.3f} (sur 255)")
        ok &= e.max() <= 2
    p = logiciel()
    from vhs_restore.profiles import profile_for
    s = p.Settings(profile=profile_for("equilibre", "video"), level_black=0.33, level_white=0.64,
                   gain_r=1.3, gain_g=0.8, gain_b=1.0)
    m = {"niveaux": True, "level_black": 0.33, "level_white": 0.64, "dominante": True, "gains": (1.3, 0.8, 1.0)}
    attendu = [f for f in (p._cast_filter(s), p._levels_filter(s)) if f]
    ok &= filtres_actuelle(m, True) == ",".join(attendu)
    print("actuelle avec plafond :", filtres_actuelle(m, True))
    print("actuelle sans plafond :", filtres_actuelle(m, False))
    ok &= p.safe_gains((2.0,)) == (p.GAIN_MAX,)     # les plafonds sont bien rétablis après coup
    print("vérifications :", "OK" if ok else "ÉCHEC")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extraits", type=Path, help="dossier de vrais extraits (sans origine connue)")
    ap.add_argument("--csv", type=Path, default=ICI / "resultats" / "f1_ia_lumiere.csv")
    ap.add_argument("--images", type=Path, default=None,
                    help="images avant / après (défaut : cache hors dépôt, …/vhs-restore-n18/f1_images)")
    ap.add_argument("--poids", default=",".join(iat.POIDS_RETENUS))
    ap.add_argument("--images-par-scene", type=int, default=4, help="3 à 5 images pour estimer IAT global")
    ap.add_argument("--n-images", type=int, default=12, help="images par scène du banc provisoire")
    ap.add_argument("--max-scenes", type=int, default=12, help="par extrait")
    ap.add_argument("--threads", type=int, default=0, help="onnxruntime (0 = tous les cœurs)")
    ap.add_argument("--verifier", action="store_true")
    a = ap.parse_args()
    a.poids = [p for p in a.poids.split(",") if p]
    for p in a.poids:
        if not iat.manifeste()["poids"].get(p, {}).get("retenu"):
            raise SystemExit(f"poids {p} non retenu (licence) : voir iat_modeles.json")
    if a.verifier:
        return verifier(a)
    dossier_img = a.images or iat.dossier_cache().parent / "f1_images"
    if a.extraits:
        fichiers = sorted(f for f in a.extraits.iterdir() if f.suffix.lower() in VIDEOS)
        scenes = [s for f in fichiers for s in scenes_extrait(f, max(3, min(5, a.images_par_scene)), a.max_scenes)]
        nom_banc = f"extraits réels ({a.extraits.name})"
    else:
        nom_banc, scenes = banc.scenes_banc(a.n_images)
    if not scenes:
        raise SystemExit("aucune scène à mesurer")
    print(f"banc : {nom_banc}, {len(scenes)} scènes, {banc.coeurs()} cœurs")
    lignes = essai(nom_banc, scenes, a, a.csv, dossier_img)
    a.csv.parent.mkdir(parents=True, exist_ok=True)
    with open(a.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLONNES, extrasaction="ignore")
        w.writeheader()
        w.writerows(lignes)
    print(f"CSV : {a.csv}\nimages : {dossier_img}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
