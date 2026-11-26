#!/usr/bin/env python3
"""Essai n°18, agent F2 : un juge de qualité choisit-il la bonne force de débruitage et de netteté ?

Depuis vhs-restore-ai/ :
    python essais/n18/essai_juge.py                       # banc F4 complet (5 références x 3 bruits)
    python essais/n18/essai_juge.py --extraits <dossier>  # en plus : vrais extraits (notes, temps, PNG)
    python essais/n18/essai_juge.py --rapide              # 2 références, bruit par défaut seulement

Pour chaque image dégradée par le banc (banc.degrader, `images` et `graine` inchangés), 9 réglages
sûrs = chaîne du logiciel « Bien nettoyé, naturel » (banc.chaine_naturelle) dont on remplace
seulement le débruitage (removegrain + hqdn3d des profils fidèle / équilibré / maximum) et la
netteté (cas 0 / 0,30 / 0,45, plages des trois rendus). Plus 3 variantes hors grille :
« aucun » (dégradée brute), « trop net » (cas 0,45 + unsharp fort), « trop coloré » (saturation 1,45).
Les juges ONNX (juges_iqa.py) notent l'image du milieu de chaque résultat.

Sorties : essais/n18/resultats-juge-detail.csv, resultats-juge-resume.csv,
resultats-juge-extraits.csv (avec --extraits) ; PNG dans essais/n18/sorties/juge/ (ignoré par git).
Poids : ~/vhs-n18-juge/poids (hors dépôt, SHA-256 vérifié). Dépendances : onnxruntime, numpy, FFmpeg.
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import banc  # noqa: E402
import juges_iqa as J  # noqa: E402

# Débruitage des trois profils (vhs_restore/profiles.py, Profile.denoise + despeckle).
DEBRUITAGE = {
    "fidele": (False, (1.5, 3.0, 2.0, 4.0)),
    "equilibre": (True, (3.0, 5.0, 4.5, 7.0)),
    "maximum": (True, (4.0, 7.0, 6.0, 10.0)),
}
NETTETE = {"n0": 0.0, "n030": 0.30, "n045": 0.45}      # cas des trois rendus : 0 / 0,3 / 0,45
# Niveaux de bruit : seul le bruit change ; images, graine et le reste de la dégradation F4 sont gardés.
NIVEAUX = {"defaut": None, "leger": dict(bruit_luma=6, bruit_chroma=12), "fort": dict(bruit_luma=20, bruit_chroma=36)}


def verifier_profils() -> str:
    sys.path.insert(0, str(banc.RACINE_LOGICIEL))
    from vhs_restore.profiles import PROFILES
    for k, (desp, den) in DEBRUITAGE.items():
        p = PROFILES[k]
        if tuple(p.denoise) != den or bool(p.despeckle) != desp:
            raise SystemExit(f"Profil {k} différent de profiles.py : {p.denoise}, {p.despeckle}")
    return "profils vérifiés"


def chaine_reglage(base: str, deb: str, net: float, saturation: float | None = None, extra: str = "") -> str:
    """Remplace dans la chaîne du logiciel le débruitage et la netteté, rien d'autre."""
    morceaux = [m for m in base.split(",") if not m.startswith(("removegrain=", "hqdn3d=", "cas="))]
    desp, den = DEBRUITAGE[deb]
    deb_f = (["removegrain=m0=1:m1=1:m2=1"] if desp else []) + ["hqdn3d=" + ":".join(f"{v:g}" for v in den)]
    out, place = [], False
    for m in morceaux:
        if m.startswith("eq=") and not place:
            out += deb_f
            place = True
            if saturation is not None:
                m = re.sub(r"saturation=[0-9.]+", f"saturation={saturation:g}", m)
            out.append(m)
            if net:
                out.append(f"cas=strength={net:g}")
            if extra:
                out.append(extra)
        else:
            out.append(m)
    if not place:
        raise SystemExit(f"Chaîne de référence inattendue (pas de eq=) : {base}")
    return ",".join(out)


def reglages(base: str) -> list[dict]:
    r = [{"reglage": f"{d}+{n}", "grille": 1, "debruitage": d, "nettete": v, "chaine": chaine_reglage(base, d, v)}
         for d in DEBRUITAGE for n, v in NETTETE.items()]
    r.append({"reglage": "aucun", "grille": 0, "debruitage": "aucun", "nettete": 0.0, "chaine": "null"})
    # cas=strength=1 n'est pas utilisé : mesuré dégénéré sur FFmpeg 7.1 (PSNR ~10 dB).
    r.append({"reglage": "biais_trop_net", "grille": 0, "debruitage": "equilibre", "nettete": 0.45,
              "chaine": chaine_reglage(base, "equilibre", 0.45, extra="unsharp=5:5:1.2:5:5:0")})
    r.append({"reglage": "biais_trop_colore", "grille": 0, "debruitage": "equilibre", "nettete": 0.30,
              "chaine": chaine_reglage(base, "equilibre", 0.30, saturation=1.45)})
    return r


def noter(juges, img, temps):
    notes = {}
    for j, modes in J.MODES.items():
        for m in modes:
            v, s = banc.chronometrer(lambda: juges.noter(img, j, m))
            notes[f"{j}/{m}"] = v
            temps.setdefault(f"{j}/{m}", []).append(s)
    return notes


def spearman(x, y):
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float("nan") if np.std(rx) == 0 or np.std(ry) == 0 else float(np.corrcoef(rx, ry)[0, 1])


def essai(refs, niveaux, juges, base):
    regs = reglages(base)
    detail, temps, t_ffmpeg = [], {}, []
    for image in refs:
        for niv in niveaux:
            r = banc.ReglagesVHS() if NIVEAUX[niv] is None else replace(banc.ReglagesVHS(), **NIVEAUX[niv])
            extrait = banc.degrader(image.rgb, r)
            for g in regs:
                res = banc.appliquer_filtre(extrait.images, g["chaine"])
                t_ffmpeg.append(res.secondes_par_image)
                img = res.images[extrait.milieu]
                m = banc.mesurer(image.rgb, img)
                ligne = {"identifiant": image.reference.identifiant, "sujet": image.reference.sujet,
                         "niveau": niv, "bruit_luma": r.bruit_luma, "bruit_chroma": r.bruit_chroma,
                         **{k: g[k] for k in ("reglage", "grille", "debruitage", "nettete")},
                         "psnr": round(m.psnr, 4), "ssim": round(m.ssim, 5), "delta_e": round(m.delta_e, 4)}
                ligne.update({k: round(v, 5) for k, v in noter(juges, img, temps).items()})
                ligne["chaine"] = g["chaine"]
                detail.append(ligne)
            print(f"{image.reference.identifiant} / {niv} : fait", flush=True)
    return detail, temps, t_ffmpeg


CLES = [f"{j}/{m}" for j, ms in J.MODES.items() for m in ms]


def resumer(detail, temps):
    groupes = {}
    for d in detail:
        groupes.setdefault((d["identifiant"], d["niveau"]), []).append(d)
    lignes = []
    candidats = [(k, None) for k in CLES] + [(None, f) for f in ("equilibre+n030", "fidele+n0", "maximum+n045")]
    for k, fixe in candidats:
        st = {}
        add = lambda n, v: st.setdefault(n, []).append(v)  # noqa: E731
        for g in groupes.values():
            gr = [d for d in g if d["grille"]]
            ps, ss, de = (np.array([d[x] for d in gr]) for x in ("psnr", "ssim", "delta_e"))
            rang = np.argsort(np.argsort(-ps)) + np.argsort(np.argsort(-ss)) + np.argsort(np.argsort(de))
            cons = int(np.argmin(rang))
            if k:
                sc = np.array([d[k] for d in gr])
                c = int(np.argmax(sc))
                add("rho_psnr", spearman(sc, ps)); add("rho_ssim", spearman(sc, ss)); add("rho_de", spearman(sc, -de))
                hors = {d["reglage"]: d for d in g if not d["grille"]}
                add("prefere_trop_net", hors["biais_trop_net"][k] > gr[cons][k])
                add("prefere_trop_colore", hors["biais_trop_colore"][k] > gr[cons][k])
                add("prefere_aucun", hors["aucun"][k] > gr[cons][k])
                add("choix_nettete_045", gr[c]["nettete"] == 0.45)
                add("choix_nettete_0", gr[c]["nettete"] == 0.0)
                add("choix_debruitage_maximum", gr[c]["debruitage"] == "maximum")
                add("choix_debruitage_fidele", gr[c]["debruitage"] == "fidele")
            else:
                c = [d["reglage"] for d in gr].index(fixe)
            add("bon_psnr", c == int(np.argmax(ps))); add("bon_ssim", c == int(np.argmax(ss)))
            add("bon_de", c == int(np.argmin(de))); add("bon_consensus", c == cons)
            add("top3_consensus", c in set(np.argsort(rang, kind="stable")[:3].tolist()))
            add("perte_psnr", ps.max() - ps[c]); add("perte_ssim", ss.max() - ss[c]); add("perte_de", de[c] - de.min())
        juge = k.split("/")[0] if k else ""
        ligne = {"juge": k or f"temoin_fixe:{fixe}", "n_cas": len(groupes)}
        for n, v in st.items():
            ligne[n] = round(100 * float(np.mean(v)), 1) if isinstance(v[0], (bool, np.bool_)) else round(float(np.nanmean(v)), 4)
        if k:
            ligne["ms_par_image_mediane"] = round(1000 * statistics.median(temps[k]), 1)
            ligne["taille_mo"] = round(J.taille_juge(None, juge) / 1e6, 1)
            ligne["coeurs"] = banc.coeurs()
        lignes.append(ligne)
    return lignes


def ecrire(chemin: Path, lignes):
    champs = list(dict.fromkeys(c for l in lignes for c in l))
    banc.ecrire_csv(chemin, lignes, champs)
    print("->", chemin)


def extraits(dossier: Path, juges, base, sortie_png: Path):
    regs = [g for g in reglages(base) if g["grille"] or g["reglage"] == "aucun"]
    lignes, temps = [], {}
    for p in banc.lister_medias(dossier):
        seq = banc.charger_media(p, 9)
        mil = seq.shape[0] // 2
        groupe, imgs = [], {}
        for g in regs:
            res = banc.appliquer_filtre(seq, g["chaine"])
            imgs[g["reglage"]] = res.images[mil]
            groupe.append({"fichier": p.name, "reglage": g["reglage"],
                           "secondes_par_image_ffmpeg": round(res.secondes_par_image, 4),
                           "psnr": "non mesuré", "ssim": "non mesuré", "delta_e": "non mesuré",
                           **{k: round(v, 5) for k, v in noter(juges, imgs[g["reglage"]], temps).items()}})
        banc.ecrire_png(imgs["aucun"], sortie_png / f"{p.stem}_avant.png")
        for k in CLES:
            best = max((x for x in groupe if x["reglage"] != "aucun"), key=lambda x: x[k])
            banc.ecrire_png(imgs[best["reglage"]], sortie_png / f"{p.stem}_choix_{k.replace('/', '-')}_{best['reglage']}.png")
        lignes += groupe
        print(f"{p.name} : fait", flush=True)
    return lignes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--poids", type=Path, default=J.DOSSIER_DEFAUT / "poids", help="poids ONNX (hors dépôt)")
    ap.add_argument("--cache", type=Path, default=banc.ICI / "cache", help="images du banc (hors dépôt)")
    ap.add_argument("--extraits", type=Path, help="vrais extraits (vidéos ou images) sans origine connue")
    ap.add_argument("--seulement-extraits", action="store_true")
    ap.add_argument("--rapide", action="store_true")
    ap.add_argument("--fils", type=int, default=None, help="fils onnxruntime (défaut : tous les cœurs)")
    ap.add_argument("--sortie", type=Path, default=ICI, help="dossier des CSV")
    a = ap.parse_args(argv)
    J.telecharger(a.poids)
    print(verifier_profils())
    base = banc.chaine_naturelle()
    print("Chaîne de référence :", base)
    juges = J.Juges(a.poids, fils=a.fils)
    m = J.info_machine()
    print(f"Machine : {m['processeur']}, {banc.coeurs()} cœurs, onnxruntime {m['onnxruntime']}")
    if not a.seulement_extraits:
        refs = banc.charger_references(a.cache)
        niveaux = list(NIVEAUX)
        if a.rapide:
            refs, niveaux = refs[:2], ["defaut"]
        detail, temps, t_ff = essai(refs, niveaux, juges, base)
        ecrire(a.sortie / "resultats-juge-detail.csv", detail)
        resume = resumer(detail, temps)
        resume.append({"juge": "ffmpeg_reglage", "ms_par_image_mediane": round(1000 * statistics.median(t_ff), 2),
                       "coeurs": banc.coeurs(), "n_cas": len(t_ff)})
        ecrire(a.sortie / "resultats-juge-resume.csv", resume)
    if a.extraits:
        lignes = extraits(a.extraits, juges, base, banc.ICI / "sorties" / "juge")
        if lignes:
            ecrire(a.sortie / "resultats-juge-extraits.csv", lignes)


if __name__ == "__main__":
    sys.exit(main())
