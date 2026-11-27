"""Détection des logiciels externes et exécution sûre des commandes.

Toutes les commandes sont lancées sous forme de liste d'arguments
(jamais via un shell) : pas d'injection possible, espaces et accents gérés.
"""
from __future__ import annotations

from contextvars import ContextVar
import time
from contextlib import contextmanager
import tempfile
import collections
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

log = logging.getLogger("vhs_restore")

# Application empaquetée (PyInstaller) : tools\ est à côté de l'exécutable.
APP_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
           else Path(__file__).resolve().parent.parent)
TOOLS_DIR = APP_DIR / "tools"


def user_tools_dir() -> Path:
    """Outils facultatifs installés depuis l'application (bouton « Installer ») : dans le profil
    de l'utilisateur, pour qu'ils servent encore après une nouvelle version du logiciel."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return Path(base) / "VHSRestoreAI" / "tools"

IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Son AAC : méthode « fast » de l'encodeur. La méthode par défaut (« twoloop ») de FFmpeg 9.1,
# celui que le logiciel installe sous Windows, tourne sans fin sur un son bref suivi d'un silence
# parfait (mesuré : mono 192 kbit/s figé, « fast » fini en 0,1 s). Un raccord de coupe en crée.
AAC = ("-c:a", "aac", "-aac_coder", "fast")

# Filtres FFmpeg indispensables à la chaîne de restauration.
QTGMC_SCRIPT = Path(__file__).resolve().parent / "qtgmc.vpy"
REQUIRED_FILTERS = ("idet", "bwdif", "hqdn3d", "removegrain", "eq", "cas", "scale", "hstack", "fftdnoiz",
                    "signalstats", "fieldmatch", "deflicker", "setpts", "atempo")
STAB_FILTERS = ("vidstabdetect", "vidstabtransform")   # libvidstab : facultatif
AUDIO_FILTERS = ("afftdn", "adeclick", "dynaudnorm", "adelay", "atrim", "bandreject", "arnndn",
                 "adeclip", "pan", "highpass", "equalizer", "aeval")  # facultatifs


class ToolError(RuntimeError):
    """Erreur compréhensible par l'utilisateur."""


class Cancelled(Exception):
    """Traitement annulé par l'utilisateur."""


@dataclass
class Tool:
    name: str
    path: str | None = None
    version: str = ""
    problem: str = ""

    @property
    def ok(self) -> bool:
        return self.path is not None and not self.problem


@dataclass
class Toolset:
    ffmpeg: Tool
    ffprobe: Tool
    realesrgan: Tool
    missing_filters: list[str] = field(default_factory=list)
    vspipe: Tool = field(default_factory=lambda: Tool("QTGMC"))
    vidstab: bool = False
    dust: bool = False          # module « poussières et rayures » (Analog Repair) installé
    deepfilter: Tool = field(default_factory=lambda: Tool("DeepFilterNet"))
    audio_filters: frozenset[str] = frozenset()
    rnnoise_model: str | None = None     # modèle RNNoise (Xiph) pour arnndn, livré avec l'application
    colorizer: Tool = field(default_factory=lambda: Tool("Colorisation (DDColor)"))   # photos, facultatif
    losslesscut: Tool = field(default_factory=lambda: Tool("LosslessCut"))   # montage simple, facultatif
    shotcut: Tool = field(default_factory=lambda: Tool("Shotcut"))           # montage complet, facultatif

    @property
    def colorize_available(self) -> bool:
        return self.colorizer.ok

    @property
    def deepfilter_available(self) -> bool:
        return self.deepfilter.ok

    @property
    def dust_available(self) -> bool:
        return self.dust

    @property
    def stab_available(self) -> bool:
        return self.vidstab

    @property
    def ai_available(self) -> bool:
        return self.realesrgan.ok

    @property
    def qtgmc_available(self) -> bool:
        return self.vspipe.ok

    def require_ffmpeg(self) -> None:
        for t in (self.ffmpeg, self.ffprobe):
            if not t.path:
                raise ToolError(
                    f"{t.name} est introuvable. Lancez installer.bat "
                    f"ou placez {t.name}{EXE} dans le dossier tools\\ffmpeg\\bin.")
        if self.missing_filters:
            raise ToolError("Votre FFmpeg est trop ancien ou incomplet (filtres manquants : "
                            + ", ".join(self.missing_filters) + "). Version 5.0 ou plus requise.")


def est_fichier(chemin, refus: list[tuple[str, str]] | None = None) -> bool:
    """`is_file()` qui ne plante pas. Chez l'utilisateur, « Accès refusé » (WinError 5) sur
    realesrgan-ncnn-vulkan.exe, gardé par un antivirus, arrêtait le logiciel au démarrage."""
    try:
        return Path(chemin).is_file()
    except OSError as exc:
        log.warning("fichier inaccessible : %s (%s)", chemin, exc)
        if refus is not None:
            refus.append((str(chemin), exc.strerror or str(exc)))
        return False


def _find(env: str, names: Iterable[str], subdirs: Iterable[str],
          exts: Iterable[str] = (EXE,), refus: list[tuple[str, str]] | None = None) -> str | None:
    """Ordre de recherche : variable d'environnement, dossier tools/ de l'appli, outils
    installés depuis l'application (profil de l'utilisateur), PATH."""
    value = os.environ.get(env)
    if value and est_fichier(value, refus):
        return value
    for base in (TOOLS_DIR, user_tools_dir()):
        for sub in subdirs:
            for n in names:
                for ext in exts:
                    p = (Path(sys.executable).parent if sub == "@python" else base / sub) / (n + ext)
                    if est_fichier(p, refus):
                        return str(p)
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None



class FichierOccupe(ToolError):
    """Le résultat est fini, mais un autre programme garde le fichier ouvert : il est laissé en place."""


class CopieIncomplete(ToolError):
    """Le principal est déjà publié. Seule la copie facultative reste à faire."""
    def __init__(self, principal, message, interrompue):
        super().__init__(message)
        self.principal = principal
        self.interrompue = interrompue


@contextmanager
def copie_annexe(principal, libelle):
    try:
        yield
    except (Cancelled, ToolError, OSError, subprocess.TimeoutExpired) as exc:
        fin = "a été interrompue." if isinstance(exc, Cancelled) else "a échoué."
        raise CopieIncomplete(principal, f"{libelle} {fin}", isinstance(exc, Cancelled)) from exc


def cacher(chemin: Path) -> None:
    """Sous Windows, un point au début ne cache rien : on pose l'attribut caché."""
    if os.name != "nt":
        return
    import ctypes
    ctypes.windll.kernel32.SetFileAttributesW(str(chemin), 0x2)  # FILE_ATTRIBUTE_HIDDEN


def partiel_unique(final: Path) -> Path:
    verifier_chemin(final)
    verifier_chemin(final.parent / ("vhs-XXXXXXXX.partiel" + final.suffix))
    fd, nom = tempfile.mkstemp(prefix="vhs-", suffix=".partiel" + final.suffix, dir=final.parent)
    os.close(fd)
    return Path(nom)


@contextmanager
def reserver_sorties(principal, annexes):
    """Un verrou exclusif par sortie, partagé entre instances, sur le disque cible."""
    if not principal.parent.is_dir():
        raise ToolError(f"Dossier de sortie introuvable : {principal.parent}")
    numero = 1
    while True:
        candidat = principal if numero == 1 else principal.with_name(
            f"{principal.stem} ({numero}){principal.suffix}")
        verrous = []
        try:
            for cible in [candidat, *annexes(candidat)]:
                verrou = cible.with_name("." + cible.name + ".reserve")
                verifier_chemin(verrou)
                verrou.touch(exist_ok=False)
                cacher(verrou)
                verrous.append(verrou)
                if cible.exists():
                    raise FileExistsError(cible)
        except FileExistsError:
            numero += 1
        except BaseException:
            for verrou in verrous:
                effacer(verrou)
            raise
        else:
            try:
                yield candidat
            finally:
                for verrou in verrous:
                    effacer(verrou)
            return
        for verrou in verrous:
            effacer(verrou)


def _publier(part, final):
    if IS_WIN:
        os.rename(part, final)  # Windows refuse une destination existante, y compris sur FAT32.
    else:
        os.link(part, final)
        effacer(part)


def finaliser(part: Path, final: Path, essais: int = 10) -> None:
    """Met le résultat terminé à sa place. Sous Windows, un lecteur vidéo ou l'antivirus peut garder
    le fichier ouvert quelques instants : on réessaie, puis on explique au lieu de tout perdre."""
    import time
    for n in range(essais):
        try:
            _publier(part, final)
            return
        except FileExistsError:
            raise FichierOccupe(f"Un fichier porte déjà ce nom. Le résultat est dans {part}. "
                                "Choisissez un autre nom pour le conserver.") from None
        except PermissionError:
            if n == essais - 1:
                raise FichierOccupe(
                    f"Le travail est terminé, mais le fichier « {Path(part).name} » est ouvert dans un autre "
                    "programme (un lecteur vidéo ?). Fermez ce programme, puis renommez ce fichier en "
                    f"« {Path(final).name} ». Il se trouve dans le dossier {Path(part).parent}.") from None
            time.sleep(1)


def effacer(path: Path) -> None:
    """Supprime un fichier inachevé sans masquer l'erreur d'origine (dossier protégé, fichier ouvert)."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def verifier_chemin(path: Path, *, origine: bool = False) -> None:
    """Windows refuse souvent les chemins de plus de 260 caractères : on le dit AVANT de travailler."""
    if IS_WIN and len(str(Path(path).resolve())) >= 250:
        n = len(str(Path(path)))
        if origine:
            raise ToolError(
                f"Le chemin du film d'origine est trop long pour Windows ({n} caractères). "
                "Déplacez le film dans un dossier plus court (par exemple « Vidéos »), puis recommencez.")
        raise ToolError(f"Le chemin du fichier à créer est trop long pour Windows ({n} caractères). "
                        "Choisissez un dossier de sortie plus court (par exemple « Vidéos »), ou raccourcissez "
                        "le nom du film, puis recommencez.")


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def ff_input(path: str | Path) -> list[str]:
    """« -i fichier » pour FFmpeg. Une image dont le chemin contient « % » (ex. « Photo%20dimanche.jpg »,
    nom venu d'Internet) serait lue comme une suite numérotée (%20d) : on l'interdit."""
    p = str(path)
    if "%" in p and Path(p).suffix.lower() in IMAGE_EXTS:
        return ["-f", "image2", "-pattern_type", "none", "-i", p]
    return ["-i", p]


_arret = ContextVar("arret_sondage", default=None)


@contextmanager
def sondages_annulables(event):
    jeton = _arret.set(event)
    try:
        yield
    finally:
        _arret.reset(jeton)


def capture(cmd, *, timeout, **options):
    event = _arret.get()
    if event is None:
        return subprocess.run(cmd, timeout=timeout, **options)
    if event.is_set():
        raise Cancelled()
    options.pop("capture_output")
    limite = time.monotonic() + timeout
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options) as proc:
        try:
            while not event.is_set():
                reste = limite - time.monotonic()
                if reste <= 0:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                try:
                    stdout, stderr = proc.communicate(timeout=min(0.15, reste))
                    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    continue
            raise Cancelled()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()


def run_capture(cmd: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    """Commande courte : renvoie stdout/stderr séparés (UTF-8)."""
    log.debug("exec: %s", cmd)
    return capture(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
                          creationflags=_NO_WINDOW)


def _version(path: str) -> str:
    try:
        out = run_capture([path, "-version"], timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"version\s+(\S+)", out)
    return m.group(1) if m else ""


def _rnnoise_model() -> str | None:
    """Modèle std de RNNoise (BSD). Variable, dossier tools, ou copie livrée."""
    env = os.environ.get("VHSRA_RNNOISE")
    if env and est_fichier(env):
        return env
    names = [
        Path(__file__).resolve().parent / "models" / "rnnoise_std.rnnn",
        TOOLS_DIR / "rnnoise" / "rnnoise_std.rnnn",
        APP_DIR / "_internal" / "vhs_restore" / "models" / "rnnoise_std.rnnn",
        APP_DIR / "vhs_restore" / "models" / "rnnoise_std.rnnn",
    ]
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        names.insert(0, Path(mei) / "vhs_restore" / "models" / "rnnoise_std.rnnn")
    for p in names:
        if est_fichier(p):
            return str(p)
    return None


REFUS_ACCES = ("Windows refuse l'accès à ce fichier ({raison}). Un antivirus le bloque peut-être : "
               "regardez l'« Historique de protection » de la Sécurité Windows, ou redémarrez "
               "l'ordinateur puis réinstallez-le.")


def _outil(nom: str, env: str, names: list[str], subdirs: list[str]) -> Tool:
    """Un outil trouvé, absent, ou présent mais refusé par Windows (dit, jamais un plantage)."""
    refus: list[tuple[str, str]] = []
    t = Tool(nom, _find(env, names, subdirs, refus=refus))
    if t.path is None and refus:
        t.path, raison = refus[0]
        t.problem = REFUS_ACCES.format(raison=raison)
    return t


def detect_tools() -> Toolset:
    ff = _outil("FFmpeg", "VHSRA_FFMPEG", ["ffmpeg"], ["ffmpeg/bin", "ffmpeg"])
    fp = _outil("FFprobe", "VHSRA_FFPROBE", ["ffprobe"], ["ffmpeg/bin", "ffmpeg"])
    re_ = _outil("Real-ESRGAN", "VHSRA_REALESRGAN", ["realesrgan-ncnn-vulkan"],
                 ["realesrgan", "realesrgan-ncnn-vulkan"])
    missing: list[str] = []
    vidstab = False
    audio_present: set[str] = set()
    for t in (ff, fp):
        if t.path and not t.problem:
            t.version = _version(t.path)
    if ff.path and not ff.problem:
        try:
            listing = run_capture([ff.path, "-hide_banner", "-filters"], timeout=15).stdout
            present = {line.split()[1] for line in listing.splitlines() if len(line.split()) > 2}
            missing = [f for f in REQUIRED_FILTERS if f not in present]
            vidstab = all(f in present for f in STAB_FILTERS)
            audio_present = {f for f in AUDIO_FILTERS if f in present}
        except (OSError, subprocess.TimeoutExpired) as exc:
            ff.problem = f"FFmpeg ne répond pas : {exc}"
    if re_.path and not re_.problem:
        # L'exécutable n'a pas d'option --version : on vérifie la présence du modèle.
        models = Path(re_.path).parent / "models"
        if not est_fichier(models / "realesrgan-x4plus.param"):
            re_.problem = f"modèle realesrgan-x4plus absent de {models}"
        re_.version = "ncnn-vulkan"
    df = _outil("DeepFilterNet", "VHSRA_DEEPFILTER", ["deep-filter"], ["deepfilter", "DeepFilterNet"])
    if df.path and not df.problem:
        df.version = "deep-filter"
    from . import colorize, dust
    model = _rnnoise_model()
    ts = Toolset(ff, fp, re_, missing, detect_qtgmc(), vidstab, dust.available(),
                 df, frozenset(audio_present), model, colorize.detect())
    ts.losslesscut = _outil("LosslessCut", "VHSRA_LOSSLESSCUT", ["LosslessCut"], ["losslesscut"])
    ts.shotcut = _outil("Shotcut", "VHSRA_SHOTCUT", ["shotcut"], ["shotcut"])
    log.info("Outils : ffmpeg=%s (%s) ffprobe=%s realesrgan=%s %s qtgmc=%s %s "
             "deepfilter=%s rnnoise=%s colorisation=%s %s audio=%s filtres manquants=%s",
             ff.path, ff.version, fp.path, re_.path, re_.problem, ts.vspipe.path, ts.vspipe.problem,
             df.path, model, ts.colorizer.path, ts.colorizer.problem, sorted(audio_present), missing)
    return ts


def explain_vs_error(text: str) -> str:
    """Traduit les erreurs VapourSynth les plus courantes en message clair."""
    m = re.search(r"No attribute with the name (\w+)", text)
    if m:
        return f"plugin VapourSynth manquant : « {m.group(1)} » (relancez installer.bat -AvecQTGMC)"
    m = re.search(r"No module named '([\w.]+)'", text)
    if m:
        return f"module Python manquant : « {m.group(1)} » (relancez installer.bat -AvecQTGMC)"
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return lines[-1][:300] if lines else "erreur inconnue"


def detect_qtgmc() -> Tool:
    """vspipe (VapourSynth) + vs-jetpack + plugins, vérifiés par un essai à blanc de qtgmc.vpy."""
    t = Tool("QTGMC", _find("VHSRA_VSPIPE", ["vspipe"], ["@python", "vapoursynth"],
                            (EXE,)))
    if not t.path:
        return t
    try:
        v = run_capture([t.path, "--version"], timeout=30)
        m = re.search(r"Core (R\d+)", v.stdout + v.stderr)
        t.version = m.group(1) if m else ""
        chk = run_capture([t.path, "-a", "check=1", "-e", "1", str(QTGMC_SCRIPT), "."], timeout=120)
        if chk.returncode != 0:
            t.problem = explain_vs_error(chk.stderr + chk.stdout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        t.problem = f"vspipe ne répond pas : {exc}"
    return t


ProgressFn = Callable[[float, str], None]


def run(cmd: list[str], *, cancel: threading.Event | None = None,
        on_line: Callable[[str], None] | None = None,
        poll: Callable[[], None] | None = None,
        what: str = "commande", feeder: list[str] | None = None,
        cwd: str | Path | None = None, env: dict[str, str] | None = None) -> list[str]:
    """Exécute une commande longue, annulable. Lève ToolError si échec.

    stdout et stderr sont fusionnés et lus ligne par ligne dans un thread,
    ce qui évite tout blocage de tampon. Renvoie les dernières lignes.
    feeder : commande dont la sortie standard alimente l'entrée de cmd (tube
    sans shell, ex. vspipe → ffmpeg) ; elle est arrêtée avec cmd en cas d'annulation.
    cwd : dossier de travail (permet de nommer un fichier dans un filtre FFmpeg sans
    avoir à échapper un chemin Windows complet).
    """
    log.info("exec: %s%s", subprocess.list2cmdline(feeder) + " | " if feeder else "",
             subprocess.list2cmdline(cmd))
    tail: collections.deque[str] = collections.deque(maxlen=40)
    feed_proc: subprocess.Popen | None = None
    feed_err: list[str] = []
    try:
        if feeder:
            feed_proc = subprocess.Popen(feeder, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)

            def drain() -> None:  # stderr du fournisseur : gardé pour le diagnostic
                for raw in feed_proc.stderr:
                    feed_err.append(raw.decode("utf-8", "replace").rstrip())
                    del feed_err[:-60]

            threading.Thread(target=drain, daemon=True).start()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=feed_proc.stdout if feed_proc else subprocess.DEVNULL,
                                cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
        if feed_proc:
            feed_proc.stdout.close()  # seul ffmpeg garde le tube ouvert
    except OSError as exc:
        if feed_proc:
            terminate(feed_proc)
        raise ToolError(f"Impossible de lancer {what} : {exc}") from exc

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            tail.append(line)
            if on_line:
                try:
                    on_line(line)
                except Exception:  # ne jamais tuer la lecture pour un callback
                    log.exception("callback on_line")

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    while True:
        try:
            proc.wait(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            pass
        if cancel is not None and cancel.is_set():
            terminate(proc)
            if feed_proc:
                terminate(feed_proc)
            th.join(timeout=2)
            raise Cancelled()
        if poll:
            poll()
    th.join(timeout=5)
    lines = list(tail)
    if feed_proc:
        try:
            feed_proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            terminate(feed_proc)
        if feed_proc.returncode != 0:
            log.error("fournisseur %s a échoué (code %s):\n%s", feeder[0], feed_proc.returncode,
                      "\n".join(feed_err))
            raise ToolError(f"QTGMC (VapourSynth) a échoué : {explain_vs_error(chr(10).join(feed_err))}")
    if proc.returncode != 0:
        log.error("%s a échoué (code %s):\n%s", what, proc.returncode, "\n".join(lines))
        detail = "\n".join(l for l in lines[-6:] if "=" not in l or " " in l)
        raise ToolError(f"{what} a échoué (code {proc.returncode}).\n{detail}".strip())
    return lines


def terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
