"""Lumière et couleurs scène par scène.

Aujourd'hui, noirs, blancs et dominante sont mesurés une fois pour tout le film :
un intérieur reste sombre, un extérieur délavé. Ici, un passage rapide (160 px de
large, 5 images par seconde) trouve les changements de scène. Chaque scène dure
au moins 2 s. La correction utilise les mêmes plafonds que le film entier
(`safe_levels`, `safe_gains`, niveaux appliqués à moitié) et ne change pas
d'une image à l'autre dans la scène.

Le passage d'une scène à l'autre est progressif sur 0,5 s, sauf à une coupure
franche. FFmpeg reçoit ces valeurs par `sendcmd` (pas une chaîne de `enable=`).
Les temps des commandes sont ceux de la SOURCE : un `-ss` avant l'entrée, un
passage enlevé ou un DVD en plusieurs morceaux ne les décale pas.

Si la lecture est impossible ou trop longue, on ne renvoie aucune scène : la
correction unique d'aujourd'hui reste en place, sans erreur.
"""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue

from .tools import _NO_WINDOW

log = logging.getLogger("vhs_restore")

LARGEUR = 160
HAUTEUR = 90
CADENCE = 5                      # images par seconde lues pour l'analyse
PAS = 1.0 / CADENCE
DUREE_MIN = 2.0                  # une scène plus courte rejoint la voisine
FONDU = 0.5                      # passage progressif, sauf coupure franche
PAS_FONDU = 0.05                 # un cran du fondu (pas une commande par image du film)
# Écart moyen RVB (0-255) entre deux images réduites.
# testsrc2, 5 i/s : au plus ~9 d'une image à la suivante, ~12 depuis la première
# sur 20 s. Une coupure de lumière ou de couleur (intérieur / extérieur) dépasse 18.
SEUIL_FRANC = 18.0
SEUIL_DOUX = 20.0
ANNONCE_S = 3.0                  # au-delà, la durée est dite dans l'attente
BUDGET_MAX = 900.0               # au-delà, on garde la correction unique


class _TropLong(Exception):
    """L'analyse dépasse le temps prévu. Ce n'est pas une erreur du film."""


@dataclass(frozen=True)
class Image:
    """Une image réduite : moyennes RVB et percentiles de luminance (0-255)."""
    t: float
    r: float
    g: float
    b: float
    noir: float
    blanc: float


@dataclass(frozen=True)
class Scene:
    """Une scène au temps de la source.

    `noir` et `blanc` sont les niveaux mesurés (0-1), avant les plafonds.
    `gains` ramène les trois moyennes au même niveau, avant `safe_gains`.
    `rvb` : moyennes R, V, B (0-255), le même seuil que le conseil de dominante.
    `franche` : la coupure qui OUVRE la scène est nette (pas de fondu).
    """
    debut: float
    fin: float
    noir: float
    blanc: float
    gains: tuple[float, float, float]
    franche: bool
    rvb: tuple[float, float, float] = (0.0, 0.0, 0.0)


def _budget(duree: float, morceaux: int) -> float:
    """Temps laissé à la lecture. Environ 0,2 s par seconde de film, plafonné.

    Mesuré sur le film PAL de 32 s : ~0,08 s de lecture par seconde. La marge
    couvre une cassette de deux heures ; au-delà du plafond, correction unique.
    """
    estime = max(0.0, duree) * max(1, morceaux)
    return min(BUDGET_MAX, max(20.0, 15.0 + 0.2 * estime))


def _ecart(a: Image | tuple, b: Image | tuple) -> float:
    ar, ag, ab = (a.r, a.g, a.b) if isinstance(a, Image) else a[:3]
    br, bg, bb = (b.r, b.g, b.b) if isinstance(b, Image) else b[:3]
    return (abs(ar - br) + abs(ag - bg) + abs(ab - bb)) / 3.0


def _mediane(valeurs: list[float]) -> float:
    ordre = sorted(valeurs)
    return ordre[len(ordre) // 2]


def _percentiles(hist: list[int], n: int) -> tuple[int, int]:
    """YLOW / YHIGH de signalstats : 10 % et 90 % des pixels."""
    def a(part: float) -> int:
        cible = n * part
        acc = 0
        for i, c in enumerate(hist):
            acc += c
            if acc >= cible:
                return i
        return 255
    return a(0.10), a(0.90)


def mesurer_image(donnees: bytes, t: float, largeur: int = LARGEUR, hauteur: int = HAUTEUR) -> Image:
    """Moyennes et percentiles d'une image RVB 8 bits."""
    n = largeur * hauteur
    rs = gs = bs = 0
    hist = [0] * 256
    for i in range(0, n * 3, 3):
        r, g, b = donnees[i], donnees[i + 1], donnees[i + 2]
        rs += r
        gs += g
        bs += b
        hist[(77 * r + 150 * g + 29 * b) >> 8] += 1
    noir, blanc = _percentiles(hist, n)
    return Image(t, rs / n, gs / n, bs / n, float(noir), float(blanc))


def _scene_de(images: list[Image], debut: float, fin: float, franche: bool) -> Scene:
    from .probe import cast_gains
    n = len(images)
    r = sum(im.r for im in images) / n
    g = sum(im.g for im in images) / n
    b = sum(im.b for im in images) / n
    return Scene(debut, fin, _mediane([im.noir for im in images]) / 255.0,
                 _mediane([im.blanc for im in images]) / 255.0, cast_gains((r, g, b)), franche,
                 (r, g, b))


def segmenter(images: list[Image], *, pas: float = PAS, duree_min: float = DUREE_MIN,
              duree: float = 0.0) -> tuple[Scene, ...]:
    """Découpe, puis rattache toute scène plus courte que 2 s à la voisine la plus proche."""
    if not images:
        return ()
    bornes = [0]
    franches = [False]
    ancre = images[0]
    for i in range(1, len(images)):
        saut = _ecart(images[i], images[i - 1])
        depuis = _ecart(images[i], ancre)
        if saut >= SEUIL_FRANC:
            bornes.append(i)
            franches.append(True)
            ancre = images[i]
        elif depuis >= SEUIL_DOUX and images[i].t - images[bornes[-1]].t >= duree_min:
            bornes.append(i)
            franches.append(False)
            ancre = images[i]
    morceaux = [(bornes[k], bornes[k + 1] if k + 1 < len(bornes) else len(images), franches[k])
                for k in range(len(bornes))]

    def duree_de(a: int, b: int) -> float:
        if b <= a:
            return 0.0
        return images[b - 1].t - images[a].t + pas

    garde = True
    while garde and len(morceaux) > 1:
        garde = False
        for i, (a, b, _f) in enumerate(morceaux):
            if duree_de(a, b) >= duree_min:
                continue
            if i == 0:
                j = 1
            elif i == len(morceaux) - 1:
                j = i - 1
            else:
                def moyenne(x0: int, x1: int) -> tuple[float, float, float]:
                    bloc = images[x0:x1]
                    n = len(bloc)
                    return (sum(im.r for im in bloc) / n, sum(im.g for im in bloc) / n,
                            sum(im.b for im in bloc) / n)
                gauche = moyenne(morceaux[i - 1][0], morceaux[i - 1][1])
                droite = moyenne(morceaux[i + 1][0], morceaux[i + 1][1])
                j = i - 1 if _ecart(moyenne(a, b), gauche) <= _ecart(moyenne(a, b), droite) else i + 1
            aa, bb, ff = morceaux[i]
            ca, cb, cf = morceaux[j]
            if j < i:
                morceaux[j] = (ca, bb, cf)
                del morceaux[i]
            else:
                morceaux[i] = (aa, cb, ff)
                del morceaux[j]
            garde = True
            break

    scenes: list[Scene] = []
    for i, (a, b, franche) in enumerate(morceaux):
        debut = images[a].t
        fin = images[morceaux[i + 1][0]].t if i + 1 < len(morceaux) else images[b - 1].t + pas
        if i == len(morceaux) - 1 and duree > fin:
            fin = duree
        scenes.append(_scene_de(images[a:b], debut, fin, franche))
    return tuple(scenes)


def _morceaux_de(path: Path) -> list[Path]:
    """Un fichier, ou tous les VOB d'un même titre DVD (le temps repart de zéro au montage)."""
    try:
        from .dvd import parts_for
        trouvés = [Path(p) for p in parts_for(Path(path))]
    except Exception:
        log.warning("scènes : morceaux DVD illisibles", exc_info=True)
        trouvés = []
    return trouvés or [Path(path)]


def _arreter(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    try:
        if proc.stdout:
            proc.stdout.close()
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _lire(ffmpeg: str, entrees: list[str], budget: float) -> list[Image]:
    """Lit le film réduit. Trop long ou illisible : lève, sans rien corriger de travers."""
    if budget <= 0:
        raise _TropLong()
    # Niveaux au format signalstats (pleine image, 5 i/s), puis image réduite pour la
    # couleur et les coupures. Une seule lecture.
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "info", *entrees, "-an",
           "-vf", (f"fps={CADENCE},signalstats,"
                   "metadata=print:key=lavfi.signalstats.YLOW,"
                   "metadata=print:key=lavfi.signalstats.YHIGH,"
                   f"scale={LARGEUR}:{HAUTEUR}:flags=area,format=rgb24"),
           "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, creationflags=_NO_WINDOW)
    # Un fil lit le tube : select() ne sait pas attendre un tube sous Windows.
    file: Queue = Queue()

    def pomper() -> None:
        try:
            assert proc.stdout is not None
            while True:
                bloc = proc.stdout.read(1 << 16)
                if not bloc:
                    file.put(None)
                    return
                file.put(bloc)
        except Exception as exc:          # le processus a été arrêté : on le dit au lecteur
            file.put(exc)

    fil = threading.Thread(target=pomper, daemon=True)
    fil.start()
    journal: list[bytes] = []

    def lire_journal() -> None:
        try:
            assert proc.stderr is not None
            while True:
                bloc = proc.stderr.read(1 << 16)
                if not bloc:
                    return
                journal.append(bloc)
        except Exception:
            return

    fil_err = threading.Thread(target=lire_journal, daemon=True)
    fil_err.start()
    images: list[Image] = []
    taille = LARGEUR * HAUTEUR * 3
    buf = bytearray()
    debut = time.monotonic()
    interrompu = False
    try:
        while True:
            reste = budget - (time.monotonic() - debut)
            if reste <= 0:
                interrompu = True
                raise _TropLong()
            try:
                bloc = file.get(timeout=min(0.5, reste))
            except Empty:
                if proc.poll() is not None and file.empty():
                    break
                continue
            if isinstance(bloc, Exception):
                raise bloc
            if bloc is None:
                break
            buf += bloc
            while len(buf) >= taille:
                images.append(mesurer_image(bytes(buf[:taille]), len(images) * PAS))
                del buf[:taille]
    finally:
        if not interrompu:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        code = proc.poll()
        fil_err.join(timeout=2)
        _arreter(proc)
        fil.join(timeout=2)
    if code not in (0, None) and len(images) < 2:
        raise RuntimeError(f"lecture des scènes interrompue (code {code})")
    texte = b"".join(journal).decode("utf-8", "replace")
    ylow = [float(v) for v in re.findall(r"signalstats\.YLOW=([\d.]+)", texte)]
    yhigh = [float(v) for v in re.findall(r"signalstats\.YHIGH=([\d.]+)", texte)]
    if len(ylow) == len(images) and len(yhigh) == len(images) and images:
        images = [Image(im.t, im.r, im.g, im.b, lo, hi)
                  for im, lo, hi in zip(images, ylow, yhigh)]
    return images


def _entrees(morceaux: list[Path]) -> tuple[list[str], tempfile.TemporaryDirectory | None]:
    if len(morceaux) == 1:
        return ["-i", str(morceaux[0])], None
    dossier = tempfile.TemporaryDirectory(prefix="vhsrestore_scenes_")
    liste = Path(dossier.name) / "concat.txt"
    lignes = []
    for morceau in morceaux:
        nom = Path(morceau).resolve().as_posix().replace("'", "'\\''")
        lignes.append(f"file '{nom}'\n")
    liste.write_text("".join(lignes), encoding="utf-8")
    return ["-f", "concat", "-safe", "0", "-i", str(liste)], dossier


def analyser(ffmpeg: str, path: str | Path, *, budget: float | None = None,
             duree: float = 0.0, morceaux: list[Path] | None = None) -> tuple[Scene, ...]:
    """Scènes du film. Le temps est celui de la source, DVD compris (morceaux à la suite)."""
    chemins = list(morceaux) if morceaux else _morceaux_de(Path(path))
    if budget is None:
        budget = _budget(duree, len(chemins))
    entrees, dossier = _entrees(chemins)
    try:
        try:
            images = _lire(ffmpeg, entrees, budget)
        except _TropLong:
            raise
        except Exception:
            if len(chemins) == 1:
                raise
            # un morceau illisible ne doit pas empêcher le premier
            log.warning("scènes : lecture du DVD réunie impossible, premier morceau seul", exc_info=True)
            images = _lire(ffmpeg, ["-i", str(chemins[0])], budget)
    finally:
        if dossier is not None:
            dossier.cleanup()
    return segmenter(images, duree=duree if len(chemins) == 1 else 0.0)


def mesure_unique(ffmpeg: str, path: str | Path, *, budget: float | None = None,
                  duree: float = 0.0) -> Scene | None:
    """La même mesure, sans découpe : ce que fait la correction unique d'aujourd'hui."""
    try:
        images = _lire(ffmpeg, ["-i", str(path)], budget if budget is not None else _budget(duree, 1))
    except Exception:
        log.warning("scènes : mesure unique impossible", exc_info=True)
        return None
    if not images:
        return None
    fin = images[-1].t + PAS
    return _scene_de(images, 0.0, max(fin, duree), False)


def attacher(info, ffmpeg: str) -> float:
    """Remplit `info.scenes`. Retourne les secondes ajoutées. N'échoue jamais."""
    debut = time.monotonic()
    trop_long = False
    try:
        info.scenes = analyser(ffmpeg, info.path, duree=float(info.duration or 0.0))
    except _TropLong:
        info.scenes = ()
        trop_long = True
        log.info("scènes : analyse trop longue, correction unique conservée")
    except Exception:
        info.scenes = ()
        log.warning("scènes : analyse impossible, correction unique conservée", exc_info=True)
    secondes = time.monotonic() - debut
    info.scenes_secondes = secondes
    if trop_long:
        info.warnings.append(
            "L'analyse des scènes n'a pas pu finir : la lumière et les couleurs "
            "seront corrigées une seule fois pour tout le film.")
    elif secondes >= ANNONCE_S and info.scenes:
        info.warnings.append(
            "L'analyse de la lumière, scène par scène, a pris "
            f"{int(round(secondes))} secondes.")
    log.info("scènes : %d, %.2f s ajoutées", len(info.scenes), secondes)
    return secondes


# ---------------------------------------------------------------- filtres
def _demandee(s) -> bool:
    """La correction automatique est demandée (conseils appliqués, ou réglage avancé).

    La teinte de l'utilisateur ne compte pas : elle s'ajoute par-dessus, comme avant.
    """
    if float(s.level_black) > 1e-3 or float(s.level_white) < 1.0 - 1e-3:
        return True
    return any(abs(float(g) - 1.0) >= 0.02 for g in (s.gain_r, s.gain_g, s.gain_b))


def _niveaux_conseilles(scene: Scene) -> bool:
    """Même porte que le conseil « niveaux » : noirs gris et blancs ternes ensemble."""
    lo, hi = float(scene.noir) * 255.0, float(scene.blanc) * 255.0
    return hi - lo < 140 and lo > 35 and hi < 190


def _dominante_conseillee(scene: Scene) -> bool:
    """Même porte que le conseil « dominante » : 15 niveaux d'écart entre R, V et B."""
    r, g, b = scene.rvb
    return max(r, g, b) - min(r, g, b) > 15


def _valeurs(scene: Scene, s) -> tuple[float, float, float, float, float]:
    """(noir, blanc, rr, gg, bb) après les mêmes plafonds qu'aujourd'hui, et la teinte."""
    from .pipeline import PAS_TEINTE, cran, safe_gains, safe_levels
    if _niveaux_conseilles(scene):
        lo, hi = safe_levels(float(scene.noir), float(scene.blanc))
        if not (0.02 < lo < hi < 0.98 and hi - lo < 0.75):
            lo, hi = 0.0, 1.0
        else:
            lo, hi = lo / 2.0, hi + (1.0 - hi) / 2.0
    else:
        lo, hi = 0.0, 1.0
    base = scene.gains if _dominante_conseillee(scene) else (1.0, 1.0, 1.0)
    t = cran(s.teinte)
    brut = (base[0] * (1 + PAS_TEINTE * t), base[1], base[2] * (1 - PAS_TEINTE * t))
    rr, gg, bb = safe_gains(brut)
    return lo, hi, rr, gg, bb


def _melange(a: tuple[float, ...], b: tuple[float, ...], part: float) -> tuple[float, ...]:
    return tuple(x + (y - x) * part for x, y in zip(a, b))


def points_de_commande(scenes: tuple[Scene, ...], s) -> list[tuple[float, tuple[float, ...]]]:
    """Instants (temps source) et valeurs. Fondu de 0,5 s, sauf coupure franche."""
    if not scenes:
        return []
    valeurs = [_valeurs(sc, s) for sc in scenes]
    points: dict[int, tuple[float, ...]] = {round(scenes[0].debut * 1000): valeurs[0]}
    for i in range(1, len(scenes)):
        t = scenes[i].debut
        avant, apres = valeurs[i - 1], valeurs[i]
        if scenes[i].franche or avant == apres:
            points[round(t * 1000)] = apres
            continue
        debut = max(scenes[i - 1].debut, t - FONDU / 2)
        fin = min(scenes[i].fin, t + FONDU / 2)
        if fin - debut < PAS_FONDU:
            points[round(t * 1000)] = apres
            continue
        n = max(2, round((fin - debut) / PAS_FONDU))
        for k in range(n + 1):
            part = k / n
            points[round((debut + (fin - debut) * part) * 1000)] = _melange(avant, apres, part)
    return [(ms / 1000.0, points[ms]) for ms in sorted(points)]


def _scene_au(scenes: tuple[Scene, ...], t: float) -> Scene:
    for scene in scenes:
        if scene.debut <= t < scene.fin:
            return scene
    return scenes[-1] if t >= scenes[-1].debut else scenes[0]


def _valeur_au(points: list[tuple[float, tuple[float, ...]]], t: float,
               defaut: tuple[float, ...]) -> tuple[float, ...]:
    courant = defaut
    for instant, valeur in points:
        if instant <= t + 1e-4:
            courant = valeur
        else:
            break
    return courant


def _commande(instant: float, valeur: tuple[float, ...], niveaux: bool, melange: bool) -> str:
    lo, hi, rr, gg, bb = valeur
    morceaux = []
    if niveaux:
        morceaux += [f"colorlevels rimin {lo:.4f}", f"colorlevels gimin {lo:.4f}",
                     f"colorlevels bimin {lo:.4f}", f"colorlevels rimax {hi:.4f}",
                     f"colorlevels gimax {hi:.4f}", f"colorlevels bimax {hi:.4f}"]
    if melange:
        morceaux += [f"colorchannelmixer rr {rr:.4f}", f"colorchannelmixer gg {gg:.4f}",
                     f"colorchannelmixer bb {bb:.4f}"]
    return f"{instant:.3f} " + ", ".join(morceaux)


def _actif_niveaux(v: tuple[float, ...]) -> bool:
    return v[0] > 1e-4 or v[1] < 1.0 - 1e-4


def _actif_melange(v: tuple[float, ...]) -> bool:
    return any(abs(g - 1.0) >= 0.02 for g in v[2:])


def filtres(info, s, origine: float = 0.0) -> list[str] | None:
    """Filtres `sendcmd` + niveaux / dominante, ou None pour la correction unique.

    `origine` est le temps source de la première image vue par le filtre
    (un `-ss` avant l'entrée remet l'horloge du filtre à zéro).
    """
    scenes = tuple(getattr(info, "scenes", ()) or ())
    if len(scenes) < 2 or not _demandee(s):
        return None
    points = points_de_commande(scenes, s)
    if not points:
        return None
    niveaux = any(_actif_niveaux(v) for _, v in points)
    melange = any(_actif_melange(v) for _, v in points)
    if not niveaux and not melange:
        return None
    lignes = []
    precedente = None
    for instant, valeur in points:
        if valeur == precedente:
            continue
        lignes.append(_commande(instant, valeur, niveaux, melange))
        precedente = valeur
    commande = "sendcmd=c='" + ";".join(lignes) + ";'"
    actuel = _valeur_au(points, origine, _valeurs(_scene_au(scenes, origine), s))
    lo, hi, rr, gg, bb = actuel
    bloc: list[str] = []
    if origine > 1e-3:
        bloc.append(f"setpts=PTS+{origine:.6f}/TB")
    bloc.append(commande)
    if melange:
        bloc.append(f"colorchannelmixer=rr={rr:.4f}:gg={gg:.4f}:bb={bb:.4f}")
    if niveaux:
        bloc.append(f"colorlevels=rimin={lo:.4f}:gimin={lo:.4f}:bimin={lo:.4f}:"
                    f"rimax={hi:.4f}:gimax={hi:.4f}:bimax={hi:.4f}")
    if origine > 1e-3:
        bloc.append(f"setpts=PTS-{origine:.6f}/TB")
    return bloc
