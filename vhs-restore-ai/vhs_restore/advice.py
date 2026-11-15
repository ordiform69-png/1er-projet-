"""Conseils de l'analyse : une phrase simple par défaut détecté, et la correction
correspondante. Rien n'est appliqué tant que l'utilisateur ne l'a pas demandé
(case « Appliquer les conseils » du mode simple, ou réglage dans les options avancées)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .probe import MediaInfo


@dataclass(frozen=True)
class Advice:
    key: str        # hum | channel | clip | wind
    text: str       # phrase affichée à l'utilisateur
    fix: dict       # champs de pipeline.Settings à modifier


def advise(info: MediaInfo) -> list[Advice]:
    if not info.has_audio or info.audio_silent:
        return []
    out: list[Advice] = []
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
        out.append(Advice("clip", f"Le son sature par moments ({info.clipped:.1%} des échantillons) : "
                                  "les crêtes coupées seront reconstruites.", {"audio_declip": True}))
    if info.hum_hz:
        out.append(Advice("hum", f"Un ronflement électrique à {info.hum_hz} Hz est audible : il sera filtré.",
                          {"audio_mains_hz": info.hum_hz}))
    if info.wind:
        out.append(Advice("wind", "Du vent ou des grondements graves couvrent le son : ils seront atténués, "
                                  "sans toucher aux voix.", {"audio_highpass": True}))
    return out


def apply(settings, advice: list[Advice]):
    """Réglages avec les corrections conseillées (settings : pipeline.Settings)."""
    fix: dict = {}
    for a in advice:
        fix.update(a.fix)
    return dataclasses.replace(settings, **fix) if fix else settings
