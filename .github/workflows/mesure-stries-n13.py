"""Étude n°13 étape 2 : une mire entrelacée est-elle striée dans le lecteur ?

Outil d'étude seulement. N'est pas une dépendance du logiciel et ne modifie pas le lecteur.
La lecture passe par vhs_restore.lecteur.Lecteur (QMediaPlayer + QVideoWidget).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

RACINE = Path(__file__).resolve().parents[2] / "vhs-restore-ai"
sys.path.insert(0, str(RACINE))

from vhs_restore.lecteur import Lecteur  # noqa: E402


class EchecLecteur(RuntimeError):
    """Le widget a été créé, mais aucune image utilisable n'est sortie."""


def resultat(lignes: list[str], cle: str, valeur: str) -> None:
    ligne = f"RESULTAT {cle}={valeur}"
    print(ligne, flush=True)
    lignes.append(ligne)


def trouver_ffmpeg() -> tuple[str, str]:
    candidats = []
    if os.environ.get("FFMPEG"):
        candidats.append(Path(os.environ["FFMPEG"]))
    candidats.append(RACINE / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe")
    candidats.append(RACINE / "tools" / "ffmpeg" / "bin" / "ffmpeg")
    for dossier in os.environ.get("PATH", "").split(os.pathsep):
        candidats.append(Path(dossier) / "ffmpeg")
        candidats.append(Path(dossier) / "ffmpeg.exe")
    for chemin in candidats:
        if chemin.is_file():
            sonde = chemin.with_name("ffprobe.exe" if chemin.suffix == ".exe" else "ffprobe")
            if not sonde.is_file():
                sonde = chemin.with_name("ffprobe")
            return str(chemin), str(sonde)
    raise RuntimeError("FFmpeg introuvable.")


def executer(commande: list[str]) -> None:
    fait = subprocess.run(commande, capture_output=True, text=True)
    if fait.returncode != 0:
        raise RuntimeError(
            f"Commande échouée ({fait.returncode}) : {' '.join(commande[:8])}…\n{fait.stderr[-800:]}"
        )


def sonder(ffprobe: str, chemin: Path) -> dict:
    fait = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,field_order,avg_frame_rate,codec_name,nb_frames",
         "-of", "json", str(chemin)],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(fait.stdout)["streams"][0]
    trame = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_frames", "-show_entries",
         "frame=interlaced_frame,top_field_first", "-read_intervals", "%+#1", "-of", "json", str(chemin)],
        capture_output=True, text=True, check=True,
    )
    frames = json.loads(trame.stdout).get("frames") or []
    if frames:
        info["interlaced_frame"] = frames[0].get("interlaced_frame")
        info["top_field_first"] = frames[0].get("top_field_first")
    return info


def entrelace_tff(info: dict) -> bool:
    if str(info.get("field_order")) in ("tt", "tb"):
        return True
    return str(info.get("interlaced_frame")) == "1" and str(info.get("top_field_first")) == "1"


def luma_de(image: QImage) -> np.ndarray:
    gris = image.convertToFormat(QImage.Format.Format_Grayscale8)
    largeur, hauteur = gris.width(), gris.height()
    pas = gris.bytesPerLine()
    brut = np.frombuffer(bytes(gris.constBits()), dtype=np.uint8, count=pas * hauteur)
    return brut.reshape(hauteur, pas)[:, :largeur]


def analyser(image: QImage) -> dict:
    """Écart moyen |ligne 2k − ligne 2k+1| contre |ligne 2k − ligne 2k+2| sur la barre."""
    if image.isNull() or image.width() < 16 or image.height() < 16:
        raise RuntimeError("Image vide.")
    luma = luma_de(image)
    lignes = np.flatnonzero(luma.max(axis=1) >= 128)
    if lignes.size < 40:
        raise RuntimeError("La barre blanche est introuvable dans l'image.")
    y0, y1 = int(lignes[0]), int(lignes[-1]) + 1
    debut = y0 if y0 % 2 == 0 else y0 + 1
    ys = np.arange(debut, y1 - 2, 2)
    ys = ys[ys + 2 < y1]
    if ys.size < 20:
        raise RuntimeError("Pas assez de paires de lignes dans la zone en mouvement.")
    a = luma[ys].astype(np.int16)
    b = luma[np.asarray(ys) + 1].astype(np.int16)
    c = luma[np.asarray(ys) + 2].astype(np.int16)
    ecart_voisin = np.abs(a - b)
    ecart_temoin = np.abs(a - c)
    par_colonne_voisin = ecart_voisin.mean(axis=0)
    par_colonne_temoin = ecart_temoin.mean(axis=0)
    return {
        "largeur": int(image.width()),
        "hauteur": int(image.height()),
        "y0": y0,
        "y1": y1,
        "paires": int(ys.size),
        "d1": float(ecart_voisin.mean()),
        "d2": float(ecart_temoin.mean()),
        "colonnes_d1": int(np.count_nonzero(par_colonne_voisin > 15)),
        "colonnes_d2": int(np.count_nonzero(par_colonne_temoin > 15)),
        "x_bord": int(np.argmax(par_colonne_voisin)),
    }


def ratio(d1: float, d2: float) -> float:
    if d2 < 0.05:
        return 999.0 if d1 >= 0.05 else 1.0
    return d1 / d2


def enregistrer_crop(image: QImage, mesures: dict, chemin: Path) -> None:
    x = mesures["x_bord"]
    x0 = max(0, min(image.width() - 160, x - 80))
    y0 = mesures["y0"]
    hauteur = min(120, mesures["y1"] - y0, image.height() - y0)
    crop = image.copy(x0, y0, min(160, image.width() - x0), hauteur)
    if not crop.save(str(chemin), "PNG"):
        raise RuntimeError(f"Écriture impossible : {chemin}")


def image_ffmpeg(ffmpeg: str, source: Path, dest: Path, filtre: str | None, numero: int) -> None:
    selection = f"select=eq(n\\,{numero})"
    vf = f"{filtre},{selection}" if filtre else selection
    executer([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
              "-vf", vf, "-frames:v", "1", str(dest)])


LARGEUR, HAUTEUR, TRAMES = 720, 576, 50


def ecrire_mire(chemin: Path) -> None:
    """50 images déjà tissées : ligne paire au temps 2k, ligne impaire au temps 2k+1.

    La barre avance de 24 px par trame de champ. Le décalage entre champs est donc
    fixe, ce qui produit des stries si personne ne désentrelace.
    """
    with chemin.open("wb") as sortie:
        for k in range(TRAMES):
            haut = np.zeros((HAUTEUR, LARGEUR), np.uint8)
            bas = np.zeros((HAUTEUR, LARGEUR), np.uint8)
            x_haut = (2 * k * 24) % 640
            x_bas = ((2 * k + 1) * 24) % 640
            haut[48:528, x_haut:x_haut + 32] = 255
            bas[48:528, x_bas:x_bas + 32] = 255
            image = haut
            image[1::2] = bas[1::2]
            sortie.write(image.tobytes())


def commande_brute(ffmpeg: str, brut: Path) -> list[str]:
    return [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{LARGEUR}x{HAUTEUR}", "-r", "25",
            "-i", str(brut)]


def fabriquer(ffmpeg: str, dossier: Path, brut: Path) -> list[tuple[str, Path]]:
    """Encode la mire en DV PAL et en MPEG-2 DVD, avec les drapeaux d'entrelacement."""
    ecrire_mire(brut)
    commun = [*commande_brute(ffmpeg, brut),
              "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-shortest"]
    cibles = (
        ("DV", dossier / "mire-dv.avi", [
            "-vf", "setfield=tff",
            "-c:v", "dvvideo", "-pix_fmt", "yuv420p", "-aspect", "4:3",
            "-flags", "+ildct+ilme", "-top", "1", "-field_order", "tt",
            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
        ]),
        ("DVD", dossier / "mire-dvd.mpg", [
            "-target", "pal-dvd", "-vf", "setfield=tff", "-aspect", "4:3",
            "-flags", "+ildct+ilme", "-top", "1", "-field_order", "tt",
        ]),
    )
    for _nom, chemin, options in cibles:
        executer([*commun, *options, str(chemin)])
    return [(nom, chemin) for nom, chemin, _options in cibles]


def filtre_temoin(ffmpeg: str, brut: Path, dest: Path, avec_bwdif: bool) -> None:
    vf = "bwdif=mode=send_frame:parity=tff:deint=all,select=eq(n\\,15)" if avec_bwdif else "select=eq(n\\,15)"
    executer([*commande_brute(ffmpeg, brut), "-vf", vf, "-frames:v", "1", str(dest)])


def lire_dans_le_lecteur(chemin: Path, dossier: Path, nom: str) -> dict:
    """Ouvre le fichier avec le Lecteur du logiciel et garde une image pendant le mouvement."""
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    lecteur = Lecteur(app)
    if lecteur.video is None:
        raise EchecLecteur("Le widget lecteur est indisponible (Qt Multimedia absent).")
    captures: list[tuple[float, QImage]] = []
    vues: list[str] = []

    def on_frame(frame) -> None:
        pos = lecteur.media.position() / 1000 if lecteur.media is not None else -1.0
        if len(vues) < 8:
            vues.append(f"{pos:.3f}:{frame.isValid()}:{frame.pixelFormat()}")
        if pos < 0.40 or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        captures.append((pos, image.copy()))

    lecteur.video.videoSink().videoFrameChanged.connect(on_frame)
    lecteur.video.resize(720, 576)
    lecteur.video.show()
    app.processEvents()
    raisons: list[str] = []
    lecteur.echec.connect(raisons.append)
    lecteur.ouvrir(chemin, "original")
    if lecteur.audio is not None:
        lecteur.audio.setMuted(True)

    def pret() -> bool:
        return bool(raisons) or any(pos >= 0.55 for pos, _image in captures)

    limite = time.monotonic() + 12
    while time.monotonic() < limite and not pret():
        app.processEvents()
        time.sleep(0.01)
    grab = lecteur.video.grab().toImage()
    position = lecteur.media.position() / 1000 if lecteur.media is not None else -1
    lecteur.fermer()
    lecteur.video.hide()
    app.processEvents()
    if raisons and not captures:
        raise EchecLecteur(f"{nom} : {raisons[0]} | images={vues}")
    if not captures:
        raise EchecLecteur(f"{nom} : aucune image du lecteur à 0,40 s. Vues={vues} position={position:.3f}")
    pos, image = min(captures, key=lambda couple: abs(couple[0] - 0.60))
    sink_path = dossier / f"{nom}-lecteur-sink.png"
    enregistrer = image
    mesures = analyser(enregistrer)
    enregistrer_crop(enregistrer, mesures, sink_path)
    grab_info = "absente"
    if not grab.isNull():
        try:
            mesures_grab = analyser(grab)
        except RuntimeError as exc:
            grab_info = f"inutilisable ({exc})"
        else:
            enregistrer_crop(grab, mesures_grab, dossier / f"{nom}-lecteur-grab.png")
            grab_info = (
                f"d1={mesures_grab['d1']:.2f} d2={mesures_grab['d2']:.2f} "
                f"{mesures_grab['largeur']}x{mesures_grab['hauteur']}"
            )
    return {
        "position": pos,
        "mesures": mesures,
        "grab": grab_info,
        "plateforme": QGuiApplication.platformName(),
        "vues": " ".join(vues),
        "sink": sink_path.name,
    }


def ecrire_reference(ffmpeg: str, source: Path, dossier: Path, nom: str, numero: int) -> dict:
    brut = dossier / f"{nom}-ffmpeg-sans.png"
    deint = dossier / f"{nom}-ffmpeg-bwdif.png"
    # Image pleine pour la mesure, puis recadrage publié. Le PNG plein reste hors dépôt (dossier de travail).
    plein_brut = dossier / f"_{nom}-plein-sans.png"
    plein_deint = dossier / f"_{nom}-plein-bwdif.png"
    image_ffmpeg(ffmpeg, source, plein_brut, None, numero)
    image_ffmpeg(
        ffmpeg, source, plein_deint,
        "bwdif=mode=send_frame:parity=tff:deint=all", numero,
    )
    ib, idn = QImage(str(plein_brut)), QImage(str(plein_deint))
    mb, md = analyser(ib), analyser(idn)
    enregistrer_crop(ib, mb, brut)
    enregistrer_crop(idn, md, deint)
    plein_brut.unlink(missing_ok=True)
    plein_deint.unlink(missing_ok=True)
    return {"sans": mb, "bwdif": md}


def publier(lignes: list[str], prefixe: str, mesures: dict) -> None:
    resultat(lignes, f"{prefixe}_D1", f"{mesures['d1']:.2f}")
    resultat(lignes, f"{prefixe}_D2", f"{mesures['d2']:.2f}")
    resultat(lignes, f"{prefixe}_RATIO", f"{ratio(mesures['d1'], mesures['d2']):.2f}")
    resultat(lignes, f"{prefixe}_COLONNES_D1", str(mesures["colonnes_d1"]))
    resultat(lignes, f"{prefixe}_COLONNES_D2", str(mesures["colonnes_d2"]))
    resultat(lignes, f"{prefixe}_TAILLE", f"{mesures['largeur']}x{mesures['hauteur']}")
    resultat(lignes, f"{prefixe}_ZONE", f"{mesures['y0']}-{mesures['y1']}")


def conclure(d1_lecteur: float, d2_lecteur: float, d1_brut: float, d2_brut: float, d1_bwdif: float) -> str:
    """Strié si l'écart voisin du lecteur reste proche du décodage sans désentrelacement."""
    if d1_brut < 2 or ratio(d1_brut, d2_brut) < 2:
        return "mire-invalide"
    r_lecteur = ratio(d1_lecteur, d2_lecteur)
    if r_lecteur >= 2 and d1_lecteur >= max(2.0, 2 * d1_bwdif) and d1_lecteur >= 0.45 * d1_brut:
        return "strie"
    if r_lecteur < 1.6 and d1_lecteur <= max(d1_bwdif * 1.5, d1_brut * 0.35):
        return "non-strie"
    return "indetermine"


def emettre_lecture(nom: str, lecture: dict) -> None:
    lignes: list[str] = []
    publier(lignes, f"{nom}_LECTEUR", lecture["mesures"])
    resultat(lignes, f"{nom}_LECTEUR_POSITION", f"{lecture['position']:.3f}")
    resultat(lignes, f"{nom}_LECTEUR_GRAB", lecture["grab"])
    resultat(lignes, f"{nom}_LECTEUR_VUES", lecture["vues"])
    resultat(lignes, f"{nom}_PLATEFORME", lecture["plateforme"])


def lire_via_processus(chemin: Path, dossier: Path, nom: str, lignes: list[str]) -> dict:
    """Le lecteur tourne dans un sous-processus : un plantage d'écran n'emporte pas la mesure."""
    script = str(Path(__file__).resolve())

    def lancer(plateforme: str | None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if plateforme:
            env["QT_QPA_PLATFORM"] = plateforme
        elif "QT_QPA_PLATFORM" in env and os.environ.get("QT_QPA_PLATFORM") is None:
            env.pop("QT_QPA_PLATFORM", None)
        return subprocess.run(
            [sys.executable, script, "--sortie", str(dossier), "--lecture", nom, str(chemin)],
            env=env, capture_output=True, text=True,
        )

    demande = os.environ.get("QT_QPA_PLATFORM")
    fait = lancer(demande)
    if fait.returncode != 0 and demande != "offscreen":
        extrait = (fait.stderr or fait.stdout or "").strip().replace("\n", " | ")[-400:]
        resultat(lignes, f"{nom}_PLATEFORME_NATIVE_ECHEC", f"code {fait.returncode} {extrait}")
        fait = lancer("offscreen")
    for ligne in (fait.stdout or "").splitlines():
        if ligne.startswith("RESULTAT "):
            print(ligne, flush=True)
            lignes.append(ligne)
    if fait.returncode != 0:
        detail = (fait.stderr or "").strip().replace("\n", " | ")[-400:]
        raise RuntimeError(f"{nom} : lecture en échec ({fait.returncode}). {detail}")
    for ligne in (fait.stderr or "").splitlines():
        if "FFmpeg version" in ligne:
            resultat(lignes, f"{nom}_BACKEND", ligne.strip()[:180])
            break

    def nombre(suffixe: str) -> float:
        prefixe = f"RESULTAT {nom}_LECTEUR_{suffixe}="
        for ligne in reversed(lignes):
            if ligne.startswith(prefixe):
                return float(ligne.split("=", 1)[1])
        raise RuntimeError(f"Mesure {suffixe} absente pour {nom}.")

    return {"d1": nombre("D1"), "d2": nombre("D2")}


def mesurer(sortie: Path) -> list[str]:
    lignes: list[str] = []
    ffmpeg, ffprobe = trouver_ffmpeg()
    version = subprocess.run([ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True, check=True)
    resultat(lignes, "FFMPEG", version.stdout.splitlines()[0])
    resultat(lignes, "PLATEFORME_DEMANDEE", os.environ.get("QT_QPA_PLATFORM", "native"))
    import PySide6
    resultat(lignes, "PYSIDE", PySide6.__version__)
    plugins = list(Path(PySide6.__file__).parent.rglob("*ffmpegmediaplugin*"))
    resultat(lignes, "PLUGIN_FFMPEG", str(plugins[0]) if plugins else "absent")

    travail = sortie / "_travail"
    travail.mkdir(parents=True, exist_ok=True)
    brut = travail / "mire.gray"
    sources = fabriquer(ffmpeg, travail, brut)
    for nom, avec in (("FILTRE", False), ("FILTRE_BWDIF", True)):
        chemin = travail / f"{nom}.png"
        filtre_temoin(ffmpeg, brut, chemin, avec)
        mesures = analyser(QImage(str(chemin)))
        publier(lignes, nom, mesures)
        enregistrer_crop(QImage(str(chemin)), mesures, sortie / f"{nom.lower()}-crop.png")
    for nom, chemin in sources:
        info = sonder(ffprobe, chemin)
        resultat(lignes, f"{nom}_CODEC", str(info.get("codec_name")))
        resultat(lignes, f"{nom}_BALAYAGE", str(info.get("field_order")))
        resultat(lignes, f"{nom}_TAILLE_SOURCE", f"{info.get('width')}x{info.get('height')}")
        resultat(lignes, f"{nom}_CADENCE", str(info.get("avg_frame_rate")))
        resultat(lignes, f"{nom}_IMAGES", str(info.get("nb_frames")))
        resultat(lignes, f"{nom}_TRAME_ENTRELACEE", str(info.get("interlaced_frame")))
        resultat(lignes, f"{nom}_TRAME_HAUTE_DABORD", str(info.get("top_field_first")))
        resultat(lignes, f"{nom}_OCTETS", str(chemin.stat().st_size))
        if not entrelace_tff(info):
            raise RuntimeError(
                f"{nom} n'est pas marqué entrelacé TFF : field_order={info.get('field_order')} "
                f"interlaced_frame={info.get('interlaced_frame')} top_field_first={info.get('top_field_first')}"
            )
        refs = ecrire_reference(ffmpeg, chemin, sortie, nom, 15)
        publier(lignes, f"{nom}_FFMPEG_SANS", refs["sans"])
        publier(lignes, f"{nom}_FFMPEG_BWDIF", refs["bwdif"])
        lecture = lire_via_processus(chemin, sortie, nom, lignes)
        verdict = conclure(
            lecture["d1"], lecture["d2"],
            refs["sans"]["d1"], refs["sans"]["d2"], refs["bwdif"]["d1"],
        )
        resultat(lignes, f"{nom}_VERDICT", verdict)
    # Les PNG pleins de travail ne sont pas des artefacts : trop lourds, et la mire vidéo non plus.
    for chemin in travail.glob("*"):
        chemin.unlink(missing_ok=True)
    travail.rmdir()
    return lignes


def main() -> int:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--sortie", type=Path, required=True)
    analyseur.add_argument("--lecture", nargs=2, metavar=("NOM", "CHEMIN"))
    args = analyseur.parse_args()
    args.sortie.mkdir(parents=True, exist_ok=True)
    if args.lecture:
        nom, chemin = args.lecture
        try:
            emettre_lecture(nom, lire_dans_le_lecteur(Path(chemin), args.sortie, nom))
        except Exception as exc:
            print(f"RESULTAT STRIES_ECHEC={exc}", flush=True)
            return 1
        return 0
    try:
        lignes = mesurer(args.sortie)
    except Exception as exc:
        print(f"RESULTAT STRIES_ECHEC={exc}", flush=True)
        return 1
    mesures = args.sortie / "mesures.txt"
    deja = mesures.read_text(encoding="utf-8") if mesures.exists() else ""
    mesures.write_text(deja + "\n".join(lignes) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
