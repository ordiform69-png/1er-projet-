"""Essai n°18, agent F1 : lumière et couleurs réglées par IAT, comparées à la méthode actuelle.

Depuis vhs-restore-ai/ :
    python essais/n18/ia_lumiere.py                          banc F4 (images de référence)
    python essais/n18/ia_lumiere.py --extraits <dossier>     + vrais extraits (sans origine)
    python essais/n18/ia_lumiere.py --verifier               contrôles de calcul seulement

Banc : celui de F4 (banc.py), via f1_banc.py. Une scène = une image de référence dégradée
(banc.degrader, réglages par défaut) ; comparaison sur l'image du milieu (banc.mesurer).

Méthodes, scène par scène :
  (0) entree             : l'extrait dégradé, sans correction (repère)
  (1) actuelle           : niveaux + dominante du logiciel, mesurés UNE fois pour tout le « film »
                           (toutes les scènes à la suite) ; vhs_restore/probe.py, advice.py,
                           pipeline._cast_filter / _levels_filter appelés tels quels
      actuelle_par_scene : la même mesure, faite sur la scène seule (information en plus)
  (2) iat_global         : matrice 3 x 3 + gamma d'IAT, médiane sur 3 à 5 images de la scène,
                           appliqués à tout l'extrait par FFmpeg (colorchannelmixer + lutrgb)
  (3) iat_complet        : IAT complet sur l'image du milieu (référence, image par image)
Chaque méthode AVEC les plafonds du logiciel (safe_levels / safe_gains) et SANS plafond.
Mesures : PSNR, SSIM, ΔE2000 (banc F4), temps sur processeur.
Dépendances : numpy, onnxruntime (CPUExecutionProvider), FFmpeg. Pas de torch.
CSV : --csv (défaut essais/n18/resultats-f1-ia-lumiere.csv) ; images avant / après dans
essais/n18/sorties/f1/ (ignoré par git).
"""
from __future__ import annotations

import argparse
import contextlib
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import f1_banc as fb    # noqa: E402
import f1_iat as iat    # noqa: E402

COLONNES = ["banc", "scene", "sujet", "methode", "plafond", "poids", "images", "images_analyse",
            "psnr", "ssim", "delta_e", "luma_moy", "ecretes_pct", "ecart_entree_de2000",
            "analyse_s", "application_ms_par_image", "film_2h_minutes", "hypothese_temps", "coeurs",
            "largeur", "hauteur", "gamma", "matrice", "dispersion_matrice", "dispersion_gamma",
            "chaine", "remarque"]
IMAGES_2H = 2 * 3600 * 25          # film PAL de 2 heures, 25 images/s
NON = fb.NON


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


def mesure_actuelle(images: np.ndarray) -> tuple[dict, float]:
    """Ce que mesure le logiciel, une fois pour le film :
    - niveaux : médiane de YLOW / YHIGH (signalstats) sur l'échantillon, via probe.parse_signals,
      après passage en YUV 4:2:0 comme un fichier de capture ;
    - dominante : moyennes R, G, B sur 8 images réduites à 32 x 32 (comme probe.rgb_mean ; ici
      8 images réparties sur l'échantillon) -> probe.cast_gains ;
    - seuils de déclenchement de advice.py (l. 44-59)."""
    logiciel()
    from vhs_restore import probe
    t0 = time.perf_counter()
    n, h, w, _ = images.shape
    r = subprocess.run([fb.banc.ffmpeg(), "-hide_banner", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", f"{w}x{h}", "-r", "25", "-i", "-", "-vf",
                        "format=yuv420p,signalstats,metadata=print:key=lavfi.signalstats.YLOW,"
                        "metadata=print:key=lavfi.signalstats.YHIGH", "-f", "null", "-"],
                       input=np.ascontiguousarray(images).tobytes(), capture_output=True)
    sig = probe.parse_signals(r.stderr.decode(errors="replace"))
    idx = np.linspace(0, n - 1, min(8, n)).round().astype(int)
    petites = fb.banc.appliquer_filtre(images[idx], "scale=32:32:flags=bicubic").images
    rgb = tuple(float(petites[..., c].mean()) for c in range(3))
    dt = time.perf_counter() - t0
    lo, hi = sig.get("level_low"), sig.get("level_high")
    m = {"level_low": lo, "level_high": hi, "cast_rgb": tuple(round(x, 2) for x in rgb),
         "niveaux": False, "dominante": False}
    if lo is not None and hi is not None and hi - lo < 140 and lo > 35 and hi < 190:
        m.update(niveaux=True, level_black=lo / 255.0, level_white=hi / 255.0)
    if max(rgb) - min(rgb) > 15:
        m.update(dominante=True, gains=probe.cast_gains(rgb))
    return m, dt


def filtres_actuelle(m: dict, plafond: bool) -> str:
    p = logiciel()
    from vhs_restore.profiles import profile_for
    kw = {}
    if m["niveaux"]:
        kw.update(level_black=m["level_black"], level_white=m["level_white"])
    if m["dominante"]:
        kw.update(gain_r=m["gains"][0], gain_g=m["gains"][1], gain_b=m["gains"][2])
    s = p.Settings(profile=profile_for("equilibre", "video"), **kw)
    with (contextlib.nullcontext() if plafond else sans_plafond()):
        f = [x for x in (p._cast_filter(s), p._levels_filter(s)) if x]   # ordre de pre_filters
    return ",".join(f)


def resume_actuelle(m: dict) -> str:
    return (f"niveaux mesurés {m['level_low']}-{m['level_high']} ({'appliqués' if m['niveaux'] else 'seuils non atteints'}), "
            f"moyennes RGB {m['cast_rgb']} ({'dominante corrigée' if m['dominante'] else 'pas de dominante'})")


# ------------------------------------------------------------------ outils
def fmt_m(M) -> str:
    return " ".join(f"{x:.5f}" for x in np.asarray(M).reshape(-1))


def choisir(n: int, k: int) -> list[int]:
    """3 à 5 images réparties dans la scène (sans les bords si possible)."""
    k = max(3, min(5, k))
    if n <= k:
        return list(range(n))
    return sorted({int(i) for i in np.linspace(0, n - 1, k + 2)[1:-1].round()})


# ------------------------------------------------------------------ essai
def essai(nom_banc: str, scenes: list, a, dossier_img: Path) -> list[dict]:
    lignes = []

    def ajoute(s, image=None, **kw):
        l = {"banc": nom_banc, "scene": s.nom, "sujet": s.sujet, "coeurs": fb.coeurs(),
             "largeur": fb.LARGEUR, "hauteur": fb.HAUTEUR, "images": int(s.images.shape[0])}
        if image is not None:
            l.update(fb.mesures(s, image))
            l.update(fb.stats_sans_reference(image, s.images[s.milieu]))
        l.update(kw)
        lignes.append(l)

    film = np.concatenate([s.images for s in scenes])
    m_film, t_film = mesure_actuelle(film)
    f_film = {pl: filtres_actuelle(m_film, pl) for pl in (True, False)}
    print("méthode actuelle (film) :", resume_actuelle(m_film))

    modeles = {}
    for p in a.poids:
        try:
            modeles[p] = (iat.IATGlobal(p, a.threads), iat.IATComplet(p, a.threads))
        except (FileNotFoundError, RuntimeError) as e:
            print(f"IAT {p} : {e}")
            modeles[p] = None

    for s in scenes:
        n, mil = int(s.images.shape[0]), s.milieu
        vign = {} if s.origine is None else {"origine": s.origine}
        vign["entree"] = s.images[mil]
        ajoute(s, s.images[mil], methode="entree", plafond="-", poids="-", images_analyse=0,
               remarque=s.infos.get("degradation", "extrait réel"))

        # (1) méthode actuelle : mesure du film entier, puis de la scène seule
        m_sc, t_sc = mesure_actuelle(s.images)
        for meth, m, t, n_an in (("actuelle", m_film, t_film, len(film)), ("actuelle_par_scene", m_sc, t_sc, n)):
            for pl in (True, False):
                vf = f_film[pl] if meth == "actuelle" else filtres_actuelle(m, pl)
                out, spi = fb.appliquer(s, vf)
                ajoute(s, out[mil], methode=meth, plafond="oui" if pl else "non", poids="-",
                       images_analyse=n_an, analyse_s=round(t, 4), application_ms_par_image=round(1000 * spi, 3),
                       film_2h_minutes=round(spi * IMAGES_2H / 60 + t / 60, 1),
                       hypothese_temps="une analyse pour le film + filtre FFmpeg sur chaque image",
                       chaine=vf or "(aucun filtre : seuils non atteints)", remarque=resume_actuelle(m))
                if meth == "actuelle":
                    vign[f"actuelle_{'plaf' if pl else 'brut'}"] = out[mil]

        idx = choisir(n, a.images_par_scene)
        for p, mod in modeles.items():
            if mod is None:
                for meth in ("iat_global", "iat_complet"):
                    ajoute(s, methode=meth, plafond="-", poids=p, psnr=NON, ssim=NON, delta_e=NON,
                           remarque="ONNX absent : lancer iat_export_onnx.py une fois")
                continue
            g_mod, c_mod = mod
            # (2) IAT global seul : 3 à 5 images, une matrice + un gamma pour la scène
            est, t_est = fb.chronometrer(lambda: [g_mod.estimer(s.images[i]) for i in idx])
            M, g, dM, dg = iat.combiner(est)
            for pl in (True, False):
                M2, g2 = iat.plafonner(M, g) if pl else (M, g)
                vf = iat.filtres_ffmpeg(M2, g2)
                out, spi = fb.appliquer(s, vf)
                ajoute(s, out[mil], methode="iat_global", plafond="oui" if pl else "non", poids=p,
                       images_analyse=len(idx), analyse_s=round(t_est, 4),
                       application_ms_par_image=round(1000 * spi, 3),
                       film_2h_minutes=round(spi * IMAGES_2H / 60 + t_est * (7200 / a.scene_s) / 60, 1),
                       hypothese_temps=f"une scène toutes les {a.scene_s:g} s (analyse IAT de {len(idx)} images "
                                       f"par scène) + filtre FFmpeg sur chaque image",
                       gamma=round(g2, 5), matrice=fmt_m(M2), dispersion_matrice=round(dM, 5),
                       dispersion_gamma=round(dg, 5), chaine=vf,
                       remarque=f"médiane des images n° {idx} ; estimation brute : gamma {g:.4f}, matrice {fmt_m(M)}")
                vign[f"iat_global_{p}_{'plaf' if pl else 'brut'}"] = out[mil]
            # (3) IAT complet sur l'image du milieu
            im = s.images[mil]
            (mul, add, Mi, gi), t_inf = fb.chronometrer(lambda: c_mod.sorties(im))
            brut, t_rec = fb.chronometrer(lambda: c_mod.recomposer(im, mul, add, Mi, gi))
            Mp, gp = iat.plafonner(Mi, gi)
            plaf = c_mod.recomposer(im, mul, add, Mp, gp)
            for pl, out, Mx, gx in ((True, plaf, Mp, gp), (False, brut, Mi, gi)):
                ajoute(s, out, methode="iat_complet", plafond="oui (partie globale)" if pl else "non", poids=p,
                       images_analyse=1, analyse_s=0, application_ms_par_image=round(1000 * (t_inf + t_rec), 3),
                       film_2h_minutes=round((t_inf + t_rec) * IMAGES_2H / 60, 1),
                       hypothese_temps="IAT complet (ONNX) sur chaque image, 720 x 576",
                       gamma=round(gx, 5), matrice=fmt_m(Mx),
                       remarque=("partie locale (mul, add par pixel) jamais plafonnée : le logiciel n'a pas "
                                 "d'équivalent" if pl else "IAT.forward exact (vérifié contre PyTorch à l'export)"))
                vign[f"iat_complet_{p}_{'plaf' if pl else 'brut'}"] = out
        if dossier_img:
            mosaique(vign, dossier_img / f"{s.nom}.png")
        print(f"{s.nom} : fait")
    return lignes


def mosaique(v: dict, chemin: Path) -> None:
    """Vignettes (moitié de la taille) côte à côte, légende dans un .txt voisin. Hors dépôt."""
    fb.ecrire_png(np.concatenate([im[::2, ::2] for im in v.values()], axis=1), chemin)
    chemin.with_suffix(".txt").write_text(" | ".join(v.keys()) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ vérifications
def verifier() -> int:
    """Contrôles de calcul (pas des résultats d'essai) :
    1. filtres FFmpeg (colorchannelmixer + lutrgb) = formule d'IAT calculée en numpy ;
    2. méthode actuelle avec plafond = filtres du logiciel (pipeline._cast_filter / _levels_filter),
       sans plafond = mêmes filtres sans safe_levels / safe_gains, plafonds bien rétablis après ;
    3. plafonner() laisse intacte une correction déjà dans les plafonds."""
    ok = True
    rng = np.random.default_rng(18)
    img = (rng.random((96, 128, 3)) * 255).astype(np.uint8)
    M = np.array([[1.10, -0.05, 0.02], [0.03, 0.95, 0.01], [-0.02, 0.04, 1.05]])
    for g in (0.8, 1.0, 1.3):
        ff = fb.banc.appliquer_filtre(img[None], iat.filtres_ffmpeg(M, g)).images[0].astype(int)
        e = np.abs(ff - iat.appliquer_global_numpy(img, M, g).astype(int))
        print(f"FFmpeg contre numpy, gamma {g} : écart max {e.max()}, moyen {e.mean():.3f} (sur 255)")
        ok &= bool(e.max() <= 2)
    p = logiciel()
    from vhs_restore.profiles import profile_for
    s = p.Settings(profile=profile_for("equilibre", "video"), level_black=0.33, level_white=0.64,
                   gain_r=1.3, gain_g=0.8, gain_b=1.0)
    m = {"niveaux": True, "level_black": 0.33, "level_white": 0.64, "dominante": True, "gains": (1.3, 0.8, 1.0)}
    ok &= filtres_actuelle(m, True) == ",".join(f for f in (p._cast_filter(s), p._levels_filter(s)) if f)
    print("actuelle avec plafond :", filtres_actuelle(m, True))
    print("actuelle sans plafond :", filtres_actuelle(m, False))
    ok &= p.safe_gains((2.0,)) == (p.GAIN_MAX,)
    M3 = np.diag([1.05, 1.0, 0.97])
    M4, g4 = iat.plafonner(M3, 1.1)
    ok &= bool(np.allclose(M4, M3) and abs(g4 - 1.1) < 1e-9)
    print("vérifications :", "OK" if ok else "ÉCHEC")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extraits", type=Path, help="dossier de vrais extraits (sans origine connue)")
    ap.add_argument("--seulement-extraits", action="store_true", help="ne pas relancer le banc de référence")
    ap.add_argument("--images-extrait", type=int, default=9, help="images consécutives au milieu de l'extrait")
    ap.add_argument("--csv", type=Path, default=ICI / "resultats-f1-ia-lumiere.csv")
    ap.add_argument("--cache", type=Path, default=ICI / "cache", help="images de référence (hors dépôt)")
    ap.add_argument("--images", type=Path, default=ICI / "sorties" / "f1", help="avant / après (hors dépôt)")
    ap.add_argument("--poids", default=",".join(iat.POIDS_RETENUS))
    ap.add_argument("--images-par-scene", type=int, default=4, help="3 à 5 images pour IAT global")
    ap.add_argument("--scene-s", type=float, default=5.0, help="durée moyenne d'une scène (estimation 2 h)")
    ap.add_argument("--threads", type=int, default=0, help="onnxruntime (0 = tous les cœurs)")
    ap.add_argument("--verifier", action="store_true")
    a = ap.parse_args()
    a.poids = [p for p in a.poids.split(",") if p]
    for p in a.poids:
        if not iat.manifeste()["poids"].get(p, {}).get("retenu"):
            raise SystemExit(f"poids {p} non retenu (licence) : voir iat_modeles.json")
    if a.verifier:
        return verifier()
    lignes = []
    try:
        if not a.seulement_extraits:
            sc = fb.scenes_banc(a.cache)
            print(f"banc F4 : {len(sc)} scènes, {fb.coeurs()} cœurs")
            lignes += essai("F4 references", sc, a, a.images)
        if a.extraits:
            sc = fb.scenes_extraits(a.extraits, a.images_extrait)
            lignes += essai(f"extraits {a.extraits.name}", sc, a, a.images / "extraits")
    except fb.ErreurBanc as e:
        print(f"banc : {e}\nnon mesuré", file=sys.stderr)
        return 1
    if not lignes:
        print("Rien à mesurer.", file=sys.stderr)
        return 1
    print("CSV :", fb.ecrire_csv(a.csv, lignes, COLONNES))
    print("images :", a.images)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
