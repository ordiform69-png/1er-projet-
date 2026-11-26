"""Point de comparaison de la demande n°18 : la chaîne du logiciel.

Profil « Bien nettoyé, naturel », via ``pipeline.filter_chain`` (rien n'est
modifié dans ``vhs_restore``). Les images viennent de ``references.csv``.

Depuis ``vhs-restore-ai/`` ::

    python essais/n18/reference.py
    python essais/n18/reference.py --extraits /chemin/extraits
    python essais/n18/reference.py --seulement-extraits --extraits /chemin/extraits

Le CSV écrit les PSNR, SSIM, ΔE2000 et le temps par image. Sans origine
connue (extraits réels), ces trois écarts valent « non mesuré » ; des PNG
avant / après sont écrits dans ``essais/n18/sorties/`` (ignoré par git).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import banc


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Point de comparaison « Bien nettoyé, naturel ».")
    parseur.add_argument("--sortie", type=Path, default=banc.ICI / "resultats-reference.csv",
                         help="CSV des chiffres (défaut : essais/n18/resultats-reference.csv).")
    parseur.add_argument("--cache", type=Path, default=banc.ICI / "cache",
                         help="Dossier des téléchargements (hors dépôt).")
    parseur.add_argument("--extraits", type=Path, default=None,
                         help="Dossier d'extraits réels, sans image d'origine.")
    parseur.add_argument("--seulement-extraits", action="store_true",
                         help="Ne pas relancer les images de référence.")
    parseur.add_argument("--images-extrait", type=int, default=9,
                         help="Images consécutives lues au milieu de chaque extrait.")
    args = parseur.parse_args(argv)
    lignes: list[dict] = []
    try:
        chaine = banc.chaine_naturelle()
    except banc.ErreurBanc as exc:
        print(f"Chaîne indisponible : {exc}", file=sys.stderr)
        return 1
    print(f"Chaîne « Bien nettoyé, naturel » : {chaine}")
    print(f"Cœurs : {banc.coeurs()}    cadre : {banc.LARGEUR}×{banc.HAUTEUR}")

    if not args.seulement_extraits:
        try:
            images = banc.charger_references(args.cache)
        except banc.ErreurBanc as exc:
            print(f"Références : {exc}", file=sys.stderr)
            print("non mesuré", file=sys.stderr)
            return 1
        for image in images:
            try:
                extrait = banc.degrader(image.rgb)
                chiffres = banc.evaluer(image.rgb, extrait, chaine)
            except banc.ErreurBanc as exc:
                print(f"{image.reference.identifiant} : {exc}", file=sys.stderr)
                print("non mesuré", file=sys.stderr)
                return 1
            chiffres.update(identifiant=image.reference.identifiant, sujet=image.reference.sujet,
                            mode="reference", profil="Bien nettoyé, naturel")
            lignes.append(chiffres)
            print(f"{image.reference.identifiant}  "
                  f"dégradé PSNR {chiffres['psnr_degrade']:.3f}  SSIM {chiffres['ssim_degrade']:.4f}  "
                  f"ΔE {chiffres['delta_e_degrade']:.3f}  |  "
                  f"restauré PSNR {chiffres['psnr']:.3f}  SSIM {chiffres['ssim']:.4f}  "
                  f"ΔE {chiffres['delta_e']:.3f}  |  "
                  f"{chiffres['secondes_par_image']:.4f} s/image")

    if args.extraits:
        try:
            lignes.extend(_extraits(args.extraits, chaine, args.images_extrait))
        except banc.ErreurBanc as exc:
            print(f"Extraits : {exc}", file=sys.stderr)
            print("non mesuré", file=sys.stderr)
            return 1

    if not lignes:
        print("Rien à mesurer.", file=sys.stderr)
        return 1
    dest = banc.ecrire_csv(args.sortie, lignes)
    print(f"CSV : {dest}")
    return 0


def _extraits(dossier: Path, chaine: str, n_images: int) -> list[dict]:
    medias = banc.lister_medias(dossier)
    if not medias:
        raise banc.ErreurBanc(f"Aucun image ni vidéo dans {dossier}.")
    sorties = banc.ICI / "sorties" / "extraits"
    lignes = []
    non = banc.texte_non_mesure()
    for media in medias:
        pile = banc.charger_media(media, n_images=n_images)
        milieu = pile.shape[0] // 2
        resultat = banc.appliquer_filtre(pile, chaine)
        if resultat.images.shape[0] != pile.shape[0]:
            raise banc.ErreurBanc(f"{media.name} : nombre d'images inattendu.")
        avant = sorties / f"{media.stem}-avant.png"
        apres = sorties / f"{media.stem}-apres.png"
        banc.ecrire_png(pile[milieu], avant)
        banc.ecrire_png(resultat.images[milieu], apres)
        lignes.append({
            "identifiant": media.name, "sujet": "extrait", "mode": "extrait",
            "psnr_degrade": non, "ssim_degrade": non, "delta_e_degrade": non,
            "psnr": non, "ssim": non, "delta_e": non,
            "secondes_par_image": resultat.secondes_par_image,
            "secondes_total": resultat.secondes,
            "images": int(resultat.images.shape[0]),
            "coeurs": banc.coeurs(),
            "largeur": banc.LARGEUR, "hauteur": banc.HAUTEUR,
            "profil": "Bien nettoyé, naturel", "chaine": chaine,
            "note_juge": non,
            "definition_temps": "mur/images, demarrage ffmpeg inclus",
        })
        print(f"{media.name}  temps {resultat.secondes_par_image:.4f} s/image  "
              f"avant {avant.name}  après {apres.name}  (écarts : non mesuré)")
    return lignes


if __name__ == "__main__":
    sys.exit(main())
