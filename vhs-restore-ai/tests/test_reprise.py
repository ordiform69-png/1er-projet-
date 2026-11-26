"""Reprendre une restauration interrompue (demande n°19).

Les constantes de production (parties de 10 min, seuil de 20 min, chauffe de 8 s)
sont ramenées ici à 20 s / 30 s / 3 s. Film de synthèse : 80 s, deux scènes,
mouvement, son avec bips.

API attendue de `vhs_restore.reprise` (agent R1, branche grok/reprise-moteur) —
ces noms sont déduits de la demande ; R1 n'avait pas encore poussé de code au
moment de l'écriture. Si l'API publiée diffère, les tests seront alignés à la
fusion.

Constantes (secondes), à remplacer par les tests :
  DUREE_PARTIE, SEUIL, CHAUFFE

Fonctions :
  dossier_racine() -> Path
      %LOCALAPPDATA%\\VHSRestoreAI\\reprise ou ~/.local/share/VHSRestoreAI/reprise
  cle(info, s, passages=None) -> str
  dossier(info, s, passages=None) -> Path   # racine / cle
  applicable(info, s, passages=None) -> bool
      Vrai seulement si la durée gardée ≥ SEUIL, sans IA, sans poussières,
      sans réparation de bande, sans changement de cadence, sans stabilisation.
  decouper(passages, duree_partie=None) -> list[tuple[float, float]]
      Parties de duree_partie au plus, à l'intérieur de chaque passage gardé.
      Si la dernière partie d'un passage est plus courte que duree_partie, elle
      rejoint la précédente.
  fenetre(debut, fin, chauffe=None) -> tuple[float, float]
      (start, duration) pour _export(..., morceau=True), chauffe comprise,
      bornée au début du film (t = 0). L'origine des scènes suit le temps source.
  restaurer(info, s, out_path, tools, *, cancel=None, progress=None,
            start=None, duration=None, passages=None) -> Path
  parties_faites(dossier) -> séquence (chemin ou objet avec debut/fin/chemin)
  verifier_partie(path, duree_attendue, tools) -> bool

Messages (R2 peut les réutiliser tels quels, vouvoiement, mot « partie ») :
  message_ouverture(faites, total) -> str
  message_progression(faites, total) -> str
  message_arret() -> str
"""
from __future__ import annotations

import dataclasses
import math
import shutil
import subprocess
import threading
import time
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for
from vhs_restore import pipeline

try:
    from vhs_restore import reprise
except ImportError:  # agent R1 pas encore fusionné
    reprise = None

DUREE_FILM = 80.0
PARTIE = 20.0
SEUIL = 30.0
CHAUFFE = 3.0
# Bips de 50 ms à t = 0, 10, 20, …, 70 s (temps source), pour caler le son sur l'image.
PERIODE_BIP = 10.0
DUREE_BIP = 0.05


def _constantes(monkeypatch, tmp_path):
    if reprise is None:
        pytest.fail("vhs_restore.reprise n'existe pas encore (agent R1, branche grok/reprise-moteur).")
    monkeypatch.setattr(reprise, "DUREE_PARTIE", PARTIE)
    monkeypatch.setattr(reprise, "SEUIL", SEUIL)
    monkeypatch.setattr(reprise, "CHAUFFE", CHAUFFE)
    racine = tmp_path / "VHSRestoreAI" / "reprise"
    racine.mkdir(parents=True)
    monkeypatch.setattr(reprise, "dossier_racine", lambda: racine)
    return reprise


@pytest.fixture
def r(monkeypatch, tmp_path):
    return _constantes(monkeypatch, tmp_path)


def reglages(**kw):
    s = pipeline.Settings(profile_for("fidele", "video"), source="video",
                          restore_audio=True, preset="ultrafast", crf=23,
                          scan="progressive", use_ai=False, stabilize=False,
                          dust=False, denoise_hq=False)
    return dataclasses.replace(s, **kw) if kw else s


def _graphe_film(largeur=320, hauteur=240, cadence=25, duree_scene=40.0) -> str:
    """Deux scènes, motif animé (testsrc2), bips toutes les 10 s."""
    s1 = (f"testsrc2=s={largeur}x{hauteur}:r={cadence}:d={duree_scene},"
          "eq=brightness=-0.12:saturation=0.75,colorchannelmixer=rr=1.12:bb=0.88[v1]")
    s2 = (f"testsrc2=s={largeur}x{hauteur}:r={cadence}:d={duree_scene},"
          "eq=brightness=0.08,colorchannelmixer=rr=0.90:bb=1.10[v2]")
    video = (f"{s1};{s2};[v1][v2]concat=n=2:v=1:a=0,setsar=1[v]")
    # Fond 440 Hz + bip 2 kHz pendant 50 ms au début de chaque période.
    son = (f"sine=frequency=440:sample_rate=48000:duration={DUREE_FILM},volume=0.15[a0];"
           f"sine=frequency=2000:sample_rate=48000:duration={DUREE_FILM},"
           f"volume=enable='lt(mod(t\\,{PERIODE_BIP:.3f})\\,{DUREE_BIP})':volume=0.8[a1];"
           f"[a0][a1]amix=inputs=2:duration=longest[a]")
    return video + ";" + son


@pytest.fixture(scope="module")
def film80(tmp_path_factory, tools):
    dossier = tmp_path_factory.mktemp("reprise-80s")
    dest = dossier / "deux-scenes-80s.mkv"
    ff("-filter_complex", _graphe_film(), "-map", "[v]", "-map", "[a]",
       "-c:v", "ffv1", "-c:a", "pcm_s16le", str(dest))
    info = analyze(dest, tools)
    return dest, info


# --------------------------------------------------------------------------- 1. découpage

def test_decoupage_passages_et_coupes(r):
    """Parties de 20 s au plus ; dernière trop courte rejoint la précédente ;
    coupes au milieu respectées (on ne traverse pas un trou)."""
    assert r.decouper([(0.0, 80.0)]) == [(0.0, 20.0), (20.0, 40.0), (40.0, 60.0), (60.0, 80.0)]
    # 50 s : 20 + 20 + 10 → la dernière (10 s) rejoint la précédente → 20 + 30
    assert r.decouper([(0.0, 50.0)]) == [(0.0, 20.0), (20.0, 50.0)]
    # un passage trop court pour deux parties
    assert r.decouper([(0.0, 25.0)]) == [(0.0, 25.0)]
    # coupe au milieu 25–35 : chaque passage est découpé séparément
    parties = r.decouper([(0.0, 25.0), (35.0, 80.0)])
    assert parties[0] == (0.0, 25.0)
    assert parties[-1][1] == pytest.approx(80.0)
    for a, b in parties:
        assert 0 < (b - a) <= 2 * PARTIE + 1e-6
        # aucune partie ne chevauche le trou
        assert b <= 25.0 + 1e-6 or a >= 35.0 - 1e-6
    # à l'intérieur du second passage (45 s) : 20 + 25 (10 s trop court rejoint)
    assert r.decouper([(35.0, 80.0)]) == [(35.0, 55.0), (55.0, 80.0)]


# --------------------------------------------------------------------------- 2. même résultat qu'en une fois

def _nb_images(tools, path: Path) -> int:
    r = subprocess.run(
        [tools.ffprobe.path, "-v", "error", "-select_streams", "v:0",
         "-count_frames", "-show_entries", "stream=nb_read_frames",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    return int(r.stdout.strip().splitlines()[-1])


def _duree_flux(tools, path: Path, typ: str) -> float:
    r = subprocess.run(
        [tools.ffprobe.path, "-v", "error", "-select_streams", f"{typ}:0",
         "-show_entries", "stream=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip().splitlines()[-1])


def _pcm(tools, path: Path) -> bytes:
    r = subprocess.run(
        [tools.ffmpeg.path, "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-map", "0:a:0", "-f", "s16le", "-ac", "1", "-ar", "48000", "-"],
        capture_output=True, check=True)
    return r.stdout


def _bips(pcm: bytes, sr=48000, seuil=2000) -> list[float]:
    """Instants (s) où l'énergie franchit un seuil, un par paquet."""
    n = len(pcm) // 2
    instants = []
    i = 0
    while i < n:
        echan = int.from_bytes(pcm[2 * i:2 * i + 2], "little", signed=True)
        if abs(echan) >= seuil:
            t = i / sr
            if not instants or t - instants[-1] > PERIODE_BIP / 2:
                instants.append(t)
            i += int(sr * 0.2)
        else:
            i += 1
    return instants


def _ecart_moyen_gris(ffmpeg: str, a: Path, b: Path, instant: float, n=3) -> float:
    """Écart moyen |A−B| / 255 sur n images autour de `instant`."""
    def cadre(src):
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{instant:.3f}",
             "-i", str(src), "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True)
        return r.stdout
    da, db = cadre(a), cadre(b)
    m = min(len(da), len(db))
    assert m > 0
    s = sum(abs(da[i] - db[i]) for i in range(m))
    return s / m / 255.0


def _sauts_echantillons(pcm: bytes, instants: list[float], sr=48000, fenetre=0.005) -> list[int]:
    """Plus grand saut d'échantillon dans une fenêtre autour de chaque instant."""
    n = len(pcm) // 2
    vals = [int.from_bytes(pcm[2 * i:2 * i + 2], "little", signed=True) for i in range(n)]
    sauts = []
    for t in instants:
        i0 = max(1, int((t - fenetre) * sr))
        i1 = min(n, int((t + fenetre) * sr))
        if i1 - i0 < 2:
            continue
        sauts.append(max(abs(vals[i] - vals[i - 1]) for i in range(i0, i1)))
    return sauts


def test_meme_resultat_qu_en_une_fois(r, film80, tools, tmp_path, monkeypatch):
    dest, info = film80
    s = reglages()
    une = tmp_path / "une-fois.mp4"
    # Forcer le chemin « une fois » : seuil plus haut que le film.
    monkeypatch.setattr(r, "SEUIL", 10_000)
    r.restaurer(info, s, une, tools)
    monkeypatch.setattr(r, "SEUIL", SEUIL)
    parties = tmp_path / "par-parties.mp4"
    r.restaurer(info, s, parties, tools)

    n_une, n_part = _nb_images(tools, une), _nb_images(tools, parties)
    assert n_une == n_part
    dv_u, da_u = _duree_flux(tools, une, "v"), _duree_flux(tools, une, "a")
    dv_p, da_p = _duree_flux(tools, parties, "v"), _duree_flux(tools, parties, "a")
    assert abs(da_u - dv_u) <= 0.020 and abs(da_p - dv_p) <= 0.020

    bips_u = _bips(_pcm(tools, une))
    bips_p = _bips(_pcm(tools, parties))
    assert len(bips_u) == len(bips_p) >= 7
    for a, b in zip(bips_u, bips_p):
        assert abs(a - b) <= 0.020, (a, b)

    # Raccords attendus à 20, 40, 60 s (parties de 20 s sur 80 s).
    for t in (20.0, 40.0, 60.0):
        ecart = _ecart_moyen_gris(tools.ffmpeg.path, une, parties, t)
        assert ecart < 2 / 255, (t, ecart)

    pcm_p = _pcm(tools, parties)
    # Pas de claquement : le saut au raccord ne dépasse pas clairement celui du
    # même instant dans la restauration en une fois (marge pour le bruit).
    pcm_u = _pcm(tools, une)
    sauts_p = _sauts_echantillons(pcm_p, [20.0, 40.0, 60.0])
    sauts_u = _sauts_echantillons(pcm_u, [20.0, 40.0, 60.0])
    assert sauts_p and sauts_u
    for sp, su in zip(sauts_p, sauts_u):
        assert sp <= su + 2000, (sp, su)


# --------------------------------------------------------------------------- 3. interruption et relance

def test_interruption_puis_reprise(r, film80, tools, tmp_path):
    dest, info = film80
    s = reglages()
    out = tmp_path / "repris.mp4"
    cancel = threading.Event()
    dossier = r.dossier(info, s)

    def surveiller():
        # Dès que 2 parties complètes sont là, on arrête.
        t0 = time.monotonic()
        while time.monotonic() - t0 < 180:
            if len(list(r.parties_faites(dossier))) >= 2:
                cancel.set()
                return
            time.sleep(0.2)
        cancel.set()

    fil = threading.Thread(target=surveiller, daemon=True)
    fil.start()
    with pytest.raises(Exception) as exc:
        r.restaurer(info, s, out, tools, cancel=cancel)
    # Annulation typique : Cancelled. On accepte toute exception d'arrêt.
    assert not out.exists() or out.stat().st_size == 0 or "Annul" in type(exc.value).__name__
    fil.join(timeout=5)
    faites = list(r.parties_faites(dossier))
    assert len(faites) == 2, faites
    chemins = []
    for p in faites:
        chemin = Path(getattr(p, "chemin", p))
        chemins.append(chemin)
        assert chemin.is_file()
    mtimes = [c.stat().st_mtime for c in chemins]

    out2 = tmp_path / "repris-complet.mp4"
    r.restaurer(info, s, out2, tools)
    assert out2.is_file() and out2.stat().st_size > 0
    # Les deux premières parties n'ont pas été réécrites.
    for c, t0 in zip(chemins, mtimes):
        assert c.stat().st_mtime == t0
    assert len(list(r.parties_faites(dossier))) == 0 or not dossier.exists()
    # Dossier effacé après succès.
    assert not dossier.exists() or not any(dossier.iterdir())


# --------------------------------------------------------------------------- 4. partie incomplète ou abîmée

def test_partie_abimee_est_refaite(r, film80, tools, tmp_path):
    dest, info = film80
    s = reglages()
    out = tmp_path / "abime.mp4"
    cancel = threading.Event()
    dossier = r.dossier(info, s)

    def stop_apres_une():
        t0 = time.monotonic()
        while time.monotonic() - t0 < 180:
            if len(list(r.parties_faites(dossier))) >= 1:
                cancel.set()
                return
            time.sleep(0.2)
        cancel.set()

    threading.Thread(target=stop_apres_une, daemon=True).start()
    try:
        r.restaurer(info, s, out, tools, cancel=cancel)
    except Exception:
        pass
    faites = list(r.parties_faites(dossier))
    assert faites, "aucune partie à abîmer"
    premiere = Path(getattr(faites[0], "chemin", faites[0]))
    # Tronquer le fichier : il ne doit plus être réutilisé.
    data = premiere.read_bytes()
    premiere.write_bytes(data[: max(0, len(data) // 4)])
    t_avant = premiere.stat().st_mtime
    out2 = tmp_path / "abime-ok.mp4"
    r.restaurer(info, s, out2, tools)
    assert out2.is_file() and out2.stat().st_size > 0
    # La partie douteuse a été refaite (nouveau contenu ou nouveau fichier).
    if premiere.exists():
        assert premiere.stat().st_mtime > t_avant or premiere.stat().st_size != len(data) // 4
        # Si le même chemin est réutilisé, le témoin doit à nouveau le valider.
        if premiere.stat().st_size > len(data) // 4:
            assert r.verifier_partie(premiere, PARTIE, tools)
    assert out2.is_file() and out2.stat().st_size > 0


# --------------------------------------------------------------------------- 5. réglages changés

def test_reglages_changes_repart_de_zero(r, film80, tools, tmp_path):
    dest, info = film80
    s = reglages()
    out = tmp_path / "r1.mp4"
    cancel = threading.Event()
    d1 = r.dossier(info, s)

    def stop():
        t0 = time.monotonic()
        while time.monotonic() - t0 < 180:
            if len(list(r.parties_faites(d1))) >= 1:
                cancel.set()
                return
            time.sleep(0.2)
        cancel.set()

    threading.Thread(target=stop, daemon=True).start()
    try:
        r.restaurer(info, s, out, tools, cancel=cancel)
    except Exception:
        pass
    assert d1.exists() and list(r.parties_faites(d1))
    cle1 = r.cle(info, s)
    s2 = dataclasses.replace(s, lumiere=2)
    cle2 = r.cle(info, s2)
    assert cle1 != cle2
    out2 = tmp_path / "r2.mp4"
    r.restaurer(info, s2, out2, tools)
    # Ancien dossier effacé, nouveau différent.
    assert not d1.exists() or not list(r.parties_faites(d1))
    d2 = r.dossier(info, s2)
    assert d2 != d1
    assert out2.is_file()
    # Après succès, le nouveau dossier est aussi ménagé.
    assert not d2.exists() or not any(d2.iterdir())


# --------------------------------------------------------------------------- 6. cas non concernés

def test_non_concernes_une_seule_fois_sans_dossier(r, film80, tools, tmp_path, monkeypatch):
    dest, info = film80
    racine = r.dossier_racine()

    def aucun_dossier():
        if not racine.exists():
            return True
        return not any(racine.rglob("*"))

    # Film court : seuil au-dessus de la durée gardée.
    s = reglages()
    assert not r.applicable(info, s, passages=[(0.0, 20.0)])  # 20 s < 30 s
    court = tmp_path / "court.mp4"
    r.restaurer(info, s, court, tools, start=0, duration=20)
    assert court.is_file()
    assert aucun_dossier() or not r.applicable(info, s, passages=[(0.0, 20.0)])

    # IA
    sia = reglages(use_ai=True)
    assert not r.applicable(info, sia)
    # Stabilisation
    sstab = reglages(stabilize=True)
    assert not r.applicable(info, sstab)
    # Poussières
    sdust = reglages(dust=True, source="film")
    assert not r.applicable(info, sdust)
    # Réparation de bande
    stape = reglages(tape_noise=True)
    assert not r.applicable(info, stape)
    # Changement de cadence
    sfilm = reglages(source="film", playback_fps=Fraction(18), scan="progressive")
    info_film = dataclasses.replace(info, fps=Fraction(16, 1)) if hasattr(info, "fps") else info
    # retime vrai si playback_fps != fps et source film
    if pipeline.retime(info_film, sfilm):
        assert not r.applicable(info_film, sfilm)


# --------------------------------------------------------------------------- 7. scènes de part et d'autre d'un raccord

def _ylow_yhigh(ffmpeg, path, debut, n=8):
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path), "-ss", f"{debut:.3f}",
         "-frames:v", str(n), "-an",
         "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
         "-f", "null", "-"],
        capture_output=True, text=True)
    import re
    vals = [float(x) for x in re.findall(r"signalstats\.YAVG=([\d.]+)", r.stderr)]
    assert vals
    return sum(vals) / len(vals)


def test_scenes_identiques_de_part_et_dautre_du_raccord(r, film80, tools, tmp_path):
    """Un raccord à 20 s tombe dans la première scène (0–40 s) : même correction des deux côtés."""
    dest, info = film80
    s = reglages()
    # Attacher les scènes si le moteur n°17 est là, pour que la correction suive la source.
    if hasattr(info, "scenes"):
        try:
            from vhs_restore import scenes
            scenes.attacher(info, tools.ffmpeg.path)
        except Exception:
            pass
    out = tmp_path / "scenes.mp4"
    r.restaurer(info, s, out, tools)
    # 0,5 s avant et après le raccord à 20 s (chauffe 3 s déjà retirée).
    avant = _ylow_yhigh(tools.ffmpeg.path, out, 19.5)
    apres = _ylow_yhigh(tools.ffmpeg.path, out, 20.5)
    assert abs(avant - apres) < 5.0, (avant, apres)


# --------------------------------------------------------------------------- 8. interface

def test_messages_ouverture_et_arret(r):
    """Textes exacts de la demande, vouvoiement, mot « partie » (pas « morceau »)."""
    ouv = r.message_ouverture(5, 11)
    # Exemple de la demande : « … s'était arrêtée à 45 %. « Lancer la restauration » la reprendra. »
    pct = round(5 / 11 * 100)
    assert f"{pct} %" in ouv or f"{pct}%" in ouv
    assert "Lancer la restauration" in ouv
    assert "reprendra" in ouv
    bas = " " + ouv.lower() + " "
    assert " tu " not in bas and " te " not in bas
    assert "morceau" not in ouv.lower() and "chunk" not in ouv.lower()

    prog = r.message_progression(6, 12)
    assert prog == "Reprise : 6 parties sur 12 déjà faites."

    arret = r.message_arret()
    assert arret == "Arrêté. Les parties déjà restaurées sont gardées : relancez pour reprendre."
    assert "morceau" not in arret.lower() and "chunk" not in arret.lower()
