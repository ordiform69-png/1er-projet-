"""Analyse d'un fichier vidéo : FFprobe pour les métadonnées, filtre idet pour
mesurer l'entrelacement sur le contenu réel.

Règle : on n'affirme jamais qu'une vidéo est entrelacée sans preuve. Si ni le
contenu ni les métadonnées ne permettent de conclure, scan = "unknown" et
l'interface demande un choix manuel.

Origine (vidéo / pellicule / pellicule transférée) : seulement une SUGGESTION à
partir d'indices (cadence, champs ou images répétés), toujours modifiable. Le
codec ou le conteneur ne disent rien du support physique d'origine.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from .tools import capture, _NO_WINDOW, ToolError, Toolset, ff_input, run_capture

SD_SIZES = {(720, 576), (704, 576), (720, 480), (704, 480), (720, 486), (352, 288), (352, 240)}
IDET_FRAMES = 600
# Cadences de numérisation image par image typiques d'une pellicule (i/s).
FILM_RATES = (Fraction(12), Fraction(16), Fraction(18), Fraction(20), Fraction(22),
              Fraction(24), Fraction(24000, 1001))
SOURCE_LABELS = {"video": "Vidéo analogique", "film": "Pellicule cinéma",
                 "transfer": "Pellicule transférée sur vidéo"}


@dataclass
class MediaInfo:
    path: Path
    container: str = ""
    duration: float = 0.0
    size_bytes: int = 0
    width: int = 0
    height: int = 0
    codec: str = ""
    pix_fmt: str = ""
    fps: Fraction = Fraction(0)
    sar: Fraction = Fraction(1)
    dar: Fraction = Fraction(4, 3)
    dar_source: str = ""
    field_order_meta: str = "unknown"
    idet: dict[str, int] = field(default_factory=dict)
    scan: str = "unknown"            # progressive | tff | bff | unknown
    scan_source: str = ""
    standard: str = "inconnu"        # "625/25" | "525/30" | inconnu
    standard_reason: str = ""
    has_audio: bool = False
    audio_desc: str = ""
    color_primaries: str = ""
    color_transfer: str = ""
    color_range: str = ""
    color_space: str = ""
    video_offset: float = 0.0        # début vidéo - début du fichier (s)
    repeated_fields: float | None = None   # part de champs répétés (idet)
    repeated_frames: float | None = None   # part d'images quasi identiques à la précédente
    saturation: float | None = None        # saturation moyenne (signalstats, 0 = gris)
    saturation_high: float | None = None   # saturation des pixels les plus colorés (SATHIGH)
    level_low: float | None = None         # médiane de YLOW (percentile bas de la luminance)
    level_high: float | None = None        # médiane de YHIGH (percentile haut)
    cast_rgb: tuple[float, float, float] | None = None   # moyennes R, G, B de l'échantillon
    edge_damage: int = 0                   # bords abîmés (traits colorés, neige) en pixels du film, 0 = aucun
    audio_silent: bool = False             # piste son présente mais vide (silence numérique)
    audio_channels: int = 0
    channel_issue: str = ""                # "" | left_silent | right_silent | phase (audio_check)
    clipped: float = 0.0                   # part d'échantillons saturés
    hum_hz: int = 0                        # ronflement détecté : 0 | 50 | 60
    wind: bool = False                     # graves forts et irréguliers (vent)
    suggested_source: str = "video"        # video | film | transfer
    source_reason: str = ""
    warnings: list[str] = field(default_factory=list)
    parts: tuple[Path, ...] = ()          # DVD : morceaux VOB d'un même titre, dans l'ordre
    output_stem: str = ""                 # nom du film restauré si différent du fichier (VTS_01)
    concat_list: Path | None = None       # liste concat FFmpeg, dossier temporaire
    # Numérisation : ce qui est déjà perdu ne se corrige pas. Mesures seulement.
    video_bitrate: int = 0                 # débit vidéo (bit/s), 0 si inconnu
    bits_per_pixel: float | None = None    # bits par pixel et par image
    low_bitrate: bool = False              # copie avec perte, débit trop bas
    already_deinterlaced: bool = False     # progressive alors qu'une cassette est entrelacée
    already_scaled: bool = False           # hauteur autre que 576 / 480 (486 admis)
    doubled_lines: bool = False            # chaque ligne recopiée sur la suivante
    crushed_blacks: bool = False           # beaucoup de pixels collés au noir
    crushed_whites: bool = False           # beaucoup de pixels collés au blanc
    line_jitter: bool = False              # lignes qui tremblent (pas de correcteur de base de temps)

    @property
    def interlaced(self) -> bool:
        return self.scan in ("tff", "bff")

    @property
    def black_and_white(self) -> bool:
        """Mesuré sur une vraie pellicule couleur décolorée (années 1970) : saturation
        moyenne 8 mais pixels les plus colorés à 15 ; un noir et blanc reste sous 5."""
        return self.saturation_high is not None and self.saturation_high < 8

    @property
    def pale_colors(self) -> bool:
        return self.saturation_high is not None and 8 <= self.saturation_high < 20

    def summary(self) -> dict[str, str]:
        scan_txt = {"progressive": "Progressive", "tff": "Entrelacée, trame haute en premier (TFF)",
                    "bff": "Entrelacée, trame basse en premier (BFF)",
                    "unknown": "Indéterminé — choisissez manuellement"}[self.scan]
        std = {"625/25": "625 lignes / 25 i/s (PAL ou SECAM)",
               "525/30": "525 lignes / 29,97 i/s (NTSC)"}.get(self.standard, "Inconnu")
        m, s = divmod(int(round(self.duration)), 60)
        h, m = divmod(m, 60)
        return {
            "Fichier": (f"{self.output_stem} ({len(self.parts)} morceaux)"
                        if self.output_stem and len(self.parts) > 1 else self.path.name),
            "Durée": f"{h:d}:{m:02d}:{s:02d}",
            "Conteneur / codec": f"{self.container} / {self.codec} ({self.pix_fmt})",
            "Résolution": f"{self.width} × {self.height} (pixels {self.sar.numerator}:{self.sar.denominator})",
            "Images par seconde": f"{float(self.fps):.3f}".rstrip("0").rstrip("."),
            "Format d'affichage": f"{self.dar.numerator}:{self.dar.denominator} ({self.dar_source})",
            "Balayage": f"{scan_txt} [{self.scan_source}]",
            "Norme probable": std,
            "Audio": (self.audio_desc + (" — Aucun son entendu dans les extraits analysés" if self.audio_silent else "")
                      if self.audio_desc else "aucune piste audio (film muet ?)"),
            "Couleur": ("Noir et blanc probable" if self.black_and_white else
                        "Couleurs très pâles (film décoloré ou noir et blanc teinté)" if self.pale_colors else
                        "Couleur" if self.saturation is not None else "Inconnue"),
            "Origine suggérée": f"{SOURCE_LABELS[self.suggested_source]} — {self.source_reason}",
        }


def _frac(text: str | None) -> Fraction | None:
    if not text or text in ("0/0", "N/A", "0:1", "0:0"):
        return None
    try:
        f = Fraction(text.replace(":", "/"))
    except (ValueError, ZeroDivisionError):
        return None
    return f if f > 0 else None


def parse_idet(text: str) -> dict[str, int]:
    """Extrait le dernier bilan 'Multi frame detection' de la sortie de idet."""
    found = re.findall(r"Multi frame detection:\s*TFF:\s*(\d+)\s*BFF:\s*(\d+)\s*"
                       r"Progressive:\s*(\d+)\s*Undetermined:\s*(\d+)", text)
    if not found:
        return {}
    tff, bff, prog, und = map(int, found[-1])
    return {"tff": tff, "bff": bff, "progressive": prog, "undetermined": und}


def decide_scan(idet: dict[str, int], field_order_meta: str) -> tuple[str, str]:
    """Décide le balayage à partir de la mesure idet et des métadonnées.

    La mesure du contenu prime (les drapeaux des captures sont souvent faux),
    mais seulement si elle est nette : un camp doit dépasser l'autre d'un facteur 3
    sur au moins 30 % des images analysées.
    """
    meta = {"tt": "tff", "bt": "tff", "bb": "bff", "tb": "bff",
            "progressive": "progressive"}.get(field_order_meta, "unknown")
    if idet:
        total = sum(idet.values()) or 1
        tff, bff, prog = idet["tff"], idet["bff"], idet["progressive"]
        inter = tff + bff
        decided = inter + prog
        if decided >= 0.3 * total:
            if inter >= 3 * max(prog, 1):
                if tff >= 3 * max(bff, 1):
                    return "tff", "mesuré sur l'image"
                if bff >= 3 * max(tff, 1):
                    return "bff", "mesuré sur l'image"
                if meta in ("tff", "bff"):
                    return meta, "entrelacement mesuré, ordre des trames lu dans les métadonnées"
            elif prog >= 3 * max(inter, 1):
                return "progressive", "mesuré sur l'image"
    if meta != "unknown":
        return meta, "métadonnées uniquement (mesure non concluante)"
    return "unknown", "mesure non concluante et métadonnées absentes"


def repeat_ratio(ydif: list[float]) -> float | None:
    """Part des images dont la variation avec la précédente est inférieure à la moitié
    de la variation médiane : image répétée (seul le bruit change). None si l'image
    est quasi fixe (indice sans valeur)."""
    if len(ydif) < 10:
        return None
    med = sorted(ydif)[len(ydif) // 2]
    if med <= 0.2:
        return None
    return sum(v < 0.5 * med for v in ydif) / len(ydif)


def parse_signals(text: str) -> dict[str, float | None]:
    """Champs répétés (idet), images répétées (YDIF de signalstats), saturation."""
    out: dict[str, float | None] = {"repeated_fields": None, "repeated_frames": None, "saturation": None,
                                    "saturation_high": None}
    rep = re.findall(r"Repeated Fields:\s*Neither:\s*(\d+)\s*Top:\s*(\d+)\s*Bottom:\s*(\d+)", text)
    if rep:
        n, t, b = map(int, rep[-1])
        if n + t + b:
            out["repeated_fields"] = (t + b) / (n + t + b)
    out["repeated_frames"] = repeat_ratio(
        [float(x) for x in re.findall(r"signalstats\.YDIF=([\d.]+)", text)][1:])
    sat = [float(x) for x in re.findall(r"signalstats\.SATAVG=([\d.]+)", text)]
    if sat:
        out["saturation"] = sum(sat) / len(sat)
    high = [float(x) for x in re.findall(r"signalstats\.SATHIGH=([\d.]+)", text)]
    if high:
        out["saturation_high"] = sum(high) / len(high)
    for name, key in (("level_low", "YLOW"), ("level_high", "YHIGH")):
        vals = sorted(float(x) for x in re.findall(rf"signalstats\.{key}=([\d.]+)", text))
        if vals:
            out[name] = vals[len(vals) // 2]          # médiane : une valeur pour tout le film
    return out


def rgb_mean(ffmpeg: str, path: Path, start: float = 0.0) -> tuple[float, float, float] | None:
    """Moyenne R, G, B sur quelques images réduites. Une seule lecture courte."""
    try:
        r = capture([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
                            "-ss", f"{max(0.0, start):.3f}", *ff_input(path),
                            "-map", "0:v:0", "-vf", "scale=32:32,format=rgb24",
                            "-frames:v", "8", "-an", "-f", "rawvideo", "-"],
                           capture_output=True, timeout=60, stdin=subprocess.DEVNULL,
                           creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None
    data = r.stdout
    if r.returncode or len(data) < 32 * 32 * 3:
        return None
    n = len(data) // 3
    return (sum(data[0::3]) / n, sum(data[1::3]) / n, sum(data[2::3]) / n)


EDGE_STRIP = 48          # pixels examinés de chaque côté (bord + intérieur de référence)
EDGE_MAX = 24            # au-delà, ce n'est plus un défaut de bord : rien n'est proposé


def _edge_columns(strip: list[tuple[float, float]], ref: tuple[float, float]) -> int:
    """Largeur abîmée d'un côté, à partir des colonnes (luma, couleur) du bord vers l'intérieur.
    Une colonne est abîmée si sa couleur est anormale (traits colorés, liseré violet) ou si elle
    est claire mais très différente de l'image (neige). Une bande noire régulière ne compte pas."""
    lref, cref = ref
    last = -1
    rampe, prec = True, 0.0     # bande noire au flou analogique : du noir, puis une montée régulière
    for c, (lum, chroma) in enumerate(strip[:EDGE_MAX + 4]):
        noire = lum < 20 and chroma < 6
        couleur = chroma > cref * 1.8 + 8
        # passage doux du noir à l'image (de plus en plus clair, jamais plus clair que l'image) :
        # c'est le bord de la bande noire, pas de la neige
        rampe = rampe and not couleur and (noire or (lum >= prec - 2 and lum <= lref + 10))
        prec = lum
        neige = lum > 20 and abs(lum - lref) > max(25.0, 0.45 * lref) and not rampe
        if (couleur or neige) and not noire:
            last = c
        elif c - last > 3 and last >= 0:        # le défaut s'arrête : on ne cherche pas plus loin
            break
    n = last + 2 if last >= 0 else 0
    n = (n + 1) // 2 * 2
    return 0 if n < 4 or n > EDGE_MAX else n


def edge_damage(ffmpeg: str, path: Path, width: int, start: float = 0.0, frames: int = 6) -> int:
    """Bords gauche et droit abîmés (VHS : traits colorés, liseré, neige), en pixels du film.
    Mesure sur quelques images réparties, colonne par colonne ; 0 si rien de net."""
    if width < 4 * EDGE_STRIP:
        return 0
    w = EDGE_STRIP
    vf = (f"[0:v:0]select='not(mod(n\\,12))',scale={width}:144:flags=area,split[a][b];"
          f"[a]crop={w}:144:0:0[l];[b]crop={w}:144:{width - w}:0,hflip[r];[l][r]hstack,format=rgb24")
    try:
        r = capture([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
                            "-ss", f"{max(0.0, start):.3f}", "-i", str(path),
                            "-filter_complex", vf, "-frames:v", str(frames), "-an", "-f", "rawvideo", "-"],
                           capture_output=True, timeout=120, stdin=subprocess.DEVNULL,
                           creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    data, row = r.stdout, 2 * w * 3
    nimg = len(data) // (row * 144)
    if r.returncode or nimg < 1:
        return 0
    cols = [[0.0, 0.0] for _ in range(2 * w)]            # somme luma, somme couleur par colonne
    for i in range(0, nimg * 144 * row, 3):
        rr, gg, bb = data[i], data[i + 1], data[i + 2]
        c = (i % row) // 3
        cols[c][0] += 0.299 * rr + 0.587 * gg + 0.114 * bb
        cols[c][1] += abs(rr - gg) + abs(bb - gg)
    n = nimg * 144
    res = 0
    for side in (cols[:w], cols[w:]):                     # le côté droit est retourné : bord en 0
        moy = [(a / n, b / n) for a, b in side]
        inner = moy[w - 16:]
        ref = (sum(x for x, _ in inner) / len(inner), sum(y for _, y in inner) / len(inner))
        res = max(res, _edge_columns(moy, ref))
    return res


def cast_gains(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """Gains fixes pour ramener les trois moyennes au même niveau. 1, 1, 1 si c'est déjà le cas."""
    r, g, b = rgb
    if min(r, g, b) < 1:
        return (1.0, 1.0, 1.0)
    mean = (r + g + b) / 3
    return (mean / r, mean / g, mean / b)


def suggest_source(info: MediaInfo) -> tuple[str, str]:
    """Origine probable, avec la raison affichée. Jamais une certitude."""
    film_rate = any(abs(float(info.fps - r)) < 0.02 for r in FILM_RATES)
    rf, rp = info.repeated_fields or 0.0, info.repeated_frames or 0.0
    fps = f"{float(info.fps):.3f}".rstrip("0").rstrip(".")
    if film_rate and not info.interlaced:
        return "film", f"cadence de {fps} i/s, typique d'une pellicule numérisée image par image"
    if info.interlaced and (rf >= 0.05 or rp >= 0.05):
        return "transfer", (f"vidéo entrelacée avec champs ou images répétés ({max(rf, rp):.0%}) : "
                            "pellicule copiée sur vidéo probable")
    if not info.interlaced and rp >= 0.10:
        return "transfer", (f"{rp:.0%} d'images répétées : pellicule recopiée à une cadence vidéo probable")
    if info.interlaced:
        return "video", "vidéo entrelacée sans images répétées : caméscope ou magnétoscope probable"
    return "video", "aucun indice net : traité comme une vidéo, à confirmer"


def guess_standard(height: int, fps: Fraction) -> tuple[str, str]:
    f = float(fps)
    by_fps = "625/25" if abs(f - 25) < 0.1 or abs(f - 50) < 0.1 else \
             "525/30" if abs(f - 29.97) < 0.05 or abs(f - 59.94) < 0.1 or abs(f - 30) < 0.05 else ""
    by_h = "625/25" if height in (576, 288) else "525/30" if height in (480, 486, 240) else ""
    if by_fps and by_h and by_fps == by_h:
        return by_fps, "cadence et nombre de lignes concordants"
    if by_fps and not by_h:
        return by_fps, "d'après la cadence seulement"
    if by_h and not by_fps:
        return by_h, "d'après le nombre de lignes seulement"
    if by_fps and by_h:
        return "inconnu", "cadence et lignes contradictoires"
    return "inconnu", ""


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _audio_timing_notes(info: MediaInfo, audio: dict, video: dict, fmt: dict) -> None:
    """Signale un écart déjà écrit dans le fichier. Ne corrige rien et ne lit pas les lèvres."""
    base = _num(fmt.get("start_time"))
    a_vs_v = (_num(audio.get("start_time")) - base) - info.video_offset
    if abs(a_vs_v) >= 0.04:
        ms = a_vs_v * 1000
        sens = ("le son commence plus tard que l'image : un décalage négatif l'avance"
                if ms > 0 else
                "le son commence plus tôt que l'image : un décalage positif le retarde")
        info.warnings.append(
            f"Métadonnées : écart son/image d'environ {ms:+.0f} ms ({sens}). "
            "À vérifier à l'oreille : ce n'est pas une détection des lèvres.")
    a_dur, v_dur = _num(audio.get("duration")), _num(video.get("duration")) or info.duration
    if a_dur > 1 and v_dur > 1:
        delta = a_dur - v_dur
        if abs(delta) >= 0.15 and abs(delta) / v_dur >= 0.002:
            per_min = delta / v_dur * 60000.0
            info.warnings.append(
                f"La piste son dure {delta:+.2f} s de plus que l'image "
                f"(environ {per_min:+.0f} ms par minute). "
                "Si le décalage s'aggrave, réglez « Dérive du son ». "
                "L'application ne détecte pas les lèvres.")


def analyze(path: str | Path, tools: Toolset, idet_frames: int = IDET_FRAMES) -> MediaInfo:
    tools.require_ffmpeg()
    p = Path(path).resolve()
    if not p.is_file():
        raise ToolError(f"Fichier introuvable : {p}")
    try:
        res = run_capture([tools.ffprobe.path, "-v", "error", "-print_format", "json",
                           "-show_format", "-show_streams", str(p)], timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise ToolError("FFprobe ne répond pas (fichier illisible ?).") from exc
    if res.returncode != 0:
        raise ToolError(f"Fichier non reconnu comme vidéo :\n{res.stderr.strip()[-400:]}")
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    if v is None:
        raise ToolError("Ce fichier ne contient pas de piste vidéo.")
    fmt = data.get("format", {})
    info = MediaInfo(path=p)
    info.container = fmt.get("format_name", "")
    info.size_bytes = int(fmt.get("size", 0) or 0)
    info.duration = float(fmt.get("duration") or v.get("duration") or 0)
    info.width, info.height = int(v.get("width", 0)), int(v.get("height", 0))
    info.codec = v.get("codec_name", "")
    info.pix_fmt = v.get("pix_fmt", "")
    info.color_primaries = v.get("color_primaries", "")
    info.color_transfer = v.get("color_transfer", "")
    info.color_range = v.get("color_range", "")
    info.color_space = v.get("color_space", "")
    info.fps = _frac(v.get("avg_frame_rate")) or _frac(v.get("r_frame_rate")) or Fraction(0)
    info.field_order_meta = v.get("field_order", "unknown")
    try:
        info.video_offset = max(0.0, float(v.get("start_time", 0)) - float(fmt.get("start_time", 0)))
    except (TypeError, ValueError):
        info.video_offset = 0.0
    if not info.width or not info.height or not info.fps:
        raise ToolError("Caractéristiques vidéo illisibles (taille ou cadence inconnue).")
    if info.duration <= 0:
        info.warnings.append("Durée inconnue : la progression sera approximative.")

    # --- format d'affichage et pixels non carrés
    sar = _frac(v.get("sample_aspect_ratio"))
    dar = _frac(v.get("display_aspect_ratio"))
    size_ratio = Fraction(info.width, info.height)
    if sar and sar != 1:
        info.sar, info.dar, info.dar_source = sar, dar or size_ratio * sar, "métadonnées"
    elif (info.width, info.height) in SD_SIZES:
        info.dar = Fraction(4, 3)
        info.sar = info.dar / size_ratio
        info.dar_source = "supposé : taille SD sans information de pixel, à vérifier"
        info.warnings.append("Format d'affichage non indiqué dans le fichier : 4:3 supposé "
                             "(cas habituel des caméscopes). Corrigez-le si l'image paraît déformée.")
    else:
        info.sar, info.dar = Fraction(1), size_ratio
        info.dar_source = "pixels carrés"
    info.dar = info.dar.limit_denominator(100)

    # --- audio
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if a:
        info.has_audio = True
        info.audio_desc = (f"{a.get('codec_name', '?')}, {a.get('sample_rate', '?')} Hz, "
                           f"{a.get('channels', '?')} canal(aux)")
        info.audio_channels = int(a.get("channels") or 0)
        _audio_timing_notes(info, a, v, fmt)

    # --- entrelacement mesuré sur le contenu (au tiers du film, hors amorce)
    start = info.duration / 3 if info.duration > 60 else 0
    try:
        r = run_capture([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-ss", f"{start:.3f}",
                         "-i", str(p), "-map", "0:v:0", "-vf",
                         "idet,signalstats,metadata=print:key=lavfi.signalstats.YDIF,"
                         "metadata=print:key=lavfi.signalstats.SATAVG,"
                         "metadata=print:key=lavfi.signalstats.SATHIGH,"
                         "metadata=print:key=lavfi.signalstats.YLOW,"
                         "metadata=print:key=lavfi.signalstats.YHIGH", "-frames:v",
                         str(idet_frames), "-an", "-f", "null", "-"], timeout=300)
        info.idet = parse_idet(r.stderr)
        sig = parse_signals(r.stderr)
        info.repeated_fields, info.repeated_frames, info.saturation, info.saturation_high = \
            sig["repeated_fields"], sig["repeated_frames"], sig["saturation"], sig["saturation_high"]
        info.level_low, info.level_high = sig.get("level_low"), sig.get("level_high")
        info.cast_rgb = rgb_mean(tools.ffmpeg.path, p, start)
        info.edge_damage = edge_damage(tools.ffmpeg.path, p, info.width, start)
    except subprocess.TimeoutExpired:
        info.idet = {}
    info.scan, info.scan_source = decide_scan(info.idet, info.field_order_meta)
    if info.interlaced:
        # Trames hautes successives : une image de film répartie sur plusieurs trames
        # donne des trames identiques au bruit près, même quand idet ne le voit pas
        # (bruit de bande). Théorie : film 18 i/s en 25i -> environ 28 % de répétitions.
        try:
            r = run_capture([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-ss", f"{start:.3f}",
                             "-i", str(p), "-map", "0:v:0", "-vf",
                             "field=top,signalstats,metadata=print:key=lavfi.signalstats.YDIF",
                             "-frames:v", "300", "-an", "-f", "null", "-"], timeout=300)
            top = repeat_ratio([float(x) for x in re.findall(r"signalstats\.YDIF=([\d.]+)", r.stderr)][1:])
            if top is not None:
                info.repeated_fields = max(info.repeated_fields or 0.0, top)
        except subprocess.TimeoutExpired:
            pass
    if info.scan == "unknown":
        info.warnings.append("Entrelacement non déterminable : choisissez le balayage manuellement "
                             "(en cas de doute sur une cassette de caméscope, essayez « Entrelacée TFF » "
                             "puis « BFF » sur l'aperçu).")
    if info.has_audio:
        # Piste vide ajoutée lors de la numérisation (constaté sur une archive réelle) :
        # on la garde (rien n'est supprimé), mais on l'annonce.
        longueur = 12.0
        positions = sorted({0.0, max(0.0, (info.duration - longueur) / 2),
                            max(0.0, info.duration - longueur)})
        silencieux = []
        for position in positions:
            try:
                r = run_capture([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-ss", str(position),
                                 "-i", str(p), "-map", "0:a:0", "-t", str(longueur),
                                 "-af", "volumedetect", "-f", "null", "-"], timeout=60)
                m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", r.stderr)
                silencieux.append(r.returncode == 0 and bool(m) and float(m.group(1)) < -60)
                if not silencieux[-1]:
                    break
            except subprocess.TimeoutExpired:
                silencieux.append(False)
                break
        info.audio_silent = info.duration > 0 and all(silencieux)
        if not info.audio_silent:
            from .audio_check import measure
            chk = measure(tools.ffmpeg.path, p, info.audio_channels)
            info.channel_issue, info.clipped, info.hum_hz = chk.channel_issue, chk.clipped, chk.hum_hz
            info.wind = chk.wind
    info.standard, info.standard_reason = guess_standard(info.height, info.fps)
    info.suggested_source, info.source_reason = suggest_source(info)
    # Débit : le flux vidéo s'il est écrit, sinon le fichier moins le son PCM.
    audio_codec = str((a or {}).get("codec_name") or "")
    info.video_bitrate = video_bitrate_bps(
        int(_num(v.get("bit_rate"))), int(_num(fmt.get("bit_rate"))),
        info.size_bytes, info.duration, audio_codec,
        int(_num((a or {}).get("sample_rate"))), int(_num((a or {}).get("channels"))))
    info.bits_per_pixel = bits_per_pixel(info.video_bitrate, info.width, info.height, info.fps)
    measure_capture(info, tools.ffmpeg.path, start)
    return info


# --- Numérisation (mesures). Les phrases affichées sont dans advice.py.
# Codecs sans perte : jamais « déjà compressée », même si le débit calculé est bas.
LOSSLESS_CODECS = frozenset({
    "ffv1", "huffyuv", "ffvhuff", "rawvideo", "utvideo", "magicyuv", "png", "qtrle",
    "zlib", "sheervideo", "rle", "v210", "v410", "r210", "ayuv", "yuv4", "bitpacked",
    "012v", "lcl", "mscc", "cscd",
})
# Codecs avec perte que l'on sait juger. Un codec inconnu n'est pas signalé.
LOSSY_CODECS = frozenset({
    "mpeg2video", "mpeg1video", "mpeg4", "msmpeg4v1", "msmpeg4v2", "msmpeg4v3",
    "wmv1", "wmv2", "wmv3", "vc1", "h264", "hevc", "h263", "h263p", "mjpeg", "mjpegb",
    "dvvideo", "dv", "vp8", "vp9", "av1", "theora", "cinepak", "flv1", "svq1", "svq3",
    "rv10", "rv20", "rv30", "rv40", "amv", "h261", "msvideo1", "indeo3", "indeo4", "indeo5",
})
# 0,25 bit par pixel et par image. En 720×576 à 25 i/s : environ 2,6 Mbit/s.
# Une capture MPEG-2 à 8 Mbit/s (environ 0,77) reste au-dessus. Le DV (environ 2,4) aussi.
LOW_BITRATE_BPP = 0.25
# Hauteurs d'une cassette gardée entière. 486 : NTSC avec les lignes du haut.
FULL_SD_HEIGHTS = frozenset({480, 486, 576})
_CAPTURE_WIDTH = 160
_DOUBLED_SHARE = 0.92          # part de paires de lignes identiques
_JITTER_STD = 1.2              # écart des décalages de ligne (pixels de l'échantillon)
_JITTER_MAD = 1.0              # saut d'une ligne à la suivante
_CRUSH_SPIKE = 0.08            # part de pixels collés à l'extrême
_CRUSH_MID = 0.20              # en dessous, l'image est noire ou blanche : pas un écrasement


def _pcm_bits(codec: str) -> int:
    name = codec.lower()
    if "24" in name:
        return 24
    if "64" in name:
        return 64
    if "32" in name:
        return 32
    if name.endswith("8") or "s8" in name or "u8" in name:
        return 8
    return 16


def video_bitrate_bps(stream_rate: int, format_rate: int, size: int, duration: float,
                      audio_codec: str = "", audio_rate: int = 0, audio_channels: int = 0) -> int:
    """Débit vidéo. Le débit du flux prime. Sinon le fichier, moins le son PCM."""
    if stream_rate > 0:
        return stream_rate
    total = format_rate if format_rate > 0 else (int(size * 8 / duration) if duration > 0 and size > 0 else 0)
    if total <= 0:
        return 0
    if audio_codec.lower().startswith("pcm") and audio_rate > 0 and audio_channels > 0:
        total -= audio_rate * audio_channels * _pcm_bits(audio_codec)
    return max(0, total)


def bits_per_pixel(bitrate: int, width: int, height: int, fps: Fraction | float) -> float | None:
    """Bits par pixel et par image. None si une grandeur manque."""
    rate = float(fps)
    if bitrate <= 0 or width <= 0 or height <= 0 or rate <= 0:
        return None
    return bitrate / (width * height * rate)


def is_low_bitrate_copy(codec: str, bpp: float | None) -> bool:
    """Copie avec perte sous le seuil. FFV1, HuffYUV, PCM et le reste sans perte : non."""
    name = (codec or "").lower()
    if name in LOSSLESS_CODECS or name.startswith("pcm"):
        return False
    if name not in LOSSY_CODECS or bpp is None:
        return False
    return bpp < LOW_BITRATE_BPP


def is_progressive_film(info: MediaInfo) -> bool:
    """Pellicule numérisée image par image : progressive et à une cadence de cinéma.
    Sa taille n'est pas celle d'une cassette, et ce n'est pas un défaut."""
    if info.scan in ("tff", "bff"):
        return False
    return any(abs(float(info.fps - rate)) < 0.02 for rate in FILM_RATES)


def judge_capture(info: MediaInfo, *, doubled: bool = False, jitter: bool = False,
                  crushed_blacks: bool = False, crushed_whites: bool = False) -> None:
    """Pose les drapeaux à partir du codec, de la taille et des mesures d'image.
    Une photo ou une pellicule progressive n'est pas une cassette mal numérisée."""
    if info.container == "image":
        info.low_bitrate = info.already_deinterlaced = info.already_scaled = False
        info.doubled_lines = info.line_jitter = False
        info.crushed_blacks = info.crushed_whites = False
        return
    film = is_progressive_film(info)
    info.low_bitrate = is_low_bitrate_copy(info.codec, info.bits_per_pixel)
    info.crushed_blacks = bool(crushed_blacks)
    info.crushed_whites = bool(crushed_whites)
    info.doubled_lines = bool(doubled) and not film
    info.line_jitter = bool(jitter) and not film
    info.already_deinterlaced = info.scan == "progressive" and not film
    info.already_scaled = bool(info.height) and info.height not in FULL_SD_HEIGHTS and not film


def _levels_of(frame: bytes, width: int, height: int) -> tuple[float, float, float, float, float] | None:
    """Sur le centre de l'image : pic de noir, voisinage du noir, milieu, pic de blanc, voisinage du blanc."""
    if width < 8 or height < 8 or len(frame) < width * height:
        return None
    x0, x1 = int(width * 0.15), int(width * 0.85)
    y0, y1 = int(height * 0.12), int(height * 0.88)
    if x1 <= x0 or y1 <= y0:
        return None
    black = near = mid = white = near_white = total = 0
    mv = memoryview(frame)
    for y in range(y0, y1):
        row = mv[y * width + x0:y * width + x1]
        total += len(row)
        for pix in row:
            if pix <= 1:
                black += 1
            elif pix < 16:
                near += 1
            if 40 <= pix < 210:
                mid += 1
            if pix >= 254:
                white += 1
            elif pix >= 236:
                near_white += 1
    if total <= 0:
        return None
    return black / total, near / total, mid / total, white / total, near_white / total


def _is_crushed(spike: float, near: float, mid: float) -> bool:
    """Pic collé à l'extrême, avec encore une image au milieu. Un fondu au noir n'a pas de milieu.
    Une scène sombre a un voisinage, pas une falaise."""
    if mid < _CRUSH_MID or spike < _CRUSH_SPIKE:
        return False
    return spike > 4.0 * near + 0.02


def doubled_line_share(frame: bytes, width: int, height: int) -> float | None:
    """Part des paires de lignes détaillées qui sont des copies. None s'il n'y a pas assez de détail."""
    if width < 8 or height < 8 or len(frame) < width * height:
        return None
    pairs = copies = 0
    mv = memoryview(frame)
    for y in range(0, height - 1, 2):
        a = mv[y * width:(y + 1) * width]
        b = mv[(y + 1) * width:(y + 2) * width]
        mean = sum(a) / width
        var = sum((pix - mean) ** 2 for pix in a) / width
        if var < 64:
            continue
        pairs += 1
        if sum(abs(p - q) for p, q in zip(a, b)) / width < 1.0:
            copies += 1
    if pairs < 12:
        return None
    return copies / pairs


def line_shift_stats(frame: bytes, width: int, height: int) -> tuple[float, float, float] | None:
    """Décalages horizontaux d'une ligne de trame à la suivante : écart-type, saut moyen, part forte.
    None s'il n'y a pas assez de lignes détaillées."""
    if width < 40 or height < 16 or len(frame) < width * height:
        return None
    x0, x1 = width // 5, 4 * width // 5
    if x1 - x0 < 16:
        return None
    shifts: list[int] = []
    prev: bytes | None = None
    mv = memoryview(frame)
    for y in range(0, height - 2, 2):
        row = bytes(mv[y * width + x0:y * width + x1])
        if prev is None:
            prev = row
            continue
        mean = sum(row) / len(row)
        var = sum((pix - mean) ** 2 for pix in row) / len(row)
        if var < 80:
            prev = row
            continue
        best, best_sad = 0, 1e18
        for shift in range(-8, 9):
            if shift < 0:
                aa, bb = prev[-shift:], row[:len(row) + shift]
            elif shift > 0:
                aa, bb = prev[:len(prev) - shift], row[shift:]
            else:
                aa, bb = prev, row
            if not aa:
                continue
            sad = sum(abs(p - q) for p, q in zip(aa, bb)) / len(aa)
            if sad < best_sad:
                best, best_sad = shift, sad
        shifts.append(best)
        prev = row
    if len(shifts) < 8:
        return None
    mean = sum(shifts) / len(shifts)
    std = (sum((s - mean) ** 2 for s in shifts) / len(shifts)) ** 0.5
    mad = sum(abs(a - b) for a, b in zip(shifts, shifts[1:])) / (len(shifts) - 1)
    big = sum(abs(s) >= 2 for s in shifts) / len(shifts)
    return std, mad, big


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _read_gray(ffmpeg: str, path: Path, width: int, height: int, start: float,
               frames: int = 4) -> tuple[int, int, list[bytes]]:
    """Quelques images en gris, largeur limitée, hauteur entière (les lignes doublées restent)."""
    sample_w = min(_CAPTURE_WIDTH, width)
    if sample_w < 8 or height < 8:
        return 0, 0, []
    vf = f"scale={sample_w}:{height}:flags=neighbor,format=gray"
    try:
        result = capture([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
                          "-ss", f"{max(0.0, start):.3f}", *ff_input(path),
                          "-map", "0:v:0", "-vf", vf, "-frames:v", str(frames),
                          "-an", "-f", "rawvideo", "-"],
                         capture_output=True, timeout=60, stdin=subprocess.DEVNULL,
                         creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return sample_w, height, []
    if result.returncode:
        return sample_w, height, []
    size = sample_w * height
    data = result.stdout
    return sample_w, height, [data[i:i + size] for i in range(0, len(data) - size + 1, size)]


def measure_capture(info: MediaInfo, ffmpeg: str, start: float = 0.0) -> None:
    """Mesure la numérisation et pose les drapeaux. N'échoue pas si la lecture est impossible."""
    if info.container == "image":
        judge_capture(info)
        return
    doubled = jitter = False
    crushed_blacks = crushed_whites = False
    width, height, frames = _read_gray(ffmpeg, info.path, info.width, info.height, start)
    if frames:
        shares = [s for frame in frames if (s := doubled_line_share(frame, width, height)) is not None]
        if shares and _median(shares) >= _DOUBLED_SHARE:
            doubled = True
        stats = [s for frame in frames if (s := line_shift_stats(frame, width, height)) is not None]
        if stats:
            std = _median([s[0] for s in stats])
            mad = _median([s[1] for s in stats])
            big = _median([s[2] for s in stats])
            if std >= _JITTER_STD and mad >= _JITTER_MAD and big >= 0.25:
                jitter = True
        black_votes: list[bool] = []
        white_votes: list[bool] = []
        for frame in frames:
            levels = _levels_of(frame, width, height)
            if levels is None:
                continue
            black, near, mid, white, near_white = levels
            if mid < _CRUSH_MID:
                continue
            black_votes.append(_is_crushed(black, near, mid))
            white_votes.append(_is_crushed(white, near_white, mid))
        if black_votes:
            crushed_blacks = sum(black_votes) * 2 >= len(black_votes)
            crushed_whites = sum(white_votes) * 2 >= len(white_votes)
    judge_capture(info, doubled=doubled, jitter=jitter,
                  crushed_blacks=crushed_blacks, crushed_whites=crushed_whites)
