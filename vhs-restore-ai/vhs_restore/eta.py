"""Temps restant affiché pendant un traitement (« environ 1 h 20 restantes »).

Vitesse mesurée sur une fenêtre glissante (les étapes n'ont pas toutes la même
vitesse) ; rien n'est affiché avant 5 % de progression et 10 s de travail, car
une estimation trop tôt serait fausse et inquiéterait inutilement."""
from __future__ import annotations

import time
from collections import deque


class Eta:
    def __init__(self, window: float = 120.0, clock=time.monotonic):
        self.clock = clock
        self.window = window
        self.start = clock()
        self.points: deque[tuple[float, float]] = deque()

    def update(self, frac: float) -> str:
        now = self.clock()
        self.points.append((now, frac))
        while len(self.points) > 2 and now - self.points[0][0] > self.window:
            self.points.popleft()
        if frac < 0.05 or now - self.start < 10 or frac >= 1:
            return ""
        t0, f0 = self.points[0]
        if now - t0 < 5 or frac <= f0:
            t0, f0 = self.start, 0.0          # pas assez d'historique : moyenne depuis le début
        rate = (frac - f0) / max(now - t0, 1e-6)
        return describe((1 - frac) / rate) if rate > 0 else ""


def describe(seconds: float) -> str:
    """Durée arrondie, en mots simples (« environ 25 minutes »)."""
    if seconds < 60:
        return "moins d'une minute"
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"environ {minutes} minute" if minutes == 1 else f"environ {minutes} minutes"
    h, m = divmod(int(round(seconds / 300)) * 5, 60)     # par tranches de 5 min au-delà d'une heure
    return f"environ {h} h {m:02d}" if m else f"environ {h} h"
