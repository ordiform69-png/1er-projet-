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
  6. correction modérée contraste / saturation (eq)
  7. [IA facultative : Real-ESRGAN x4 sur images PNG]
  8. mise à l'échelle lanczos vers la taille cible, matrice couleur BT.709 en HD
  9. netteté adaptative (cas), sauf si l'IA est utilisée
 10. rapport de pixel (setsar) pour un affichage 4:3 sans étirement, yuv420p
Une seule compression finale (H.264) : pas de conversions successives destructives
(l'intermédiaire du mode IA est sans perte : FFV1 + FLAC, images PNG).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from .probe import MediaInfo, analyze
from .profiles import Profile
from .tools import (_NO_WINDOW, QTGMC_SCRIPT, Cancelled, ToolError, Toolset, run, run_capture,
                    terminate)
from .dvd import input_args as dvd_input
from .dvd import is_menu, open_media, titles_in
from .upscaler import RealEsrganUpscaler

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
    if abs(factor - 1.0) < 1e-4:
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
    """Chemin dans un graphe -af : les « : » (lecteur Windows) doivent être échappés."""
    return Path(path).as_posix().replace("\\", "/").replace(":", "\\:")


def _has(present: frozenset[str] | None, name: str) -> bool:
    return present is None or name in present


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
            # Q élevé = encoche étroite : le bourdonnement, pas la musique grave
            chain.append(f"bandreject=f={hz}:t=q:w=30")
            chain.append(f"bandreject=f={hz * 2}:t=q:w=30")
        if s.audio_highpass and _has(present, "highpass"):
            # 6 dB/octave : le vent et les grondements, pas les voix (300 Hz ≈ −0,3 dB)
            chain.append("highpass=f=80:poles=1")
        if s.audio_presence and _has(present, "equalizer"):
            # Cloche étroite : +3 dB à 3 kHz, pas plus. Les graves et les aigus extrêmes restent.
            chain.append("equalizer=f=3000:t=q:w=1:g=3")
    if restore and s.restore_audio and not info.audio_silent:
        p = s.profile
        if p.adeclick and _has(present, "adeclick"):
            chain.append("adeclick")
        # RNNoise (Xiph, modèle livré) seulement si la case est cochée, et seulement
        # à la place d'afftdn en Équilibré et Maximum. Mélangé au signal d'origine.
        # DeepFilterNet, s'il a tourné, a déjà traité le souffle. Défaut : afftdn.
        speech = bool(s.use_rnnoise and p.afftdn_nr and p.afftdn_nr >= 8)
        if (speech and rnnoise and not skip_afftdn and _has(present, "arnndn")):
            mix = 0.55 if p.afftdn_nr >= 12 else 0.35
            chain.append(f"arnndn=m={_ff_filter_path(rnnoise)}:mix={mix}")
        elif p.afftdn_nr and not skip_afftdn and _has(present, "afftdn"):
            chain.append(f"afftdn=nr={p.afftdn_nr:g}:nf=-50:tn=1")
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
    return "bt709" if info.color_space == "bt709" else "bt601"


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
    """Étirement fixe des noirs et des blancs. Absent si les niveaux sont déjà ouverts."""
    lo, hi = safe_levels(float(s.level_black), float(s.level_white))
    if not (0.02 < lo < hi < 0.98 and hi - lo < 0.75):
        return None
    return (f"colorlevels=rimin={lo:.4f}:gimin={lo:.4f}:bimin={lo:.4f}:"
            f"rimax={hi:.4f}:gimax={hi:.4f}:bimax={hi:.4f}")


def _cast_filter(s: Settings) -> str | None:
    """Balance calculée une fois (gains fixes). Absente si les trois canaux sont déjà égaux."""
    gains = (float(s.gain_r), float(s.gain_g), float(s.gain_b))
    if all(abs(g - 1.0) < 0.02 for g in gains):
        return None
    rr, gg, bb = safe_gains(gains)
    return f"colorchannelmixer=rr={rr:.4f}:gg={gg:.4f}:bb={bb:.4f}"


def pre_filters(info: MediaInfo, s: Settings) -> list[str]:
    p = s.profile
    f = _base_filters(info, s)
    if s.stabilize:
        f.append(stab_transform_filter(info, s))
    if s.deflicker:
        f.append("deflicker=size=5:mode=pm")   # lisse la luminosité moyenne sur 5 images
    cast = _cast_filter(s)
    if cast:
        f.append(cast)                         # avant les niveaux : le même étirement garde l'équilibre
    lvl = _levels_filter(s)
    if lvl:
        f.append(lvl)                          # une correction pour tout le film, pas image par image
    shift = max(-8, min(8, int(s.chroma_shift or 0)))
    if shift:
        # VHS : la couleur glisse souvent horizontalement. 0 = filtre absent.
        f.append(f"chromashift=cbh={shift}:crh={shift}")
    if p.despeckle:
        f.append("removegrain=m0=1:m1=1:m2=1")
    if s.denoise_hq:
        sigma, cs, ct = p.denoise_hq
        f.append(f"fftdnoiz=sigma={sigma:g}:prev=1:next=1")
        f.append(f"hqdn3d=0:{cs:g}:0:{ct:g}")
    elif p.denoise:
        f.append("hqdn3d=" + ":".join(f"{v:g}" for v in p.denoise))
    if p.contrast != 1 or p.saturation != 1:
        f.append(f"eq=contrast={p.contrast:g}:saturation={p.saturation:g}")
    return f


def post_filters(info: MediaInfo, s: Settings, from_rgb: bool = False) -> list[str]:
    w, h, sar = target_size(info, s)
    f: list[str] = []
    if effective_resolution(s) != "source":
        src_m = "" if from_rgb else f":in_color_matrix={_in_matrix(info)}"
        f.append(f"scale={w}:{h}:flags=lanczos{src_m}:out_color_matrix=bt709")
    if s.profile.sharpen and not s.use_ai:
        f.append(f"cas=strength={s.profile.sharpen:g}")
    f += _bottom_mask(info, s)
    f += _edge_mask(info, s)
    f.append(f"setsar={sar.numerator}/{sar.denominator}")
    f.append("format=yuv420p")
    return f


def _bottom_mask(info: MediaInfo, s: Settings) -> list[str]:
    """Bande noire en bas, même taille d'image. 0 ligne = filtre absent (comportement d'origine)."""
    n = int(s.mask_bottom or 0)
    if n < 2 or s.source != "video":
        return []
    w, h, _ = target_size(info, s)
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


def filter_chain(info: MediaInfo, s: Settings) -> str:
    return ",".join(pre_filters(info, s) + post_filters(info, s))


def encode_args(info: MediaInfo, s: Settings) -> list[str]:
    if effective_resolution(s) != "source":
        color = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
    elif info.standard == "525/30":
        color = ["-colorspace", "smpte170m", "-color_primaries", "smpte170m", "-color_trc", "smpte170m"]
    else:
        color = ["-colorspace", "bt470bg", "-color_primaries", "bt470bg", "-color_trc", "bt709"]
    return ["-c:v", "libx264", "-preset", s.preset, "-crf", str(s.crf), "-pix_fmt", "yuv420p",
            *color, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]


def _ff_base(tools: Toolset) -> list[str]:
    return [tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning",
            "-progress", "pipe:1", "-nostats"]


def _seek(start: float | None, duration: float | None) -> list[str]:
    a: list[str] = []
    if start:
        a += ["-ss", f"{start:.3f}"]
    if duration:
        a += ["-t", f"{duration:.3f}"]
    return a


class _FFProgress:
    """Convertit les lignes 'out_time_us=' de -progress en fraction."""

    def __init__(self, total: float, cb: Progress | None, lo: float, hi: float, label: str):
        self.total, self.cb, self.lo, self.hi, self.label = max(total, 0.001), cb, lo, hi, label

    def __call__(self, line: str) -> None:
        if self.cb and line.startswith("out_time_us="):
            try:
                t = int(line.split("=", 1)[1]) / 1e6
            except ValueError:
                return
            self.cb(self.lo + (self.hi - self.lo) * min(1.0, max(0.0, t / self.total)), self.label)


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
    args = (["-itsoffset", f"{offset:.6f}", "-f", "yuv4mpegpipe", "-i", "-"]
            + _seek(start, duration) + ["-i", str(info.path)])
    return args, vs, "0:v:0", "1:a:0?"


# ---------------------------------------------------------------- dossier de sortie
def is_writable(folder: Path) -> bool:
    """Vrai test d'écriture (os.access ne voit pas un DVD ou une clé protégée sous Windows)."""
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".vhsrestore_test_"):
            return True
    except OSError:
        return False


def fallback_dir() -> Path:
    """« Vidéos\\Films restaurés » de l'utilisateur (VHSRA_SORTIE pour les tests)."""
    if os.environ.get("VHSRA_SORTIE"):
        return Path(os.environ["VHSRA_SORTIE"])
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
    if s.restore_audio and s.profile.deepfilter and info.has_audio:
        temp += dur * 48000 * 2 * 2 * 2   # WAV source + WAV nettoyé
    return final, temp


def check_disk_space(info: MediaInfo, s: Settings, out_dir: Path, start: float | None = None,
                     duration: float | None = None) -> None:
    """Refuse de commencer s'il ne reste pas assez de place (le mode IA a son propre contrôle)."""
    final, temp = disk_needs(info, s, start, duration)
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
        roots[dev] = (prev[0], prev[1] + need, free)
    for path, need, free in roots.values():
        if free < need * 1.1:
            raise ToolError(f"Espace disque insuffisant dans {path} : il faut environ "
                            f"{need / GB:.1f} Go, il en reste {free / GB:.1f} Go. Libérez de la place "
                            "ou choisissez un autre dossier de sortie (disque externe, par exemple).")


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
    length = (end or info.duration) - begin
    return (begin or None), length


def unique_output_path(info: MediaInfo, s: Settings, out_dir: Path) -> Path:
    base = output_base(info, s)
    cand = out_dir / f"{base}.mp4"
    n = 2
    while cand.exists() or cand.resolve() == info.path.resolve():
        cand = out_dir / f"{base} ({n}).mp4"
        n += 1
    return cand


def export(info: MediaInfo, s: Settings, out_path: Path, tools: Toolset, *,
           cancel: threading.Event | None = None, progress: Progress | None = None,
           start: float | None = None, duration: float | None = None) -> Path:
    """Restaure et encode vers out_path. Le fichier n'apparaît qu'une fois complet."""
    tools.require_ffmpeg()
    if not s.use_ai:   # le mode IA fait son propre contrôle, plus fin (images PNG)
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
    part = out_path.with_name(out_path.stem + ".partiel.mp4").resolve()
    total = (duration or info.duration) * time_ratio(info, s)   # en temps exporté
    work: Path | None = None
    df_owned = False
    try:
        if s.restore_audio and s.profile.deepfilter and tools.deepfilter.ok and info.has_audio \
                and not info.audio_silent:
            work = Path(tempfile.mkdtemp(prefix="vhsrestore_son_", dir=_work_root()))
            df_owned = True
        df_wav = _try_deepfilter(info, s, tools, work, start, duration, cancel) if work else None
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
                _stab_detect(info, s, tools, work, start, duration, total, cancel, progress, 0, lo)
            args, vs, vmap, amap = source_inputs(info, s, tools, start, duration)
            if df_wav is not None:
                args = args + ["-i", str(df_wav)]
                amap = f"{sum(a == '-i' for a in args) - 1}:a:0"
            if vs and progress:
                progress(lo, "QTGMC : préparation (indexation de la vidéo)…")
            cmd = (_ff_base(tools) + args + ["-map", vmap, "-map", amap, "-vf", filter_chain(info, s),
                   *encode_args(info, s), *retime_args(info, s), *_cfr_args(info, s),
                   *audio_args(info, s, skip_afftdn=df_wav is not None, present=present,
                              rnnoise=tools.rnnoise_model),
                   "-f", "mp4", str(part)])
            run(cmd, cancel=cancel, what="FFmpeg (restauration)", feeder=vs, cwd=work,
                on_line=_FFProgress(total, progress, lo, 1, "Restauration…"))
        os.replace(part, out_path)
        _write_audio_copy(out_path, info, s, tools, cancel, progress)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    finally:
        if work is not None and (df_owned or s.stabilize):
            shutil.rmtree(work, ignore_errors=True)
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
    part = dest.with_name(dest.stem + ".partiel" + dest.suffix)
    codec = (["-c:a", "pcm_s16le"] if kind == "wav"
             else ["-c:a", "flac", "-compression_level", "8"])
    if progress:
        progress(0.99, "Copie du son restauré…")
    try:
        run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
             "-i", str(out_path), "-vn", "-map", "0:a:0", *codec, str(part)],
            cancel=cancel, what="FFmpeg (copie du son)")
        os.replace(part, dest)
    except BaseException:
        part.unlink(missing_ok=True)
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
            return export(cleaned, dataclasses.replace(s, dust=False, constant_rate=True), out_path, tools,
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
        return export(cleaned, quiet, out_path, tools, cancel=cancel, progress=sub(0.55, 1.0))
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


def _export_ai(info: MediaInfo, s: Settings, part: Path, tools: Toolset,
               cancel: threading.Event | None, progress: Progress | None,
               start: float | None, duration: float | None, total: float,
               df_wav: Path | None = None, present: frozenset[str] | None = None) -> None:
    upscaler = RealEsrganUpscaler(tools.realesrgan)
    fps = output_fps(info, s)
    frames_est = int(total * fps) + 1
    px = info.width * info.height
    need = frames_est * px * 1.5 * 0.7 + AI_CHUNK_FRAMES * px * 3 * (1 + upscaler.scale ** 2)
    root = _work_root()
    free = shutil.disk_usage(root).free
    if free < need * 1.2:
        raise ToolError(f"Espace disque insuffisant dans {root} : environ {need / 1e9:.1f} Go "
                        f"nécessaires, {free / 1e9:.1f} Go libres.")
    tmp = Path(tempfile.mkdtemp(prefix="vhsrestore_", dir=root))
    enc: subprocess.Popen | None = None
    try:
        # 1. pré-traitement sans perte (vidéo FFV1 tout-intra + audio FLAC)
        lo = 0.0
        if s.stabilize:
            lo = 0.04
            _stab_detect(info, s, tools, tmp, start, duration, total, cancel, progress, 0, lo)
        inter = tmp / "inter.mkv"
        pre = ",".join(pre_filters(info, s)) or "null"
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
        meta = run_capture([tools.ffprobe.path, "-v", "error", "-count_packets",
                            "-show_entries", "stream=codec_type,start_time,nb_read_packets:format=start_time",
                            "-of", "json", str(inter)])
        d = json.loads(meta.stdout)
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
                 "-pix_fmt", "rgb24", "-start_number", "0", str(d_in / "%08d.png")],
                cancel=cancel, what="FFmpeg (extraction d'images)")

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


def restore_folder(folder: Path, tools: Toolset, settings_for: Callable[[MediaInfo], Settings], *,
                   cancel: threading.Event | None = None,
                   progress: Progress | None = None) -> BatchResult:
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
    for k, f in enumerate(files):
        if cancel is not None and cancel.is_set():
            raise Cancelled()

        def sub(frac: float, msg: str, k=k, name=f.name) -> None:
            if progress:
                progress((k + frac) / n, f"Film {k + 1}/{n} ({name}) : {msg}")
        try:
            sub(0.0, "analyse…")
            if photo.is_photo(f):
                pinfo = photo.analyze_photo(f, tools)
                ps = settings_for(pinfo)
                if (out_dir / f"{pinfo.path.stem}_restaure_{ps.profile.key}{'_ia' if ps.use_ai else ''}.png").exists():
                    res.skipped.append(f.name)
                    continue
                res.done.append(photo.restore_photo(pinfo, ps, photo.output_path(pinfo, ps, out_dir), tools,
                                                    cancel=cancel, progress=sub))
                continue
            info = open_media(f, tools)
            s = settings_for(info)
            if (out_dir / f"{output_base(info, s)}.mp4").exists():
                # déjà restauré avec les mêmes réglages (relance après une coupure)
                res.skipped.append(f.name)
                continue
            res.done.append(export(info, s, unique_output_path(info, s, out_dir), tools,
                                   cancel=cancel, progress=sub))
        except Cancelled:
            raise
        except ToolError as exc:
            log.warning("Dossier : %s ignoré : %s", f.name, exc)
            res.errors.append((f.name, str(exc).splitlines()[0]))
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
            old.unlink()
    sp = dataclasses.replace(s, preset="veryfast")
    restored = workdir / "apercu_restaure.mp4"

    def sub(lo: float, hi: float) -> Progress | None:
        return (lambda f, m: progress(lo + (hi - lo) * f, m)) if progress else None

    export(info, sp, restored, tools, cancel=cancel, progress=sub(0, 0.8),
           start=start, duration=duration)

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
    ref_vf += [f"fps={fps.numerator}/{fps.denominator}", f"scale={w}:{h}:flags=lanczos", "setsar=1",
               "format=yuv420p"]
    out_duration = duration * time_ratio(info, s)
    reference = workdir / "apercu_original.mp4"
    run(_ff_base(tools) + _seek(start, duration) + [
        *dvd_input(info), "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(ref_vf),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-c:a", "aac", "-b:a", "160k",
        *retime_args(info, s),
        *audio_args(info, s, restore=False, apply_offset=False, apply_drift=False), "-f", "mp4", str(reference)],
        cancel=cancel, what="FFmpeg (aperçu de l'original)",
        on_line=_FFProgress(out_duration, progress, 0.8, 0.88, "Comparaison…"))
    fc = (f"[0:v]setpts=PTS-STARTPTS[a];[1:v]scale={w}:{h}:flags=lanczos,setsar=1,setpts=PTS-STARTPTS[b];"
          "[a][b]hstack=inputs=2:shortest=1,format=yuv420p[v]")
    compare = workdir / "apercu_comparaison.mp4"
    run(_ff_base(tools) + ["-i", str(reference), "-i", str(restored),
        "-filter_complex", fc, "-map", "[v]", "-map", "1:a:0?", "-c:v", "libx264", "-preset",
        "veryfast", "-crf", "16", "-c:a", "copy", "-movflags", "+faststart",
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
    return PreviewResult(start, duration, restored, compare, stills, reference)
