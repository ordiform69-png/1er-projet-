"""Essai n°18, agent F3 : modèles entraînés sur de la vraie VHS (OpenModelDB) contre l'IA actuelle.

Depuis ``vhs-restore-ai/`` :

    python essais/n18/f3_vhs.py                      # banc commun de F4 (images d'origine connues)
    python essais/n18/f3_vhs.py --extraits <dossier> # en plus : vrais extraits (pas d'origine connue)
    python essais/n18/f3_vhs.py --chrono 3           # temps seulement (machine au repos), f3_chrono.csv

Dépendances : onnxruntime, onnx, numpy et FFmpeg (ce que le logiciel a déjà). Les fichiers .onnx
sont produits À PART, une fois, par ``f3_convertir_onnx.py`` (torch + spandrel, dépendances d'essai
seulement). Ce script vérifie leur SHA-256 notée à la conversion.

Banc : module ``banc`` de F4 (branche grok/ia-essai), importé tel quel, sans modification :
``charger_references``, ``degrader`` (réglages par défaut : images et graine inchangées),
``chaine_naturelle``, ``appliquer_filtre``, ``chronometrer``, ``mesurer``, ``coeurs``.

Comparé, sur l'image du milieu de chaque extrait dégradé :
  - « degradee »          : l'image dégradée telle quelle (repère) ;
  - « sans_ia »           : chaîne du logiciel, profil « Bien nettoyé, naturel » (banc.chaine_naturelle) ;
  - « vhs_sharpen », « baldrick », « vhs_film_2x » : les trois candidats OpenModelDB, en ONNX ;
  - « realesrgan_x4plus » : l'IA actuelle (mêmes poids que realesrgan-x4plus du logiciel), seule ;
  - « rendu_maximum »     : comme le rendu « Nettoyage au plus fort » : pre_filters du profil
                            « maximum » (FFmpeg, sur les 9 images) puis Real-ESRGAN x4.
Les sorties agrandies (x2, x4) sont ramenées en 720 × 576 (moyenne par blocs) avant la mesure.

Détails inventés : en plus de PSNR / SSIM / ΔE2000 (banc.mesurer), sur l'image entière et sur des
zones « visage » (référence visages-krampf du banc) et « texte » (mire de texte COMPLÉMENTAIRE F3,
générée par FFmpeg drawtext, dégradée par banc.degrader) :
  hf_rapport = énergie des fins détails (laplacien de la luminance) / celle de l'origine
               (> 1 : plus de fins détails que l'original, donc inventés ou accentués ; < 1 : lissé) ;
  hf_ecart   = écart moyen absolu entre ces fins détails et ceux de l'origine (0 = identiques).

Temps : temps mur par image 720 × 576 sur processeur (ONNX Runtime, CPUExecutionProvider,
``--coeurs`` fils), médiane sur les images du banc. Film de 2 h en PAL :
  heures = secondes_par_image × 180 000 / 3 600   (180 000 = 25 images/s × 7 200 s).

Résultats : CSV et images avant / après dans ``--sortie``, HORS du dépôt
(par défaut <cache>/resultats, cache = VHSRA_N18_CACHE ou ~/.cache/vhsrestore-n18/f3).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
DEPOT = ICI.parents[1]                       # vhs-restore-ai/
sys.path.insert(0, str(ICI))
import banc  # noqa: E402  (banc commun de F4, non modifié)
from f3_modeles import CACHE, MODELES, chemin_onnx  # noqa: E402

L, H = banc.LARGEUR, banc.HAUTEUR
IMAGES_FILM_2H = 25 * 2 * 3600               # PAL 25 images/s x 7200 s = 180 000 images
CLES_MODELES = ["vhs_sharpen", "baldrick", "vhs_film_2x", "realesrgan_x4plus"]

# Zones (type, x, y, largeur, hauteur) dans l'image 720 × 576 préparée par le banc.
# Relevées à l'œil sur visages-krampf (recadrage centré du banc) : visage de femme, visage d'homme.
ZONES = {
    "visages-krampf": [("visage", 230, 90, 230, 210), ("visage", 400, 0, 150, 150)],
    "f3-mire-texte": [("texte", 40, 40, 640, 120), ("texte", 40, 200, 640, 120), ("texte", 40, 360, 640, 180)],
}


# ------------------------------------------------------------------ mire de texte (complément F3)
def mire_texte() -> np.ndarray:
    """Mire de texte noir (ni « : » ni « , » dans les textes : séparateurs de drawtext) sur fond clair, 720 × 576, générée par FFmpeg (aucune image dans le dépôt).
    Police : fontconfig « Sans » de la machine (notée dans le CSV des temps)."""
    lignes = [("VHS RESTORE AI - ESSAI 18", 48, 60), ("Le vif zephyr jubile sur les kiwis", 36, 130),
              ("0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ", 30, 220), ("abcdefghijklmnopqrstuvwxyz", 30, 270),
              ("Petit texte - generique de fin et sous-titres", 22, 380), ("Tres petit texte 12345 67890", 16, 430),
              ("Lignes fines ||||| ///// ##### ooooo", 22, 480)]
    dessins = ",".join(
        f"drawtext=font=Sans:text='{t}':fontsize={s}:fontcolor=0x202020:x=50:y={y}" for t, s, y in lignes)
    cmd = [banc.ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-f", "lavfi",
           "-i", f"color=c=0xE8E4D8:s={L}x{H}:d=1", "-vf", dessins + ",format=rgb24",
           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    brut = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(brut, np.uint8)[: L * H * 3].reshape(H, L, 3).copy()


def police_sans() -> str:
    try:
        return subprocess.run(["fc-match", "Sans"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "inconnue"


# ------------------------------------------------------------------ détails inventés (numpy)
def _luma(img: np.ndarray) -> np.ndarray:
    f = img.astype(np.float64)
    return 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]


def _laplacien(img: np.ndarray) -> np.ndarray:
    y = _luma(img)
    return 4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:]


def details(origine: np.ndarray, image: np.ndarray) -> dict:
    lo, li = _laplacien(origine), _laplacien(image)
    eo = float(np.mean(np.abs(lo))) or 1e-9
    return {"hf_rapport": float(np.mean(np.abs(li))) / eo, "hf_ecart": float(np.mean(np.abs(li - lo)))}


def mesures(origine: np.ndarray, image: np.ndarray) -> dict:
    m = banc.mesurer(origine, image)
    return {"psnr": m.psnr, "ssim": m.ssim, "delta_e": m.delta_e, **details(origine, image)}


# ------------------------------------------------------------------ rendu « Nettoyage au plus fort »
def pre_filtres_maximum() -> str:
    """pre_filters du profil « maximum » avec l'IA (lecture seule de vhs_restore), pour une image
    720 × 576 progressive décrite comme dans banc.chaine_naturelle."""
    if str(DEPOT) not in sys.path:
        sys.path.insert(0, str(DEPOT))
    from vhs_restore.pipeline import Settings, pre_filters
    from vhs_restore.probe import MediaInfo
    from vhs_restore.profiles import PROFILES
    info = MediaInfo(path=Path("image"), width=L, height=H, fps=Fraction(25, 1), sar=Fraction(1),
                     dar=Fraction(4, 3), scan="progressive", color_space="bt470bg", color_range="tv",
                     color_primaries="bt470bg", color_transfer="bt470bg", standard="625/25",
                     has_audio=False, codec="rawvideo", pix_fmt="rgb24")
    s = Settings(profile=PROFILES["maximum"], resolution="source", scan="progressive", source="video",
                 deinterlacer="bwdif", use_ai=True, denoise_hq=False, restore_audio=False, stabilize=False)
    return ",".join(pre_filters(info, s)) or "null"


# ------------------------------------------------------------------ modèles ONNX
class ModeleOnnx:
    def __init__(self, m: dict, coeurs: int, tuile: int, recouvrement: int = 16) -> None:
        import onnxruntime as ort
        chemin = chemin_onnx(m)
        if not chemin.is_file():
            raise FileNotFoundError(f"{chemin} absent : lancez d'abord python essais/n18/f3_convertir_onnx.py {m['cle']}")
        note = Path(str(chemin) + ".sha256")
        if not note.is_file():
            raise FileNotFoundError(f"{note} absent : relancez f3_convertir_onnx.py {m['cle']}")
        h = hashlib.sha256()
        with chemin.open("rb") as f:
            for bloc in iter(lambda: f.read(1 << 20), b""):
                h.update(bloc)
        if h.hexdigest() != json.loads(note.read_text(encoding="utf-8"))["sha256"]:
            raise RuntimeError(f"SHA-256 de {chemin} différente de celle notée à la conversion")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = coeurs
        opts.inter_op_num_threads = 1
        self.s = ort.InferenceSession(str(chemin), sess_options=opts, providers=["CPUExecutionProvider"])
        self.m, self.echelle, self.tuile, self.rec = m, m["echelle"], tuile, recouvrement
        c = tuile + 2 * recouvrement if tuile else 64
        self.s.run(None, {"image": np.zeros((1, 3, c, c), np.float32)})   # chauffe (hors chrono)

    def _passe(self, x: np.ndarray) -> np.ndarray:
        return self.s.run(None, {"image": x[None]})[0][0]

    def __call__(self, img: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(img.transpose(2, 0, 1), np.float32) / 255
        _, h, l = x.shape
        e, t, r = self.echelle, self.tuile, self.rec
        if not t or (h <= t and l <= t):
            y = self._passe(x)
        else:   # tuiles avec recouvrement (comme realesrgan-ncnn-vulkan -t), bords recollés au centre
            y = np.zeros((3, h * e, l * e), np.float32)
            for y0 in range(0, h, t):
                for x0 in range(0, l, t):
                    a0, a1 = max(0, y0 - r), min(h, y0 + t + r)
                    b0, b1 = max(0, x0 - r), min(l, x0 + t + r)
                    p = self._passe(np.ascontiguousarray(x[:, a0:a1, b0:b1]))
                    yy, xx = (y0 - a0) * e, (x0 - b0) * e
                    hh, ll = (min(h, y0 + t) - y0) * e, (min(l, x0 + t) - x0) * e
                    y[:, y0 * e:y0 * e + hh, x0 * e:x0 * e + ll] = p[:, yy:yy + hh, xx:xx + ll]
        return (np.clip(y, 0, 1).transpose(1, 2, 0) * 255 + 0.5).astype(np.uint8)


def ramener(img: np.ndarray, e: int) -> np.ndarray:
    """Sortie x e ramenée à 720 × 576 : moyenne de chaque bloc e × e."""
    if e == 1:
        return img
    h, l = img.shape[0] // e, img.shape[1] // e
    return (img[: h * e, : l * e].reshape(h, e, l, e, 3).astype(np.float64).mean((1, 3)) + 0.5).astype(np.uint8)


# ------------------------------------------------------------------ machine
def machine(coeurs: int) -> dict:
    import onnx
    import onnxruntime as ort
    cpu = platform.processor() or ""
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    ff = subprocess.run([banc.ffmpeg(), "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    return {"processeur": cpu, "coeurs_utilisables": banc.coeurs(), "fils_onnx": coeurs,
            "systeme": platform.platform(), "python": platform.python_version(),
            "onnxruntime": ort.__version__, "onnx": onnx.__version__, "numpy": np.__version__,
            "ffmpeg": ff.replace("ffmpeg version ", "")[:40], "police_mire": police_sans(),
            # machine partagée ? une charge supérieure au nombre de cœurs allonge les temps
            "charge_1min_debut": round(os.getloadavg()[0], 1) if hasattr(os, "getloadavg") else ""}


# ------------------------------------------------------------------ essai
class Variantes:
    """Applique chaque variante à une pile d'images (extrait) ; rend (image du milieu 720 × 576, s/image)."""

    def __init__(self, args) -> None:
        self.chaine = banc.chaine_naturelle()
        self.modeles: dict[str, ModeleOnnx] = {}
        self.noms = ["degradee", "sans_ia"]
        for cle in args.modeles:
            m = next(x for x in MODELES if x["cle"] == cle)
            try:
                self.modeles[cle] = ModeleOnnx(m, args.coeurs, args.tuile)
                self.noms.append(cle)
            except Exception as exc:
                print(f"  {cle} : non mesuré ({exc})")
        self.pre_max = None
        if "realesrgan_x4plus" in self.modeles:
            try:
                self.pre_max = pre_filtres_maximum()
                self.noms.append("rendu_maximum")
            except Exception as exc:
                print(f"  rendu_maximum : non mesuré ({exc})")

    def appliquer(self, nom: str, pile: np.ndarray, milieu: int) -> tuple[np.ndarray, float | None]:
        if nom == "degradee":
            return pile[milieu], None
        if nom == "sans_ia":
            r = banc.appliquer_filtre(pile, self.chaine)
            return r.images[milieu], r.secondes_par_image
        if nom == "rendu_maximum":
            r = banc.appliquer_filtre(pile, self.pre_max)
            mo = self.modeles["realesrgan_x4plus"]
            img, dt = banc.chronometrer(lambda: mo(r.images[milieu]))
            return ramener(img, mo.echelle), r.secondes_par_image + dt
        mo = self.modeles[nom]
        img, dt = banc.chronometrer(lambda: mo(pile[milieu]))
        return ramener(img, mo.echelle), dt


COLONNES = ["image", "sujet", "variante", "zone", "psnr", "ssim", "delta_e", "hf_rapport", "hf_ecart",
            "secondes_par_image", "film_2h_heures", "coeurs", "largeur", "hauteur", "tuile", "banc"]


def chrono(args, v: "Variantes", mach: dict, sortie: Path) -> int:
    """Temps seulement, à lancer sur une machine au repos : N passes de chaque variante sur la même image."""
    origine = banc.charger_references(args.cache_banc)[0].rgb
    extrait = banc.degrader(origine)
    rows = []
    for nom in v.noms:
        if nom == "degradee":
            continue
        ts = []
        for _ in range(args.chrono):
            charge = os.getloadavg()[0] if hasattr(os, "getloadavg") else float("nan")
            _, dt = v.appliquer(nom, extrait.images, extrait.milieu)
            ts.append(dt)
        med = statistics.median(ts)
        print(f"  {nom:18s} médiane {med:.3f} s/image  (min {min(ts):.3f}, max {max(ts):.3f}, charge {charge:.1f})")
        rows.append({"variante": nom, "passes": len(ts), "secondes_par_image_mediane": med,
                     "secondes_par_image_min": min(ts), "secondes_par_image_max": max(ts),
                     "taille_image": f"{L}x{H}", "tuile": args.tuile, "film_2h_images": IMAGES_FILM_2H,
                     "film_2h_heures": med * IMAGES_FILM_2H / 3600,
                     "formule": "heures = s/image x 180000 / 3600", **mach,
                     "charge_1min_fin": round(os.getloadavg()[0], 1) if hasattr(os, "getloadavg") else ""})
    banc.ecrire_csv(sortie / "f3_chrono.csv", rows, list(rows[0].keys()))
    print(f"Écrit : {sortie / 'f3_chrono.csv'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--extraits", type=Path, help="dossier de vrais extraits (vidéos ou images), hors dépôt")
    ap.add_argument("--sortie", type=Path, default=CACHE / "resultats", help="dossier des CSV et images (hors dépôt)")
    ap.add_argument("--cache-banc", type=Path, default=CACHE / "banc-f4", help="téléchargements du banc (hors dépôt)")
    ap.add_argument("--modeles", nargs="+", default=CLES_MODELES, choices=CLES_MODELES)
    ap.add_argument("--coeurs", type=int, default=banc.coeurs(), help="fils de calcul ONNX Runtime")
    ap.add_argument("--tuile", type=int, default=256, help="taille des tuiles (0 = image entière)")
    ap.add_argument("--sans-mire", action="store_true", help="ne pas ajouter la mire de texte F3")
    ap.add_argument("--chrono", type=int, default=0, metavar="N",
                    help="temps seulement : N passes par variante sur la 1re image du banc (f3_chrono.csv)")
    args = ap.parse_args()
    sortie = args.sortie.resolve()
    racine_git = DEPOT.parent.resolve()
    if sortie == racine_git or racine_git in sortie.parents:
        sys.exit("--sortie doit être HORS du dépôt (aucune image dans le dépôt).")
    images_dir = sortie / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    mach = machine(args.coeurs)
    print("Machine :", json.dumps(mach, ensure_ascii=False))
    v = Variantes(args)
    print("Chaîne « Bien nettoyé, naturel » :", v.chaine)
    print("Pré-filtres « maximum » :", v.pre_max)
    if args.chrono:
        return chrono(args, v, mach, sortie)
    temps: dict[str, list[float]] = {}
    lignes: list[dict] = []

    def heures(s):
        return None if s is None else s * IMAGES_FILM_2H / 3600

    # 1. banc commun : images d'origine connues (+ mire de texte F3)
    sujets = [(im.reference.identifiant, im.reference.sujet, im.rgb, "F4 banc.py")
              for im in banc.charger_references(args.cache_banc)]
    if not args.sans_mire:
        sujets.append(("f3-mire-texte", "texte (mire F3)", mire_texte(), "F4 banc.py + mire F3"))
    for ident, sujet, origine, nom_banc in sujets:
        extrait = banc.degrader(origine)          # réglages par défaut du banc (images, graine)
        banc.ecrire_png(origine, images_dir / f"{ident}__origine.png")
        for nom in v.noms:
            try:
                img, dt = v.appliquer(nom, extrait.images, extrait.milieu)
            except Exception as exc:
                print(f"  {ident} / {nom} : non mesuré ({exc})")
                continue
            if dt is not None:
                temps.setdefault(nom, []).append(dt)
            banc.ecrire_png(img, images_dir / f"{ident}__{nom}.png")
            commun = {"image": ident, "sujet": sujet, "variante": nom, "coeurs": args.coeurs,
                      "largeur": L, "hauteur": H, "tuile": args.tuile if nom in v.modeles or nom == "rendu_maximum" else "",
                      "banc": nom_banc}
            m = mesures(origine, img)
            lignes.append({**commun, "zone": "image entière", **m, "secondes_par_image": dt,
                           "film_2h_heures": heures(dt)})
            print(f"  {ident:20s} {nom:18s} PSNR {m['psnr']:.2f}  SSIM {m['ssim']:.4f}  ΔE {m['delta_e']:.2f}  "
                  f"hf {m['hf_rapport']:.2f}  " + (f"{dt:.2f} s" if dt is not None else ""))
            for k, (typ, x, y, w, h) in enumerate(ZONES.get(ident, [])):
                o, i, d = origine[y:y + h, x:x + w], img[y:y + h, x:x + w], extrait.images[extrait.milieu][y:y + h, x:x + w]
                lignes.append({**commun, "zone": f"{typ} {k + 1} ({x},{y},{w}x{h})", **mesures(o, i)})
                banc.ecrire_png(np.ascontiguousarray(np.concatenate([o, d, i], 1)),
                                images_dir / f"{ident}__{nom}__{typ}{k + 1}__origine-degradee-sortie.png")

    # 2. extraits réels : pas d'origine connue -> temps, détails vs avant, images avant / après
    lignes_ext: list[dict] = []
    if args.extraits:
        for media in banc.lister_medias(args.extraits):
            try:
                pile = banc.charger_media(media, n_images=9)
            except banc.ErreurBanc as exc:
                print(f"  {media.name} : illisible ({exc})")
                continue
            milieu = pile.shape[0] // 2
            avant = pile[milieu]
            base = f"extrait_{media.stem}"
            banc.ecrire_png(avant, images_dir / f"{base}__avant.png")
            for nom in v.noms:
                if nom == "degradee":
                    continue
                try:
                    img, dt = v.appliquer(nom, pile, milieu)
                except Exception as exc:
                    print(f"  {media.name} / {nom} : non mesuré ({exc})")
                    continue
                banc.ecrire_png(img, images_dir / f"{base}__{nom}.png")
                lignes_ext.append({"extrait": media.name, "variante": nom,
                                   "psnr": "non mesuré", "ssim": "non mesuré", "delta_e": "non mesuré",
                                   **{f"{a}_vs_avant": b for a, b in details(avant, img).items()},
                                   "secondes_par_image": dt, "film_2h_heures": heures(dt)})

    # 3. CSV
    def ecrire(nom, rows, colonnes):
        if rows:
            banc.ecrire_csv(sortie / nom, rows, colonnes)
            print(f"Écrit : {sortie / nom}")
    ecrire("f3_resultats.csv", lignes, COLONNES)
    if lignes_ext:
        ecrire("f3_extraits.csv", lignes_ext, list(lignes_ext[0].keys()))
    rows_t = []
    for nom, ts in temps.items():
        med = statistics.median(ts)
        rows_t.append({"variante": nom, "nb_images": len(ts), "secondes_par_image_mediane": med,
                       "secondes_par_image_min": min(ts), "secondes_par_image_max": max(ts),
                       "taille_image": f"{L}x{H}", "tuile": args.tuile,
                       "film_2h_images": IMAGES_FILM_2H, "film_2h_heures": med * IMAGES_FILM_2H / 3600,
                       "formule": "heures = s/image x 180000 / 3600", **mach,
                       "charge_1min_fin": round(os.getloadavg()[0], 1) if hasattr(os, "getloadavg") else ""})
    if rows_t:
        ecrire("f3_temps.csv", rows_t, list(rows_t[0].keys()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
