"""Orchestration : construction de la chaîne de filtres FFmpeg, aperçu, export.

Une seule chaîne, trois origines (Settings.source) qui changent seulement des
paramètres, jamais de moteur :
  video    : cassette analogique ; désentrelacement par trame (50p) si mesuré.
  film     : pellicule numérisée directement ; jamais désentrelacée sans choix
             manuel ; cadence de tournage réglable (re-cadencement sans
             créer ni supprimer d'image) ; grain préservé (profils plus légers).
  transfer : pellicule copiée sur vidéo ; si entrelacée, appariement des trames
             (fieldmatch) puis désentrelacement des seules images encore
             mélangées, à la cadence vidéo (25p). Aucune suppression d'images
             répétées : la cadence d'origine n'est pas supposée connue.

Ordre des traitements (du plus « physique » au plus « cosmétique ») :
  1. recadrage à des dimensions paires (si nécessaire, 1 pixel au plus)
  2. désentrelacement, une image par trame (50p / 59,94p) : conserve la
     fluidité de mouvement d'origine ; ordre des trames explicite.
     bwdif (FFmpeg) ou QTGMC (VapourSynth, vspipe → FFmpeg par un tube)
  3. [stabilisation facultative : vid.stab, 2 passes] sur images progressives,
     avant le débruitage temporel qui profite d'images alignées
  4. suppression des parasites ponctuels (removegrain)
  5. réduction du bruit spatio-temporelle : hqdn3d, ou en haute qualité
     fftdnoiz (FFT 3D) + renfort chroma
  6. contraste, saturation et gamma (lutyuv en 10 bits : eq ne dépasse pas 8 bits)
  7. [IA facultative : Real-ESRGAN x4 sur images PNG]
  8. mise à l'échelle lanczos vers la taille cible, matrice couleur BT.709 en HD
  9. netteté adaptative (cas), sauf si l'IA est utilisée
 10. rapport de pixel (setsar), puis UNE descente en yuv420p 8 bits, tramée
Une seule compression finale (H.264 8 bits) : pas de conversions successives destructives
(l'intermédiaire du mode IA est sans perte : FFV1 + FLAC, images PNG).
Le calcul reste en 10 bits dès que les filtres le permettent. removegrain, fieldmatch
et vid.stab n'existent qu'en 8 bits (FFmpeg 6.1 et 9.1) : on ne monte en précision
qu'après eux, pour ne pas redescendre au milieu de la chaîne.
"""
from __future__ import annotations

import contextvars
import dataclasses
import json
import hashlib
import logging
import math
import os
import re
import shutil
import subprocess
import time
import tempfile
import threading
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from .probe import MediaInfo
from .profiles import Profile
from .tools import AAC, CopieIncomplete, copie_annexe
from .tools import partiel_unique, reserver_sorties
from .tools import (_NO_WINDOW, QTGMC_SCRIPT, Cancelled, FichierOccupe, ToolError, Toolset, effacer,
                    finaliser, run, run_capture, verifier_chemin,
                    terminate)
from . import reprise
from .dvd import input_args as _entree_dvd
from .dvd import lecture_dvd, is_menu, open_media, titles_in
from .upscaler import RealEsrganUpscaler

# Dernier `-ss` placé AVANT l'entrée. Le filtre voit alors le temps repartir de zéro :
# la correction de scène doit quand même suivre le temps de la source.
_origine_gen: contextvars.ContextVar[int] = contextvars.ContextVar("vhs_origine_gen", default=0)
_origine_en_attente: contextvars.ContextVar[tuple[int, float] | None] = contextvars.ContextVar(
    "vhs_origine_attente", default=None)
_origine_liee: contextvars.ContextVar[tuple[int, int, float] | None] = contextvars.ContextVar(
    "vhs_origine_liee", default=None)

log = logging.getLogger("vhs_restore")
Progress = Callable[[float, str], None]
AI_CHUNK_FRAMES = 60
STAB_FILE = "transforms.trf"   # nom relatif : les commandes vid.stab tournent dans le dossier de travail

# Réglages de stabilisation (vid.stab). Objectif : atténuer les tremblements de la
# caméra tenue à la main, pas figer les mouvements volontaires (panoramiques).
STAB_SHAKINESS = 5            # 1-10 : tremblements attendus (5 = défaut vid.stab)
STAB_ACCURACY = 15            # précision maximale de la détection
STAB_SMOOTH_SECONDS = 0.3     # lissage de la trajectoire : ±0,3 s
STAB_MAX_SHIFT = 0.04         # correction maximale : 4 % de la largeur…
STAB_MAX_ANGLE = 0.035        # …et 2° de rotation : limite le zoom nécessaire


@dataclass
class Settings:
    profile: Profile
    resolution: str = "source"            # source | 1080 | 2160
    scan: str | None = None               # forçage manuel : progressive | tff | bff
    dar: Fraction | None = None           # forçage manuel du format d'affichage
    use_ai: bool = False
    deinterlacer: str = "bwdif"           # bwdif | qtgmc
    stabilize: bool = False
    denoise_hq: bool = False
    source: str = "video"                 # video | film | transfer
    playback_fps: Fraction | None = None  # film : cadence de tournage choisie (None = celle du fichier)
    deflicker: bool = False               # film / transfert : réduction du scintillement
    constant_rate: bool = False           # interne : imposer la cadence (après Analog Repair, dont
                                          # les horodatages sont irréguliers sur un MPEG NTSC réel)
    dust: bool = False                    # film : poussières et rayures (Analog Repair, facultatif)
    tape_noise: bool = False              # vidéo : poursuite, bande du bas, lignes (Analog Repair)
    chroma_repair: bool = False           # vidéo : arcs-en-ciel et couleur perdue, luminance intacte
    dropouts: bool = False                # vidéo : taches ou lignes d'une seule image
    restore_audio: bool = True            # nettoyage du son selon le profil (jamais si piste muette)
    audio_offset_ms: float = 0.0          # >0 retarde le son, <0 l'avance. 0 = inchangé
    audio_drift_ms_per_min: float = 0.0   # >0 le son prend du retard : on l'accélère (atempo)
    audio_mains_hz: int = 0                # 0 | 50 | 60 : encoche secteur, seulement si demandé
    audio_channel_fix: str = ""            # "" | left | right (canal gardé des deux côtés) | phase
    audio_declip: bool = False             # reconstruire les crêtes saturées (adeclip)
    audio_highpass: bool = False           # vent et grondements : passe-haut doux à 80 Hz
    audio_presence: bool = False           # voix étouffée : présence vers 3 kHz, +3 dB au plus
    level_black: float = 0.0              # 0 et 1 = ne pas toucher aux niveaux
    level_white: float = 1.0
    chroma_shift: int = 0                  # décalage horizontal de la couleur, en pixels (−8 à +8)
    gain_r: float = 1.0                    # dominante : 1 = ne pas toucher
    gain_g: float = 1.0
    gain_b: float = 1.0
    audio_copy: str = ""                   # "" | wav | flac : copie du son restauré à côté du film
    use_rnnoise: bool = False              # Équilibré / Maximum : RNNoise à la place d'afftdn
    mask_bottom: int = 0                   # lignes noires en bas (bande de commutation VHS), 0 = rien
    mask_sides: int = 0                    # pixels noirs sur les bords, 0 = rien. Pellicule : les quatre côtés
    colorize: bool = False                 # photo noir et blanc : copie colorisée par IA EN PLUS (couleurs inventées)
    # Réglages de l'utilisateur avant de lancer (−3 à +3, 0 = rendu du profil inchangé) :
    # lumière des tons moyens (gamma), contraste, couleurs (saturation), teinte (froide / chaude)
    lumiere: int = 0
    contraste: int = 0
    couleurs: int = 0
    teinte: int = 0
    crf: int = 18
    preset: str = "medium"


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def effective_scan(info: MediaInfo, s: Settings) -> str:
    """'unknown' n'est jamais traité comme entrelacé (pas de supposition).
    Pellicule numérisée directement : progressive, sauf choix manuel explicite."""
    if s.scan:
        return s.scan
    return "progressive" if s.source == "film" else info.scan


def uses_qtgmc(info: MediaInfo, s: Settings) -> bool:
    return (s.source == "video" and s.deinterlacer == "qtgmc"
            and effective_scan(info, s) in ("tff", "bff"))


def retime(info: MediaInfo, s: Settings) -> Fraction | None:
    """Nouvelle cadence si l'utilisateur a indiqué une cadence de tournage différente
    de celle du fichier (pellicule numérisée image par image uniquement)."""
    if s.source == "film" and s.playback_fps and s.playback_fps != info.fps:
        return s.playback_fps
    return None


def time_ratio(info: MediaInfo, s: Settings) -> float:
    """Durée exportée / durée du fichier (1 sans re-cadencement)."""
    r = retime(info, s)
    return float(info.fps / r) if r else 1.0


def _cfr_args(info: MediaInfo, s: Settings) -> list[str]:
    if not s.constant_rate or retime(info, s):   # le re-cadencement impose déjà -r
        return []
    r = output_fps(info, s)
    return ["-r", f"{r.numerator}/{r.denominator}"]


def retime_args(info: MediaInfo, s: Settings) -> list[str]:
    """Cadence de sortie fixe. Le son correspondant est dans audio_args (atempo)."""
    r = retime(info, s)
    if not r:
        return []
    return ["-r", f"{r.numerator}/{r.denominator}"]


def _tempo_factor(info: MediaInfo, s: Settings, *, drift: bool) -> float:
    """Vitesse du son par rapport au fichier. 1 = inchangée.
    Le re-cadencement pellicule et la dérive se combinent en un seul atempo."""
    f = 1.0
    r = retime(info, s)
    if r:
        f *= float(r / info.fps)
    if drift:
        # positif : le son s'éloigne en retard de N ms par minute de film → on l'accélère
        per = max(-0.04, min(0.04, s.audio_drift_ms_per_min / 60000.0))
        if abs(per) >= 0.5 / 60000.0:
            f *= 1.0 / (1.0 - per)
    return f


def _atempo_chain(factor: float) -> list[str]:
    # 1e-7 (n°20, A3) : avec 1e-4, une dérive de moins de 6 ms par minute était ignorée
    # (5 ms/min laissaient 0,9 s de décalage à la fin d'un film de 3 h).
    if abs(factor - 1.0) < 1e-7:
        return []
    f, chain = factor, []
    while f > 2.0:
        chain.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        chain.append("atempo=0.5")
        f /= 0.5
    chain.append(f"atempo={f:.6f}")
    return chain


def _atempo_filters(info: MediaInfo, s: Settings, *, drift: bool = True) -> list[str]:
    if not info.has_audio:
        return []
    return _atempo_chain(_tempo_factor(info, s, drift=drift))


def _ff_filter_path(path: str) -> str:
    """Chemin comme valeur d'option dans un graphe de filtres (-af, -vf, -filter_complex).

    FFmpeg lit ce texte DEUX fois : le graphe d'abord (« , ; [ ] » séparent les filtres), puis
    les options du filtre (« : » sépare les options). Chaque lecture retire un niveau de « \\ ».
    Un seul niveau ne suffit pas : « C\\:/Users » redevenait « C:/Users » à la première lecture,
    puis le « : » coupait le chemin (erreur « No option name near '/Users/…' » sous Windows).
    Apostrophes (« l'été »), virgules et crochets d'un nom de dossier sont protégés de même."""
    p = Path(path).as_posix().replace("\\", "/")
    option = re.sub(r"([\\':])", r"\\\1", p)              # 2e lecture : options du filtre
    return re.sub(r"([\\'\[\],;])", r"\\\1", option)       # 1re lecture : le graphe


def _has(present: frozenset[str] | None, name: str) -> bool:
    return present is None or name in present


# Valeur invalide (NaN, infini) remplacée par du silence. RNNoise (arnndn) en a produit à la fin
# d'un film chez l'utilisateur : l'encodeur AAC refuse alors tout (« Input contains NaN »).
GARDE_NAN = "aeval='if(isnan(val(ch))+isinf(val(ch)),0,val(ch))':c=same"


AFFTDN_RETARD = 0.025   # s : afftdn de FFmpeg, mesuré à 48 000, 44 100 et 32 000 Hz (corrélation)


def audio_filters(info: MediaInfo, s: Settings, *, restore: bool = True,
                  skip_afftdn: bool = False, apply_offset: bool = True,
                  apply_drift: bool = True,
                  present: frozenset[str] | None = None,
                  rnnoise: str | None = None) -> list[str]:
    """Chaîne -af. Les ambiances restent dans le signal : pas de séparation voix/bruit.
    present=None : on suppose les filtres présents (tests). Un ensemble vide les retire."""
    if not info.has_audio:
        return []
    chain: list[str] = []
    # Corrections demandées explicitement (conseils de l'analyse) : appliquées même si
    # « Restaurer le son » est décoché, car elles réparent un défaut et n'embellissent pas.
    if restore and not info.audio_silent:
        fix = {"left": "pan=stereo|c0=c0|c1=c0", "right": "pan=stereo|c0=c1|c1=c1",
               "phase": "pan=stereo|c0=c0|c1=-1*c1"}.get(s.audio_channel_fix)
        if fix and info.audio_channels == 2 and _has(present, fix.split("=")[0]):
            chain.append(fix)
        if s.audio_declip and _has(present, "adeclip"):
            chain.append("adeclip")
        if s.audio_mains_hz in (50, 60) and _has(present, "bandreject"):
            hz = int(s.audio_mains_hz)
            # Q élevé = encoche étroite : le bourdonnement et ses harmoniques, pas la voix
            for n in (1, 2, 3, 4):
                chain.append(f"bandreject=f={hz * n}:t=q:w=30")
        if s.audio_highpass and _has(present, "highpass"):
            # 6 dB/octave : le vent et les grondements, pas les voix (300 Hz ≈ −0,3 dB)
            chain.append("highpass=f=80:poles=1")
        if s.audio_presence and _has(present, "equalizer"):
            # Cloche étroite : +3 dB à 3 kHz, pas plus. Les graves et les aigus extrêmes restent.
            chain.append("equalizer=f=3000:t=q:w=1:g=3")
    if restore and s.restore_audio and not info.audio_silent:
        p = s.profile
        latence = 0.0
        if p.adeclick and _has(present, "adeclick"):
            chain.append("adeclick")
        # RNNoise (Xiph, modèle livré) seulement si la case est cochée, et seulement
        # à la place d'afftdn en Équilibré et Maximum. Mélangé au signal d'origine.
        # DeepFilterNet, s'il a tourné, a déjà traité le souffle. Défaut : afftdn.
        speech = bool(s.use_rnnoise and p.afftdn_nr and p.afftdn_nr >= 8)
        if (speech and rnnoise and not skip_afftdn and _has(present, "arnndn")):
            mix = 0.55 if p.afftdn_nr >= 12 else 0.35
            chain.append(f"arnndn=m={_ff_filter_path(rnnoise)}:mix={mix}")
            if _has(present, "aeval"):
                chain.append(GARDE_NAN)
        elif p.afftdn_nr and not skip_afftdn and _has(present, "afftdn"):
            chain.append(f"afftdn=nr={p.afftdn_nr:g}:nf=-50:tn=1")
            latence = AFFTDN_RETARD
        frequence = int(getattr(info, "audio_rate", 0) or 0)
        if latence and frequence > 0 and _has(present, "atrim"):
            # Mesuré (n°20, A2) : afftdn retarde le son de 25 ms exactement (48 000, 44 100 et
            # 32 000 Hz) et sort d'abord 25 ms de silence. Ce silence est retiré, compté en
            # ÉCHANTILLONS, puis l'horloge reculée d'autant : son calé, début gardé, durée exacte.
            # Pas de silence ajouté devant (adelay) : lu au milieu du film (passages gardés),
            # adelay donne une horloge invalide que la suite propage (son coupé à 0,25 s).
            chain += [f"atrim=start_sample={round(latence * frequence)}", f"asetpts=PTS-{latence:.3f}/TB",
                      f"apad=pad_dur={latence:.3f}"]
        if p.loudnorm and _has(present, "dynaudnorm"):
            # gain plafonné : rattrape les écarts de volume sans écraser l'ambiance
            chain.append("dynaudnorm=f=250:g=15:p=0.95:m=8")
    ms = s.audio_offset_ms if apply_offset else 0.0
    if abs(ms) >= 1:
        if ms > 0 and _has(present, "adelay"):
            chain.append(f"adelay={int(round(ms))}:all=1")
        elif ms < 0 and _has(present, "atrim"):
            chain += [f"atrim=start={-ms / 1000:.4f}", "asetpts=PTS-STARTPTS"]
    chain += _atempo_filters(info, s, drift=apply_drift)
    return chain


def audio_args(info: MediaInfo, s: Settings, *, restore: bool = True,
               skip_afftdn: bool = False, apply_offset: bool = True,
               apply_drift: bool = True,
               present: frozenset[str] | None = None,
               rnnoise: str | None = None) -> list[str]:
    chain = audio_filters(info, s, restore=restore, skip_afftdn=skip_afftdn,
                          apply_offset=apply_offset, apply_drift=apply_drift,
                          present=present, rnnoise=rnnoise)
    return ["-af", ",".join(chain)] if chain else []


def _try_deepfilter(info: MediaInfo, s: Settings, tools: Toolset, work: Path,
                    start: float | None, duration: float | None,
                    cancel: threading.Event | None) -> Path | None:
    """DeepFilterNet (binaire libre) sur un WAV 48 kHz. Échec = repli afftdn, pas d'arrêt."""
    if not (s.restore_audio and s.profile.deepfilter and tools.deepfilter.ok
            and info.has_audio and not info.audio_silent):
        return None
    src = work / "son_source.wav"
    out_dir = work / "son_df"
    out_dir.mkdir(exist_ok=True)
    try:
        run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
             *_seek(start, duration), *dvd_input(info), "-map", "0:a:0",
             "-ar", "48000", "-c:a", "pcm_s16le", str(src)],
            cancel=cancel, what="FFmpeg (extraction du son)")
        run([tools.deepfilter.path, "-D", "-a", "12", "-o", str(out_dir), str(src)],
            cancel=cancel, what="DeepFilterNet")
    except (ToolError, Cancelled):
        if cancel is not None and cancel.is_set():
            raise
        log.warning("DeepFilterNet indisponible ou en échec : repli sur afftdn", exc_info=True)
        return None
    wavs = sorted(out_dir.glob("*.wav"))
    if not wavs:
        log.warning("DeepFilterNet n'a rien écrit dans %s", out_dir)
        return None
    log.info("Son traité par DeepFilterNet : %s", wavs[0])
    return wavs[0]


def effective_dar(info: MediaInfo, s: Settings) -> Fraction:
    return s.dar or info.dar


def effective_resolution(s: Settings) -> str:
    if s.resolution == "2160" and not s.use_ai:
        raise ToolError("La 4K n'est proposée qu'avec l'amélioration IA "
                        "(un simple agrandissement n'apporte aucun détail).")
    if s.use_ai and s.resolution == "source":
        return "1080"   # l'IA agrandit forcément : on vise au moins le Full HD
    return s.resolution


def output_fps(info: MediaInfo, s: Settings) -> Fraction:
    r = retime(info, s)
    if r:
        return r
    if s.source == "video" and effective_scan(info, s) in ("tff", "bff"):
        return info.fps * 2      # une image par trame
    return info.fps


def target_size(info: MediaInfo, s: Settings) -> tuple[int, int, Fraction]:
    """(largeur, hauteur, rapport de pixel) en sortie."""
    dar = effective_dar(info, s)
    res = effective_resolution(s)
    if res == "source":
        w, h = info.width // 2 * 2, info.height // 2 * 2
        return w, h, (dar * h / w).limit_denominator(1000)
    h = int(res)
    return _even(h * dar), h, Fraction(1)


def _in_matrix(info: MediaInfo) -> str:
    return {"bt709": "bt709", "fcc": "fcc", "smpte240m": "smpte240m",
            "bt2020nc": "bt2020", "bt470bg": "bt601", "smpte170m": "bt601"}.get(
                info.color_space, "bt601")


def _base_filters(info: MediaInfo, s: Settings) -> list[str]:
    """Recadrage pair + désentrelacement FFmpeg : ce que voient les deux passes de stabilisation."""
    f: list[str] = []
    if info.width % 2 or info.height % 2:
        f.append(f"crop={info.width // 2 * 2}:{info.height // 2 * 2}:0:0")
    scan = effective_scan(info, s)
    if scan in ("tff", "bff"):
        if s.source == "video":
            if not uses_qtgmc(info, s):
                f.append(f"bwdif=mode=send_field:parity={scan}:deint=all")
        else:
            # pellicule passée par la vidéo : on recolle les trames issues d'une même
            # image de film, et on ne désentrelace que les images restées mélangées
            f.append(f"fieldmatch=order={scan}:combmatch=full")
            f.append(f"bwdif=mode=send_frame:parity={scan}:deint=interlaced")
    r = retime(info, s)
    if r:
        f.append(f"setpts=N*{r.denominator}/{r.numerator}/TB")
    return f


def stab_detect_filters(info: MediaInfo, s: Settings) -> list[str]:
    return _base_filters(info, s) + [
        f"vidstabdetect=result={STAB_FILE}:shakiness={STAB_SHAKINESS}:accuracy={STAB_ACCURACY}"]


def stab_transform_filter(info: MediaInfo, s: Settings) -> str:
    """Zoom statique optimal (pas de bords noirs en général) borné par maxshift/maxangle ;
    s'il reste un bord, il est noir (crop=black) plutôt que rempli avec une image passée."""
    smoothing = max(1, round(float(output_fps(info, s)) * STAB_SMOOTH_SECONDS))
    maxshift = max(1, round(info.width * STAB_MAX_SHIFT))
    return (f"vidstabtransform=input={STAB_FILE}:smoothing={smoothing}:optzoom=1:"
            f"maxshift={maxshift}:maxangle={STAB_MAX_ANGLE:g}:crop=black:interpol=bicubic")


# Plafonds de fidélité, constatés sur une vraie VHS de 1988 (très verte, niveaux 84-163) :
# corrigée sans limite (rouge x1,56, contraste x2,8), l'image virait au magenta avec des
# noirs bouchés. On atténue le défaut au lieu de chercher à l'annuler.
MAX_CONTRAST = 1.6            # étirement des niveaux au plus x1,6
GAIN_MIN, GAIN_MAX = 0.85, 1.18   # dominante : chaque couleur de -15 % à +18 % au plus


def safe_levels(lo: float, hi: float) -> tuple[float, float]:
    """Élargit la plage mesurée autour de son milieu pour ne pas dépasser MAX_CONTRAST."""
    width = 1.0 / MAX_CONTRAST
    if hi - lo < width:
        mid = (lo + hi) / 2
        lo, hi = max(0.0, mid - width / 2), min(1.0, mid + width / 2)
    return lo, hi


def safe_gains(gains: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(min(GAIN_MAX, max(GAIN_MIN, g)) for g in gains)


def _levels_filter(s: Settings) -> str | None:
    """Étirement fixe des noirs et des blancs. Absent si les niveaux sont déjà ouverts.

    À moitié seulement : mesuré sur tout le film, l'étirement complet noircissait les scènes
    d'intérieur peu éclairées (ombres bouchées, image « trop sombre » chez l'utilisateur)."""
    lo, hi = safe_levels(float(s.level_black), float(s.level_white))
    if not (0.02 < lo < hi < 0.98 and hi - lo < 0.75):
        return None
    lo, hi = lo / 2, hi + (1.0 - hi) / 2
    return (f"colorlevels=rimin={lo:.4f}:gimin={lo:.4f}:bimin={lo:.4f}:"
            f"rimax={hi:.4f}:gimax={hi:.4f}:bimax={hi:.4f}")


# Un cran des réglages « Lumière et couleurs » (−3 à +3) : gamma des tons moyens, contraste,
# saturation, et 3 % de rouge en plus / de bleu en moins vers le chaud (l'inverse vers le froid).
PAS_LUMIERE, PAS_CONTRASTE, PAS_COULEURS, PAS_TEINTE = 0.10, 0.06, 0.12, 0.03
CRANS = 3


def cran(v) -> int:
    return max(-CRANS, min(CRANS, int(v or 0)))


def reglages_image(s: Settings) -> tuple[float, float, float]:
    """(contraste, saturation, gamma) : le profil, puis les réglages de l'utilisateur (−3 à +3)."""
    p = s.profile
    return (p.contrast * (1 + PAS_CONTRASTE * cran(s.contraste)), p.saturation * (1 + PAS_COULEURS * cran(s.couleurs)),
            1 + PAS_LUMIERE * cran(s.lumiere))


# eq (contraste, saturation, gamma) ne connaît que le 8 bits. On le remplace par lutyuv,
# qui accepte le 10 bits, avec les mêmes formules (partie entière du filtre eq pour le
# contraste et la saturation ; table gamma × 256 pour la lumière). Le pic est 1023,
# pas maxval : en gamme TV, maxval vaut 940 et décalerait les moyennes.
_PEAK10 = 1023
# Ces filtres refusent tout format au-dessus de 8 bits, y compris dans FFmpeg 9.1.
_FILTRES_8BITS = frozenset({"fieldmatch", "removegrain", "vidstabdetect", "vidstabtransform"})


def _format_10(info: MediaInfo) -> str:
    """10 bits, en gardant le sous-échantillonnage de la source (4:2:0 par défaut)."""
    fmt = (info.pix_fmt or "").lower()
    if "444" in fmt or "gbr" in fmt or fmt.startswith(("rgb", "bgr")):
        return "yuv444p10le"
    if "422" in fmt:
        return "yuv422p10le"
    return "yuv420p10le"


def _coeffs_eq(contrast: float) -> tuple[int, int]:
    """Mêmes entiers que le chemin rapide d'eq (gamma = 1) : contraste × 4096, décalage."""
    ci = int(contrast * 4096)
    bi = (int(100.0) * 511) // 200 - 128 - ci // 32
    return ci, bi


def _expr_lineaire(contrast: float) -> str:
    """Droite continue calée sur la troncature d'eq (−0,5), en codes 10 bits pleins."""
    ci, bi = _coeffs_eq(contrast)
    return f"val*({ci}/4096)+({bi - 0.5})*({_PEAK10}/255)"


def _expr_gamma(contrast: float, gamma: float) -> str:
    """Courbe d'eq quand le gamma n'est pas 1 : puissance, puis × 256 tronqué.

    (v + abs(v)) / 2 remplace un max(v, 0) : log() refuserait un argument négatif
    et la chaîne ne doit pas contenir de virgule (les tests découpent dessus)."""
    inv = 1.0 / gamma
    v = f"({contrast:.8g}*(val/{_PEAK10}-0.5)+0.5)"
    vpos = f"(({v}+abs({v}))/2+0.000000001)"
    return f"(exp(log({vpos})*{inv:.8g})*256-0.5)/255*{_PEAK10}"


def _filtres_eq(contraste: float, saturation: float, gamma: float) -> list[str]:
    """Remplace eq=contrast:saturation[:gamma]. Liste vide si rien ne change."""
    if abs(contraste - 1) <= 1e-6 and abs(saturation - 1) <= 1e-6 and abs(gamma - 1) <= 1e-6:
        return []
    opts: list[str] = []
    if abs(gamma - 1) > 1e-6:
        opts.append(f"y='{_expr_gamma(contraste, gamma)}'")
    elif abs(contraste - 1) > 1e-6:
        opts.append(f"y='{_expr_lineaire(contraste)}'")
    if abs(saturation - 1) > 1e-6:
        uv = _expr_lineaire(saturation)
        opts.append(f"u='{uv}'")
        opts.append(f"v='{uv}'")
    return ["lutyuv=" + ":".join(opts)]


# colorlevels, colorchannelmixer : calcul RVB. colorlevels en 10 bits est faux sur
# FFmpeg 6.1 et 9.1 (le point noir est multiplié par 65535, pas par 1023) : l'image
# devient noire. En 16 bits le calcul est juste. On groupe donc ces filtres en gbrp16le
# une fois la chaîne en haute précision, puis on revient au YUV 10 bits.
_FILTRES_RVB = ("colorchannelmixer", "colorlevels")


def _monter_precision(filtres: list[str], info: MediaInfo) -> list[str]:
    """10 bits après le dernier filtre bloqué en 8 bits, niveaux en 16 bits vrais."""
    fmt = _format_10(info)
    last = -1
    for i, flt in enumerate(filtres):
        if flt.split("=", 1)[0] in _FILTRES_8BITS:
            last = i
    staged: list[str] = []
    for i, flt in enumerate(filtres):
        if i == last + 1:
            staged.append(f"format={fmt}")
        staged.append(flt)
    if last + 1 == len(filtres):
        staged.append(f"format={fmt}")

    out: list[str] = []
    en_dix = False
    i = 0
    while i < len(staged):
        flt = staged[i]
        nom = flt.split("=", 1)[0]
        if en_dix and nom in _FILTRES_RVB:
            out.append("format=gbrp16le")
            while i < len(staged) and staged[i].split("=", 1)[0] in _FILTRES_RVB:
                out.append(staged[i])
                i += 1
            out.append(f"format={fmt}")
            continue
        if flt == f"format={fmt}":
            en_dix = True
        out.append(flt)
        i += 1
    return out


def _cast_filter(s: Settings) -> str | None:
    """Balance calculée une fois (gains fixes). Absente si les trois canaux sont déjà égaux.
    La teinte de l'utilisateur (−3 froide … +3 chaude) s'y ajoute : 3 % de rouge / bleu par cran."""
    t = cran(s.teinte)
    # Plafond de la dominante d'abord, PUIS la teinte (n°20, B2) : au plafond (1,18), « Plus
    # chaude » n'ajoutait plus rien au film alors que l'aperçu, lui, réchauffait l'image.
    gr, gg, gb = safe_gains((float(s.gain_r), float(s.gain_g), float(s.gain_b)))
    rr, bb = gr * (1 + PAS_TEINTE * t), gb * (1 - PAS_TEINTE * t)
    if all(abs(g - 1.0) < 0.02 for g in (rr, gg, bb)):
        return None
    return f"colorchannelmixer=rr={rr:.4f}:gg={gg:.4f}:bb={bb:.4f}"


def pre_filters(info: MediaInfo, s: Settings, origine: float | None = None) -> list[str]:
    p = s.profile
    f = _base_filters(info, s)
    if s.stabilize:
        f.append(stab_transform_filter(info, s))
    if s.deflicker:
        f.append("deflicker=size=5:mode=pm")   # lisse la luminosité moyenne sur 5 images
    # Plusieurs scènes : une correction par scène (temps de la source). Sinon, la correction unique.
    from . import scenes
    bloc = scenes.filtres(info, s, _origine_effective(info, origine))
    if bloc is None:
        cast = _cast_filter(s)
        if cast:
            f.append(cast)                     # avant les niveaux : le même étirement garde l'équilibre
        lvl = _levels_filter(s)
        if lvl:
            f.append(lvl)                      # une correction pour tout le film, pas image par image
    else:
        f.extend(bloc)
    shift = max(-8, min(8, int(s.chroma_shift or 0)))
    if shift:
        # VHS : la couleur glisse souvent horizontalement. 0 = filtre absent.
        # Compté en pixels de couleur (deux pixels d'image en 4:2:0 et 4:2:2) : la détection
        # automatique et ses essais comptent ainsi (n°20, B3 : limite connue, gardée).
        f.append(f"chromashift=cbh={shift}:crh={shift}")
    if p.despeckle:
        f.append("removegrain=m0=1:m1=1:m2=1")
    if s.denoise_hq:
        sigma, cs, ct = p.denoise_hq
        f.append(f"fftdnoiz=sigma={sigma:g}:prev=1:next=1")
        f.append(f"hqdn3d=0:{cs:g}:0:{ct:g}")
    elif p.denoise:
        f.append("hqdn3d=" + ":".join(f"{v:g}" for v in p.denoise))
    contraste, saturation, gamma = reglages_image(s)
    f.extend(_filtres_eq(contraste, saturation, gamma))
    return _monter_precision(f, info)


def post_filters(info: MediaInfo, s: Settings, from_rgb: bool = False) -> list[str]:
    w, h, sar = target_size(info, s)
    f: list[str] = []
    # Images de l'IA : PNG 8 bits. On remonte en 10 bits avant l'agrandissement.
    if from_rgb:
        f.append("format=gbrp10le")
    if effective_resolution(s) != "source":
        src_m = "" if from_rgb else f":in_color_matrix={_in_matrix(info)}"
        plage = ""
        if info.color_range == "pc":
            plage = ("" if from_rgb else f":in_range={info.color_range}") + ":out_range=tv"
        f.append(f"scale={w}:{h}:flags=lanczos{src_m}:out_color_matrix=bt709{plage}")
        # Le scale ne doit pas négocier le 8 bits avec le format final : on fixe le 10 bits
        # avant la netteté. Depuis le RVB, on garde le 4:4:4 jusqu'à la descente finale.
        f.append("format=yuv444p10le" if from_rgb else f"format={_format_10(info)}")
    elif from_rgb:
        f.append("format=yuv444p10le")
    if s.profile.sharpen and not s.use_ai:
        f.append(f"cas=strength={s.profile.sharpen:g}")
    f += _bottom_mask(info, s)
    f += _edge_mask(info, s)
    f.append(f"setsar={sar.numerator}/{sar.denominator}")
    if effective_resolution(s) == "source" and info.color_range == "pc":
        f.append(f"scale=iw:ih:out_color_matrix={_in_matrix(info)}:out_range=pc")
    # Seule descente en 8 bits. swscale (dither automatique : Bayer en 4:2:0, 6.1 et 9.1)
    # trame pendant cette conversion. Pas de second scale : il coûtait trop cher en Full HD.
    f.append("format=yuv420p")
    return f


def _bottom_mask(info: MediaInfo, s: Settings) -> list[str]:
    """Bande noire en bas, même taille d'image. 0 ligne = filtre absent (comportement d'origine)."""
    n = int(s.mask_bottom or 0)
    if n < 2 or s.source != "video":
        return []
    w, h, _ = target_size(info, s)
    # n est compté en lignes du film d'origine (n°20, B4) : en Full HD, 16 lignes de 576 en font 30
    n = round(n * h / max(1, int(info.height or h)))
    n = min(n // 2 * 2, (h // 4) // 2 * 2)
    if n < 2 or h - n < 2:
        return []
    return [f"crop={w}:{h - n}:0:0", f"pad={w}:{h}:0:0:black"]


def _edge_mask(info: MediaInfo, s: Settings) -> list[str]:
    """Bords noirs, même taille et même format. Vidéo : gauche et droite.
    Pellicule : cadre des quatre côtés. 0 = filtre absent."""
    n = int(s.mask_sides or 0)
    if n < 2:
        return []
    w, h, _ = target_size(info, s)
    if info.width:                       # réglage en pixels du film d'origine : même largeur en Full HD
        n = int(round(n * w / info.width))
    n = min(n // 2 * 2, (min(w, h) // 4) // 2 * 2)
    if n < 2:
        return []
    if s.source == "film":
        cw, ch = w - 2 * n, h - 2 * n
        if cw < 2 or ch < 2:
            return []
        return [f"crop={cw}:{ch}:{n}:{n}", f"pad={w}:{h}:{n}:{n}:black"]
    cw = w - 2 * n
    if cw < 2:
        return []
    return [f"crop={cw}:{h}:{n}:0", f"pad={w}:{h}:{n}:0:black"]


def filter_chain(info: MediaInfo, s: Settings, origine: float | None = None) -> str:
    """`origine` : temps source de la première image (après un `-ss` avant l'entrée)."""
    return ",".join(pre_filters(info, s, origine) + post_filters(info, s))


def encode_args(info: MediaInfo, s: Settings) -> list[str]:
    hd = effective_resolution(s) != "source"
    ntsc = info.standard == "525/30"
    matrice_sd = "smpte170m" if ntsc else "bt470bg"
    def connue(valeur, defaut):
        return defaut if valeur in ("", "unknown", "unspecified", "reserved") else valeur
    # RGB devient YUV420 lors de l’encodage : le tag de matrice RGB ne peut pas être recopié.
    source = "" if info.color_space in ("gbr", "rgb") else info.color_space
    matrice = "bt709" if hd else connue(source, matrice_sd)
    # scale convertit la matrice, sans changer les primaires ni la courbe de transfert.
    primaires = connue(info.color_primaries, "bt709" if hd else matrice_sd)
    transfert = connue(info.color_transfer, "bt709" if hd or not ntsc else "smpte170m")
    color = ["-colorspace", matrice, "-color_primaries", primaires, "-color_trc", transfert]
    if info.color_range in ("pc", "tv"):
        color += ["-color_range", "tv" if hd else info.color_range]
    return ["-c:v", "libx264", "-preset", s.preset, "-crf", str(s.crf), "-pix_fmt", "yuv420p",
            *color, *AAC, "-b:a", "192k", "-movflags", "+faststart"]


def _ff_base(tools: Toolset) -> list[str]:
    return [tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
            "-progress", "pipe:1", "-nostats"]


def _seek(start: float | None, duration: float | None, *, video: bool = True) -> list[str]:
    """`-ss` / `-t` avant une entrée. `video=False` : un second saut (la piste son) ne décale pas l'image."""
    if video:
        gen = _origine_gen.get() + 1
        _origine_gen.set(gen)
        _origine_en_attente.set((gen, float(start or 0.0)))
    a: list[str] = []
    if start:
        a += ["-ss", f"{start:.3f}"]
    if duration:
        a += ["-t", f"{duration:.3f}"]
    return a


def _retenir_origine(info: MediaInfo) -> None:
    """Associe le dernier `-ss` vidéo à CE film. Un autre film ne le récupère pas."""
    attente = _origine_en_attente.get()
    if attente is None:
        return
    gen, valeur = attente
    liee = _origine_liee.get()
    if liee and liee[1] == gen and liee[0] != id(info):
        return
    _origine_liee.set((id(info), gen, valeur))


def dvd_input(info: MediaInfo) -> list[str]:
    """`-i` du film. Retient le `-ss` vidéo qui précède, pour la correction par scène."""
    _retenir_origine(info)
    return _entree_dvd(info)


def _origine_effective(info: MediaInfo, imposee: float | None) -> float:
    """Temps source de la première image que le filtre va voir. 0 si le film part du début."""
    if imposee is not None:
        return max(0.0, float(imposee))
    liee = _origine_liee.get()
    if liee and liee[0] == id(info):
        return max(0.0, float(liee[2]))
    return 0.0


class _FFProgress:
    """Convertit les lignes 'out_time_us=' de -progress en fraction."""

    def __init__(self, total: float, cb: Progress | None, lo: float, hi: float, label: str):
        self.inconnue = not total or total <= 0.01
        self.total, self.cb, self.lo, self.hi, self.label = max(total, 0.001), cb, lo, hi, label

    def __call__(self, line: str) -> None:
        if self.cb and line.startswith("out_time_us="):
            try:
                t = int(line.split("=", 1)[1]) / 1e6
            except ValueError:
                return
            if self.inconnue:
                # Durée inconnue (n°20, E5) : la barre avance sans jamais toucher la fin
                # (moitié à 5 minutes de film), au lieu de 100 % dès la première image.
                part = max(0.0, t) / (max(0.0, t) + 300.0)
            else:
                part = min(1.0, max(0.0, t / self.total))
            self.cb(self.lo + (self.hi - self.lo) * part, self.label)


def source_inputs(info: MediaInfo, s: Settings, tools: Toolset, start: float | None,
                  duration: float | None) -> tuple[list[str], list[str] | None, str, str]:
    """Entrées FFmpeg : (arguments, commande vspipe éventuelle, map vidéo, map audio).

    Avec QTGMC, la vidéo arrive désentrelacée par un tube (y4m) et le son est lu
    dans la source ; -itsoffset recale la vidéo sur le son (début vidéo décalé,
    première image de l'extrait arrondie)."""
    if uses_qtgmc(info, s) and len(info.parts) > 1:
        raise ToolError("QTGMC ne lit pas un DVD découpé en plusieurs VOB. "
                        "Choisissez le désentrelaceur bwdif : il traite le film réuni.")
    if not uses_qtgmc(info, s):
        return _seek(start, duration) + dvd_input(info), None, "0:v:0", "0:a:0?"
    if not tools.qtgmc_available:
        raise ToolError("QTGMC n'est pas disponible : " + (tools.vspipe.problem or
                        "VapourSynth (vspipe) introuvable. Relancez installer.bat -AvecQTGMC "
                        "ou choisissez le désentrelaceur bwdif."))
    first = round((start or 0) * info.fps)
    count = round(duration * info.fps) if duration else 0
    offset = info.video_offset + float(first / info.fps) - (start or 0)
    vs = [tools.vspipe.path, "-c", "y4m", "-a", f"src={info.path}",
          "-a", f"tff={1 if effective_scan(info, s) == 'tff' else 0}",
          "-a", f"first={first}", "-a", f"count={count}", str(QTGMC_SCRIPT), "-"]
    saut = _seek(start, duration)
    _retenir_origine(info)
    args = (["-itsoffset", f"{offset:.6f}", "-f", "yuv4mpegpipe", "-i", "-"]
            + saut + ["-i", str(info.path)])
    return args, vs, "0:v:0", "1:a:0?"


# ---------------------------------------------------------------- dossier de sortie
def is_writable(folder: Path) -> bool:
    """Vrai test d'écriture (os.access ne voit pas un DVD ou une clé protégée sous Windows)."""
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".vhsrestore_test_"):
            return True
    except OSError:
        return False


def _dossier_videos_windows() -> Path | None:
    """Vrai dossier « Vidéos » de Windows : il peut avoir été déplacé, par OneDrive notamment."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        import uuid
        guid = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID("18989B1D-99B5-455B-841C-AB7C74E4DDFC").bytes_le)
        chemin = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(chemin)):
            return None
        try:
            return Path(chemin.value) if chemin.value else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(chemin)
    except Exception:            # API absente ou refusée : chemin habituel
        return None


def fallback_dir() -> Path:
    """« Vidéos\\Films restaurés » de l'utilisateur (VHSRA_SORTIE pour les tests)."""
    if os.environ.get("VHSRA_SORTIE"):
        return Path(os.environ["VHSRA_SORTIE"])
    videos = _dossier_videos_windows()
    if videos is not None and videos.is_dir():
        return videos / BATCH_DIR
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    videos = home / "Videos"            # nom réel du dossier « Vidéos » de Windows
    return (videos if videos.is_dir() else home) / BATCH_DIR


def output_dir_for(folder: Path) -> tuple[Path, bool]:
    """Dossier où enregistrer : celui du film, sinon (DVD, clé protégée…) le dossier
    de secours. Renvoie (dossier, True si c'est le dossier de secours)."""
    folder = Path(folder)
    if folder.is_dir() and is_writable(folder):
        return folder, False
    fb = fallback_dir()
    try:
        fb.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ToolError(f"Impossible de créer le dossier de sortie {fb} : {exc}") from exc
    return fb, True


# ---------------------------------------------------------------- espace disque
GB = 1e9


def disk_needs(info: MediaInfo, s: Settings, start: float | None = None,
               duration: float | None = None) -> tuple[float, float]:
    """Estimation prudente (octets) : (fichier final, fichiers temporaires).
    Débits H.264 CRF 18 constatés : SD ~5 Mbit/s, Full HD ~12, 4K ~35 (marge x1,5)."""
    dur = (duration or max(0.0, info.duration - (start or 0.0))) * time_ratio(info, s)
    w, h, _ = target_size(info, s)
    rate = 5e6 if h <= 576 else 12e6 if h <= 1080 else 35e6
    final = dur * rate / 8 * 1.5
    temp = 0.0
    if s.dust or _tape_job(s):   # ProRes 422 : ~2,4 bits par pixel et par image
        temp += info.width * info.height * float(info.fps) * dur * 2.4 / 8
        if _tape_job(s) and effective_scan(info, s) in ("tff", "bff"):
            # désentrelacement ffv1 avant Analog Repair (vidéo : une image par trame)
            frames = 2 if s.source == "video" else 1
            temp += info.width * info.height * float(info.fps) * frames * dur
    if s.use_ai:
        images = int(dur * output_fps(info, s)) + 1
        pixels = info.width * info.height
        temp += images * pixels * 1.5 * 0.7
        temp += min(images, AI_CHUNK_FRAMES) * pixels * 3 * (1 + RealEsrganUpscaler.scale ** 2)
    if s.restore_audio and s.profile.deepfilter and info.has_audio:
        temp += dur * 48000 * 2 * 2 * 2   # WAV source + WAV nettoyé
    return final, temp


def check_disk_space(info: MediaInfo, s: Settings, out_dir: Path, start: float | None = None,
                     duration: float | None = None, extra_temp: float = 0.0) -> None:
    """Refuse de commencer s'il ne reste pas assez de place (le mode IA a son propre contrôle).

    extra_temp : octets en plus dans le dossier temporaire (les morceaux d'une coupe au milieu,
    présents en même temps que le fichier final).
    """
    final, temp = disk_needs(info, s, start, duration)
    temp += max(0.0, extra_temp)
    roots = {}
    for path, need in ((Path(out_dir), final), (Path(_work_root()), temp)):
        if need <= 0:
            continue
        try:
            dev = os.stat(path).st_dev
        except OSError:
            continue
        free = shutil.disk_usage(path).free
        prev = roots.get(dev, (path, 0.0, free))
        roots[dev] = (prev[0], prev[1] + need, min(prev[2], free))
    for path, need, free in roots.values():
        if free < need * 1.1:
            raise ToolError(f"Espace disque insuffisant dans {path} : il faut environ "
                            f"{need / GB:.1f} Go, il en reste {free / GB:.1f} Go. Libérez de la place "
                            "ou choisissez un autre dossier de sortie (disque externe, par exemple).")


def systeme_de_fichiers(path: Path) -> str:
    """« NTFS », « FAT32 », « exFAT »… du disque qui contient `path` (Windows seulement, sinon "")."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        racine = os.path.splitdrive(str(Path(path).resolve()))[0] + "\\"
        nom = ctypes.create_unicode_buffer(64)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(ctypes.c_wchar_p(racine), None, 0, None, None,
                                                          None, nom, len(nom))
        return nom.value if ok else ""
    except Exception:            # lecteur réseau, ctypes indisponible : on ne bloque pas
        return ""


def check_fat32(info: MediaInfo, s: Settings, out_dir: Path, start: float | None = None,
                duration: float | None = None) -> None:
    """Clé USB ou carte SD en FAT32 : un fichier ne peut pas y dépasser 4 Go. On le dit avant
    des heures de travail (taille estimée sans la marge de prudence)."""
    final, _ = disk_needs(info, s, start, duration)
    if final / 1.5 > 3.6 * GB and systeme_de_fichiers(out_dir).upper().startswith("FAT"):
        raise ToolError(f"Le dossier de sortie est sur une clé USB ou une carte au format FAT32, qui n'accepte "
                        f"pas de fichier de plus de 4 Go ; le film restauré devrait faire environ "
                        f"{final / 1.5 / GB:.1f} Go".replace(".", ",") + ". Choisissez un dossier sur l'ordinateur (par exemple "
                        "« Vidéos ») avec « Dossier de sortie », puis recommencez.")


def output_base(info: MediaInfo, s: Settings) -> str:
    res = effective_resolution(s)
    tag = ({"video": "", "film": "_film", "transfer": "_transfert"}.get(s.source, "")
           + {"source": "", "1080": "_1080p", "2160": "_4k"}[res]
           + ("_stab" if s.stabilize else "") + ("_hq" if s.denoise_hq else "")
           + ("_poussieres" if s.dust else "")
           + ("_bande" if s.tape_noise else "")
           + ("_couleur" if s.chroma_repair else "")
           + ("_decrochages" if s.dropouts else "")
           + ("_ia" if s.use_ai else ""))
    return f"{(info.output_stem or info.path.stem)}_restaure_{s.profile.key}{tag}"


def trim_window(info: MediaInfo, begin: float, end: float) -> tuple[float | None, float | None]:
    """Début et fin choisis (secondes ; fin à 0 = jusqu'au bout) -> (start, duration) pour
    export(). (None, None) si on garde tout le film."""
    begin, end = max(0.0, float(begin or 0)), float(end or 0)
    if end and info.duration:
        end = min(end, info.duration)
    if end and end <= begin + 0.5:
        raise ToolError("La fin doit être après le début (au moins une demi-seconde plus loin).")
    if info.duration and begin >= info.duration - 0.5:
        raise ToolError("Le début choisi est après la fin du film.")
    if begin <= 0 and not end:
        return None, None
    if not info.duration and not end:
        return begin or None, None
    length = (end or info.duration) - begin
    return (begin or None), length


_MIN_PASSAGE = 0.5   # en dessous, une coupe est ignorée et un morceau gardé est abandonné


def passages_gardes(duree: float, debut: float, fin: float,
                    coupes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Fenêtre extérieure (debut, fin ; fin 0 = jusqu'au bout) moins les passages à enlever.

    Retourne les intervalles [début, fin] absolus à garder, dans l'ordre.
    Mêmes contrôles que trim_window pour la fenêtre. Une coupe plus courte que
    0,5 s est ignorée ; les coupes qui se recouvrent ou se touchent sont fusionnées.
    Un morceau gardé plus court que 0,5 s est abandonné. Sans coupe : un seul
    intervalle, celui que trim_window garderait (0 et 0 → tout le film).
    """
    info = MediaInfo(path=Path("."), duration=float(duree or 0))
    debut_lu, longueur = trim_window(info, debut, fin)
    if debut_lu is None and longueur is None:
        w0, w1 = 0.0, float(info.duration)
    else:
        w0 = float(debut_lu or 0.0)
        w1 = w0 + float(longueur or 0.0)
    if not coupes:
        return [(w0, w1)]

    bornes: list[tuple[float, float]] = []
    for brut_a, brut_b in coupes:
        a, b = float(brut_a), float(brut_b)
        if b < a:
            a, b = b, a
        a, b = max(a, w0), min(b, w1)
        if b - a < _MIN_PASSAGE:
            continue
        bornes.append((a, b))
    bornes.sort()
    fusionnees: list[list[float]] = []
    for a, b in bornes:
        if fusionnees and a <= fusionnees[-1][1]:
            fusionnees[-1][1] = max(fusionnees[-1][1], b)
        else:
            fusionnees.append([a, b])

    gardes: list[tuple[float, float]] = []
    curseur = w0
    for a, b in fusionnees:
        if a - curseur >= _MIN_PASSAGE:
            gardes.append((curseur, a))
        curseur = b
    if w1 - curseur >= _MIN_PASSAGE:
        gardes.append((curseur, w1))
    if not gardes:
        raise ToolError("Il ne resterait plus rien du film. Laissez au moins un passage.")
    return gardes


def bornes_a_exporter(duree: float, debut: float, fin: float,
                      coupes: list[tuple[float, float]]
                      ) -> tuple[list[tuple[float, float]], float | None, float | None]:
    """Intervalles gardés, puis (début, durée) quand il n'en reste qu'un.

    Deux intervalles ou plus : une coupe au milieu. (début, durée) vaut (None, None) ;
    l'appelant passe la liste à export(..., passages=). Un seul intervalle plus court
    que le film (coupe collée au début ou à la fin) : (début, durée) comme trim_window,
    sinon le film entier partirait alors que l'écran annonce un temps plus court.
    """
    if not duree and not fin and not coupes:
        return [], max(0.0, debut) or None, None
    gardes = passages_gardes(duree, debut, fin, coupes)
    if len(gardes) >= 2:
        return gardes, None, None
    a, b = gardes[0]
    if a <= 0 and (not duree or b >= float(duree) - 1e-3):
        return gardes, None, None
    return gardes, (a if a > 0 else None), (b - a)


def filtres_passages(chaine: str, plages: list[tuple[float, float]], *, audio: bool) -> str:
    """Enveloppe une chaîne -vf ou -af : ne garde que des plages relatives au temps 0
    (après -ss), puis les enchaîne. À n'appeler que si len(plages) >= 2.

    La chaîne existante est appliquée une seule fois, avant le split : les filtres
    lourds ne tournent pas une fois par passage. Le concat final n'a pas d'étiquette
    de sortie (c'est la sortie du graphe). Temps au millième de seconde.
    """
    n = len(plages)
    if audio:
        decoupe, coupe, recale = "asplit", "atrim", "asetpts"
        concat = f"concat=n={n}:v=0:a=1"
    else:
        decoupe, coupe, recale = "split", "trim", "setpts"
        concat = f"concat=n={n}:v=1:a=0"
    branches = "".join(f"[p{i}]" for i in range(n))
    tete = f"{chaine},{decoupe}={n}{branches}" if chaine else f"{decoupe}={n}{branches}"
    parties = [tete]
    sorties: list[str] = []
    for i, (a, b) in enumerate(plages):
        parties.append(
            f"[p{i}]{coupe}=start={a:.3f}:end={b:.3f},{recale}=PTS-STARTPTS[o{i}]")
        sorties.append(f"[o{i}]")
    parties.append("".join(sorties) + concat)
    return ";".join(parties)


def unique_output_path(info: MediaInfo, s: Settings, out_dir: Path) -> Path:
    base = output_base(info, s)
    cand = out_dir / f"{base}.mp4"
    n = 2
    while cand.exists() or cand.resolve() == info.path.resolve():
        cand = out_dir / f"{base} ({n}).mp4"
        n += 1
    return cand


def _duree_gardee(info: MediaInfo, start: float | None, duration: float | None,
                  passages: list[tuple[float, float]] | None) -> float:
    if passages is not None and len(passages) >= 2:
        return sum(max(0.0, float(b) - float(a)) for a, b in passages)
    if duration is not None:
        return max(0.0, float(duration))
    if info.duration:
        return max(0.0, float(info.duration) - float(start or 0.0))
    return 0.0


def _tenter_reprise(info: MediaInfo, s: Settings, out_path: Path, tools: Toolset, *,
                    cancel: threading.Event | None, progress: Progress | None,
                    start: float | None, duration: float | None,
                    passages: list[tuple[float, float]] | None) -> Path | None:
    """Parties de 10 minutes, ou None pour le chemin d'aujourd'hui."""
    duree = _duree_gardee(info, start, duration, passages)
    if not reprise.possible(s, duree, cadence=retime(info, s) is not None, bande=_tape_job(s)):
        return None
    gardes = reprise.intervalles(info, start, duration, passages)
    if len(reprise.decouper(gardes)) < 2:
        return None
    return _export_parties(info, s, out_path, tools, cancel, progress, gardes)


@lecture_dvd
def export(info: MediaInfo, s: Settings, out_path: Path, tools: Toolset, *,
           cancel: threading.Event | None = None, progress: Progress | None = None,
           start: float | None = None, duration: float | None = None,
           passages: list[tuple[float, float]] | None = None) -> Path:
    cible = Path(out_path).resolve()
    if cible == info.path.resolve():
        raise ToolError("Le fichier de sortie ne peut pas remplacer le fichier original.")
    def annexes(p):
        return [p.with_suffix("." + s.audio_copy)] if info.has_audio and s.audio_copy in ("wav", "flac") else []
    with reserver_sorties(cible, annexes) as libre:
        return _export(info, s, libre, tools, cancel=cancel, progress=progress, start=start, duration=duration, passages=passages)


def _export(info: MediaInfo, s: Settings, out_path: Path, tools: Toolset, *,
           cancel: threading.Event | None = None, progress: Progress | None = None,
           start: float | None = None, duration: float | None = None,
           morceau: bool = False,
           passages: list[tuple[float, float]] | None = None,
           chauffe: float = 0.0, _partie: bool = False) -> Path:
    """Restaure et encode vers out_path. Le fichier n'apparaît qu'une fois complet.

    passages : deux intervalles [début, fin] ou plus, en secondes absolues, à garder.
    Chaque morceau gardé est restauré seul (les trous ne sont pas traités), puis les
    morceaux sont assemblés sans recompression. Moins de deux intervalles (ou None) :
    ignoré, le début et la fin seuls restent comme avant.

    chauffe : secondes de source lues avant `start`, traitées puis retirées
    (image et son). Le temps des scènes reste celui de la source. `_partie` empêche
    une partie déjà découpée de se redécouper.
    """
    tools.require_ffmpeg()
    verifier_chemin(Path(info.path), origine=True)
    if passages is not None and len(passages) >= 2:
        if s.use_ai or s.dust or _tape_job(s) or retime(info, s):
            raise ToolError(
                "Enlever un passage au milieu ne va pas avec cette option. "
                "Décochez l'amélioration IA, les poussières, la réparation de bande ou la cadence "
                "de tournage (re-cadencement de la pellicule), ou bien n'enlevez que le début et la fin.")
        # taille estimée de ce qui est gardé, pas du film entier
        check_fat32(info, s, Path(out_path).parent, None, sum(max(0.0, b - a) for a, b in passages))
        if not _partie and not morceau:
            repris = _tenter_reprise(info, s, out_path, tools, cancel=cancel, progress=progress,
                                     start=start, duration=duration, passages=passages)
            if repris is not None:
                return repris
            reprise.retirer_source(info)
        return _export_morceaux(info, s, out_path, tools, cancel, progress, passages)
    check_fat32(info, s, Path(out_path).parent, start, duration)
    if not _partie and not morceau:
        repris = _tenter_reprise(info, s, out_path, tools, cancel=cancel, progress=progress,
                                 start=start, duration=duration, passages=passages)
        if repris is not None:
            return repris
        reprise.retirer_source(info)
    check_disk_space(info, s, Path(out_path).parent, start, duration)
    if s.dust or _tape_job(s):
        return _export_with_dust(info, s, out_path, tools, cancel, progress, start, duration)
    out_path = Path(out_path).resolve()
    if out_path.resolve() == info.path.resolve():
        raise ToolError("Le fichier de sortie ne peut pas être le fichier original.")
    if not out_path.parent.is_dir():
        raise ToolError(f"Dossier de sortie introuvable : {out_path.parent}")
    if s.stabilize and not tools.stab_available:
        raise ToolError("La stabilisation demande un FFmpeg compilé avec libvidstab "
                        "(filtres vidstabdetect/vidstabtransform), absent de votre FFmpeg.")
    part = partiel_unique(out_path)
    verifier_chemin(part)
    total = (duration or info.duration) * time_ratio(info, s)   # en temps exporté
    # Chauffe : on lit plus tôt dans la SOURCE (le temps des scènes suit ce point),
    # les filtres voient ces images, puis on les retire. Le nombre d'images gardées
    # est celui de la partie, pas celui de la chauffe.
    debut = float(start or 0.0)
    chauffe_reelle = min(float(chauffe or 0.0), debut) if duration and debut > 0 else 0.0
    origine_entree = debut - chauffe_reelle
    fps_sortie = output_fps(info, s)
    images_chauffe = 0
    if chauffe_reelle:
        images_chauffe = int(round(debut * fps_sortie) - round(origine_entree * fps_sortie))
        if images_chauffe < 1:
            chauffe_reelle = 0.0
            origine_entree = debut
            images_chauffe = 0
    seek_start = origine_entree if chauffe_reelle else start
    seek_duree = duration
    # Marge après la partie : les filtres qui regardent la suivante sont lancés,
    # et -t s'arrête parfois une image trop tôt. -frames:v ne garde pas ce surplus.
    marge_images = 8.0 / float(fps_sortie) if duration and (_partie or chauffe_reelle) else 0.0
    if duration is not None and marge_images:
        seek_duree = float(duration) + chauffe_reelle + marge_images
    n_images = 0
    if duration:
        if _partie or chauffe_reelle:
            fin = debut + float(duration)
            n_images = max(1, int(round(fin * fps_sortie) - round(debut * fps_sortie)))
        else:
            n_images = max(1, round(float(duration) * float(fps_sortie)))
    duree_audio_sortie = (n_images / float(fps_sortie)) if n_images and (_partie or chauffe_reelle) else (
        float(duration) if duration else 0.0)
    work: Path | None = None
    df_owned = False
    try:
        if s.restore_audio and s.profile.deepfilter and tools.deepfilter.ok and info.has_audio \
                and not info.audio_silent:
            work = Path(tempfile.mkdtemp(prefix="vhsrestore_son_", dir=_work_root()))
            df_owned = True
        son_debut, son_duree = start, duration
        manque = 0.0
        vide = False
        if morceau and info.has_audio:
            vitesse = _tempo_factor(info, s, drift=True)
            # La chauffe se compte en temps source, puis la vitesse de dérive.
            depart_son = origine_entree if chauffe_reelle else float(start or 0)
            # Même marge que l'image : le son de la chauffe ne doit pas être amputé.
            longueur_son = float(duration) + chauffe_reelle + (marge_images if chauffe_reelle else 0.0)
            premier = (depart_son - s.audio_offset_ms / 1000) * vitesse
            dernier = premier + longueur_son * vitesse
            son_debut = max(0.0, premier)
            son_fin = min(info.duration, dernier) if info.duration else dernier
            son_duree = son_fin - son_debut
            manque = max(0.0, -premier / vitesse)
            if son_duree <= 0:
                vide = True
                son_debut, son_duree = 0, 0.1
        df_wav = _try_deepfilter(info, s, tools, work, son_debut, son_duree, cancel) if work and not vide else None
        present = frozenset(tools.audio_filters)
        if s.use_ai:
            _export_ai(info, s, part, tools, cancel, progress, start, duration, total,
                       df_wav, present)
        else:
            lo = 0.0
            if s.stabilize:
                if work is None:
                    work = Path(tempfile.mkdtemp(prefix="vhsrestore_stab_", dir=_work_root()))
                lo = 0.35
                _stab_detect(info, s, tools, work, seek_start, seek_duree, total, cancel, progress, 0, lo)
            args, vs, vmap, amap = source_inputs(info, s, tools, seek_start, seek_duree)
            if df_wav is not None:
                args = args + ["-i", str(df_wav)]
                amap = f"{sum(a == '-i' for a in args) - 1}:a:0"
            elif morceau and info.has_audio:
                args += _seek(son_debut, son_duree, video=False) + dvd_input(info)
                amap = f"{args.count('-i') - 1}:a:0"
            if vs and progress:
                progress(lo, "QTGMC : préparation (indexation de la vidéo)…")
            # `origine` = temps source de la première image vue, chauffe comprise.
            origine_filtre = origine_entree if chauffe_reelle else (start or 0)
            vf = filter_chain(info, s, origine=origine_filtre)
            if images_chauffe:
                # PTS-STARTPTS d'abord : sinon un temps légèrement négatif (arrondi de
                # setpts) fait jeter une image de plus par trim, et la partie sort à N-1.
                vf += (f",setpts=PTS-STARTPTS,trim=start_frame={images_chauffe}"
                       f",setpts=PTS-STARTPTS")
            chaine_son = audio_filters(info, s, skip_afftdn=df_wav is not None, present=present,
                                       apply_offset=not morceau, rnnoise=tools.rnnoise_model)
            if morceau and info.has_audio:
                if vide:
                    chaine_son.append("volume=0")
                if manque and not vide:
                    chaine_son.append(f"adelay={round(manque * 1000)}:all=1")
                if images_chauffe and not vide:
                    # Le filtre sonore peut commencer un peu avant zéro. On recale,
                    # puis on retire exactement les mêmes secondes que les images.
                    secondes = images_chauffe / float(fps_sortie)
                    chaine_son += ["asetpts=PTS-STARTPTS", f"atrim=start={secondes:.9f}",
                                   "asetpts=PTS-STARTPTS"]
                # apad seul ajoute du silence sans fin et -frames:v ne coupe que l'image :
                # avec FFmpeg 9.1 (Windows) la commande ne se terminait jamais. whole_dur borne
                # le silence, atrim garde la durée exacte du morceau (sans la chauffe).
                chaine_son += [f"apad=whole_dur={duree_audio_sortie:.9f}",
                               f"atrim=duration={duree_audio_sortie:.9f}"]
            sons = ["-af", ",".join(chaine_son)] if chaine_son else []
            # Nombre d'images imposé : FFmpeg 6.1 garde une image de trop par morceau
            # avec -t seul. FFmpeg 7.1, avec -frames:v, n'écrit pas la durée de la
            # dernière image (499 images comptées, 19,960 s). Une cadence constante
            # donne la même durée, image par image, en 6.1 et en 7.1.
            limite = ["-frames:v", str(n_images)] if n_images else []
            if n_images and (_partie or images_chauffe):
                cadence = f"{fps_sortie.numerator}/{fps_sortie.denominator}"
                limite = ["-fps_mode", "cfr", "-r", cadence, *limite]
            cmd = (_ff_base(tools) + args + ["-map", vmap, "-map", amap, "-vf", vf,
                   *encode_args(info, s), *retime_args(info, s), *_cfr_args(info, s),
                   *sons, *limite, "-f", "mp4", str(part)])
            run(cmd, cancel=cancel, what="FFmpeg (restauration)", feeder=vs, cwd=work,
                on_line=_FFProgress(total, progress, lo, 1, "Restauration…"))
        finaliser(part, out_path)
        with copie_annexe(out_path, "La copie du son"):
            _write_audio_copy(out_path, info, s, tools, cancel, progress)
    except BaseException as exc:
        if not isinstance(exc, FichierOccupe):
            effacer(part)
        raise
    finally:
        if work is not None and (df_owned or s.stabilize):
            shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(1.0, "Terminé")
    log.info("Export terminé : %s", out_path)
    return out_path


def _concat_sans_recompression(tools: Toolset, morceaux: list[Path], dest: Path,
                               cancel: threading.Event | None, *,
                               sans_audio: bool = False) -> None:
    """Assemble des films déjà restaurés. -c copy : pas de seconde compression de l'image."""
    liste = dest.with_suffix(".liste.txt")
    lignes = []
    for morceau in morceaux:
        nom = morceau.resolve().as_posix().replace("'", "'\\''")
        lignes.append(f"file '{nom}'")
        # Le premier paquet AAC est un délai d'encodeur à temps négatif. Sans inpoint,
        # l'assemblage le ramène à zéro et retarde l'image d'une trame (21 ms).
        lignes.append("inpoint 0.000000")
        r = run_capture([tools.ffprobe.path, "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=duration", "-of", "csv=p=0", str(morceau)])
        lignes.append(f"duration {float(r.stdout.strip()):.9f}")
    liste.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    cmd = [tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy"]
    if sans_audio:
        cmd.append("-an")
    cmd.append(str(dest))
    try:
        run(cmd, cancel=cancel, what="FFmpeg (assemblage)")
    finally:
        effacer(liste)


def _assembler_parties(tools: Toolset, morceaux: list[Path], dest: Path,
                       cancel: threading.Event | None) -> None:
    """Image copiée, son réencodé une seule fois.

    Chaque partie AAC décode 512 échantillons de plus que sa durée (une demi-trame
    que le conteneur ne saute pas au collage). Ces échantillons s'ajoutent à chaque
    raccord et le son prend du retard. On ne garde que la durée de l'image, puis
    un seul AAC (tools.AAC) pour tout le film.
    """
    sonde = run_capture([tools.ffprobe.path, "-v", "error", "-select_streams", "a:0",
                         "-show_entries", "stream=sample_rate,channels", "-of", "csv=p=0",
                         str(morceaux[0])])
    if sonde.returncode != 0 or not (sonde.stdout or "").strip():
        _concat_sans_recompression(tools, morceaux, dest, cancel)
        return
    cadence, canaux = (int(x) for x in sonde.stdout.strip().split(",")[:2])
    travail = Path(tempfile.mkdtemp(prefix="vhsrestore_assemblage_", dir=_work_root()))
    try:
        video = travail / "image.mp4"
        _concat_sans_recompression(tools, morceaux, video, cancel, sans_audio=True)
        pcm = travail / "son.s16le"
        with pcm.open("wb") as flux:
            for morceau in morceaux:
                if cancel is not None and cancel.is_set():
                    raise Cancelled("Annulé.")
                duree = run_capture([tools.ffprobe.path, "-v", "error", "-select_streams", "v:0",
                                     "-show_entries", "stream=duration", "-of", "csv=p=0", str(morceau)])
                octets = int(round(float(duree.stdout.strip()) * cadence)) * canaux * 2
                brut = travail / "bout.s16le"
                run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
                     "-i", str(morceau), "-vn", "-ac", str(canaux), "-ar", str(cadence),
                     "-f", "s16le", str(brut)],
                    cancel=cancel, what="FFmpeg (son des parties)")
                donnees = brut.read_bytes()
                if len(donnees) < octets:
                    donnees += bytes(octets - len(donnees))
                flux.write(donnees[:octets])
                effacer(brut)
        run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
             "-i", str(video), "-f", "s16le", "-ar", str(cadence), "-ac", str(canaux),
             "-i", str(pcm), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
             *AAC, "-b:a", "192k", "-movflags", "+faststart", str(dest)],
            cancel=cancel, what="FFmpeg (assemblage)")
    finally:
        shutil.rmtree(travail, ignore_errors=True)


def _export_morceaux(info: MediaInfo, s: Settings, out_path: Path, tools: Toolset,
                     cancel: threading.Event | None, progress: Progress | None,
                     passages: list[tuple[float, float]]) -> Path:
    """Restaure chaque passage gardé, sans traiter les trous, puis assemble."""
    out_path = Path(out_path).resolve()
    if out_path.resolve() == info.path.resolve():
        raise ToolError("Le fichier de sortie ne peut pas être le fichier original.")
    if not out_path.parent.is_dir():
        raise ToolError(f"Dossier de sortie introuvable : {out_path.parent}")
    gardes = [(float(a), float(b)) for a, b in passages]
    durees = [max(0.0, b - a) for a, b in gardes]
    somme = sum(durees) or 1.0
    if not s.use_ai:
        final, _ = disk_needs(info, s, None, somme)
        # Les morceaux restaurés sont sur le disque temporaire en même temps que le résultat.
        check_disk_space(info, s, out_path.parent, None, somme, extra_temp=final)
    part = partiel_unique(out_path)
    verifier_chemin(part)                   # chemin trop long pour Windows : dit avant de travailler
    travail = Path(tempfile.mkdtemp(prefix="vhsrestore_morceaux_", dir=_work_root()))
    try:
        faits = 0.0
        fichiers: list[Path] = []
        for i, ((a, b), duree) in enumerate(zip(gardes, durees), start=1):
            if cancel is not None and cancel.is_set():
                raise Cancelled("Annulé.")
            dest = travail / f"morceau-{i}.mp4"

            def sous(f: float, m: str, *, i: int = i, faits: float = faits, duree: float = duree) -> None:
                if progress:
                    progress((faits + max(0.0, min(1.0, f)) * duree) / somme,
                             f"Morceau {i} sur {len(gardes)} — {m}")

            _export(info, dataclasses.replace(s, audio_copy=""), dest, tools, morceau=True,
                    cancel=cancel, progress=sous,
                   start=a or None, duration=duree)
            fichiers.append(dest)
            faits += duree
        if progress:
            progress(0.98, "Assemblage des morceaux…")
        _concat_sans_recompression(tools, fichiers, part, cancel)
        finaliser(part, out_path)           # lecteur vidéo qui garde le fichier : réessai, rien de perdu
        with copie_annexe(out_path, "La copie du son"):
            _write_audio_copy(out_path, info, s, tools, cancel, progress)
    except BaseException as exc:
        if not isinstance(exc, FichierOccupe):
            effacer(part)
        raise
    finally:
        shutil.rmtree(travail, ignore_errors=True)
    if progress:
        progress(1.0, "Terminé")
    log.info("Export terminé : %s", out_path)
    return out_path


def _export_parties(info: MediaInfo, s: Settings, out_path: Path, tools: Toolset,
                    cancel: threading.Event | None, progress: Progress | None,
                    gardes: list[tuple[float, float]]) -> Path:
    """Restaure chaque partie de 10 minutes, reprend celles déjà faites, assemble."""
    out_path = Path(out_path).resolve()
    if out_path.resolve() == info.path.resolve():
        raise ToolError("Le fichier de sortie ne peut pas être le fichier original.")
    if not out_path.parent.is_dir():
        raise ToolError(f"Dossier de sortie introuvable : {out_path.parent}")
    parties = reprise.decouper(gardes)
    if len(parties) < 2:
        raise ToolError("La reprise par parties ne s'applique pas à ce film.")
    somme = sum(max(0.0, b - a) for a, b in parties) or 1.0
    dossier = reprise.preparer(info, s, gardes)
    fps = float(output_fps(info, s))
    attend_son = bool(info.has_audio)
    probe = tools.ffprobe.path or ""
    n = len(parties)
    etats = [reprise.partie_valide(probe, reprise.fichier(dossier, i), reprise.temoin(dossier, i),
                                   b - a, fps, attend_son)
             for i, (a, b) in enumerate(parties, start=1)]
    final, temp = disk_needs(info, s, None, somme)
    manquante = sum((b - a) for ok, (a, b) in zip(etats, parties) if not ok)
    reprise.verifier_place([
        (dossier, final * (manquante / somme)),
        (out_path.parent, final),
        (Path(_work_root()), temp),
    ])
    part = partiel_unique(out_path)
    verifier_chemin(part)
    try:
        deja = sum(etats)
        if deja and progress:
            faite = sum((b - a) for ok, (a, b) in zip(etats, parties) if ok)
            if deja == 1:
                annonce = f"Reprise : 1 partie sur {n} déjà faite."
            else:
                annonce = f"Reprise : {deja} parties sur {n} déjà faites."
            progress(faite / somme, annonce)
        faits = 0.0
        fichiers: list[Path] = []
        for i, ((a, b), ok) in enumerate(zip(parties, etats), start=1):
            if cancel is not None and cancel.is_set():
                raise Cancelled("Annulé.")
            dest = reprise.fichier(dossier, i)
            duree = b - a
            if not ok:
                reprise.oublier_partie(dossier, i)
                ch = reprise.chauffe_partie(a, gardes)

                def sous(f: float, m: str, *, i: int = i, faits: float = faits, duree: float = duree) -> None:
                    if progress:
                        progress((faits + max(0.0, min(1.0, f)) * duree) / somme,
                                 f"Partie {i} sur {n} — {m}")

                _export(info, dataclasses.replace(s, audio_copy=""), dest, tools, morceau=True,
                        _partie=True, chauffe=ch, cancel=cancel, progress=sous,
                        start=a if a > 0 else None, duration=duree)
                if not reprise.sonder(probe, dest, duree, fps, attend_son):
                    reprise.oublier_partie(dossier, i)
                    raise ToolError("Une partie restaurée est incomplète. Relancez pour la refaire.")
                reprise.ecrire_temoin(reprise.temoin(dossier, i), duree)
            fichiers.append(dest)
            faits += duree
        if progress:
            progress(0.98, "Assemblage des parties…")
        _assembler_parties(tools, fichiers, part, cancel)
        finaliser(part, out_path)
        reprise.supprimer(dossier)
        with copie_annexe(out_path, "La copie du son"):
            _write_audio_copy(out_path, info, s, tools, cancel, progress)
    except BaseException as exc:
        if not isinstance(exc, FichierOccupe):
            effacer(part)
        raise
    if progress:
        progress(1.0, "Terminé")
    log.info("Export terminé : %s", out_path)
    return out_path


def _write_audio_copy(out_path: Path, info: MediaInfo, s: Settings, tools: Toolset,
                      cancel: threading.Event | None, progress: Progress | None) -> None:
    """WAV ou FLAC du son déjà présent dans le film restauré. L'original n'est pas touché."""
    kind = (s.audio_copy or "").lower()
    if kind not in ("wav", "flac") or not info.has_audio:
        return
    dest = out_path.with_suffix(".wav" if kind == "wav" else ".flac")
    if dest.resolve() == info.path.resolve():
        raise ToolError("La copie du son ne peut pas remplacer le fichier original.")
    part = partiel_unique(dest)
    codec = (["-c:a", "pcm_s16le"] if kind == "wav"
             else ["-c:a", "flac", "-compression_level", "8"])
    if progress:
        progress(0.99, "Copie du son restauré…")
    try:
        # avancement suivi (n°20, E9) : la barre restait à 99 % pendant toute la copie
        suivi = _FFProgress(float(info.duration or 0), progress, 0.99, 1.0, "Copie du son restauré…")
        run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
             "-progress", "pipe:1", "-nostats",
             "-i", str(out_path), "-vn", "-map", "0:a:0", *codec, str(part)],
            cancel=cancel, on_line=suivi, what="FFmpeg (copie du son)")
        if progress:
            progress(1.0, "Copie du son restauré…")
        finaliser(part, dest)
    except BaseException as exc:
        if not isinstance(exc, FichierOccupe):
            effacer(part)
        raise
    log.info("Copie du son : %s", dest)


def _tape_job(s: Settings) -> bool:
    """Réparations Analog Repair utiles sur une cassette, pas sur une pellicule."""
    return s.source != "film" and (s.tape_noise or s.chroma_repair or s.dropouts)


def _to_progressive(info: MediaInfo, s: Settings, tools: Toolset, work: Path,
                   start: float | None, duration: float | None,
                   cancel: threading.Event | None) -> MediaInfo:
    """Images progressives avant Analog Repair, sinon il désentrelace lui-même
    (une image par image) et la chaîne le referait. Vidéo : une image par trame.
    Transfert pellicule : appariement des trames, cadence d'origine."""
    scan = effective_scan(info, s)
    if s.source == "video":
        vf = f"bwdif=mode=send_field:parity={scan}:deint=all,setfield=prog"
        fps = info.fps * 2
    else:
        vf = (f"fieldmatch=order={scan}:combmatch=full,"
              f"bwdif=mode=send_frame:parity={scan}:deint=interlaced,setfield=prog")
        fps = info.fps
    out = work / "desentrelace.mkv"
    run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
         *_seek(start, duration), "-i", str(info.path), "-map", "0:v:0", "-map", "0:a:0?",
         "-vf", vf, "-c:v", "ffv1", "-level", "3", "-g", "1", "-c:a", "flac", str(out)],
        cancel=cancel, what="FFmpeg (désentrelacement)")
    length = duration or max(0.0, info.duration - (start or 0.0))
    return dataclasses.replace(info, path=out, duration=length, video_offset=0.0,
                               scan="progressive", fps=fps, field_order_meta="progressive")


def _export_with_dust(info: MediaInfo, s: Settings, out_path: Path, tools: Toolset,
                      cancel: threading.Event | None, progress: Progress | None,
                      start: float | None, duration: float | None) -> Path:
    """Analog Repair avant le reste de la chaîne : poussières de pellicule, ou
    bruit de bande / couleur / décrochages d'une cassette. Intermédiaire ProRes."""
    from . import dust
    if s.dust and s.source != "film":
        raise ToolError("« Poussières et rayures » est réservé aux pellicules numérisées directement.")
    if not (s.dust or _tape_job(s)):
        raise ToolError("Rien à réparer avec Analog Repair.")
    if len(info.parts) > 1:   # Analog Repair ne lirait que le premier VOB
        raise ToolError("Les réparations Analog Repair (poussières, bande) ne s'appliquent pas "
                        "à un DVD en plusieurs morceaux.")
    if not tools.dust_available:
        raise ToolError("Le module « poussières et rayures » n'est pas installé.")
    if Path(out_path).resolve() == info.path.resolve():
        raise ToolError("Le fichier de sortie ne peut pas être le fichier original.")
    work = Path(tempfile.mkdtemp(prefix="vhsrestore_poussieres_", dir=_work_root()))

    def sub(lo: float, hi: float) -> Progress | None:
        return (lambda f, m: progress(lo + (hi - lo) * f, m)) if progress else None
    try:
        if s.dust:
            inter = dust.clean(info.path, work, str(Path(tools.ffmpeg.path).parent), start, duration,
                               cancel=cancel, progress=sub(0.0, 0.5))
            length = duration or max(0.0, info.duration - (start or 0.0))
            # Même film, mêmes caractéristiques (proportions, cadence, origine) : seul le
            # fichier lu change. Le rapport de pixel d'origine est donc conservé.
            cleaned = dataclasses.replace(info, path=inter, duration=length, video_offset=0.0,
                                          parts=(), concat_list=None)
            return _export(cleaned, dataclasses.replace(s, dust=False, constant_rate=True), out_path, tools,
                          cancel=cancel, progress=sub(0.5, 1.0))
        src, seek_start, seek_len = info, start, duration
        deinterlaced = effective_scan(info, s) in ("tff", "bff")
        if deinterlaced:
            if progress:
                progress(0.02, "Désentrelacement avant réparation de la bande…")
            src = _to_progressive(info, s, tools, work, start, duration, cancel)
            seek_start, seek_len = None, None
        inter = dust.clean(src.path, work, str(Path(tools.ffmpeg.path).parent), seek_start, seek_len,
                           cancel=cancel, progress=sub(0.15, 0.55), signal="tape",
                           dust_strength=dust.TAPE_DROPOUT if s.dropouts else 0,
                           tape_strength=dust.TAPE_NOISE if s.tape_noise else 0,
                           colour_strength=dust.TAPE_COLOUR if s.chroma_repair else 0,
                           label="Réparation de la bande…")
        length = src.duration if deinterlaced else (duration or max(0.0, info.duration - (start or 0.0)))
        cleaned = dataclasses.replace(src, path=inter, duration=length, video_offset=0.0,
                                      parts=(), concat_list=None)
        quiet = dataclasses.replace(s, dust=False, tape_noise=False, chroma_repair=False, dropouts=False,
                                    constant_rate=True,
                                    scan="progressive" if deinterlaced else s.scan)
        return _export(cleaned, quiet, out_path, tools, cancel=cancel, progress=sub(0.55, 1.0))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _work_root() -> str:
    return os.environ.get("VHSRA_TMP") or tempfile.gettempdir()


def _stab_detect(info: MediaInfo, s: Settings, tools: Toolset, work: Path,
                 start: float | None, duration: float | None, total: float,
                 cancel: threading.Event | None, progress: Progress | None,
                 lo: float, hi: float) -> None:
    """Passe 1 : mesure des mouvements de caméra -> work/transforms.trf.
    Elle voit exactement les mêmes images que la passe 2 (mêmes entrées, même
    désentrelacement), condition pour que les corrections tombent sur les bonnes images."""
    args, vs, vmap, _ = source_inputs(info, s, tools, start, duration)
    if progress:
        progress(lo, "Stabilisation : analyse des mouvements…")
    run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
         "-progress", "pipe:1", "-nostats", *args, "-map", vmap,
         "-vf", ",".join(stab_detect_filters(info, s)), "-f", "null", "-"],
        cancel=cancel, what="FFmpeg (analyse de stabilisation)", feeder=vs, cwd=work,
        on_line=_FFProgress(total, progress, lo, hi, "Stabilisation : analyse des mouvements…"))
    if not (work / STAB_FILE).is_file():
        raise ToolError("L'analyse de stabilisation n'a produit aucun résultat.")


@lecture_dvd
def essayer_ia(info, s, tools, duree, demander, cancel, progress, *, apercu=False):
    """Mesure le coût fixe de lancement et le coût par image sur la machine locale.

    apercu : ne demander que si l'attente estimée dépasse 2 minutes.
    La restauration garde le seuil actuel (3 × la durée, ou 2 h).
    """
    if not s.use_ai:
        return s
    from .tools import ff_input
    photo = info.container == "image"
    images = 1 if photo else max(1, math.ceil(duree * time_ratio(info, s) * output_fps(info, s)))
    moteur = RealEsrganUpscaler(tools.realesrgan)
    if progress:
        progress(0, "Mesure de la vitesse de l’amélioration IA…")
    with tempfile.TemporaryDirectory(prefix="vhsrestore_vitesse_", dir=_work_root()) as tmp:
        racine = Path(tmp)
        entree = racine / "images"
        entree.mkdir()
        run([tools.ffmpeg.path, "-nostdin", "-loglevel", "error",
             *(ff_input(info.path) if photo else dvd_input(info)), "-frames:v", "1",
             "-pix_fmt", "rgb24", "image.png"], cwd=entree, cancel=cancel, what="Lecture d’une image")
        temps = []
        for nombre in (1, 2):
            if nombre == 2:
                shutil.copyfile(entree / "image.png", entree / "autre.png")
            debut = time.monotonic()
            moteur.upscale_dir(entree, racine / str(nombre), cancel=cancel)
            temps.append(time.monotonic() - debut)
    par_image = max(0.0, temps[1] - temps[0])
    if par_image <= 0 or par_image > temps[0]:
        par_image = temps[1] / 2
    demarrage = max(0.0, temps[0] - par_image)
    estimation = images * par_image + math.ceil(images / AI_CHUNK_FRAMES) * demarrage
    trop_long = estimation > 120 if apercu else (
        estimation > 7200 or (not photo and (not duree or estimation > 3 * duree)))
    if trop_long:
        choix = demander(estimation, s.resolution == "2160", not photo and not duree)
        if choix == "annuler":
            raise Cancelled()
        if choix == "sans":
            return dataclasses.replace(s, use_ai=False, resolution="1080" if s.resolution == "2160" else s.resolution)
    return s


def _export_ai(info: MediaInfo, s: Settings, part: Path, tools: Toolset,
               cancel: threading.Event | None, progress: Progress | None,
               start: float | None, duration: float | None, total: float,
               df_wav: Path | None = None, present: frozenset[str] | None = None) -> None:
    upscaler = RealEsrganUpscaler(tools.realesrgan)
    fps = output_fps(info, s)
    root = _work_root()
    tmp = Path(tempfile.mkdtemp(prefix="vhsrestore_", dir=root))
    enc: subprocess.Popen | None = None
    try:
        # 1. pré-traitement sans perte (vidéo FFV1 tout-intra + audio FLAC)
        lo = 0.0
        if s.stabilize:
            lo = 0.04
            _stab_detect(info, s, tools, tmp, start, duration, total, cancel, progress, 0, lo)
        inter = tmp / "inter.mkv"
        pre = ",".join(pre_filters(info, s, origine=start or 0)) or "null"
        args, vs, vmap, amap = source_inputs(info, s, tools, start, duration)
        if df_wav is not None:
            args = args + ["-i", str(df_wav)]
            amap = f"{sum(a == '-i' for a in args) - 1}:a:0"
        run(_ff_base(tools) + args + [
            "-map", vmap, "-map", amap, "-vf", pre, *retime_args(info, s),
            *audio_args(info, s, skip_afftdn=df_wav is not None, present=present,
                       rnnoise=tools.rnnoise_model),
            "-c:v", "ffv1", "-level", "3", "-g", "1", "-c:a", "flac", "-f", "matroska", str(inter)],
            cancel=cancel, what="FFmpeg (pré-traitement)", feeder=vs, cwd=tmp,
            on_line=_FFProgress(total, progress, lo, 0.1, "Nettoyage avant IA…"))
        lignes = []
        run([tools.ffprobe.path, "-v", "error", "-count_packets", "-show_entries",
             "stream=codec_type,start_time,nb_read_packets:format=start_time", "-of", "json", str(inter)],
            cancel=cancel, on_line=lignes.append, what="Comptage des images")
        d = json.loads("\n".join(lignes))
        vst = next(x for x in d["streams"] if x["codec_type"] == "video")
        n = int(vst["nb_read_packets"])
        v_off = float(vst.get("start_time", 0) or 0) - float(d["format"].get("start_time", 0) or 0)

        # 2. encodeur final unique, alimenté en PNG par un tube
        enc_log = open(tmp / "encodeur.log", "w", encoding="utf-8", errors="replace")
        enc_cmd = [tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
                   "-itsoffset", f"{v_off:.6f}", "-f", "image2pipe", "-c:v", "png",
                   "-framerate", f"{fps.numerator}/{fps.denominator}", "-i", "-",
                   "-i", str(inter), "-map", "0:v:0", "-map", "1:a:0?",
                   "-vf", ",".join(post_filters(info, s, from_rgb=True)),
                   *encode_args(info, s), "-f", "mp4", str(part)]
        log.info("exec: %s", subprocess.list2cmdline(enc_cmd))
        enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=enc_log, creationflags=_NO_WINDOW)

        # 3. traitement IA par paquets (limite l'espace disque utilisé)
        chunks = math.ceil(n / AI_CHUNK_FRAMES)
        for i in range(chunks):
            done = i * AI_CHUNK_FRAMES
            cnt = min(AI_CHUNK_FRAMES, n - done)
            d_in, d_out = tmp / "in", tmp / "out"
            for dd in (d_in, d_out):
                shutil.rmtree(dd, ignore_errors=True)
                dd.mkdir()
            ss = ["-ss", f"{v_off + (done - 0.5) / float(fps):.6f}"] if done else []
            run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
                 *ss, "-i", str(inter), "-map", "0:v:0", "-frames:v", str(cnt),
                 "-pix_fmt", "rgb24", "-start_number", "0", "%08d.png"],     # motif relatif : un « % »
                cancel=cancel, what="FFmpeg (extraction d'images)", cwd=d_in)   # du dossier ne gêne pas

            def on_count(k: int, done=done) -> None:
                if progress:
                    progress(0.1 + 0.9 * (done + k) / n, f"Amélioration IA : image {done + k}/{n}")

            upscaler.upscale_dir(d_in, d_out, cancel=cancel, on_count=on_count)
            for png in sorted(d_out.glob("*.png")):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                try:
                    enc.stdin.write(png.read_bytes())
                except (BrokenPipeError, OSError) as exc:
                    raise ToolError("L'encodeur s'est arrêté :\n" + _tail(tmp / "encodeur.log")) from exc
        enc.stdin.close()
        while True:
            try:
                enc.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
        enc_log.close()
        if enc.returncode != 0:
            raise ToolError("Échec de l'encodage final :\n" + _tail(tmp / "encodeur.log"))
    finally:
        if enc is not None:
            terminate(enc)
            try:
                enc_log.close()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _tail(p: Path, n: int = 8) -> str:
    try:
        return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


# ---------------------------------------------------------------- dossier entier
VIDEO_EXTS = {".avi", ".mp4", ".mkv", ".mov", ".mpg", ".mpeg", ".m2t", ".mts", ".ts", ".dv",
              ".vob", ".wmv", ".m4v"}
BATCH_DIR = "Films restaurés"


@dataclass
class BatchResult:
    out_dir: Path
    done: list[Path]
    errors: list[tuple[str, str]]
    skipped: list[str] = dataclasses.field(default_factory=list)   # déjà restaurés
    fallback: bool = False             # dossier source non modifiable : sortie de secours


def dossier_recus() -> Path:
    """Reçus « déjà fait » : dans le profil, pas à côté des films (Windows montre les dossiers pointés)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/state")
    d = Path(base) / "VHSRestoreAI" / "recus"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _duree_totale(files: list[Path], tools: Toolset) -> float:
    """Somme des durées des films du dossier (une photo compte une image)."""
    from . import photo
    total = 0.0
    for f in files:
        if photo.is_photo(f):
            total += 1 / 25
            continue
        try:
            info = open_media(f, tools)
        except (ToolError, OSError, ValueError):
            continue
        total += float(info.duration or 0)
    return total


def restore_folder(folder: Path, tools: Toolset, settings_for: Callable[[MediaInfo], Settings], *,
                   cancel: threading.Event | None = None,
                   progress: Progress | None = None,
                   demander=None) -> BatchResult:
    """Restaure toutes les vidéos d'un dossier (sans sous-dossiers) dans
    « Films restaurés ». Un fichier en erreur n'arrête pas les suivants ;
    une annulation arrête tout (les films déjà terminés restent)."""
    folder = Path(folder)
    if folder.is_dir() and not any(p.is_file() and p.suffix.lower() in VIDEO_EXTS for p in folder.iterdir()):
        nested = folder / "VIDEO_TS"
        if nested.is_dir():
            folder = nested
    titles = titles_in(folder) if folder.is_dir() else []
    used = {p.resolve() for parts in titles for p in parts}
    files = [parts[0] for parts in titles]
    if folder.is_dir():
        files += sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS
                        and p.resolve() not in used and not is_menu(p.name)
                        and "_restaure_" not in p.stem and not p.stem.endswith(".partiel"))
    if not titles:
        # dossier ordinaire : le tri ci-dessus suffit, menus exclus seulement s'ils portent ce nom
        files = sorted(files)
    from . import photo   # import tardif : photo.py importe pipeline
    if folder.is_dir():   # photos du même dossier (mode Photo), après les films
        files += sorted(p for p in folder.iterdir() if p.is_file() and photo.is_photo(p)
                        and "_restaure_" not in p.stem and not p.stem.endswith(".partiel"))
    if not files:
        raise ToolError(f"Aucune vidéo ni photo trouvée dans ce dossier :\n{folder}")
    base_dir, fallback = output_dir_for(folder)
    out_dir = base_dir if fallback else folder / BATCH_DIR
    out_dir.mkdir(exist_ok=True)
    res = BatchResult(out_dir, [], [], fallback=fallback)
    n = len(files)
    # Une seule mesure et une seule question pour tout le dossier.
    decision: dict = {"fait": False, "sans": False, "resolution": None}
    duree_totale = _duree_totale(files, tools) if demander is not None else 0.0

    def reglages_pour(info: MediaInfo) -> Settings:
        s = settings_for(info)
        if not s.use_ai or demander is None:
            return s
        if not decision["fait"]:
            choisi = essayer_ia(info, s, tools, duree_totale or info.duration, demander,
                                cancel, progress)
            decision["fait"] = True
            decision["sans"] = not choisi.use_ai
            decision["resolution"] = choisi.resolution
            return choisi
        if decision["sans"]:
            return dataclasses.replace(
                s, use_ai=False,
                resolution=decision["resolution"] or s.resolution)
        return s

    for k, f in enumerate(files):
        if cancel is not None and cancel.is_set():
            raise Cancelled()

        def sub(frac: float, msg: str, k=k, name=f.name, est_photo=photo.is_photo(f)) -> None:
            if progress:
                mot = "Photo" if est_photo else "Film"
                progress((k + frac) / n, f"{mot} {k + 1} sur {n} : {name} — {msg}")
        try:
            sub(0.0, "analyse…")
            image = photo.is_photo(f)
            info = photo.analyze_photo(f, tools) if image else open_media(f, tools)
            s = reglages_pour(info)
            sources = []
            for source in info.parts or (f,):
                stat = source.stat()
                sources.append((str(source.resolve()), stat.st_size, stat.st_mtime_ns))
            identite = json.dumps(
                [str(out_dir.resolve()), sources, dataclasses.asdict(s)],
                sort_keys=True, default=str)
            cle = hashlib.sha256(identite.encode()).hexdigest()
            registre = dossier_recus()
            recu = registre / cle
            principal = None
            try:
                nom = recu.read_text(encoding="utf-8")
                if Path(nom).name == nom:
                    principal = out_dir / nom
            except FileNotFoundError:
                pass

            def sorties(p):
                chemins = [p]
                if image and photo.wants_color(info, s):
                    chemins.append(photo.colorized_path(p))
                elif not image and info.has_audio and s.audio_copy in ("wav", "flac"):
                    chemins.append(p.with_suffix("." + s.audio_copy))
                return chemins

            if principal and all(p.is_file() for p in sorties(principal)):
                res.skipped.append(f.name)
                continue
            arrete = False
            try:
                if principal and principal.is_file():
                    if image:
                        photo.copie_couleur(principal, tools, cancel)
                    else:
                        with copie_annexe(principal, "La copie du son"):
                            _write_audio_copy(principal, info, s, tools, cancel, sub)
                elif image:
                    cible = photo.output_path(info, s, out_dir)
                    principal = photo.restore_photo(info, s, cible, tools, cancel=cancel, progress=sub)
                else:
                    cible = unique_output_path(info, s, out_dir)
                    principal = export(info, s, cible, tools, cancel=cancel, progress=sub)
            except CopieIncomplete as exc:
                principal = exc.principal
                res.errors.append((f.name, str(exc)))
                arrete = exc.interrompue
            registre.mkdir(exist_ok=True)
            temporaire = partiel_unique(recu)
            try:
                temporaire.write_text(principal.name, encoding="utf-8")
                os.replace(temporaire, recu)  # reçu interne, version la plus récente
            finally:
                effacer(temporaire)
            res.done.append(principal)
            if arrete:
                break
        except Cancelled:
            raise
        except subprocess.TimeoutExpired:
            res.errors.append((f.name, "La lecture de ce fichier a pris trop de temps."))
        except (ToolError, OSError, ValueError) as exc:     # un fichier bloqué n'arrête pas les autres
            log.warning("Dossier : %s ignoré : %s", f.name, exc)
            res.errors.append((f.name, (str(exc).splitlines() or [type(exc).__name__])[0]))
    if progress:
        progress(1.0, "Terminé")
    return res


# ---------------------------------------------------------------- aperçu
@dataclass
class PreviewResult:
    start: float
    duration: float
    restored: Path
    compare: Path
    stills: list[Path]
    original: Path | None = None
    restauration_s: float = 0.0      # secondes de la seule restauration de l'extrait


@lecture_dvd
def make_preview(info: MediaInfo, s: Settings, tools: Toolset, workdir: Path, start: float,
                 duration: float = 10.0, *, cancel: threading.Event | None = None,
                 progress: Progress | None = None) -> PreviewResult:
    """Restaure un extrait puis fabrique une vidéo côte à côte (original | restauré)
    et trois images fixes : même instant, même cadrage, même taille d'affichage."""
    if info.duration > 0:
        duration = min(duration, info.duration)
        start = max(0.0, min(start, info.duration - duration))
    workdir.mkdir(parents=True, exist_ok=True)
    for old in workdir.glob("*"):
        if old.is_file():
            effacer(old)          # encore ouvert dans le lecteur (« Écouter ») : il reste, sans gêner
    sp = dataclasses.replace(s, preset="veryfast")
    if start and abs(s.audio_drift_ms_per_min) >= 1:
        # La dérive court depuis le début du FILM, pas de l'extrait : correction au temps t =
        # décalage − dérive × t / 60. L'extrait part donc avec la correction déjà accumulée.
        # Sans cela, l'aperçu de la fin du film n'entendait pas l'export (mesuré : voix avancée
        # de 80 ms dans l'aperçu, retardée de 130 ms dans le film, au même endroit).
        t_sortie = float(start) * time_ratio(info, s)
        sp = dataclasses.replace(sp, audio_offset_ms=s.audio_offset_ms - s.audio_drift_ms_per_min * t_sortie / 60.0)
    restored = workdir / "apercu_restaure.mp4"

    def sub(lo: float, hi: float) -> Progress | None:
        return (lambda f, m: progress(lo + (hi - lo) * f, m)) if progress else None

    t0 = time.monotonic()
    export(info, sp, restored, tools, cancel=cancel, progress=sub(0, 0.8),
           start=start, duration=duration)
    restauration_s = time.monotonic() - t0

    # Moitié « original » : produite par le même chemin que l'export (même saut,
    # même calage sur le son, même cadence), sans aucun filtre de restauration.
    # Aligner les deux moitiés sur leurs horodatages ne suffit pas : sur un MPEG
    # de graveur DVD réel, l'image ne reprend que 0,4 s après le son au point de
    # saut, et la comparaison était décalée d'environ 0,5 s.
    h = 540
    w = _even(h * effective_dar(info, s))
    fps = output_fps(info, s)
    ref_vf = [f"crop={info.width // 2 * 2}:{info.height // 2 * 2}:0:0"]
    r = retime(info, s)
    if r:
        ref_vf.append(f"setpts=N*{r.denominator}/{r.numerator}/TB")
    # Les deux moitiés en couleurs de définition standard (BT.601), dites dans le fichier.
    # Le film restauré en Full HD est codé en BT.709 : collé tel quel à côté de l'original,
    # sa moitié tirait au vert et ses rouges étaient ternes (constaté en « Nettoyage au plus
    # fort », alors que le film lui-même était juste).
    ref_vf += [f"fps={fps.numerator}/{fps.denominator}",
               f"scale={w}:{h}:flags=lanczos:in_color_matrix={_in_matrix(info)}:out_color_matrix=bt601",
               "setsar=1", "format=yuv420p"]
    matrice_restaure = "bt709" if effective_resolution(s) != "source" else _in_matrix(info)
    etiquette_sd = "smpte170m" if info.standard == "525/30" else "bt470bg"
    out_duration = duration * time_ratio(info, s)
    reference = workdir / "apercu_original.mp4"
    run(_ff_base(tools) + _seek(start, duration) + [
        *dvd_input(info), "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(ref_vf),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", *AAC, "-b:a", "160k",
        *retime_args(info, s),
        *audio_args(info, s, restore=False, apply_offset=False, apply_drift=False), "-f", "mp4", str(reference)],
        cancel=cancel, what="FFmpeg (aperçu de l'original)",
        on_line=_FFProgress(out_duration, progress, 0.8, 0.88, "Comparaison…"))
    fc = (f"[0:v]setpts=PTS-STARTPTS[a];[1:v]scale={w}:{h}:flags=lanczos:in_color_matrix={matrice_restaure}"
          ":out_color_matrix=bt601,setsar=1,setpts=PTS-STARTPTS[b];"
          "[a][b]hstack=inputs=2:shortest=1,format=yuv420p[v]")
    compare = workdir / "apercu_comparaison.mp4"
    run(_ff_base(tools) + ["-i", str(reference), "-i", str(restored),
        "-filter_complex", fc, "-map", "[v]", "-map", "1:a:0?", "-c:v", "libx264", "-preset",
        "veryfast", "-crf", "16", "-colorspace", etiquette_sd, "-c:a", "copy", "-movflags", "+faststart",
        str(compare)], cancel=cancel, what="FFmpeg (comparaison)",
        on_line=_FFProgress(out_duration, progress, 0.88, 0.95, "Comparaison…"))
    stills = []
    for k, frac in enumerate((0.2, 0.5, 0.8)):
        still = workdir / f"image_{k + 1}.png"
        run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
             "-ss", f"{out_duration * frac:.3f}", "-i", str(compare), "-frames:v", "1", str(still)],
            cancel=cancel, what="FFmpeg (image fixe)")
        stills.append(still)
    if progress:
        progress(1.0, "Aperçu prêt")
    return PreviewResult(start, duration, restored, compare, stills, reference, restauration_s)
