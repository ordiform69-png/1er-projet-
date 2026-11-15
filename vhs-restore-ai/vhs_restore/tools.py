"""Détection des logiciels externes et exécution sûre des commandes.

Toutes les commandes sont lancées sous forme de liste d'arguments
(jamais via un shell) : pas d'injection possible, espaces et accents gérés.
"""
from __future__ import annotations

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
IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Filtres FFmpeg indispensables à la chaîne de restauration.
QTGMC_SCRIPT = Path(__file__).resolve().parent / "qtgmc.vpy"
REQUIRED_FILTERS = ("idet", "bwdif", "hqdn3d", "removegrain", "eq", "cas", "scale", "hstack", "fftdnoiz",
                    "signalstats", "fieldmatch", "deflicker", "setpts", "atempo")
STAB_FILTERS = ("vidstabdetect", "vidstabtransform")   # libvidstab : facultatif


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


def _find(env: str, names: Iterable[str], subdirs: Iterable[str],
          exts: Iterable[str] = (EXE,)) -> str | None:
    """Ordre de recherche : variable d'environnement, dossier tools/ de l'appli, PATH."""
    value = os.environ.get(env)
    if value and Path(value).is_file():
        return value
    for sub in subdirs:
        for n in names:
            for ext in exts:
                p = (Path(sys.executable).parent if sub == "@python" else TOOLS_DIR / sub) / (n + ext)
                if p.is_file():
                    return str(p)
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None



def run_capture(cmd: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    """Commande courte : renvoie stdout/stderr séparés (UTF-8)."""
    log.debug("exec: %s", cmd)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
                          creationflags=_NO_WINDOW)


def _version(path: str) -> str:
    try:
        out = run_capture([path, "-version"], timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"version\s+(\S+)", out)
    return m.group(1) if m else ""


def detect_tools() -> Toolset:
    ff = Tool("FFmpeg", _find("VHSRA_FFMPEG", ["ffmpeg"], ["ffmpeg/bin", "ffmpeg"]))
    fp = Tool("FFprobe", _find("VHSRA_FFPROBE", ["ffprobe"], ["ffmpeg/bin", "ffmpeg"]))
    re_ = Tool("Real-ESRGAN", _find("VHSRA_REALESRGAN", ["realesrgan-ncnn-vulkan"],
                                    ["realesrgan", "realesrgan-ncnn-vulkan"]))
    missing: list[str] = []
    vidstab = False
    for t in (ff, fp):
        if t.path:
            t.version = _version(t.path)
    if ff.path:
        try:
            listing = run_capture([ff.path, "-hide_banner", "-filters"], timeout=15).stdout
            present = {line.split()[1] for line in listing.splitlines() if len(line.split()) > 2}
            missing = [f for f in REQUIRED_FILTERS if f not in present]
            vidstab = all(f in present for f in STAB_FILTERS)
        except (OSError, subprocess.TimeoutExpired) as exc:
            ff.problem = f"FFmpeg ne répond pas : {exc}"
    if re_.path:
        # L'exécutable n'a pas d'option --version : on vérifie la présence du modèle.
        models = Path(re_.path).parent / "models"
        if not (models / "realesrgan-x4plus.param").is_file():
            re_.problem = f"modèle realesrgan-x4plus absent de {models}"
        re_.version = "ncnn-vulkan"
    from . import dust
    ts = Toolset(ff, fp, re_, missing, detect_qtgmc(), vidstab, dust.available())
    log.info("Outils : ffmpeg=%s (%s) ffprobe=%s realesrgan=%s %s qtgmc=%s %s filtres manquants=%s",
             ff.path, ff.version, fp.path, re_.path, re_.problem, ts.vspipe.path, ts.vspipe.problem, missing)
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
