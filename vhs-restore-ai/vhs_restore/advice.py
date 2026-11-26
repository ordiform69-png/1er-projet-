"""Conseils de l'analyse : une phrase simple par défaut détecté, et la correction
correspondante. Rien n'est appliqué tant que l'utilisateur ne l'a pas demandé
(case « Appliquer les conseils » du mode simple, ou réglage dans les options avancées).

La numérisation (copie trop compressée, déjà désentrelacée, noirs écrasés…)
s'affiche seulement : aucune correction, le moteur de restauration ne change pas.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .probe import MediaInfo, cast_gains


@dataclass(frozen=True)
class Advice:
    key: str        # hum | channel | clip | wind | levels | cast | edges
    text: str       # phrase affichée à l'utilisateur
    fix: dict       # champs de pipeline.Settings à modifier


def advise(info: MediaInfo) -> list[Advice]:
    out: list[Advice] = []
    if info.has_audio and not info.audio_silent:
        if info.channel_issue == "left_silent":
            out.append(Advice("channel", "Le son n'est enregistré que du côté droit : il sera mis des deux côtés.",
                              {"audio_channel_fix": "right"}))
        elif info.channel_issue == "right_silent":
            out.append(Advice("channel", "Le son n'est enregistré que du côté gauche : il sera mis des deux côtés.",
                              {"audio_channel_fix": "left"}))
        elif info.channel_issue == "phase":
            out.append(Advice("channel", "Les deux côtés du son s'annulent en partie (opposition de phase) : "
                                         "ils seront remis en accord.", {"audio_channel_fix": "phase"}))
        if info.clipped >= 0.0005:
            part = f"{info.clipped * 100:.1f}".replace(".", ",")
            out.append(Advice("clip", f"Le son sature par moments ({part} % des échantillons) : "
                                      "les crêtes coupées seront reconstruites.", {"audio_declip": True}))
        if info.hum_hz:
            out.append(Advice("hum", f"Un ronflement électrique à {info.hum_hz} Hz est audible : il sera filtré.",
                              {"audio_mains_hz": info.hum_hz}))
        if info.wind:
            out.append(Advice("wind", "Du vent ou des grondements graves couvrent le son : ils seront atténués, "
                                      "sans toucher aux voix.", {"audio_highpass": True}))
    lo, hi = info.level_low, info.level_high
    # Noirs gris ET blancs ternes : l'écart de luminance est écrasé. Une scène de nuit
    # (blancs absents mais noirs vraiment noirs) n'est pas étirée.
    if lo is not None and hi is not None and hi - lo < 140 and lo > 35 and hi < 190:
        out.append(Advice("levels",
                          f"Les noirs sont gris et les blancs ternes (niveaux {lo:.0f} à {hi:.0f}) : "
                          "le contraste sera rehaussé avec modération"
                          + (" pour toute la photo." if info.container == "image"
                             else ", une seule fois pour tout le film."),
                          {"level_black": lo / 255.0, "level_white": hi / 255.0}))
    if info.edge_damage:
        out.append(Advice("edges", f"Les bords de l'image sont abîmés (traits colorés ou neige sur environ "
                                   f"{info.edge_damage} pixels) : ils seront masqués en noir, sans changer "
                                   "la taille ni le format de l'image.", {"mask_sides": info.edge_damage}))
    if info.cast_rgb and max(info.cast_rgb) - min(info.cast_rgb) > 15:
        gr, gg, gb = cast_gains(info.cast_rgb)
        out.append(Advice("cast", "Une dominante de couleur couvre l'image : elle sera atténuée "
                                  "(sans raviver une image pâle).",
                          {"gain_r": gr, "gain_g": gg, "gain_b": gb}))
    return out


# Phrase imposée pour une copie déjà compressée à faible débit.
PHRASE_COMPRESSEE = (
    "Cette copie est déjà compressée : les détails perdus ne reviendront pas. "
    "Si vous avez encore la cassette, une nouvelle numérisation sans compression "
    "donnera un meilleur résultat."
)
PHRASE_TRAITEE = (
    "Cette copie est déjà désentrelacée ou réduite : les lignes perdues ne reviendront pas. "
    "Si vous avez encore la cassette, refaites la numérisation sans désentrelacer "
    "et sans réduire l'image."
)
PHRASE_NOIRS = (
    "Les noirs sont écrasés dès la numérisation : le sombre est collé au noir, "
    "et ces détails sont perdus. Si vous avez encore la cassette, "
    "refaites la numérisation sans forcer les noirs."
)
PHRASE_BLANCS = (
    "Les blancs sont écrasés dès la numérisation : le clair est collé au blanc, "
    "et ces détails sont perdus. Si vous avez encore la cassette, "
    "refaites la numérisation sans forcer les blancs."
)
PHRASE_NOIRS_BLANCS = (
    "Les noirs et les blancs sont écrasés dès la numérisation : le sombre et le clair "
    "sont collés aux extrêmes. Si vous avez encore la cassette, "
    "refaites la numérisation en gardant tous les gris."
)
PHRASE_LIGNES = (
    "Les lignes de l'image tremblent. Si vous pouvez, refaites la numérisation "
    "avec un magnétoscope équipé d'un correcteur de base de temps."
)
# Une seule ligne dans l'assistant, à l'étape 1. Le détail est dans « Détails du fichier ».
LIGNE_ASSISTANT = "Des détails sont déjà perdus. Ouvrez « Détails du fichier »."


def conseils_numerisation(info: MediaInfo) -> list[str]:
    """Phrases à montrer, dans l'ordre. Liste vide si rien n'est à signaler.
    Aucune de ces phrases n'est une correction : apply() ne les reçoit pas."""
    if info.container == "image":
        return []
    out: list[str] = []
    if info.low_bitrate:
        out.append(PHRASE_COMPRESSEE)
    if info.already_deinterlaced or info.already_scaled or info.doubled_lines:
        out.append(PHRASE_TRAITEE)
    if info.crushed_blacks and info.crushed_whites:
        out.append(PHRASE_NOIRS_BLANCS)
    elif info.crushed_blacks:
        out.append(PHRASE_NOIRS)
    elif info.crushed_whites:
        out.append(PHRASE_BLANCS)
    if info.line_jitter:
        out.append(PHRASE_LIGNES)
    return out


def ligne_assistant(info: MediaInfo) -> str:
    """Une seule ligne pour l'étape 1, ou rien si la numérisation ne pose pas de problème."""
    return LIGNE_ASSISTANT if conseils_numerisation(info) else ""


def apply(settings, advice: list[Advice]):
    """Réglages avec les corrections conseillées (settings : pipeline.Settings)."""
    fix: dict = {}
    for a in advice:
        fix.update(a.fix)
    if "mask_sides" in fix:              # un masque plus large choisi à la main est gardé
        fix["mask_sides"] = max(int(fix["mask_sides"]), int(getattr(settings, "mask_sides", 0) or 0))
    return dataclasses.replace(settings, **fix) if fix else settings
