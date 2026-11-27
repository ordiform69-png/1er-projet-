"""Bugs n°20, agent A : son et image sur la durée. Rien n'est corrigé.

Chaque test décrit le comportement attendu. Il échoue tant que le bug est là
(`xfail` strict). Les films sont générés ici, jamais commités.
"""
import array
import dataclasses
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore import pipeline, reprise
from vhs_restore.probe import MediaInfo, analyze
from vhs_restore.profiles import profile_for


def _bips(ffmpeg: str, path: Path, ecart_min: float = 0.4) -> list[float]:
    brut = subprocess.check_output(
        [ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "48000",
         "-f", "s16le", "pipe:"])
    vals = array.array("h")
    vals.frombytes(brut[:len(brut) // 2 * 2])
    pas = 96  # 2 ms
    energie = [sum(abs(int(v)) for v in vals[i:i + pas]) / pas
               for i in range(0, len(vals) - pas, pas)]
    if not energie:
        return []
    seuil = max(energie) * 0.4
    instants, dernier = [], float("-inf")   # un bip à 0 s compte, même avec un grand écart (Claude, n°21)
    for i, e in enumerate(energie):
        t = i * pas / 48000
        if e >= seuil and t - dernier > ecart_min:
            instants.append(t)
            dernier = t
    return instants


def _film_bips(dossier: Path, secondes: int, nom: str = "film.mp4") -> Path:
    """320×240, image blanche et bip de 20 ms toutes les 10 s (et à 0)."""
    chemin = dossier / nom
    ff("-f", "lavfi", "-i",
       f"color=c=black:s=320x240:r=25:d={secondes},"
       "drawbox=c=white:t=fill:enable='eq(mod(n\\,250)\\,0)'",
       "-f", "lavfi", "-i",
       f"aevalsrc=0.8*sin(2*PI*1000*t)*lt(mod(t\\,10)\\,0.02):s=48000:d={secondes}",
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
       "-c:a", "pcm_s16le", str(chemin))
    return chemin


def _reglages(profil="fidele"):
    return pipeline.Settings(profile_for(profil, "video"), preset="ultrafast", crf=30,
                             scan="progressive")


@pytest.mark.xfail(strict=True, reason=(
    "Collage des passages gardés : le son prend environ 3 ms de retard à chaque "
    "raccord (AAC copié). Après 12 coupes, le dernier bip a 30 ms de plus de retard "
    "que le premier."))
def test_passages_gardes_le_son_ne_derive_pas(tmp_path, tools):
    src = _film_bips(tmp_path, 12, "source.mp4")
    info = dataclasses.replace(analyze(src, tools), scan="progressive")
    out = tmp_path / "coupes.mp4"
    pipeline.export(info, _reglages(), out, tools, passages=[(i, i + 1) for i in range(12)])
    bips = _bips(tools.ffmpeg.path, out)
    assert len(bips) >= 12, bips
    croissance = (bips[-1] - 11) - bips[0]
    assert croissance <= 0.020, (
        f"premier bip {bips[0]:.3f} s, bip à 11 s lu {bips[-1]:.3f} s, "
        f"retard en plus {croissance * 1000:.0f} ms")


def test_film_long_bip_et_repere_a_20ms(tmp_path, tools, monkeypatch):
    """60 min, 320×240, bip et repère toutes les 10 s. Ils doivent rester à 20 ms."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "loc"))
    monkeypatch.setattr(reprise, "SEUIL", 1e12)  # une seule passe, le décalage est déjà là
    src = _film_bips(tmp_path, 3600, "heure.mp4")
    info = dataclasses.replace(analyze(src, tools), scan="progressive")
    out = tmp_path / "restaure.mp4"
    pipeline.export(info, _reglages(), out, tools)
    bips = _bips(tools.ffmpeg.path, out, ecart_min=5)
    cible = 3590.0
    proche = min(bips, key=lambda t: abs(t - cible))
    ecart = abs(proche - cible)
    assert ecart <= 0.020, f"bip le plus proche de {cible:.0f} s : {proche:.3f} s ({ecart * 1000:.0f} ms)"


def test_petite_derive_est_corrigee():
    info = MediaInfo(path=Path("film.mp4"), duration=3 * 3600, fps=Fraction(25), has_audio=True)
    s = pipeline.Settings(profile_for("fidele", "video"), audio_drift_ms_per_min=5)
    chaine = pipeline._atempo_filters(info, s, drift=True)
    assert chaine, (
        f"dérive 5 ms/min ignorée (facteur {_tempo(info, s):.8f}). "
        f"Sur 3 h : {5 * 180} ms non corrigés")


def _tempo(info, s) -> float:
    return pipeline._tempo_factor(info, s, drift=True)


def test_equilibre_garde_le_bip_d_ouverture(tmp_path, tools):
    src = _film_bips(tmp_path, 12, "source.mp4")
    info = dataclasses.replace(analyze(src, tools), scan="progressive")
    out = tmp_path / "equilibre.mp4"
    pipeline.export(info, _reglages("equilibre"), out, tools)
    bips = _bips(tools.ffmpeg.path, out, ecart_min=5)
    assert any(abs(t) <= 0.020 for t in bips), f"aucun bip dans les 20 premières ms : {bips[:4]}"
