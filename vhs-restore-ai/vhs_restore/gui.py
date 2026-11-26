"""Interface PySide6. Les traitements tournent dans un QThread : l'interface
reste réactive, et rien ne tourne en arrière-plan quand l'application est inactive."""
from __future__ import annotations

import dataclasses
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
import atexit
import weakref
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (QEvent, QObject, QPoint, QRect, QSettings, QSize, QStandardPaths, Qt, QThread,
                            QTimer, QUrl, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QApplication, QButtonGroup,
                               QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QFrame, QGraphicsDropShadowEffect, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox,
                               QVBoxLayout, QWidget, QPlainTextEdit)

from . import ecran, ergonomie, icons, installer, lumiere, partage, photo, pipeline, theme, vides, vignettes
from .dvd import open_media
from .probe import MediaInfo, cast_gains
from .advice import advise
from .eta import Eta
from .advice import apply as apply_advice
from .profiles import PROFILES, RESOLUTIONS, profile_for
from .tools import Cancelled, ToolError, Toolset, detect_tools, run_capture

log = logging.getLogger("vhs_restore")

# Fenêtres encore vivantes, et fils qui effacent les dossiers d'images.
# À la fermeture : on arrête les minuteurs, on tue les FFmpeg d'images, on attend les fils.
# Pas de os._exit : la fin normale de Python doit rester (autres atexit, journaux).
_FENETRES: weakref.WeakSet = weakref.WeakSet()
_NETTOYEURS: list[threading.Thread] = []


def _eteindre_a_la_sortie() -> None:
    """Plus aucun fil d'images ni FFmpeg. Sans os._exit : Python finit normalement."""
    if getattr(_eteindre_a_la_sortie, "_fait", False):
        return
    _eteindre_a_la_sortie._fait = True  # type: ignore[attr-defined]
    for win in list(_FENETRES):
        try:
            fab = getattr(win, "_fab", None)
            if fab is not None:
                fab.stop()
            for nom in ("_pompe", "_replan_images", "_attente_moment"):
                timer = getattr(win, nom, None)
                if timer is not None:
                    timer.stop()
            for fil in list(getattr(win, "_fils", []) or []):
                try:
                    if fil.isRunning():
                        fil.wait(2000)
                except RuntimeError:
                    pass
        except RuntimeError:
            pass
    try:
        vignettes.tuer_extractions()
    except Exception:
        pass
    for win in list(_FENETRES):
        fab = getattr(win, "_fab", None)
        if fab is None:
            continue
        for fil in list(getattr(fab, "fils", ())):
            fil.join(2)
        try:
            win._fab = None
        except RuntimeError:
            pass
    for fil in list(_NETTOYEURS):
        fil.join(3)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    # Pas de os._exit : un vrai plantage futur ne doit pas être masqué.


atexit.register(_eteindre_a_la_sortie)


VIDEO_FILTER = ("Vidéos et photos (*.avi *.mp4 *.mkv *.mov *.mpg *.mpeg *.m2t *.mts *.ts *.dv *.vob *.wmv *.m4v "
                "*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp);;Tous les fichiers (*)")


from .tools import CopieIncomplete, sondages_annulables


class Worker(QThread):
    """Exécute fn(cancel, progress) hors du thread graphique."""
    progressed = Signal(float, str)
    succeeded = Signal(object)
    failed = Signal(str)
    copie_incomplete = Signal(object)
    choix_ia = Signal(object)
    cancelled = Signal()

    def __init__(self, fn: Callable[[threading.Event, Callable[[float, str], None]], Any]):
        super().__init__()
        self.fn = fn
        self.cancel_event = threading.Event()

    def demander_ia(self, duree, en_4k, inconnue):
        reponse = []
        pret = threading.Event()
        self.choix_ia.emit((duree, en_4k, inconnue, reponse, pret))
        while not pret.wait(0.1):
            if self.cancel_event.is_set():
                raise Cancelled()
        return reponse[0]

    def run(self) -> None:
        _keep_awake(True)
        try:
            with sondages_annulables(self.cancel_event):
                res = self.fn(self.cancel_event, lambda f, m: self.progressed.emit(f, m))
        except CopieIncomplete as exc:
            self.copie_incomplete.emit(exc)
        except Cancelled:
            self.cancelled.emit()
        except ToolError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # erreur imprévue : journalisée en détail
            log.error("échec\n%s", traceback.format_exc())
            self.failed.emit(f"Erreur inattendue : {exc}\nConsultez le journal pour le détail.")
        else:
            self.succeeded.emit(res)
        finally:
            _keep_awake(False)


def _keep_awake(on: bool) -> None:
    """Empêche la veille Windows pendant un film long. Sans effet ailleurs."""
    if sys.platform != "win32":
        return
    import ctypes
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if on else ES_CONTINUOUS
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


class CompareView(QWidget):
    """Image avant/après avec rideau : la gauche montre l'original, la droite la
    restauration ; déplacer la souris (ou cliquer) déplace la séparation."""

    def __init__(self) -> None:
        super().__init__()
        self.before: QPixmap | None = None
        self.after: QPixmap | None = None
        self.split = 0.5
        self.mode = "split"              # split (glisser) | before (original seul) | after (restauré seul)
        self.after_label = "APRÈS"
        self.setMinimumSize(480, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self._moment: QPixmap | None = None
        self._moment_texte = ""
        self.montrer_position = False

    def set_still(self, path: Path) -> None:
        pm = QPixmap(str(path))
        half = pm.width() // 2
        self.before, self.after = pm.copy(0, 0, half, pm.height()), pm.copy(half, 0, half, pm.height())
        self.update()

    def clear(self) -> None:
        self.before = self.after = None
        self.update()

    def poser_moment(self, chemin: str, temps: float | None) -> None:
        """Image du film tant qu'aucun aperçu n'a été fait. L'aperçu la remplace."""
        pix = QPixmap(chemin)
        if pix.isNull():
            return
        self._moment = pix
        self._moment_texte = "Photo d’origine" if temps is None else f"Image du film à {_duree(temps)}"
        self.setAccessibleDescription(self._moment_texte)
        if self.before is None or self.montrer_position:
            self.update()

    def oublier_moment(self) -> None:
        self._moment = None
        self._moment_texte = ""
        if self.before is None or self.montrer_position:
            self.update()

    def set_mode(self, mode: str) -> None:
        """Comparer sans geste précis : original seul, restauré seul, ou les deux (souris)."""
        self.mode = mode if mode in ("before", "after") else "split"
        if self.mode == "split":
            self.split = 0.5
        self.update()

    def set_after_label(self, text: str) -> None:
        """Étiquette de droite : « APRÈS », ou « COULEURS IA » pour une photo colorisée."""
        if text == "RESTAURÉ":
            text = "APRÈS"
        self.after_label = text
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self.before is not None and self.mode == "split":
            self.split = min(1.0, max(0.0, e.position().x() / max(1, self.width())))
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        frame = self.rect().adjusted(1, 1, -2, -2)
        p.setPen(QPen(QColor("#1d5c68"), 1))
        p.setBrush(QColor(theme.MONITEUR))
        p.drawRoundedRect(frame, 12, 12)
        inner = frame.adjusted(10, 10, -10, -10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#0a0e13"))
        p.drawRoundedRect(inner, 6, 6)
        if self.before is None or self.after is None or self.montrer_position:
            if self._moment is not None and not self._moment.isNull():
                size = self._moment.size().scaled(inner.size(), Qt.KeepAspectRatio)
                r = QRect(QPoint(0, 0), size)
                r.moveCenter(inner.center())
                p.setRenderHint(QPainter.SmoothPixmapTransform)
                p.drawPixmap(r, self._moment)
                p.setPen(QColor("#f3f6fa"))
                f = p.font()
                f.setPointSizeF(max(f.pointSizeF(), 13))
                p.setFont(f)
                p.drawText(inner.adjusted(8, 8, -8, -8), Qt.AlignBottom | Qt.AlignHCenter, self._moment_texte)
                return
            p.setPen(QColor(theme.MONITEUR_TEXTE))
            f = p.font()
            f.setPointSizeF(max(f.pointSizeF(), 13))
            p.setFont(f)
            # retour à la ligne : à 150 %, la phrase dépassait du cadre noir et se coupait
            p.drawText(inner.adjusted(16, 8, -16, -8), Qt.AlignCenter | Qt.TextWordWrap,
                       _insecables("L'avant / après apparaîtra ici\n\n"
                                   "(choisissez un film ou une photo, puis « Voir l'avant / après »)")
                       .replace(" / ", "\u00a0/\u00a0"))
            return
        size = self.before.size().scaled(inner.size(), Qt.KeepAspectRatio)
        r = QRect(QPoint(0, 0), size)
        r.moveCenter(inner.center())
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.mode in ("before", "after"):          # une seule image, plein cadre
            p.drawPixmap(r, self.before if self.mode == "before" else self.after)
            self._badges(p, r, ("AVANT",) if self.mode == "before" else (self.after_label,))
            return
        p.drawPixmap(r, self.after)
        cut = int(r.width() * self.split)
        sx = self.before.width() * self.split
        p.drawPixmap(QRect(r.x(), r.y(), cut, r.height()), self.before,
                     QRect(0, 0, int(sx), self.before.height()))
        x = r.x() + cut
        p.setPen(QPen(QColor(theme.MONITEUR_ACCENT), 2))
        p.drawLine(x, r.top(), x, r.bottom())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.MONITEUR_ACCENT))
        p.drawEllipse(QPoint(x, r.center().y()), 5, 5)
        self._badges(p, r, ("AVANT", self.after_label))

    def _badges(self, p: QPainter, r: QRect, texts: tuple) -> None:
        """Pastilles « AVANT » (à gauche) et « APRÈS » (à droite) sur l'image.
        « COULEURS IA » reste tel quel quand la photo est colorisée."""
        f = p.font()
        f.setPointSizeF(max(f.pointSizeF(), 13))
        f.setBold(True)
        p.setFont(f)
        fm = p.fontMetrics()
        h = fm.height() + 10
        largeur = sum(fm.horizontalAdvance(t) + 22 for t in ("AVANT", self.after_label)) + 36
        etroit = r.width() < largeur    # photo en hauteur : « Après » passe en bas
        for text in texts:
            left = text == "AVANT"
            w = fm.horizontalAdvance(text) + 22
            y = r.bottom() - h - 12 if (etroit and not left) else r.y() + 12
            box = QRect(r.x() + 12 if left else r.right() - w - 12, y, w, h)
            p.setPen(QPen(QColor(theme.MONITEUR_ACCENT), 1))
            p.setBrush(QColor(16, 32, 40, 210))
            p.drawRoundedRect(box, 4, 4)
            p.setPen(QColor("#f3f6fa"))
            p.drawText(box, Qt.AlignCenter, text)


class DropZone(QLabel):
    dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__("Déposez un film ou une photo ici\nou cliquez sur « Choisir un film ou une photo »")
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(72)
        self.setObjectName("depot")

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        urls = e.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.dropped.emit(urls[0].toLocalFile())


def _insecables(texte: str) -> str:
    """Espaces insécables dans « … » : le guillemet ne se retrouve jamais seul en bout de ligne."""
    return texte.replace("« ", "«\u00a0").replace(" »", "\u00a0»")


class Statut(QLabel):
    def setText(self, texte: str) -> None:
        super().setText(_insecables(texte))


class _DropFilter(QObject):
    """Accepte un film ou une photo déposé n'importe où sur la page simple."""

    def __init__(self, on_drop) -> None:
        super().__init__()
        self._on = on_drop

    def eventFilter(self, obj, e) -> bool:  # noqa: N802
        if e.type() in (QEvent.DragEnter, QEvent.DragMove) and e.mimeData().hasUrls():
            e.acceptProposedAction()
            return True
        if e.type() == QEvent.Drop:
            urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if urls:
                self._on(urls[0])
                return True
        return False


class _HoverHalo(QObject):
    """Léger halo coloré au survol. Rien n'est animé tant que la souris n'est pas dessus."""

    def __init__(self, color: str) -> None:
        super().__init__()
        self._color = QColor(color)

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if ev.type() == QEvent.Enter and obj.isEnabled():
            eff = QGraphicsDropShadowEffect(obj)
            eff.setBlurRadius(26)
            eff.setOffset(0, 0)
            c = QColor(self._color)
            c.setAlpha(170)
            eff.setColor(c)
            obj.setGraphicsEffect(eff)
        elif ev.type() in (QEvent.Leave, QEvent.Hide) or (
                ev.type() == QEvent.EnabledChange and not obj.isEnabled()):
            obj.setGraphicsEffect(None)
        return False


class Carte(QFrame):
    """Carte « console » : en-tête avec icône néon, titre, numéro d'étape, coins façon HUD."""

    def __init__(self, title: str, icon: str, number: str = "", subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("carte")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon, 26))
        ic.setFixedSize(30, 30)
        ic.setAlignment(Qt.AlignCenter)
        ic.setObjectName("carteIcone")
        t = QLabel(title.upper())
        t.setObjectName("carteTitre")
        head.addWidget(ic)
        head.addWidget(t)
        self.sous: QLabel | None = None
        if subtitle:
            st = self.sous = QLabel(subtitle)
            st.setObjectName("carteSous")
            head.addWidget(st)
        head.addStretch(1)
        if number:
            n = QLabel(number.zfill(2))
            n.setObjectName("carteNumero")
            head.addWidget(n)
        outer.addLayout(head)
        line = QFrame()
        line.setObjectName("carteFilet")
        outer.addWidget(line)
        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        outer.addLayout(self.body, 1)

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(theme.ACCENT)
        c.setAlpha(170)
        p.setPen(QPen(c, 2))
        r, k = self.rect().adjusted(3, 3, -4, -4), 14
        for (x, y, dx, dy) in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                               (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            p.drawLine(x, y + dy * 6, x, y + dy * k)
            p.drawLine(x + dx * 6, y, x + dx * k, y)


class ProfileTile(QPushButton):
    """Tuile de profil (réglages libres) : icône, nom, petite phrase.

    Le nom peut tenir sur deux lignes. La largeur minimale reste fixe pour que
    les trois tuiles de « Qualité » ne forcent pas un défilement horizontal.
    """

    def __init__(self, name: str, icon: str, tagline: str) -> None:
        super().__init__(name)
        self.icon_name, self.tagline = icon, tagline
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(104)
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(160, max(104, self.minimumHeight()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(150, self.minimumHeight() or 80)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on, en = self.isChecked(), self.isEnabled()
        r = self.rect().adjusted(1, 1, -2, -2)
        if on:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor(theme.TUILE_ACTIVE))
            g.setColorAt(1, QColor(theme.CARTE_SUR))
            p.setBrush(g)
            p.setPen(QPen(QColor(theme.ACCENT), 2))
        else:
            p.setBrush(QColor(theme.CARTE_SUR))
            p.setPen(QPen(QColor(theme.ACCENT if self.underMouse() and en else theme.BORD), 1.2))
        p.drawRoundedRect(r, 12, 12)
        col = theme.ACCENT if (on or self.underMouse()) and en else theme.ACCENT_SOURD
        p.drawPixmap(16, 16, icons.pixmap(self.icon_name, 32, col))
        f = QFont(theme.DISPLAY_FAMILY or p.font().family())
        f.setPointSizeF(14)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXTE))
        p.drawText(QRect(56, 8, r.width() - 68, 46), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.text())
        f = QFont(theme.BODY_FAMILY or p.font().family())
        f.setPointSizeF(12)
        p.setFont(f)
        p.setPen(QColor(theme.TEXTE_DOUX))
        p.drawText(QRect(16, 54, r.width() - 24, max(16, r.height() - 60)),
                   Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.tagline)
        if on:                                    # voyant allumé
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT))
            p.drawEllipse(QPoint(r.right() - 14, r.top() + 14), 4, 4)


TOOL_INFO = {
    "ffmpeg": ("FFmpeg", "Moteur de traitement de l'image et du son, livré avec le logiciel. "
                         "Indispensable."),
    "qtgmc": ("QTGMC", "Désentrelaceur de référence pour les cassettes entrelacées : un peu plus fin que "
                       "celui du logiciel (bwdif), mais plusieurs fois plus lent. Il demande Python et "
                       "VapourSynth, il ne s'installe donc pas depuis cette fenêtre. Le désentrelaceur "
                       "intégré suffit pour des films de famille."),
    "realesrgan": ("Real-ESRGAN", "Agrandissement par intelligence artificielle (profil Nettoyage au plus fort, photos). "
                                  "Demande une carte graphique compatible Vulkan. L'IA peut inventer des "
                                  "détails, surtout sur les petits visages : vérifiez toujours l'aperçu."),
    "deepfilter": ("DeepFilterNet", "Nettoyage poussé des voix pour le profil Nettoyage au plus fort, sur le processeur. "
                                    "Les rires, la musique et les bruits d'ambiance restent."),
    "colorisation": ("Colorisation", "Colorisation des photos noir et blanc par l'IA (DDColor). Les couleurs "
                                     "sont inventées ; une copie à part est écrite, le noir et blanc est gardé."),
    "losslesscut": ("LosslessCut", "Montage simple : couper, retirer des passages, découper en morceaux et "
                                   "assembler plusieurs films, sans perte de qualité. Logiciel libre (GPL), "
                                   "en français, qui s'ouvre dans sa propre fenêtre avec votre film."),
    "shotcut": ("Shotcut", "Montage complet : titres, fondus, musique, transitions. Logiciel libre (GPL), "
                           "en français, plus riche mais plus complexe. Votre film s'y ouvre : faites-le "
                           "glisser dans la ligne de temps pour commencer."),
}

PROFILE_LOOK = {"fidele": ("bouclier", "Garde l'aspect d'époque"),
                "equilibre": ("balance", "Bon équilibre"),
                "maximum": ("fusee", "Plus long")}


def _demarrer(programme: str, args: list[str], dossier: str) -> bool:
    """Lance un programme séparé (logiciel de montage, redémarrage) sans l'attendre."""
    from PySide6.QtCore import QProcess
    res = QProcess.startDetached(programme, args, dossier)
    return bool(res[0] if isinstance(res, tuple) else res)


def _duree(sec: float) -> str:
    """Durée lisible : « 31 secondes », « 12 min 05 s », « 1 h 04 min »."""
    sec = max(0, int(round(sec)))
    if sec < 60:
        return f"{sec} seconde{'s' if sec > 1 else ''}"
    if sec < 3600:
        return f"{sec // 60} min {sec % 60:02d} s"
    return f"{sec // 3600} h {sec % 3600 // 60:02d} min"


def _lire_temps(text: str) -> float:
    """« 1 min 05 s », « 1:05 », « 90 » ou « 1 h 04 min » → secondes. Sans chiffre : 0."""
    brut = text.strip().lower().replace(",", ".")
    if not any(c.isdigit() for c in brut):
        return 0.0
    if ":" in brut:
        try:
            nums = [float(p) for p in brut.split(":")]
        except ValueError:
            return 0.0
        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        if len(nums) == 3:
            return nums[0] * 3600 + nums[1] * 60 + nums[2]
    m = re.search(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*min)?\s*(?:(\d+(?:\.\d+)?)\s*(?:s|sec|seconde|secondes)?)?",
                  brut)
    if m and any(m.groups()):
        h, mi, s = m.group(1), m.group(2), m.group(3)
        return (int(h) * 3600 if h else 0) + (int(mi) * 60 if mi else 0) + (float(s) if s else 0)
    nombre = "".join(ch for ch in brut if ch.isdigit() or ch == ".")
    try:
        return float(nombre) if nombre else 0.0
    except ValueError:
        return 0.0


class TempsSpin(QDoubleSpinBox):
    """Secondes en interne (`.value()`), affichage « 1 min 05 s ». Les flèches avancent d'une seconde."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDecimals(0)
        self.setSingleStep(1)
        self.setAccelerated(True)
        self.setAlignment(Qt.AlignRight)
        self.setMinimumHeight(44)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def wheelEvent(self, event) -> None:  # noqa: N802
        # Sans le focus, la molette doit seulement faire défiler la page.
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)

    def textFromValue(self, value: float) -> str:  # noqa: N802
        return _duree(value)

    def valueFromText(self, text: str) -> float:  # noqa: N802
        return _lire_temps(text)


def _en_clair(a) -> str:
    """Un conseil de l'analyse, dit avec des mots de tous les jours."""
    if a.key == "channel":
        return "son qui s'annule en partie" if a.fix.get("audio_channel_fix") == "phase" else "son d'un seul côté"
    return {"clip": "son saturé par moments", "hum": "ronflement électrique", "wind": "vent dans le micro",
            "levels": "image un peu terne", "cast": "couleurs un peu tirées",
            "edges": "bords abîmés"}.get(a.key, a.text)


def _ilabel(text: str, icon: str) -> QWidget:
    """Libellé précédé d'une petite icône néon."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    ic = QLabel()
    ic.setPixmap(icons.pixmap(icon, 18))
    h.addWidget(ic)
    h.addWidget(QLabel(text))
    return w


def _with_icon(widget: QAbstractButton, icon: str) -> QAbstractButton:
    widget.setIcon(icons.icon(icon))
    widget.setIconSize(QSize(20, 20))
    return widget


def _wrap(layout: QHBoxLayout) -> QWidget:
    """Met une ligne de réglages dans un conteneur, pour pouvoir la cacher d'un coup."""
    w = QWidget()
    layout.setContentsMargins(0, 0, 0, 0)
    w.setLayout(layout)
    return w


_MAX_COUPES = 8

# Guide des coupes au milieu : les trois textes selon l'état. Même texte dans
# le guide sous la barre, dans « Comment faire ? » et dans « Aide ».
GUIDE_COUPES_AUCUNE = (
    "1. Glissez jusqu'au début du moment à enlever. "
    "2. Cliquez sur « Couper ici ». "
    "3. Glissez jusqu'à la reprise, puis « Le film reprend ici ».")
GUIDE_COUPES_OUVERTE = (
    "Maintenant, glissez jusqu'à l'endroit où le film reprend, "
    "puis cliquez sur « Le film reprend ici ».")
GUIDE_COUPES_FAITE = (
    "1 passage enlevé (en doré). Pour en enlever un autre, "
    "recommencez ailleurs sur la barre (8 au plus).")
GUIDE_COUPES_CARRES = (
    "Les carrés blancs sur la barre se tirent pour ajuster le passage. "
    "« Annuler la dernière coupe » remet le dernier passage.")


def _texte_guide_coupes(ouverte: bool, n: int) -> str:
    """Texte du guide selon l'état : aucune coupe, coupe commencée, ou passage enlevé."""
    if ouverte:
        return GUIDE_COUPES_OUVERTE
    if n <= 0:
        return GUIDE_COUPES_AUCUNE
    if n == 1:
        return GUIDE_COUPES_FAITE
    return (f"{n} passages enlevés (en doré). Pour en enlever un autre, "
            "recommencez ailleurs sur la barre (8 au plus).")


# travaux de plusieurs minutes : phrase de patience, confirmation avant d'arrêter
_TRAVAUX_LONGS = ("export", "dossier", "vides_copie", "separation", "partage")
_MIN_COUPE = 0.5


def _bouton_secondaire(texte: str, accessible: str, *, elargi: bool = True) -> QPushButton:
    """Gros bouton lisible, qui peut rétrécir : pas de défilement horizontal."""
    b = QPushButton(texte)
    b.setObjectName("secondaire")
    b.setMinimumHeight(44)
    b.setMinimumWidth(0)
    b.setSizePolicy(QSizePolicy.Expanding if elargi else QSizePolicy.Minimum, QSizePolicy.Fixed)
    b.setCursor(Qt.PointingHandCursor)
    b.setAccessibleName(accessible)
    return b


def _fusionner_coupes(coupes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Passages à enlever, du plus tôt au plus tard.

    Ce qui se recouvre, se touche, ou laisse moins d'une demi-seconde entre les deux
    devient un seul passage.
    """
    ordre: list[tuple[float, float]] = []
    for a, b in coupes:
        a, b = float(a), float(b)
        if b < a:
            a, b = b, a
        if b - a < _MIN_COUPE:
            continue
        ordre.append((a, b))
    ordre.sort()
    if not ordre:
        return []
    fusion: list[tuple[float, float]] = [ordre[0]]
    for a, b in ordre[1:]:
        pa, pb = fusion[-1]
        if a - pb < _MIN_COUPE:
            fusion[-1] = (pa, max(pb, b))
        else:
            fusion.append((a, b))
    return fusion


def _coupes_depuis_gardes(duree: float, gardes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Inverse les intervalles gardés : ce qu'il faut enlever, pas ce qu'il faut garder."""
    trous: list[tuple[float, float]] = []
    curseur = 0.0
    for a, b in gardes:
        if a - curseur >= _MIN_COUPE:
            trous.append((float(curseur), float(a)))
        curseur = float(b)
    if duree - curseur >= _MIN_COUPE:
        trous.append((float(curseur), float(duree)))
    return trous


def _memes_coupes(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
    def cle(xs: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return sorted((round(x, 3), round(y, 3)) for x, y in xs)
    return cle(a) == cle(b)


class _Boite:
    """Résultats des fils Python, lus ensuite par le fil de l'interface."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.vignettes: list[tuple[int, str, int]] = []
        self.moments: list[tuple[float, str, int]] = []

    def ajouter_vignette(self, index: int, chemin: str, generation: int) -> None:
        with self._lock:
            self.vignettes.append((index, chemin, generation))

    def ajouter_moment(self, instant: float, chemin: str, generation: int) -> None:
        with self._lock:
            self.moments.append((instant, chemin, generation))

    def prendre(self) -> tuple[list[tuple[int, str, int]], list[tuple[float, str, int]]]:
        with self._lock:
            v, m = self.vignettes, self.moments
            self.vignettes, self.moments = [], []
        return v, m


class _Fab:
    """Un lot de petites images, et une image du moment à la fois. Fils démons :
    ils ne sont pas des QThread, donc la fermeture de Python ne plante pas."""

    def __init__(self, ffmpeg: str, info: MediaInfo, dossier: Path, moments: list[float],
                 lw: int, lh: int, mw: int, mh: int, generation: int, boite: _Boite) -> None:
        self.ffmpeg, self.info = ffmpeg, info
        self.dossier = Path(dossier)
        self.lw, self.lh, self.mw, self.mh = lw, lh, mw, mh
        self.generation = generation
        self.boite = boite
        self.annuler = threading.Event()
        self._lock = threading.Lock()
        self._moment_id = 0
        self._procs_lot: list = []
        self._procs_moment: list = []
        self.fils: list[threading.Thread] = []
        fil = threading.Thread(target=self._lot, args=(list(moments),), name="vhs-vignettes", daemon=True)
        fil.start()
        self.fils.append(fil)

    def _lot(self, moments: list[float]) -> None:
        for i, instant in enumerate(moments):
            if self.annuler.is_set():
                return
            dest = self.dossier / f"v{i:03d}.png"
            if vignettes.extraire(self.ffmpeg, self.info, instant, dest,
                                  self.lw, self.lh, self.annuler, self._procs_lot):
                self.boite.ajouter_vignette(i, str(dest), self.generation)

    def demander(self, instant: float, generation: int) -> None:
        with self._lock:
            self._moment_id += 1
            ident = self._moment_id
            for proc in list(self._procs_moment):
                try:
                    if proc.poll() is None:
                        proc.kill()
                except OSError:
                    pass
        fil = threading.Thread(target=self._moment, args=(float(instant), generation, ident),
                               name="vhs-moment", daemon=True)
        fil.start()
        self.fils.append(fil)

    def _moment(self, instant: float, generation: int, ident: int) -> None:
        if self.annuler.is_set():
            return
        dest = self.dossier / f"m{ident}.png"
        if not vignettes.extraire(self.ffmpeg, self.info, instant, dest,
                                  self.mw, self.mh, self.annuler, self._procs_moment):
            return
        with self._lock:
            if ident != self._moment_id or self.annuler.is_set():
                return
        self.boite.ajouter_moment(instant, str(dest), generation)

    def stop(self) -> None:
        self.annuler.set()
        for proc in list(self._procs_lot) + list(self._procs_moment):
            try:
                if proc.poll() is None:
                    proc.kill()
            except OSError:
                pass


class _Ruban(QWidget):
    """Barre du film, dessinée pour cet écran. Un clic ou un glisser place l'extrait.

    En doré : ce qui ne sera pas restauré. Le curseur est le moment choisi.
    Les bords dorés se tirent pour ajuster un passage.
    """

    clique = Signal(float)
    borde = Signal(int, bool, float)
    borde_fini = Signal()
    valider = Signal()
    largeur_changee = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.duree = 0.0
        self.position = 0.0
        self.debut = 0.0
        self.fin = 0.0
        self.coupes: list[tuple[float, float]] = []
        self._glisse_bord: tuple[int, bool] | None = None
        self._glisse_piste = False
        # bord doré saisi mais pas encore tiré : un simple clic ne doit pas modifier la coupe
        self._bord_saisi: tuple[int, bool] | None = None
        self._x_appui = 0.0
        self._vignettes: list[QPixmap] = []
        self._compacte = False
        self.setMinimumHeight(56)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("Barre du film")
        self.setAccessibleDescription(
            "Faites glisser pour vous placer. Tirez les bords dorés pour ajuster un passage enlevé.")

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(400, 64 if self._compacte else 88)

    def vider_images(self, nombre: int) -> None:
        """Places grises en attendant les petites images. `nombre` 0 : barre comme avant."""
        self._vignettes = [QPixmap() for _ in range(max(0, int(nombre)))]
        self.update()

    def poser_image(self, index: int, chemin: str) -> None:
        if not (0 <= index < len(self._vignettes)):
            return
        pix = QPixmap(chemin)
        if not pix.isNull():
            self._vignettes[index] = pix
            self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.largeur_changee.emit(max(0, self._zone().width()))

    def definir(self, duree: float, position: float, debut: float, fin: float,
                coupes: list[tuple[float, float]]) -> None:
        # Ne pas interrompre un glisser : cette méthode est rappelée pendant qu'on tire un bord.
        self.duree = max(0.0, float(duree or 0))
        self.position = float(position or 0)
        self.debut = float(debut or 0)
        self.fin = float(fin or 0)
        self.coupes = list(coupes)
        self.update()

    def _zone(self):
        bas = 22 if self.height() >= 80 else 10
        return self.rect().adjusted(1, 16, -1, -bas)

    def _x_de(self, t: float) -> float:
        r = self._zone()
        if self.duree <= 0 or r.width() <= 0:
            return float(r.left())
        borne = max(0.0, min(self.duree, float(t)))
        return float(r.left()) + (borne / self.duree) * float(r.width())

    def _temps(self, x: float) -> float:
        r = self._zone()
        if self.duree <= 0 or r.width() <= 0:
            return 0.0
        return max(0.0, min(self.duree, (float(x) - float(r.left())) / float(r.width()) * self.duree))

    PRISE_BORD = 22.0      # px de chaque côté du bord : une prise de 44 px en tout
    SEUIL_GLISSER = 4.0    # px : en dessous, c'est un clic (le curseur se place), pas un glisser

    def _bord_sous(self, x: float) -> tuple[int, bool] | None:
        """Bord doré : prise de 44 px en tout (22 de chaque côté). Le plus proche l'emporte."""
        if self.duree <= 0 or not self.coupes:
            return None
        choisi: tuple[int, bool] | None = None
        ecart = self.PRISE_BORD + 1.0
        for i, (a, b) in enumerate(self.coupes):
            for est_fin, moment in ((False, a), (True, b)):
                d = abs(float(x) - self._x_de(moment))
                if d <= self.PRISE_BORD and d < ecart:
                    choisi = (i, est_fin)
                    ecart = d
        return choisi

    def _curseur_pour(self, x: float) -> None:
        self.setCursor(Qt.SizeHorCursor if self._bord_sous(x) is not None else Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.duree > 0:
            x = float(event.position().x())
            self._curseur_pour(x)
            bord = self._bord_sous(x)
            if bord is not None:
                # le bord ne bouge qu'une fois vraiment tiré : un clic près d'une coupe la
                # rallongeait sans prévenir (des minutes sur une longue cassette)
                self._bord_saisi = bord
                self._x_appui = x
                self._glisse_bord = None
                self._glisse_piste = False
            else:
                self._glisse_bord = None
                self._glisse_piste = True
                self.clique.emit(self._temps(x))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        x = float(event.position().x())
        self._curseur_pour(x)
        if self.duree > 0 and (event.buttons() & Qt.LeftButton):
            if self._bord_saisi is not None and abs(x - self._x_appui) >= self.SEUIL_GLISSER:
                self._glisse_bord, self._bord_saisi = self._bord_saisi, None
            if self._glisse_bord is not None:
                indice, est_fin = self._glisse_bord
                self.borde.emit(indice, est_fin, self._temps(x))
            elif self._glisse_piste:
                self.clique.emit(self._temps(x))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            bord = self._glisse_bord
            saisi = self._bord_saisi
            self._glisse_bord = None
            self._bord_saisi = None
            self._glisse_piste = False
            if bord is not None:
                self.borde_fini.emit()
            elif saisi is not None and self.duree > 0:      # simple clic près d'un bord : se placer
                self.clique.emit(self._temps(float(event.position().x())))
            self._curseur_pour(float(event.position().x()))
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.duree <= 0:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key_Left:
            self.clique.emit(max(0.0, self.position - 1.0))
        elif event.key() == Qt.Key_Right:
            self.clique.emit(min(self.duree, self.position + 1.0))
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            self.valider.emit()
        else:
            super().keyPressEvent(event)

    def _dessiner_images(self, p: QPainter, r: QRect) -> None:
        """Petites images du film, ou un gris tant qu'elles ne sont pas prêtes."""
        n = len(self._vignettes)
        if n <= 0 or r.width() <= 0:
            return
        p.save()
        p.setClipRect(r.adjusted(2, 2, -2, -2))
        slot = r.width() / n
        for i, pix in enumerate(self._vignettes):
            x = int(r.left() + i * slot)
            suivant = int(r.left() + (i + 1) * slot)
            dest = QRect(x, r.top() + 3, max(1, suivant - x), max(1, r.height() - 6))
            if pix.isNull():
                p.fillRect(dest, QColor("#5c6570"))
                continue
            scaled = pix.scaled(dest.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            sx = max(0, (scaled.width() - dest.width()) // 2)
            sy = max(0, (scaled.height() - dest.height()) // 2)
            p.drawPixmap(dest, scaled, QRect(sx, sy, dest.width(), dest.height()))
        p.restore()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._zone()
        p.setPen(QPen(QColor(theme.BORD), 1))
        p.setBrush(QColor(theme.PISTE))
        p.drawRoundedRect(r, 6, 6)
        self._dessiner_images(p, r)
        if self.duree <= 0:
            p.end()
            return

        fin = self.fin if self.fin > 0 else self.duree
        p.setPen(Qt.NoPen)
        a_images = any(not pix.isNull() for pix in self._vignettes)
        bleu = QColor(theme.ACCENT)
        dore = QColor(theme.AMBRE)
        if a_images:
            bleu.setAlpha(55)
            dore.setAlpha(150)
        p.setBrush(bleu)
        x0, x1 = self._x_de(self.debut), self._x_de(fin)
        p.drawRect(int(x0), r.top() + 4, max(2, int(x1 - x0)), r.height() - 8)
        p.setBrush(dore)
        for a, b in self.coupes:
            xa, xb = self._x_de(a), self._x_de(b)
            p.drawRect(int(xa), r.top() + 4, max(2, int(xb - xa)), r.height() - 8)
        xp = int(self._x_de(self.position))
        p.setPen(QPen(QColor(theme.TEXTE), 3))
        p.drawLine(xp, r.top(), xp, r.bottom())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.TEXTE))
        p.drawPolygon([QPoint(xp, r.top() - 1), QPoint(xp - 7, r.top() - 12), QPoint(xp + 7, r.top() - 12)])
        cote = 12
        milieu = r.top() + 4 + (r.height() - 8) / 2.0
        p.setPen(QPen(QColor("#1a1206"), 1))
        p.setBrush(QColor("#ffffff"))
        for a, b in self.coupes:
            for moment in (a, b):
                cx = self._x_de(moment)
                p.drawRoundedRect(int(round(cx - cote / 2)), int(round(milieu - cote / 2)), cote, cote, 2, 2)
        if self.height() >= 80:
            p.setPen(QColor(theme.TEXTE_DOUX))
            bas = QRect(4, self.height() - 18, max(0, self.width() - 8), 16)
            p.drawText(bas, Qt.AlignLeft | Qt.AlignVCenter, _duree(0))
            p.drawText(bas, Qt.AlignHCenter | Qt.AlignVCenter, _duree(self.duree / 2))
            p.drawText(bas, Qt.AlignRight | Qt.AlignVCenter, _duree(self.duree))
        p.end()


class BarreFilm(_Ruban):
    """Barre de la page simple. Un findChild(BarreFilm) trouve celle-ci, pas l'autre."""


class BarreCompacte(_Ruban):
    """Même barre, dans les options avancées. Ce n'est pas une BarreFilm."""


class SchemaCoupe(QWidget):
    """Petit schéma dessiné : barre, zone dorée, carrés blancs. Pas de fichier image."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(56)
        self.setMaximumHeight(72)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName("Schéma : la zone dorée est le passage enlevé")

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(4, 14, -4, -14)
        if r.width() < 20 or r.height() < 8:
            p.end()
            return
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.PISTE))
        p.drawRoundedRect(r, 6, 6)
        dore = QColor(theme.AMBRE)
        dore.setAlpha(180)
        p.setBrush(dore)
        xa = r.left() + r.width() // 3
        xb = r.left() + 2 * r.width() // 3
        p.drawRect(xa, r.top() + 3, max(2, xb - xa), r.height() - 6)
        cote = 12
        milieu = r.top() + r.height() / 2.0
        p.setPen(QPen(QColor("#1a1206"), 1))
        p.setBrush(QColor("#ffffff"))
        for cx in (xa, xb):
            p.drawRoundedRect(int(round(cx - cote / 2)), int(round(milieu - cote / 2)),
                              cote, cote, 2, 2)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, tools: Toolset | None = None) -> None:
        super().__init__()
        self.setWindowTitle("VHS Restore AI")
        self.resize(1100, 760)
        app = QApplication.instance()
        if app is not None:
            theme.apply(app)
        self.tools = tools or detect_tools()
        self.info: MediaInfo | None = None
        self.worker: Worker | None = None
        self.preview: pipeline.PreviewResult | None = None
        self.preview_dir = Path(tempfile.mkdtemp(prefix="vhsrestore_apercu_"))
        self._coupes: list[tuple[float, float]] = []
        self._coupe_ouverte: float | None = None
        self.lumiere = lumiere.Lumiere(self)          # lumière et couleurs : avant de lancer
        self._build()
        self._refresh_tools()
        self._update_state()
        _FENETRES.add(self)

    # ------------------------------------------------------------ construction
    def _commandes_accueil(self) -> None:
        self.help_btn = QPushButton("Aide")
        self.help_btn.setIcon(icons.icon("info"))
        self.help_btn.clicked.connect(self.show_welcome)
        self.help_btn.setAccessibleName("Aide")
        self.help_btn.setAccessibleDescription("Explique les trois étapes. Le bouton entouré est celui à utiliser.")
        self.theme_btn = QPushButton("Affichage clair" if theme.MODE == "sombre" else "Affichage sombre")
        self.theme_btn.setIcon(icons.icon("soleil"))
        self.theme_btn.setToolTip("Change les couleurs de la fenêtre (fond clair ou fond sombre). "
                                  "Le logiciel redémarre.")
        self.theme_btn.setAccessibleName("Changer l'affichage, clair ou sombre")
        self.theme_btn.setAccessibleDescription("Le logiciel redémarre. Rien n'est perdu.")
        self.theme_btn.clicked.connect(self.toggle_theme)
        for b in (self.help_btn, self.theme_btn):
            b.setObjectName("bandeauBouton")
            b.setCursor(Qt.PointingHandCursor)
            b.setIconSize(QSize(20, 20))
            b.setMinimumHeight(44)
        self._taille_btns: dict[int, QPushButton] = {}
        self._echelle = 1.0
        for pct, lib in ((100, "A−"), (125, "A"), (150, "A+")):
            b = QPushButton(lib)
            b.setObjectName("bandeauBouton")
            b.setMinimumSize(44, 44)
            b.setCursor(Qt.PointingHandCursor)
            b.setAccessibleName(f"Taille du texte {pct} %")
            b.setAccessibleDescription("Agrandit ou réduit les textes.")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.clicked.connect(lambda _=False, p=pct: self.set_taille_texte(p))
            self._taille_btns[pct] = b
        self.s_info = QLabel("Choisissez un film ou une photo.")
        self.s_info.setWordWrap(True)
        self.s_info.setObjectName("infos")
        self.s_info.setMinimumWidth(80)
        self.s_fini = QFrame()
        self.s_fini.setObjectName("fini")
        fv = QVBoxLayout(self.s_fini)
        fv.setContentsMargins(16, 14, 16, 16)
        fv.setSpacing(10)
        self.s_fini_titre = QLabel("C'est prêt")
        self.s_fini_titre.setObjectName("finiTitre")
        self.s_fini_texte = QLabel("")
        self.s_fini_texte.setObjectName("finiTexte")
        self.s_fini_texte.setWordWrap(True)
        self.s_fini_texte.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fv.addWidget(self.s_fini_titre)
        self.s_voir = QPushButton("Regarder le film")
        self.s_voir.setObjectName("action")
        self.s_ouvrir = QPushButton("Ouvrir le dossier")
        self.s_autre = QPushButton("Restaurer un autre film")
        for b in (self.s_voir, self.s_ouvrir, self.s_autre):
            b.setMinimumHeight(52)
            b.setCursor(Qt.PointingHandCursor)
            if b is not self.s_voir:
                b.setObjectName("secondaire")
        self.s_voir.clicked.connect(self._voir_resultat)
        self.s_ouvrir.clicked.connect(self._ouvrir_dossier_fini)
        self.s_autre.clicked.connect(self._restaurer_autre)
        self.s_vides = _with_icon(QPushButton("Retirer les passages vides"), "ciseaux")
        self.s_vides.setToolTip("Neige, écran bleu ou noir en début, en fin ou au milieu de la cassette : "
                                "le logiciel les repère et propose une copie sans eux.")
        self.s_montage = _with_icon(QPushButton("Faire un montage"), "film")
        self.s_montage.setToolTip("Couper, assembler, ajouter un titre : ouvre votre film dans un "
                                  "logiciel de montage gratuit.")
        self.s_nommer = _with_icon(QPushButton("Nommer ce film"), "etiquette")
        self.s_nommer.setToolTip("« Noël 1988 » plutôt qu'un nom de fichier compliqué. Le titre et la date "
                                 "sont aussi écrits dans le fichier.")
        self.s_partager = _with_icon(QPushButton("Faire une copie à partager"), "envoyer")
        self.s_partager.setToolTip("Une copie légère pour l'envoyer (e-mail, WhatsApp), ou une copie pour "
                                   "la télévision (clé USB). Le film restauré n'est pas modifié.")
        self.s_separer = _with_icon(QPushButton("Séparer en plusieurs films"), "separer")
        self.s_separer.setToolTip("Une cassette avec Noël, des vacances, un anniversaire : un fichier pour "
                                  "chacun, aux coupures (neige, écran bleu ou noir).")
        self.s_vides.clicked.connect(self.retirer_vides)
        self.s_montage.clicked.connect(self.faire_montage)
        self.s_nommer.clicked.connect(self.nommer_resultat)
        self.s_partager.clicked.connect(self.partager_resultat)
        self.s_separer.clicked.connect(self.separer_films)
        fv.addWidget(self.s_fini_texte)
        self.s_fini.setVisible(False)
        self._recents_box = QWidget()
        self._recents_lay = QVBoxLayout(self._recents_box)
        self._recents_lay.setContentsMargins(0, 0, 0, 0)
        self._recents_lay.setSpacing(6)
        rec_titre = QLabel("Derniers fichiers")
        rec_titre.setObjectName("note")
        self._recents_lay.addWidget(rec_titre)
        self._recent_btns: list[QPushButton] = []
        self._recents_box.setVisible(False)
        self.advice: list = []
        self.s_advice = QCheckBox("Corriger aussi ces défauts, avec prudence")
        self.s_advice.setObjectName("caseSimple")
        self.s_advice.setVisible(False)
        _with_icon(self.s_advice, "conseil")
        self.s_aide_conseil = QPushButton("?")
        self.s_aide_conseil.setObjectName("aide")
        self.s_aide_conseil.setFixedSize(44, 44)
        self.s_aide_conseil.setCursor(Qt.PointingHandCursor)
        self.s_aide_conseil.setAccessibleName("Explication des défauts repérés")
        self.s_aide_conseil.setAccessibleDescription("Ouvre une explication. Rien n'est modifié tant que la case n'est pas cochée.")
        self.s_aide_conseil.setVisible(False)
        self.s_aide_conseil.clicked.connect(self._expliquer_conseil)
        self.s_colorize = QCheckBox("Coloriser aussi (IA)")
        self.s_colorize.setObjectName("caseSimple")
        _with_icon(self.s_colorize, "palette")
        self.s_colorize.setVisible(False)
        self.s_colorize.toggled.connect(lambda _on: self._colorize_toggled())
        self.s_aide_couleur = QPushButton("?")
        self.s_aide_couleur.setObjectName("aide")
        self.s_aide_couleur.setFixedSize(44, 44)
        self.s_aide_couleur.setCursor(Qt.PointingHandCursor)
        self.s_aide_couleur.setAccessibleName("Explication de la colorisation")
        self.s_aide_couleur.setAccessibleDescription(
            "Les couleurs sont inventées. Une copie à part est créée. Le noir et blanc est gardé.")
        self.s_aide_couleur.setVisible(False)
        self.s_aide_couleur.clicked.connect(self._expliquer_couleur)
        self.s_colorize_note = QLabel("Couleurs inventées par l'IA, pas les vraies. Une copie à part est créée : "
                                      "la photo en noir et blanc est gardée.")
        self.s_colorize_note.setObjectName("note")
        self.s_colorize_note.setWordWrap(True)
        self.s_colorize_note.setVisible(False)
        self._halos = (_HoverHalo(theme.ACCENT), _HoverHalo(theme.AMBRE))
        self.s_progress = theme.SweepBar()
        self.s_status = Statut("Prêt.")
        self.s_status.setWordWrap(True)
        self.s_status.setObjectName("statut")
        self.s_cancel = QPushButton("Arrêter")
        self.s_cancel.setObjectName("secondaire")
        self.s_cancel.clicked.connect(lambda: self.cancel(confirmer=True))
        self.s_cancel.setMinimumHeight(44)
        self.s_cancel.setAccessibleName("Arrêter le travail en cours")
        self.s_cancel.setAccessibleDescription("Demande confirmation si le travail a déjà commencé depuis un moment.")
        _with_icon(self.s_cancel, "stop")
        self.s_note = note = QLabel("Votre fichier d'origine n'est jamais modifié : le résultat est enregistré "
                                    "à côté, avec « restaure » dans son nom.")
        note.setWordWrap(True)
        note.setObjectName("note")
        self.s_moment_heure = QLabel("")
        self.s_moment_heure.setObjectName("carteTitre")
        self.s_moment_heure.setWordWrap(True)
        self.s_moment_heure.setMinimumWidth(0)
        self.barre = BarreFilm()
        self.barre.clique.connect(self._barre_cliquee)
        self.barre.borde.connect(self._bord_bouge)
        self.barre.borde_fini.connect(self._bord_fini)
        self.barre.valider.connect(self._couper_ici)
        self.barre.largeur_changee.connect(self._sur_largeur_barre)
        self.s_guide_coupes = QLabel(_texte_guide_coupes(False, 0))
        self.s_guide_coupes.setWordWrap(True)
        self.s_guide_coupes.setMinimumWidth(0)
        self.s_guide_coupes.setObjectName("note")
        self.s_guide_coupes.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.s_comment_faire = _bouton_secondaire("Comment faire ?", "Comment faire ?", elargi=False)
        self.s_comment_faire.clicked.connect(self._comment_faire_coupes)
        self.s_couper = _bouton_secondaire("Couper ici", "Couper ici")
        self.s_couper.setObjectName("couper")
        self.s_couper.clicked.connect(self._couper_ici)
        self.coupes_rapides = []
        for texte, sec in (("Enlever 10 secondes ici", 10),
                           ("Enlever 30 secondes ici", 30),
                           ("Enlever 1 minute ici", 60)):
            b = _bouton_secondaire(texte, texte)
            b.clicked.connect(lambda _=False, s=sec: self._passage_duree(s))
            self.coupes_rapides.append(b)
        self.s_passage_annuler = _bouton_secondaire(
            "Annuler la dernière coupe", "Annuler la dernière coupe")
        self.s_passage_annuler.clicked.connect(self._passage_annuler)
        self.s_trim_start = TempsSpin()
        self.s_trim_end = TempsSpin()
        self.s_trim_start.setSpecialValueText("dès le début")
        self.s_trim_end.setSpecialValueText("à la fin")
        self.s_trim_start.setAccessibleName("Le film commence à")
        self.s_trim_start.setAccessibleDescription(
            "Ce qui est avant ce moment ne sera pas dans la copie. « dès le début » garde le début.")
        self.s_trim_end.setAccessibleName("Le film s'arrête à")
        self.s_trim_end.setAccessibleDescription(
            "Ce qui est après ce moment ne sera pas dans la copie. « à la fin » garde jusqu'au bout.")
        self.s_trim_start.setToolTip("Neige ou écran bleu du début, à ne pas mettre dans la copie.")
        self.s_trim_end.setToolTip("Fin de bande à ne pas mettre dans la copie. « à la fin » = tout garder.")
        self.s_trim_note = QLabel()
        self.s_trim_note.setWordWrap(True)
        self.s_trim_note.setObjectName("note")
        self.s_trim_voir = QPushButton("Montrer ce début dans l'aperçu")
        self.s_trim_tout = QPushButton("Tout garder")
        for b in (self.s_trim_voir, self.s_trim_tout):
            b.setObjectName("secondaire")
            b.setMinimumHeight(44)
            b.setMinimumWidth(0)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setCursor(Qt.PointingHandCursor)
        self.s_trim_voir.setAccessibleName("Placer l'aperçu au début choisi")
        self.s_trim_tout.setAccessibleName("Garder le film en entier")
        self.s_trim_voir.clicked.connect(self._montrer_debut_garde)
        self.s_trim_tout.clicked.connect(self._coupe_tout)
        self.s_passages_note = QLabel("Aucun passage du milieu n'est enlevé.")
        self.s_passages_note.setWordWrap(True)
        self.s_passages_note.setObjectName("note")
        self._passage_lignes: list[tuple[QLabel, QPushButton, QWidget]] = []
        for i in range(_MAX_COUPES):
            ligne = QWidget()
            ligne.setMinimumWidth(0)
            hl = QHBoxLayout(ligne)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(8)
            lab = QLabel("")
            lab.setWordWrap(True)
            lab.setMinimumWidth(0)
            lab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn = _bouton_secondaire("Remettre", f"Remettre le passage {i + 1}", elargi=False)
            btn.setProperty("indice", i)
            btn.clicked.connect(self._remettre_depuis_bouton)
            hl.addWidget(lab, 1)
            hl.addWidget(btn, 0)
            ligne.setVisible(False)
            self._passage_lignes.append((lab, btn, ligne))
        self.s_compare = CompareView()

        # comparer sans geste précis : trois gros boutons sous l'image
        self.s_segments = QWidget()
        hs = self._segments_row = QHBoxLayout(self.s_segments)
        hs.setContentsMargins(0, 0, 0, 0)
        hs.addStretch(1)
        self.segment_group = QButtonGroup(self)
        self.segments: dict[str, QPushButton] = {}
        for mode, txt, ic in (("before", "Avant", "film"), ("split", "Les deux", "comparer"),
                              ("after", "Après", "etincelle")):
            b = _with_icon(QPushButton(txt), ic)
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(44)
            b.clicked.connect(lambda _=False, m=mode: self._choisir_comparaison(m))
            self.segment_group.addButton(b)
            self.segments[mode] = b
            hs.addWidget(b)
        hs.addStretch(1)
        self.segments["before"].setAccessibleName("Voir seulement l'avant")
        self.segments["split"].setAccessibleName("Comparer l'avant et l'après")
        self.segments["after"].setAccessibleName("Voir seulement l'après")
        self.segments["split"].setChecked(True)
        self.s_segments.setVisible(False)
        self.s_folder = QPushButton("Restaurer tout un dossier")
        self.s_folder.setObjectName("secondaire")
        self.s_folder.clicked.connect(self.start_folder)
        self.s_folder.setMinimumHeight(48)
        self.s_folder.setMinimumWidth(0)
        self.s_folder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.s_folder.setAccessibleName("Restaurer tous les films et toutes les photos d'un dossier")
        self.s_folder.setAccessibleDescription("Les fichiers d'origine ne sont pas modifiés.")
        self.s_hear_orig = QPushButton("Écouter l'avant")
        self.s_hear_new = QPushButton("Écouter l'après")
        for b in (self.s_hear_orig, self.s_hear_new):
            b.setObjectName("secondaire")
            b.setMinimumHeight(44)
            _with_icon(b, "casque")
        self.s_hear_orig.setAccessibleName("Écouter le son d'avant")
        self.s_hear_new.setAccessibleName("Écouter le son d'après")
        _with_icon(self.s_folder, "pile")
        self.s_hear_orig.clicked.connect(self._play_original)
        self.s_hear_new.clicked.connect(self._play_restored)

    def _build(self) -> None:
        self._commandes_accueil()
        self._drop_filter = _DropFilter(self._deposer)
        self._gen_images = 0
        self._fab: _Fab | None = None
        self._dossier_images: Path | None = None
        self._boite = _Boite()
        self._pompe = QTimer(self)
        self._pompe.setInterval(40)
        self._pompe.timeout.connect(self._pomper_images)
        self._replan_images = QTimer(self)
        self._replan_images.setSingleShot(True)
        self._replan_images.setInterval(250)
        self._replan_images.timeout.connect(self._lancer_images)
        self._attente_moment = QTimer(self)
        self._attente_moment.setSingleShot(True)
        self._attente_moment.setInterval(120)
        self._attente_moment.timeout.connect(self._demander_moment)

        # Import
        self.drop = DropZone()
        self.drop.setParent(self)
        self.drop.hide()
        self.drop.dropped.connect(self.load_file)

        # Caractéristiques
        g = self._card_info = Carte("Caractéristiques", "info")
        self.info_form = QFormLayout()
        g.body.addLayout(self.info_form)
        self.info_labels: dict[str, QLabel] = {}
        for key in ("Fichier", "Durée", "Conteneur / codec", "Résolution", "Images par seconde",
                    "Format d'affichage", "Balayage", "Norme probable", "Audio", "Couleur",
                    "Origine suggérée"):
            lab = QLabel("—")
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.info_labels[key] = lab
            self.info_form.addRow(key + " :", lab)
        self.scan_combo = QComboBox()
        for txt, val in (("Automatique (analyse)", None), ("Progressive", "progressive"),
                         ("Entrelacée TFF (trame haute)", "tff"), ("Entrelacée BFF (trame basse)", "bff")):
            self.scan_combo.addItem(txt, val)
        self.dar_combo = QComboBox()
        for txt, val in (("Automatique (analyse)", None), ("4:3", Fraction(4, 3)), ("16:9", Fraction(16, 9))):
            self.dar_combo.addItem(txt, val)
        self.source_combo = QComboBox()
        for txt, val, ic, aide in (
                ("Automatique (analyse)", None, "info", "L'analyse propose l'origine (ligne du dessus)."),
                ("Vidéo (VHS, Video8, Hi8…)", "video", "bande", "Vidéo analogique : VHS, Video8, Hi8, Betamax…"),
                ("Pellicule (Super 8, 8 mm…)", "film", "film", "Pellicule cinéma numérisée : Super 8, 8 mm, 16 mm…"),
                ("Pellicule copiée sur vidéo", "transfer", "pile",
                 "Pellicule transférée sur vidéo : film copié sur VHS, DVD…")):
            self.source_combo.addItem(icons.icon(ic), txt, val)
            self.source_combo.setItemData(self.source_combo.count() - 1, aide, Qt.ToolTipRole)
        self.source_combo.setToolTip("L'origine change les réglages appliqués (grain du film préservé, "
                                     "pas de désentrelacement automatique d'une pellicule…).")
        self.source_combo.currentIndexChanged.connect(lambda _i: self._update_state())
        self.info_form.addRow(_ilabel("Origine du film :", "film"), self.source_combo)
        self.cadence_combo = QComboBox()
        self.cadence_combo.addItem("Celle du fichier", None)
        for r in (16, 18, 24):
            self.cadence_combo.addItem(f"{r} images/s", r)
        self.cadence_combo.setToolTip(
            "À changer seulement si la pellicule a été numérisée image par image mais enregistrée "
            "à une autre cadence (mouvements trop rapides). Aucune image n'est créée ni supprimée : "
            "la durée change. Laissez « Celle du fichier » en cas de doute.")
        self.info_form.addRow(_ilabel("Cadence de tournage :", "cadence"), self.cadence_combo)
        self.scan_combo.currentIndexChanged.connect(lambda _i: self._update_state())
        self.info_form.addRow(_ilabel("Balayage à utiliser :", "trames"), self.scan_combo)
        self.info_form.addRow(_ilabel("Format à utiliser :", "format"), self.dar_combo)
        self.warn_label = QLabel()
        self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet(f"color:{theme.AVERT}")
        self.info_form.addRow(self.warn_label)
        self.a_advice = QCheckBox("Corriger aussi ces défauts, avec prudence")
        _with_icon(self.a_advice, "conseil")
        self.a_advice.setVisible(False)
        self.a_advice.setToolTip("La même case que dans « Qualité ». Cochée d'office quand l'analyse "
                                 "repère des défauts ; décochez-la pour garder le film tel quel.")
        self.a_advice.toggled.connect(self.s_advice.setChecked)
        self.s_advice.toggled.connect(self.a_advice.setChecked)
        self.s_advice.toggled.connect(lambda _c: self._refresh_hints())
        self.info_form.addRow(self.a_advice)
        self.profile_group = QButtonGroup(self)
        self.profile_buttons: dict[str, QAbstractButton] = {}
        for p in PROFILES.values():
            ic, tag = PROFILE_LOOK.get(p.key, ("etincelle", ""))
            tile = ProfileTile(p.name, ic, tag)
            tile.setToolTip(p.description)
            tile.installEventFilter(self._halos[0])
            self.profile_group.addButton(tile)
            self.profile_buttons[p.key] = tile
            tile.toggled.connect(lambda on, k=p.key: on and self._profile_changed(k))
        self.profile_desc = QLabel()
        self.profile_desc.setWordWrap(True)
        self.profile_desc.setObjectName("note")

        # Image
        self.res_combo = QComboBox()
        for k, txt in RESOLUTIONS.items():
            self.res_combo.addItem(icons.icon("ecran"), txt, k)
        self.ai_check = _with_icon(QCheckBox("Amélioration IA (Real-ESRGAN)"), "puce")
        self.ai_check.toggled.connect(self._ai_toggled)
        h = QHBoxLayout()
        h.addWidget(_ilabel("Sortie :", "ecran"))
        h.addWidget(self.res_combo, 1)
        self._row_res = _wrap(h)
        h = QHBoxLayout()
        self.deint_combo = QComboBox()
        self.deint_combo.addItem("bwdif (rapide)", "bwdif")
        self.deint_combo.addItem("QTGMC (meilleure qualité, plus lent)", "qtgmc")
        h.addWidget(_ilabel("Désentrelaceur :", "trames"))
        h.addWidget(self.deint_combo, 1)
        self._row_deint = _wrap(h)
        self.dust_check = _with_icon(QCheckBox("Enlever les poussières et rayures (pellicule, plus lent)"),
                                     "poussiere")
        self.tape_check = _with_icon(QCheckBox("Bruit de bande (poursuite, lignes, bande du bas)"), "bande")
        self.chroma_check = _with_icon(QCheckBox("Couleur des décrochages (arcs-en-ciel, couleur perdue)"), "arc")
        self.dropout_check = _with_icon(QCheckBox("Taches d'une seule image (décrochages)"), "eclat")
        tip = ("Moteur Analog Repair, désactivé par défaut. La luminance et le grain ne sont pas "
               "lissés, le tampon date n'est pas effacé. Une cassette entrelacée est d'abord "
               "désentrelacée (bwdif, ou fieldmatch si c'est une pellicule copiée sur bande). "
               "QTGMC n'est pas refait ensuite. Sans le module : installer.bat -AvecPoussieres.")
        for box in (self.tape_check, self.chroma_check, self.dropout_check):
            box.setToolTip(tip)
        self.flicker_check = _with_icon(QCheckBox("Réduire le scintillement lumineux (pellicule)"), "soleil")
        self.flicker_check.setToolTip("Lisse les variations de luminosité d'une image à l'autre "
                                      "(filtre deflicker sur 5 images). À vérifier sur l'aperçu.")
        self.hq_check = _with_icon(QCheckBox("Débruitage haute qualité (environ 3 fois plus lent)"), "lisse")
        self.hq_check.setToolTip("Remplace le débruitage standard par fftdnoiz (FFT 3D) avec un renfort "
                                 "sur les taches de couleur. Plus efficace sur le bruit analogique ; "
                                 "intensité adaptée au profil.")
        self.stab_check = _with_icon(
            QCheckBox("Stabiliser l'image (tremblements, 2 passes)"), "viseur")
        self.cast_check = _with_icon(QCheckBox("Corriger la dominante de couleur"), "goutte")
        self.cast_check.toggled.connect(lambda _c: self._marquer_auto())
        self.cast_check.setToolTip(
            "Retire une teinte qui couvre tout le film (vert de VHS, par exemple). "
            "Les trois gains sont calculés une seule fois, pour tout le film. "
            "Un noir et blanc reste neutre, une image pâle n'est pas ravivée. "
            "Désactivé par défaut. L'analyse le conseille seulement si la dominante est forte.")
        self.mask_spin = QDoubleSpinBox()
        self.mask_spin.setRange(0, 32)
        self.mask_spin.setDecimals(0)
        self.mask_spin.setSingleStep(2)
        self.mask_spin.setSuffix(" lignes")
        self.mask_spin.setToolTip(
            "Bande parasite en bas de certaines VHS (commutation des têtes). "
            "Ces lignes deviennent noires. L'image n'est ni agrandie ni déformée. 0 = ne rien masquer.")
        self.mask_label = _ilabel("Masquer la bande du bas :", "bande_bas")
        h = QHBoxLayout()
        h.addWidget(self.mask_label)
        h.addWidget(self.mask_spin)
        h.addStretch(1)
        self._row_mask = _wrap(h)
        self.edge_spin = QDoubleSpinBox()
        self.edge_spin.setRange(0, 64)
        self.edge_spin.setDecimals(0)
        self.edge_spin.setSingleStep(2)
        self.edge_spin.setSuffix(" px")
        self.edge_spin.setToolTip(
            "Bords abîmés, remplacés par du noir. Cassette : gauche et droite. "
            "Pellicule : un cadre des quatre côtés. L'image garde la même taille "
            "et le même format (4:3 inchangé). 0 = ne rien masquer. « auto » : bords abîmés "
            "repérés par l'analyse, masqués d'office (la plus grande des deux largeurs compte).")
        self.edge_label = _ilabel("Masquer les bords :", "cadre")
        h = QHBoxLayout()
        h.addWidget(self.edge_label)
        h.addWidget(self.edge_spin)
        h.addStretch(1)
        self._row_edge = _wrap(h)
        h = QHBoxLayout()
        self.chroma_spin = QSpinBox()
        self.chroma_spin.setRange(-8, 8)
        self.chroma_spin.setSuffix(" px")
        self.chroma_spin.setToolTip(
            "Décalage horizontal de la couleur, typique d'une VHS (la couleur glisse "
            "par rapport au dessin). 0 = ne pas toucher. Négatif = vers la gauche.")
        h.addWidget(_ilabel("Décalage de couleur :", "decalage"))
        h.addWidget(self.chroma_spin)
        h.addStretch(1)
        self._row_chroma = _wrap(h)

        # Son
        self.audio_check = _with_icon(QCheckBox("Restaurer le son (souffle, clics, volume)"), "haut_parleur")
        self.audio_check.setChecked(True)
        self.audio_check.setToolTip(
            "Suit le profil image. Nettoyage léger : souffle très léger. "
            "Bien nettoyé, naturel : clics, souffle, volume. "
            "Nettoyage au plus fort : DeepFilterNet si tools\\deepfilter\\deep-filter est installé "
            "(installer.bat -AvecSon), sinon le même souffle FFmpeg plus fort. "
            "Le plafond de DeepFilterNet est de 12 dB. Les rires, la musique et la rue restent. "
            "Une piste muette le reste.")
        self.rnnoise_check = _with_icon(QCheckBox("Souffle de la voix (RNNoise, mélangé à l'original)"), "micro")
        self.rnnoise_check.setToolTip(
            "Option, désactivée par défaut : les profils ne changent pas. "
            "Remplace le souffle FFmpeg de « Bien nettoyé, naturel » (35 %) et de "
            "« Nettoyage au plus fort » (55 %) par RNNoise "
            "(modèle Xiph inclus, licence BSD). Le reste du signal, donc la pièce, est conservé. "
            "Inutile si DeepFilterNet a déjà traité « Nettoyage au plus fort ». "
            "« Nettoyage léger » n'est pas concerné.")
        self.wind_check = _with_icon(QCheckBox("Réduire le vent et les grondements"), "vent")
        self.wind_check.toggled.connect(lambda _c: self._marquer_auto())
        self.wind_check.setToolTip(
            "Passe-haut doux à 80 Hz (6 dB par octave). Coupe le vent sur le micro et les "
            "grondements graves. Une voix à partir de 300 Hz n'est presque pas touchée. "
            "Désactivé par défaut. L'analyse le conseille si les graves sont forts et irréguliers.")
        self.presence_check = _with_icon(QCheckBox("Rendre les voix plus claires"), "egaliseur")
        self.presence_check.setToolTip(
            "Légère présence autour de 3 kHz, +3 dB au plus. Pour un son étouffé. "
            "Désactivé par défaut : rien n'est ajouté si la case n'est pas cochée.")
        self.declip_check = _with_icon(QCheckBox("Réparer le son saturé"), "sature")
        self.declip_check.toggled.connect(lambda _c: self._marquer_auto())
        self.declip_check.setToolTip("Reconstruit les crêtes coupées d'un son enregistré trop fort "
                                     "(cris, fêtes, vent). L'analyse le détecte et le conseille.")
        h = QHBoxLayout()
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-500, 500)
        self.offset_spin.setDecimals(0)
        self.offset_spin.setSingleStep(10)
        self.offset_spin.setSuffix(" ms")
        self.offset_spin.setToolTip(
            "Décalage constant entre le son et l'image. Positif : retarder le son "
            "(il était en avance). Négatif : avancer le son. 0 : ne rien changer.")
        self.drift_spin = QDoubleSpinBox()
        self.drift_spin.setRange(-2000, 2000)
        self.drift_spin.setDecimals(0)
        self.drift_spin.setSingleStep(10)
        self.drift_spin.setSuffix(" ms/min")
        self.drift_spin.setToolTip(
            "Si le décalage s'aggrave au fil du film. Positif : le son prend du retard "
            "(il est accéléré, la hauteur des voix est conservée). "
            "Exemple : +100 = une seconde de retard au bout de 10 minutes. "
            "0 = ne rien changer. Ce n'est pas une détection des lèvres.")
        self.mains_combo = QComboBox()
        for txt, val in (("Pas de ronflement à enlever", 0), ("Ronflement 50 Hz (Europe)", 50),
                         ("Ronflement 60 Hz (Amérique)", 60)):
            self.mains_combo.addItem(icons.icon("prise"), txt, val)
        self.mains_combo.setToolTip(
            "Encoche très étroite sur la fréquence du secteur et son double. "
            "À n'activer que si un bourdonnement continu est audible. La musique grave reste.")
        self.copy_combo = QComboBox()
        for txt, val in (("Pas de copie séparée du son", ""), ("Aussi un fichier WAV", "wav"),
                         ("Aussi un fichier FLAC", "flac")):
            self.copy_combo.addItem(icons.icon("fichier_son"), txt, val)
        self.copy_combo.setToolTip(
            "Enregistre le son restauré à côté du film, sans modifier l'original. "
            "C'est le même son que dans la vidéo.")
        self.channel_combo = QComboBox()
        for txt, val in (("Canaux du son inchangés", ""), ("Son gauche mis des deux côtés", "left"),
                         ("Son droit mis des deux côtés", "right"), ("Remettre les deux côtés en phase", "phase")):
            self.channel_combo.addItem(icons.icon("canaux"), txt, val)
        self.channel_combo.setToolTip("Pour un son enregistré d'un seul côté, ou dont les deux côtés "
                                      "s'annulent. L'analyse le détecte et le conseille.")

        # Aperçu
        self.start_spin = TempsSpin()
        self.start_spin.setRange(0, 0)
        self.start_spin.setAccessibleName("Début de l'extrait à regarder")
        self.start_spin.setToolTip("Moment du film montré dans l'aperçu de 10 secondes.")
        self.start_spin.valueChanged.connect(lambda _v: self._rafraichir_barre())
        self.preview_btn = _with_icon(QPushButton("Voir l'avant / après"), "oeil")
        self.preview_btn.clicked.connect(self.start_preview)
        self.still_combo = QComboBox()
        self.still_combo.setMinimumContentsLength(9)
        self.still_combo.setToolTip("Image de l'extrait à comparer.")
        self.still_combo.currentIndexChanged.connect(self._show_still)
        self.play_btn = _with_icon(QPushButton("Lire la comparaison"), "jouer")
        self.play_btn.clicked.connect(self._play_compare)
        self.hear_orig_btn = self.s_hear_orig
        self.hear_new_btn = self.s_hear_new
        self.start_label = _ilabel("Début de l'extrait :", "horloge")
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("À côté du fichier d'origine")
        self.out_edit.textEdited.connect(lambda t: setattr(self, "_out_manual", bool(t.strip())))
        bo = self._out_btn = _with_icon(QPushButton("Dossier de sortie…"), "dossier")
        bo.clicked.connect(self._choose_outdir)
        self.trim_start = self.s_trim_start
        self.trim_end = self.s_trim_end
        self.trim_note = self.s_trim_note

        def compact(b: QPushButton, ic: str | None = None) -> QPushButton:
            if ic:
                _with_icon(b, ic)
            b.setMinimumHeight(36)
            b.setMinimumWidth(0)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setCursor(Qt.PointingHandCursor)
            return b

        self.trim_ici_debut = compact(QPushButton("Commencer à l'extrait"), "ciseaux")
        self.trim_ici_fin = compact(QPushButton("Arrêter après l'extrait"), "ciseaux")
        self.trim_tout = self.s_trim_tout
        self.trim_ici_debut.setToolTip("Le moment « Début de l'extrait » devient le début de la copie.")
        self.trim_ici_fin.setToolTip("La copie s'arrête à la fin de cet extrait de 10 secondes.")
        self.trim_ici_debut.setAccessibleName("Faire commencer le film au début de l'extrait")
        self.trim_ici_fin.setAccessibleName("Faire arrêter le film après l'extrait")
        self.trim_tout.setAccessibleName("Garder le film en entier")
        self.trim_ici_debut.clicked.connect(lambda: self._coupe_depuis_extrait(False))
        self.trim_ici_fin.clicked.connect(lambda: self._coupe_depuis_extrait(True))
        self.trim_couper = self.s_couper
        self.trim_passage_annuler = self.s_passage_annuler
        self.trim_passage_deb = compact(QPushButton("Début du passage ici"))
        self.trim_passage_fin = compact(QPushButton("Le film reprend ici"))
        self.trim_passage_deb.setAccessibleName("Ce passage inutile commence ici")
        self.trim_passage_fin.setAccessibleName("Le film reprend ici")
        self.trim_passage_deb.setToolTip("Ce passage inutile commence ici (en deux temps : puis « Le film reprend ici »).")
        self.trim_passage_deb.clicked.connect(self._passage_commence)
        self.trim_passage_fin.clicked.connect(self._passage_reprend)
        self.s_passage_deb = self.trim_passage_deb
        self.s_passage_fin = self.trim_passage_fin
        self.trim_start.valueChanged.connect(self._dire_coupe)
        self.trim_end.valueChanged.connect(self._dire_coupe)
        self._dire_coupe()
        self.run_btn = QPushButton("Lancer la restauration")
        self.run_btn.setObjectName("action")
        self.run_btn.setIcon(icons.icon("etincelle", theme.AMBRE_TEXTE, 24))
        self.run_btn.setIconSize(QSize(24, 24))
        self.run_btn.clicked.connect(self.start_export)
        self.run_btn.installEventFilter(self._halos[1])
        self.cancel_btn = self.s_cancel
        self.check_btn = _with_icon(QPushButton("Vérifier l'installation"), "diagnostic")
        self.check_btn.setToolTip("Restaure une courte vidéo d'essai et affiche un rapport "
                                  "(utile si quelque chose ne marche pas).")
        self.check_btn.clicked.connect(self.check_install)
        self.vides_btn = _with_icon(QPushButton("Retirer les passages vides…"), "ciseaux")
        self.vides_btn.clicked.connect(self.retirer_vides)
        self.montage_btn = _with_icon(QPushButton("Faire un montage…"), "film")
        self.montage_btn.clicked.connect(self.faire_montage)
        self.separer_btn = _with_icon(QPushButton("Séparer en films…"), "separer")
        self.separer_btn.clicked.connect(self.separer_films)
        for b in (self.vides_btn, self.separer_btn, self.montage_btn):
            b.setToolTip("Sur le dernier film restauré, ou sinon sur le film ouvert.")
        self.nommer_btn = _with_icon(QPushButton("Nommer le résultat…"), "etiquette")
        self.nommer_btn.setToolTip("Nouveau nom (et date) pour le dernier film ou la dernière photo restaurés. "
                                   "Le fichier d'origine n'est jamais renommé.")
        self.nommer_btn.clicked.connect(self.nommer_resultat)
        self.partager_btn = _with_icon(QPushButton("Copie à partager…"), "envoyer")
        self.partager_btn.setToolTip("Copie légère (e-mail, WhatsApp) ou pour la télévision (clé USB), du dernier "
                                     "film restauré ou sinon du film ouvert.")
        self.partager_btn.clicked.connect(self.partager_resultat)
        self.status = self.s_status
        self.progress = self.s_progress
        self.compare = self.s_compare
        # voyants des outils : cliquables (fiche de l'outil, bouton « Installer » si besoin)
        self.tools_label = QWidget()
        hb = QHBoxLayout(self.tools_label)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(2)
        self.voyants: dict[str, QPushButton] = {}
        for key in TOOL_INFO:
            b = QPushButton()
            b.setObjectName("voyant")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_tool(k))
            hb.addWidget(b)
            self.voyants[key] = b
        self.statusBar().setVisible(False)       # mode simple : pas de noms d'outils techniques
        # une option cochée après coup peut rendre la coupe au milieu impossible : la note se met à jour
        for case in (self.ai_check, self.dust_check, self.tape_check, self.chroma_check, self.dropout_check):
            case.toggled.connect(lambda _c: self._rafraichir_passages())
        for liste in (self.cadence_combo, self.source_combo):
            liste.currentIndexChanged.connect(lambda _i: self._rafraichir_passages())
        self._out_manual = False        # dossier de sortie choisi exprès par l'utilisateur ?
        ecran.installer(self)
        self.s_choose, self.s_preview, self.s_run = self.choisir, self.preview_btn, self.run_btn
        for b in (self.s_choose, self.s_preview, self.s_run):
            b.suggested = False
            b.setAccessibleName(b.text())

        self.profile_buttons["equilibre"].setChecked(True)
        self._load_prefs()
        # le choix voulu, pas celui que la petite fenêtre de départ (1100 × 760) a plafonné :
        # la fenêtre agrandie le rétablit
        self.set_taille_texte(getattr(self, "_texte_voulu", round(self._echelle * 100)), annoncer=False)

    # ------------------------------------------------------------ état
    def _refresh_tools(self) -> None:
        t = self.tools
        for key, b in self.voyants.items():
            ok = self._tool_ok(key)
            b.setText(f"{'●' if ok else '○'} {TOOL_INFO[key][0]}")
            b.setToolTip("Installé. Cliquez pour en savoir plus." if ok else
                         "Pas installé. Cliquez pour l'installer." if installer.can_install(key) else
                         "Pas installé. Cliquez pour en savoir plus.")
        self.s_colorize.setToolTip(
            "Photo noir et blanc seulement. L'IA (DDColor) DEVINE des couleurs plausibles : elles peuvent "
            "être fausses (vêtements, peau, objets). Une copie « …_colorisee_ia.png » est écrite en plus ; "
            "la photo restaurée en noir et blanc est toujours gardée." if t.colorize_available else
            "Colorisation pas encore installée : cochez la case pour l'installer "
            + (f"({t.colorizer.problem})" if t.colorizer.problem else ""))
        self.deint_combo.model().item(1).setEnabled(t.qtgmc_available)
        self.stab_check.setToolTip(
            "Atténue les tremblements (vid.stab). L'image est légèrement agrandie pour masquer "
            "les bords : le cadrage change un peu. Vérifiez sur l'aperçu." if t.stab_available else
            "Indisponible : votre FFmpeg n'inclut pas libvidstab (le FFmpeg installé par installer.bat l'inclut).")
        self.deint_combo.setToolTip(
            "Utilisé seulement si la vidéo est entrelacée. QTGMC : désentrelaceur de référence "
            "(VapourSynth), plus stable sur les détails fins, mais plusieurs fois plus lent."
            if t.qtgmc_available else "QTGMC indisponible : " + (t.vspipe.problem or
                                      "relancez installer.bat -AvecQTGMC (Python 3.12+)."))
        self.ai_check.setToolTip("Agrandissement par IA sur carte graphique (Vulkan). "
                                 "Peut inventer des détails : vérifiez l'aperçu." if t.ai_available else
                                 "Real-ESRGAN n'est pas installé : cliquez sur « ○ Real-ESRGAN » dans « Détails du fichier » "
                                 + (f"({t.realesrgan.problem})" if t.realesrgan.problem else ""))

    def show_welcome(self) -> None:
        """Mode d'emploi en trois étapes (au premier lancement, puis par le bouton « Aide »)."""
        box = QMessageBox(QMessageBox.Information, "Bienvenue dans VHS Restore AI",
                          "Restaurer un film ou une photo se fait en trois étapes :\n\n"
                          "1.  « Choisir un film ou une photo » : sélectionnez le fichier.\n"
                          "2.  « Voir l'avant / après » : regardez le résultat sur un petit extrait. "
                          "Image trop sombre ou couleurs ternes ? « Lumière et couleurs » les règle "
                          "avant, et la grande image change tout de suite.\n"
                          "3.  « Lancer la restauration » : le logiciel travaille, cela peut prendre du temps. "
                          "Vous pouvez laisser l'ordinateur faire.\n\n"
                          "Le bouton à utiliser est entouré d'un cadre plus épais. "
                          "La touche Entrée l'active.\n\n"
                          "Votre fichier d'origine n'est jamais modifié : le résultat est enregistré "
                          "à côté, avec « restaure » dans son nom. À la fin, l'écran « C'est prêt » "
                          "propose de le regarder ou d'ouvrir le dossier.\n\n"
                          "Pour enlever la neige du début ou la fin de bande : « Le film commence à » "
                          "et « Le film s'arrête à », dans « Couper le film ». "
                          "Pour un moment au milieu, regardez les petites images sur la barre, "
                          "puis « Couper ici » au début du moment à enlever et « Le film reprend ici » "
                          "à la reprise. "
                          "L'image au-dessus de la barre montre où vous êtes. "
                          "Seule la copie est découpée.\n\n"
                          "Pour enlever plusieurs moments au milieu :\n\n"
                          + GUIDE_COUPES_AUCUNE + "\n\n"
                          "Après le premier clic : " + GUIDE_COUPES_OUVERTE + "\n\n"
                          "Après une coupe : " + GUIDE_COUPES_FAITE + "\n\n"
                          + GUIDE_COUPES_CARRES + "\n\n"
                          "« A− », « A » et « A+ » en haut à droite agrandissent le texte.\n\n"
                          "Ce que le logiciel ne peut pas faire :\n\n"
                          "· il ne retrouve pas un détail absent de la bande ;\n"
                          "· il ne répare pas un mauvais tracking ni une bande abîmée : "
                          "il faut renumériser ou couper ;\n"
                          "· la qualité de la numérisation compte plus que les filtres ;\n"
                          "· les couleurs restaurées sont une estimation ;\n"
                          "· l'IA peut inventer des textures : regardez toujours l'avant / après.",
                          parent=self)
        box.setStyleSheet("QLabel#qt_msgbox_label { min-width: 620px; font-size: 14pt; }")   # large, lisible
        box.addButton("C'est parti", QMessageBox.AcceptRole)
        box.exec()

    def maybe_welcome(self) -> None:
        """Premier lancement : montre le mode d'emploi une fois."""
        s = self._prefs()
        if s is None or s.value("accueil_vu", False, type=bool):
            return
        s.setValue("accueil_vu", True)
        self.show_welcome()

    def toggle_theme(self) -> None:
        """Affichage clair <-> sombre : enregistré, puis le logiciel redémarre."""
        if self._busy():
            return
        nouveau = "sombre" if theme.MODE == "clair" else "clair"
        if not self._question("Affichage", f"Passer à l'affichage {nouveau} ?\n\nLe logiciel va redémarrer. "
                              "Vos réglages sont gardés ; le film ouvert sera à rouvrir.",
                              f"Oui, affichage {nouveau}", "Non"):
            return
        s = self._prefs()
        if s is not None:
            s.setValue("affichage", nouveau)
            s.sync()
        args = [] if getattr(sys, "frozen", False) else ["-m", "vhs_restore"]
        dossier = str(Path(sys.executable).parent) if getattr(sys, "frozen", False) else os.getcwd()
        if _demarrer(sys.executable, args, dossier):
            self.close()

    def _question(self, titre: str, texte: str, oui: str, non: str, oui_par_defaut: bool = False) -> bool:
        """Question à deux boutons écrits en français (Qt afficherait « Yes / No »)."""
        box = QMessageBox(QMessageBox.Question, titre, texte, parent=self)
        b_oui = box.addButton(oui, QMessageBox.YesRole)
        b_non = box.addButton(non, QMessageBox.NoRole)
        box.setDefaultButton(b_oui if oui_par_defaut else b_non)
        box.setEscapeButton(b_non)
        r = box.exec()
        clique = box.clickedButton()
        if clique is not None:
            return clique is b_oui
        return r == QMessageBox.Yes             # exec remplacé dans les tests

    def _info_suite(self, prefixe: str = "") -> None:
        """Texte du haut selon l'état : rien d'ouvert, prêt pour l'aperçu, ou aperçu prêt."""
        if self.info is None or not getattr(self, "_info_debut", ""):
            self.s_info.setText(prefixe + "Cliquez sur « Choisir un film ou une photo ».")
            return
        if self.preview is not None:
            suite = (" Aperçu prêt : comparez avec les boutons « Avant » et « Après », "
                     "puis « Lancer la restauration » si cela vous plaît.")
        else:
            suite = " Cliquez sur « Voir l'avant / après »."
        self._set_simple_info(prefixe + self._info_debut + suite)

    def _set_simple_info(self, text: str) -> None:
        """Texte du mode simple : des mots de tous les jours ; le détail technique en infobulle."""
        if self.advice:
            text += "<br>Défauts repérés : " + ", ".join(dict.fromkeys(_en_clair(a) for a in self.advice)) + "."
        detail = "\n".join("• " + a.text for a in self.advice)
        self.s_info.setText(_insecables(text))
        self.s_info.setToolTip(("Détail des défauts repérés :\n" + detail) if detail else "")
        self.s_advice.setToolTip("Corrige les défauts repérés avec modération (jamais d'effet fort). "
                                 "Cochée d'office ; décochez-la pour garder le film tel quel, "
                                 "sans ces corrections.\n\n" + detail)

    def _tool_ok(self, key: str) -> bool:
        t = self.tools
        return {"ffmpeg": bool(t.ffmpeg.path and t.ffprobe.path and not t.missing_filters),
                "qtgmc": t.qtgmc_available, "realesrgan": t.ai_available,
                "deepfilter": t.deepfilter_available, "colorisation": t.colorize_available,
                "losslesscut": t.losslesscut.ok, "shotcut": t.shotcut.ok}[key]

    def _tool_obj(self, key: str):
        t = self.tools
        return {"ffmpeg": t.ffmpeg, "qtgmc": t.vspipe, "realesrgan": t.realesrgan,
                "deepfilter": t.deepfilter, "colorisation": t.colorizer,
                "losslesscut": t.losslesscut, "shotcut": t.shotcut}[key]

    def show_tool(self, key: str) -> None:
        """Fiche d'un outil : à quoi il sert, s'il est installé, et « Installer » si possible."""
        name, what = TOOL_INFO[key]
        tool, ok = self._tool_obj(key), self._tool_ok(key)
        if ok:
            state = f"✔ Installé.\n{tool.path}"
        elif tool.problem:
            state = f"⚠ Trouvé mais inutilisable : {tool.problem}"
        else:
            state = "○ Pas installé."
        can = installer.can_install(key) and not self._busy()
        if not ok and key in installer.PAQUETS and not installer.can_install(key):
            state += "\nL'installation automatique n'est proposée que sous Windows."
        box = QMessageBox(QMessageBox.Information, name, f"{what}\n\n{state}", parent=self)
        btn = None
        if can and not ok:
            btn = box.addButton(f"Installer ({installer.PAQUETS[key].size_mb} Mo)", QMessageBox.AcceptRole)
        elif can and tool.problem:
            btn = box.addButton("Réinstaller", QMessageBox.AcceptRole)
        box.addButton("Fermer", QMessageBox.RejectRole)
        box.exec()
        if btn is not None and box.clickedButton() is btn:
            self.install_tool(key)

    def install_tool(self, key: str) -> None:
        if self._busy():
            return
        name = TOOL_INFO[key][0]
        self.status.setText(f"Installation de {name}…")

        def job(cancel, progress):
            installer.install(key, cancel=cancel, progress=progress)
            return key, detect_tools()          # l'outil est cherché à nouveau, comme au démarrage
        self._launch(job, self._tool_installed, job="installation")

    def _tool_installed(self, res) -> None:
        key, tools = res
        self.tools = tools
        self._refresh_tools()
        self._update_state()
        name = TOOL_INFO[key][0]
        if self._tool_ok(key):
            self.status.setText(f"Terminé : {name} est installé.")
            attente = getattr(self, "_montage_en_attente", None)
            if attente and attente[0] == key:                # installé pour un montage : on l'ouvre
                self._montage_en_attente = None
                self._lancer_montage(key, attente[1])
                return
            QMessageBox.information(self, name, f"{name} est installé et prêt à servir.\n\n"
                                    "Il restera installé après une mise à jour du logiciel.")
        else:
            prob = self._tool_obj(key).problem
            self.status.setText(f"{name} : installation à vérifier.")
            QMessageBox.warning(self, name, f"{name} a été téléchargé mais ne fonctionne pas sur cet "
                                f"ordinateur.\n{prob}")

    # ------------------------------------------------------------ montage et passages vides
    def _cible_montage(self) -> Path | None:
        """Le dernier film restauré, sinon le film ouvert (pas une photo). Un DVD en plusieurs
        morceaux n'est pas proposé tel quel : seul le premier morceau serait pris."""
        fini = getattr(self, "_fini_fichier", None)
        if fini and Path(fini).is_file() and not photo.is_photo(fini):
            return Path(fini)
        if self.info is not None and not getattr(self, "is_photo", False):
            if len(self.info.parts) > 1:
                QMessageBox.information(
                    self, "DVD en plusieurs morceaux",
                    f"Ce DVD est en {len(self.info.parts)} morceaux.\n\nRestaurez-le d'abord (bouton « Restaurer ») : "
                    "le film restauré est d'un seul tenant. Les passages vides et le montage se feront ensuite "
                    "sur ce film restauré.")
                return None
            return Path(self.info.path)
        return None

    def retirer_vides(self) -> None:
        """Repère neige, écran bleu et noir, puis propose une copie sans ces passages."""
        self._chercher_coupures(self._vides_trouves, "Recherche des passages vides…")

    def separer_films(self) -> None:
        """Une cassette qui mélange Noël, des vacances… : un fichier par film, aux coupures."""
        self._chercher_coupures(self._coupures_trouvees, "Recherche des coupures entre les films…")

    def _chercher_coupures(self, suite: Callable[[Any], None], texte: str) -> None:
        if self._busy():
            return
        cible = self._cible_montage()
        if cible is None:
            if self.info is None or getattr(self, "is_photo", False):
                self.status.setText("Choisissez d'abord un film.")
            return
        t = self.tools

        def job(cancel, progress):
            r = run_capture([t.ffprobe.path, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                             "-of", "default=nw=1", str(cible)], timeout=60)
            try:                                        # « N/A » : durée inconnue, mesurée en lisant
                duree = float(next((x.split("=")[1] for x in r.stdout.split() if x.startswith("duration=")), 0))
            except ValueError:
                duree = 0.0
            son = "codec_type=audio" in r.stdout
            passages, duree = vides.detecter_tout(t.ffmpeg.path, cible, duree, cancel=cancel, progress=progress)
            return cible, duree, son, passages
        self.status.setText(texte)
        self._launch(job, suite, job="vides")

    def _vides_trouves(self, res) -> None:
        cible, duree, son, passages = res
        if not passages:
            self.status.setText("Aucun passage vide trouvé.")
            QMessageBox.information(self, "Passages vides", "Aucun passage vide (neige, écran bleu ou noir) "
                                    f"n'a été trouvé dans « {cible.name} ». Le film est gardé tel quel.")
            return
        total = sum(p.duree for p in passages)
        liste = "\n".join("•  " + vides.decrire(p) for p in passages)
        films = partage.films_separables(vides.a_garder(passages, duree), duree, film_min=partage.FILM_MIN)
        aussi = (f"\n\nCes passages séparent {len(films)} films : vous pouvez aussi en faire {len(films)} "
                 "fichiers, un par film." if films else "")
        box = QMessageBox(QMessageBox.Question, "Passages vides", _insecables(
                          f"{len(passages)} passage{'s' if len(passages) > 1 else ''} vide"
                          f"{'s' if len(passages) > 1 else ''} trouvé{'s' if len(passages) > 1 else ''} "
                          f"dans « {cible.name} » ({vides._hms(total)} en tout) :\n\n{liste}\n\n"
                          f"Créer une copie du film sans ces passages ? Le film actuel n'est pas modifié.{aussi}"),
                          parent=self)
        box.setStyleSheet("QLabel#qt_msgbox_label { min-width: 520px; font-size: 14pt; }")
        oui = box.addButton("Créer la copie", QMessageBox.AcceptRole)
        separer = box.addButton(f"Séparer en {len(films)} films", QMessageBox.AcceptRole) if films else None
        box.addButton("Garder le film tel quel", QMessageBox.RejectRole)
        box.exec()
        if separer is not None and box.clickedButton() is separer:
            self._proposer_separation(cible, duree, son, films)
            return
        if box.clickedButton() is not oui:
            self.status.setText("Le film est gardé tel quel.")
            return
        try:
            dossier, _secours = pipeline.output_dir_for(cible.parent)   # DVD, clé protégée : dossier de secours
        except ToolError as exc:
            ergonomie.montrer_erreur(self, str(exc))
            return
        dst = vides.sortie_sans_vides(cible, dossier)
        ffmpeg = self.tools.ffmpeg.path
        self.status.setText("Copie sans les passages vides…")
        self._launch(lambda c, p: (vides.retirer(ffmpeg, cible, dst, passages, duree, son, cancel=c, progress=p),
                                   total), self._vides_retires, job="vides_copie")

    def _vides_retires(self, res) -> None:
        out, total = res
        self._montrer_fini(f"Copie sans les passages vides :\n{out.name}\n\n{vides._hms(total)} retirées "
                           f"(neige, écran bleu ou noir).\n\nElle se trouve dans le dossier :\n{out.parent}\n\n"
                           "Le film précédent n'a pas été modifié.", out.parent, out, "film")
        self.status.setText(f"Terminé : {out.name}")

    # ------------------------------------------------------------ séparer, nommer, partager
    def _coupures_trouvees(self, res) -> None:
        cible, duree, son, passages = res
        films = partage.films_separables(vides.a_garder(passages, duree), duree, film_min=partage.FILM_MIN)
        if not films:
            self.status.setText("Pas de coupure entre deux films.")
            QMessageBox.information(
                self, "Séparer en plusieurs films", _insecables(
                f"Aucune coupure nette (neige, écran bleu ou noir) n'a été trouvée entre deux films de plus de "
                f"{int(partage.FILM_MIN)} secondes dans « {cible.name} ».\n\nLe film reste d'un seul tenant. "
                "Pour couper ailleurs, utilisez « Faire un montage »."))
            return
        self._proposer_separation(cible, duree, son, films)

    def _proposer_separation(self, cible: Path, duree: float, son: bool, films: list) -> None:
        noms = self._demander_noms_films(cible, films, duree)
        if noms is None:
            self.status.setText("Le film est gardé d'un seul tenant.")
            return
        try:
            dossier, _secours = pipeline.output_dir_for(cible.parent)   # DVD, clé protégée : dossier de secours
        except ToolError as exc:
            ergonomie.montrer_erreur(self, str(exc))
            return
        ffmpeg = self.tools.ffmpeg.path
        self.status.setText(f"Séparation en {len(films)} films…")
        self._launch(lambda c, p: partage.separer(ffmpeg, cible, films, noms, son, dossier=dossier, cancel=c,
                                                  progress=p, duree=duree),
                     lambda sortis: self._films_separes(cible, sortis), job="separation")

    def _films_separes(self, cible: Path, sortis: list) -> None:
        liste = "\n".join("•  " + p.name for p in sortis)
        self._montrer_fini(f"« {cible.name} » est séparé en {len(sortis)} films :\n{liste}\n\n"
                           f"Ils se trouvent dans le dossier :\n{sortis[0].parent}\n\n"
                           "Le film entier est gardé tel quel, sans aucun changement.",
                           sortis[0].parent, sortis[0], "films")
        self.status.setText(f"Terminé : {len(sortis)} films")

    def _demander_noms_films(self, cible: Path, films: list, duree: float) -> list[str] | None:
        """Un nom par film (facultatif). None : annulé."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Séparer en plusieurs films")
        dlg.setStyleSheet("QLabel, QLineEdit, QPushButton { font-size: 13pt; }")
        lay = QVBoxLayout(dlg)
        tete = QLabel(_insecables(f"{len(films)} films trouvés dans « {cible.name} ». Donnez un nom à chacun "
                                  "(par exemple « Noël 1988 ») ; sans nom, un numéro est donné.\n"
                                  "Le film entier n'est pas modifié."))
        tete.setWordWrap(True)
        lay.addWidget(tete)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.NoFrame)
        corps = QWidget()
        form = QFormLayout(corps)
        champs = []
        for i, (a, b) in enumerate(films, start=1):
            fin = b if b is not None else duree
            champ = QLineEdit()
            champ.setPlaceholderText(f"{cible.stem} - film {i}")
            champ.setMaxLength(80)
            champ.setAccessibleName(f"Nom du film {i}")
            form.addRow(QLabel(f"Film {i} : de {vides._hms(a)} à {vides._hms(fin)} "
                               f"({vides._hms(max(0.0, fin - a))})"), champ)
            champs.append(champ)
        zone.setWidget(corps)
        zone.setMinimumHeight(min(360, 42 * len(films) + 6))
        lay.addWidget(zone, 1)
        lay.addLayout(self._boutons_dialogue(dlg, "Séparer"))
        dlg.resize(720, dlg.sizeHint().height())
        if dlg.exec() != QDialog.Accepted:
            return None
        return [c.text() for c in champs]

    def _boutons_dialogue(self, dlg: QDialog, oui: str, accepter: Callable[[], None] | None = None) -> QHBoxLayout:
        h = QHBoxLayout()
        h.addStretch(1)
        ok = QPushButton(oui)
        ok.setObjectName("action")
        ok.setDefault(True)
        non = QPushButton("Annuler")
        non.setObjectName("secondaire")
        for b in (ok, non):
            b.setMinimumHeight(44)
            b.setMinimumWidth(140)
            b.setCursor(Qt.PointingHandCursor)
            h.addWidget(b)
        ok.clicked.connect(accepter or dlg.accept)
        non.clicked.connect(dlg.reject)
        return h

    def _demander_nom(self, cible: Path, est_photo: bool) -> tuple[str, str] | None:
        """(nom, date ISO ou « ») ; None : annulé."""
        dlg = QDialog(self)
        quoi = "cette photo" if est_photo else "ce film"
        dlg.setWindowTitle(f"Nommer {quoi}")
        dlg.setStyleSheet("QLabel, QLineEdit, QPushButton { font-size: 13pt; }")
        lay = QVBoxLayout(dlg)
        tete = QLabel(_insecables(f"Nom actuel : {cible.name}\n\nNouveau nom (par exemple « Noël 1988 ») :"))
        tete.setWordWrap(True)
        lay.addWidget(tete)
        nom = QLineEdit()
        nom.setMaxLength(80)
        nom.setPlaceholderText("Noël 1988")
        nom.setAccessibleName("Nouveau nom")
        lay.addWidget(nom)
        date = QLineEdit()
        date.setMaxLength(20)
        date.setPlaceholderText("1988 ou 25/12/1988")
        date.setAccessibleName("Date du film")
        if not est_photo:                    # le titre et la date sont écrits dans le film
            note_date = QLabel("Date du film (facultatif) :")
            lay.addWidget(note_date)
            lay.addWidget(date)
        erreur = QLabel("")
        erreur.setObjectName("note")
        erreur.setWordWrap(True)
        erreur.setVisible(False)
        lay.addWidget(erreur)

        def verifier() -> None:              # la fenêtre reste ouverte tant que le nom ne convient pas
            if not partage.nom_de_fichier(nom.text()):
                erreur.setText("Tapez un nom, par exemple « Noël 1988 ».")
            elif partage.date_iso(date.text()) is None:
                erreur.setText("Date non comprise. Écrivez par exemple 1988, 12/1988 ou 25/12/1988, "
                               "ou laissez la case vide.")
            else:
                dlg.accept()
                return
            erreur.setVisible(True)
        dlg._verifier = verifier             # pour les tests
        lay.addLayout(self._boutons_dialogue(dlg, "Nommer", verifier))
        dlg.resize(620, dlg.sizeHint().height())
        if dlg.exec() != QDialog.Accepted:
            return None
        return nom.text().strip(), partage.date_iso(date.text()) or ""

    def nommer_resultat(self) -> None:
        """« Noël 1988 » plutôt que « DVD_041544_0_restaure_equilibre.mp4 ». Seulement un résultat du
        logiciel (film, photo) : le fichier d'origine n'est jamais renommé."""
        if self._busy():
            return
        fini = getattr(self, "_fini_fichier", None)
        if not fini or not Path(fini).is_file():
            self.status.setText("Restaurez d'abord le film ou la photo. Vous pourrez ensuite nommer le résultat.")
            return
        cible = Path(fini)
        est_photo = photo.is_photo(cible)
        rep = self._demander_nom(cible, est_photo)
        if rep is None:
            self.status.setText("Le nom n'a pas changé.")
            return
        nom, date = rep
        ffmpeg = self.tools.ffmpeg.path
        original = getattr(self.info, "path", None) if self.info is not None else None
        annexes = [] if est_photo else [cible.with_suffix(".wav"), cible.with_suffix(".flac")]
        couleur = photo.colorized_path(cible) if est_photo else None

        def job(cancel, progress):
            progress(0.2, "Changement de nom…")
            out = partage.nommer(ffmpeg, cible, nom, date, annexes=annexes, original=original, cancel=cancel)
            if couleur is not None and couleur.is_file():     # la copie colorisée suit la photo
                partage.nommer(ffmpeg, couleur, photo.colorized_path(out).stem, original=original)
            return out
        self.status.setText("Changement de nom…")
        self._launch(job, self._nomme, job="nommer")

    def _nomme(self, out: Path) -> None:
        est_photo = photo.is_photo(out)
        if est_photo:
            couleur = photo.colorized_path(out)
            more = (f"\n\nCopie colorisée par l'IA (couleurs inventées) :\n{couleur.name}"
                    if couleur.is_file() else "")
            texte = (f"Votre photo s'appelle maintenant :\n{out.name}{more}\n\nElle se trouve dans le dossier :\n"
                     f"{out.parent}\n\nLa photo d'origine n'a pas été modifiée.")
        else:
            sons = [x.name for x in (out.with_suffix(".wav"), out.with_suffix(".flac")) if x.is_file()]
            extra = f"\n\nCopie du son restauré :\n{sons[0]}" if sons else ""
            texte = (f"Votre film s'appelle maintenant :\n{out.name}\n\nIl se trouve dans le dossier :\n"
                     f"{out.parent}{extra}\n\nLe titre (et la date) sont aussi écrits dans le fichier : "
                     "les téléviseurs et les lecteurs les affichent. Le film d'origine n'a pas été modifié.")
        self._montrer_fini(texte, out.parent, out, "photo" if est_photo else "film")
        self.status.setText(f"Terminé : {out.name}")

    def _choisir_copie(self, cible: Path) -> str | None:
        box = QMessageBox(QMessageBox.Question, "Faire une copie à partager", _insecables(
                          f"Quelle copie de « {cible.name} » voulez-vous ?\n\n"
                          "•  Copie légère : petite, pour l'envoyer par e-mail ou WhatsApp, ou la regarder "
                          "sur un téléphone (environ 5 à 15 Mo par minute de film).\n\n"
                          "•  Pour la télévision : à copier sur une clé USB et à brancher sur le téléviseur "
                          "(belle image, lue par presque tous les téléviseurs).\n\n"
                          "Le film n'est pas modifié : la copie est un nouveau fichier, dans le même dossier."),
                          parent=self)
        box.setStyleSheet("QLabel#qt_msgbox_label { min-width: 560px; font-size: 14pt; }")
        legere = box.addButton("Copie légère (pour envoyer)", QMessageBox.AcceptRole)
        tele = box.addButton("Pour la télévision (clé USB)", QMessageBox.AcceptRole)
        box.addButton("Annuler", QMessageBox.RejectRole)
        box.exec()
        choix = box.clickedButton()
        return "legere" if choix is legere else "tele" if choix is tele else None

    def partager_resultat(self) -> None:
        """Copie légère (e-mail, WhatsApp) ou pour la télévision (clé USB) : un nouveau fichier."""
        if self._busy():
            return
        cible = self._cible_montage()
        if cible is None:
            if self.info is None or getattr(self, "is_photo", False):
                self.status.setText("Choisissez d'abord un film.")
            return
        cle = self._choisir_copie(cible)
        if cle is None:
            self.status.setText("Aucune copie faite.")
            return
        try:
            dossier, _secours = pipeline.output_dir_for(cible.parent)
        except ToolError as exc:
            ergonomie.montrer_erreur(self, str(exc))
            return
        t = self.tools
        self.status.setText(f"Préparation de la {partage.COPIES[cle].libelle}…")
        self._launch(lambda c, p: partage.faire_copie(t.ffmpeg.path, t.ffprobe.path, cible, cle, dossier=dossier,
                                                      cancel=c, progress=p),
                     lambda out: self._copie_faite(out, cle), job="partage")

    def _copie_faite(self, out: Path, cle: str) -> None:
        try:
            taille = out.stat().st_size / 1e6
        except OSError:
            taille = 0.0
        poids = f"{taille:.0f} Mo" if taille < 1000 else f"{taille / 1000:.1f} Go".replace(".", ",")
        if cle == "legere":
            usage = "Pour l'envoyer : joignez ce fichier à un e-mail ou à un message WhatsApp."
            if taille > 25:
                usage += (" Un e-mail refuse souvent les fichiers de plus de 25 Mo : pour celui-ci, passez "
                          "plutôt par WhatsApp ou un service d'envoi de gros fichiers.")
        else:
            usage = ("Copiez ce fichier sur une clé USB, branchez la clé sur le téléviseur, puis choisissez "
                     "« USB » ou « Média » avec la télécommande.")
        ajout = f"{partage.COPIES[cle].libelle.capitalize()} prête :\n{out.name} ({poids})\n\n{usage}"
        if not self.s_fini.isHidden():
            self.s_fini_texte.setText(f"{ajout}\n\nElle se trouve dans le dossier :\n{out.parent}\n\n"
                                      + self.s_fini_texte.text())
            self._signaler_fin()
        else:
            box = QMessageBox(QMessageBox.Information, "Copie à partager",
                              f"{ajout}\n\nElle se trouve dans le dossier :\n{out.parent}", parent=self)
            box.setStyleSheet("QLabel#qt_msgbox_label { min-width: 520px; font-size: 14pt; }")
            ouvrir = box.addButton("Ouvrir le dossier", QMessageBox.AcceptRole)
            box.addButton("Fermer", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is ouvrir:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(out.parent)))
        self.status.setText(f"Terminé : {out.name}")

    def faire_montage(self) -> None:
        """Ouvre le film dans LosslessCut (simple) ou Shotcut (complet), installés d'un clic si besoin."""
        cible = self._cible_montage()
        if cible is None:
            self.status.setText("Choisissez d'abord un film.")
            return
        box = QMessageBox(QMessageBox.Question, "Faire un montage",
                          "Quel montage voulez-vous faire ?\n\n"
                          "•  Couper ou assembler : retirer des moments, garder les meilleurs, mettre "
                          "plusieurs films bout à bout. Simple, sans perte de qualité (LosslessCut).\n\n"
                          "•  Montage complet : titres, fondus, musique (Shotcut). Plus riche, plus complexe.\n\n"
                          "Le film s'ouvre dans un logiciel gratuit, dans sa propre fenêtre. "
                          "Votre film n'est pas modifié tant que vous n'y enregistrez pas un nouveau fichier.",
                          parent=self)
        box.setStyleSheet("QLabel#qt_msgbox_label { min-width: 560px; font-size: 14pt; }")
        simple = box.addButton("Couper ou assembler", QMessageBox.AcceptRole)
        complet = box.addButton("Montage complet", QMessageBox.AcceptRole)
        box.addButton("Annuler", QMessageBox.RejectRole)
        box.exec()
        choix = box.clickedButton()
        key = "losslesscut" if choix is simple else "shotcut" if choix is complet else None
        if key:
            self._lancer_montage(key, cible)

    def _lancer_montage(self, key: str, cible: Path) -> None:
        name = TOOL_INFO[key][0]
        if not self._tool_ok(key):                           # pas encore installé : fiche « Installer »
            self._montage_en_attente = (key, cible)
            self.show_tool(key)
            if not self._busy():                             # fiche fermée sans installer : on oublie
                self._montage_en_attente = None
            return
        exe = Path(self._tool_obj(key).path)
        if _demarrer(str(exe), [str(cible)], str(exe.parent)):
            self.status.setText(f"{name} s'ouvre avec {cible.name}…")
        else:
            ergonomie.montrer_erreur(self, f"{name} n'a pas pu démarrer : {exe}")

    def _colorize_toggled(self) -> None:
        """L'aperçu affiché ne correspond plus aux réglages : on l'efface. Si la colorisation
        n'est pas installée, la fiche « Installer » s'ouvre (pas besoin des voyants du bas)."""
        if self.s_colorize.isChecked() and not self.tools.colorize_available:
            self.s_colorize.blockSignals(True)
            self.s_colorize.setChecked(False)
            self.s_colorize.blockSignals(False)
            self.show_tool("colorisation")
            return
        if getattr(self, "is_photo", False) and self.preview is not None:
            self.preview = None
            self.compare.clear()
            self.status.setText("Réglage changé : cliquez sur « Voir l'avant / après » pour un nouvel aperçu.")

    def _busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _update_state(self) -> None:
        busy, loaded = self._busy(), self.info is not None
        self.preview_btn.setEnabled(loaded and not busy)
        self.run_btn.setEnabled(loaded and not busy)
        self.cancel_btn.setEnabled(busy)
        self.check_btn.setEnabled(not busy)
        for b, ok in ((self.s_choose, not busy), (self.s_preview, loaded and not busy),
                      (self.s_run, loaded and not busy), (self.s_folder, not busy), (self.s_cancel, busy)):
            b.setEnabled(ok)
        self.ai_check.setEnabled(self.tools.ai_available and not busy)
        self.s_colorize.setEnabled(not busy)       # pas installée : cocher propose de l'installer
        self.rnnoise_check.setEnabled(bool(self.tools.rnnoise_model) and not busy)
        if not self.tools.rnnoise_model:
            self.rnnoise_check.setChecked(False)
        self.deint_combo.setEnabled(not busy)
        self.hq_check.setEnabled(not busy)
        self.stab_check.setEnabled(self.tools.stab_available and not busy)
        # fonctions affichées selon l'origine
        src = self.source()
        self.image_form.setRowVisible(self.cadence_combo, src == "film")
        if src != "film":
            self.cadence_combo.setCurrentIndex(0)
        self.flicker_check.setVisible(src in ("film", "transfer"))
        self.dust_check.setVisible(src == "film")
        for box in (self.tape_check, self.chroma_check, self.dropout_check):
            box.setVisible(src != "film")
            box.setEnabled(self.tools.dust_available and not busy)
            if not self.tools.dust_available:
                box.setChecked(False)
        self.mask_spin.setVisible(src == "video")
        self.mask_label.setVisible(src == "video")
        self.dust_check.setEnabled(self.tools.dust_available and not busy)
        if src != "film" or not self.tools.dust_available:
            self.dust_check.setChecked(False)
        self.dust_check.setToolTip(
            "Efface les poussières et atténue les rayures, en gardant le grain du film "
            "(moteur Analog Repair). Vérifiez l'aperçu sur les objets qui bougent vite."
            if self.tools.dust_available else
            "Module non installé : relancez installer.bat -AvecPoussieres.")
        self.flicker_check.setEnabled(not busy)
        if src not in ("film", "transfer"):
            self.flicker_check.setChecked(False)
        self.deint_combo.setEnabled(src == "video" and not busy)
        self._refresh_hints()
        if not self.tools.stab_available:
            self.stab_check.setChecked(False)
        if not self.tools.ai_available:
            self.ai_check.setChecked(False)
        idx_4k = self.res_combo.findData("2160")
        self.res_combo.model().item(idx_4k).setEnabled(self.ai_check.isChecked())
        if not self.ai_check.isChecked() and self.res_combo.currentData() == "2160":
            self.res_combo.setCurrentIndex(self.res_combo.findData("1080"))
        has_prev = self.preview is not None
        photo_mode = getattr(self, "is_photo", False)
        sound = bool(self.info is not None and self.info.has_audio)
        self.play_btn.setEnabled(has_prev and not busy)
        self.play_btn.setVisible(not photo_mode)
        for b in (self.s_hear_orig, self.s_hear_new):
            b.setEnabled(has_prev and sound and not busy)          # film muet : rien à écouter
            b.setToolTip("" if sound or not loaded else "Ce film n'a pas de son.")
        self.still_combo.setEnabled(has_prev and not busy)
        # vide ou une seule image : caché. Assistant : caché aussi (une liste de plus à manier ;
        # « Avant », « Les deux », « Après » suffisent), et la colonne de l'image reste étroite.
        guide = getattr(getattr(self, "assistant", None), "actif", False) and loaded
        self.still_combo.setVisible(self.still_combo.count() > 1 and not guide)
        self.s_colorize_note.setVisible(not self.s_colorize.isHidden())
        for lab in self.info_labels.values():                            # photo : pas de lignes « — »
            self.info_form.setRowVisible(lab, not (photo_mode and lab.text() == "—"))
        cible = loaded or bool(getattr(self, "_fini_fichier", None))
        for b in (self.vides_btn, self.montage_btn, self.separer_btn, self.partager_btn):
            b.setEnabled(cible and not busy)                             # pendant un travail ou pour une
            b.setVisible(not photo_mode)                                 # photo : sans objet
        resultat = getattr(self, "_fini_fichier", None)                  # nommer : un résultat seulement
        self.nommer_btn.setEnabled(bool(resultat) and Path(resultat).is_file() and not busy)
        self.a_advice.setVisible(not self.s_advice.isHidden())
        # mode simple : seulement ce qui sert maintenant
        self.s_cancel.setVisible(busy)
        self.s_aide_conseil.setVisible(not self.s_advice.isHidden())
        self.s_aide_couleur.setVisible(not self.s_colorize.isHidden())
        for b in (self.s_hear_orig, self.s_hear_new):
            b.setVisible(has_prev and sound and not photo_mode)
        self.s_segments.setVisible(has_prev)
        for b in self.segments.values():
            b.setEnabled(not busy)
        self.theme_btn.setEnabled(not busy)
        # l'étape suivante conseillée est mise en évidence
        fini = not self.s_fini.isHidden()           # « C'est prêt » : Entrée ne relance rien
        nxt = None if busy or fini else (self.s_choose if not loaded else self.s_preview if not has_prev
                                         else self.s_run)
        for b in (self.s_choose, self.s_preview, self.s_run):
            if b.suggested != (b is nxt):
                b.suggested = b is nxt
                b.setProperty("conseille", b.suggested)
                b.style().unpolish(b)
                b.style().polish(b)
                b.update()
            if b is nxt:
                b.setAccessibleDescription("Étape conseillée. La touche Entrée l'active.")
            elif not b.isEnabled():
                b.setAccessibleDescription("Pas encore disponible.")
        # Pendant un traitement, les réglages ne servent plus (ils ont été lus au lancement) :
        # on les grise pour ne pas laisser croire qu'ils changent le travail en cours.
        for wd in (self.drop, self._card_info, self.start_spin, self.out_edit, self._out_btn):
            wd.setEnabled(not busy)
        # Photo : seuls le profil, la dominante, l'IA et la colorisation comptent. Les réglages
        # propres aux films sont cachés (ils n'auraient aucun effet).
        for wd in (self._row_res, self._row_deint, self._row_edge, self._row_chroma, self.hq_check,
                   self.stab_check, self.start_label, self.start_spin):
            wd.setVisible(not photo_mode)
        for box in (self.tape_check, self.chroma_check, self.dropout_check):
            box.setVisible(src != "film" and not photo_mode)
        self.flicker_check.setVisible(src in ("film", "transfer") and not photo_mode)
        self.dust_check.setVisible(src == "film" and not photo_mode)
        self._row_mask.setVisible(src == "video" and not photo_mode)
        for combo in (self.source_combo, self.scan_combo, self.dar_combo):
            self.image_form.setRowVisible(combo, not photo_mode)
        self.image_form.setRowVisible(self.cadence_combo, src == "film" and not photo_mode)
        self._masquer_recent_courant()
        ecran.actualiser(self, loaded, photo_mode, busy, fini)

    def _masquer_recent_courant(self) -> None:
        """Le fichier déjà ouvert ne reste pas proposé : un clic dessus ne ferait rien de neuf."""
        boutons = getattr(self, "_recent_btns", None)
        if not boutons:
            return
        liste = [str(b.property("chemin")) for b in boutons if b.property("chemin")]
        if liste:
            self._afficher_recents(liste)

    def _profile_changed(self, key: str) -> None:
        p = PROFILES[key]
        self.profile_desc.setText(p.description)
        self.ai_check.setChecked(p.ai_default and self.tools.ai_available)
        self.res_combo.setCurrentIndex(self.res_combo.findData(p.default_resolution))
        want = p.deinterlacer if (p.deinterlacer != "qtgmc" or self.tools.qtgmc_available) else "bwdif"
        self.deint_combo.setCurrentIndex(self.deint_combo.findData(want))
        self._update_state()

    def _ai_toggled(self, on: bool) -> None:
        if on and self.res_combo.currentData() == "source":
            self.res_combo.setCurrentIndex(self.res_combo.findData("1080"))
        self._update_state()

    def source(self) -> str:
        """Origine effective : choix de l'utilisateur, sinon suggestion de l'analyse."""
        chosen = self.source_combo.currentData()
        if chosen:
            return chosen
        return self.info.suggested_source if self.info else "video"

    def _lignes_conseils(self) -> list[str]:
        """Défauts repérés, dits selon la case : corrigés d'office, ou seulement signalés."""
        if self.s_advice.isChecked():
            return [f"💡 Corrigé d'office : {a.text}" for a in self.advice]
        return [f"💡 Repéré, pas corrigé (case décochée) : {a.text.split(' : ')[0]}." for a in self.advice]

    def _marquer_auto(self) -> None:
        """Défauts corrigés d'office : les réglages concernés l'affichent au lieu de « rien »."""
        actifs = {a.key: a for a in self.advice} if (self.info is not None and self.s_advice.isChecked()) else {}
        for case, cle, texte in ((self.declip_check, "clip", "Réparer le son saturé"),
                                 (self.wind_check, "wind", "Réduire le vent et les grondements"),
                                 (self.cast_check, "cast", "Corriger la dominante de couleur")):
            case.setText(texte + ("  · corrigé d'office" if cle in actifs and not case.isChecked() else ""))
        hum = actifs.get("hum")
        self.mains_combo.setItemText(0, f"Automatique : ronflement {hum.fix['audio_mains_hz']} Hz filtré" if hum
                                     else "Pas de ronflement à enlever")
        ch = actifs.get("channel")
        self.channel_combo.setItemText(0, {"left": "Automatique : son de gauche des deux côtés",
                                           "right": "Automatique : son de droite des deux côtés",
                                           "phase": "Automatique : côtés remis en accord"}
                                       .get(ch.fix["audio_channel_fix"], "Automatique") if ch
                                       else "Canaux du son inchangés")

    def _refresh_hints(self) -> None:
        self._marquer_auto()
        # bords abîmés repérés : la case « Masquer les bords » dit ce qui sera fait (pas « 0 px »)
        bords = next((a.fix["mask_sides"] for a in self.advice if a.key == "edges"), 0) if self.info else 0
        self.edge_spin.setSpecialValueText(f"auto ({bords} px)" if bords and self.s_advice.isChecked() else "")
        if not self.info:
            return
        notes = ["⚠ " + w for w in self.info.warnings]
        if getattr(self, "is_photo", False):          # une photo : pas de son, pas de « film »
            if self.info.black_and_white:
                notes.append("ℹ Photo noir et blanc : elle le restera"
                             + (". La case « Coloriser aussi » dans « Qualité » peut ajouter une copie "
                                "colorisée par l'IA (couleurs inventées)." if self.tools.colorize_available else "."))
            notes += self._lignes_conseils()
            if getattr(self, "out_note", ""):
                notes.append(self.out_note)
            self.warn_label.setText("\n".join(notes))
            return
        src = self.source()
        if src == "film" and self.info.interlaced and not self.scan_combo.currentData():
            notes.append("⚠ L'analyse mesure de l'entrelacement : s'il s'agit d'une copie sur vidéo, "
                         "choisissez « Pellicule transférée sur vidéo ».")
        if self.info.black_and_white:
            notes.append("ℹ Film noir et blanc probable : aucune colorisation n'est appliquée.")
        if not self.info.has_audio:
            notes.append("ℹ Aucune piste son : le fichier restauré restera muet.")
        elif self.info.audio_silent:
            notes.append("ℹ Aucun son entendu dans les extraits analysés.")
        notes += self._lignes_conseils()
        if getattr(self, "out_note", ""):
            notes.append(self.out_note)
        if self.info.pale_colors:
            notes.append("ℹ Couleurs très pâles : film probablement décoloré. Aucune correction "
                         "automatique des couleurs n'est faite (fidélité).")
        self.warn_label.setText("\n".join(notes))

    def settings(self, with_advice: bool = True) -> pipeline.Settings:
        """Réglages choisis ; avec les conseils de l'analyse si la case est cochée."""
        s = self._raw_settings()
        if with_advice and self.info is not None and self.s_advice.isChecked():
            s = apply_advice(s, self.advice)
        return s

    def _raw_settings(self) -> pipeline.Settings:
        key = next(k for k, b in self.profile_buttons.items() if b.isChecked())
        src = self.source()
        gains = (1.0, 1.0, 1.0)
        if self.cast_check.isChecked() and self.info is not None and self.info.cast_rgb:
            gains = cast_gains(self.info.cast_rgb)
        return pipeline.Settings(profile=profile_for(key, src), resolution=self.res_combo.currentData(),
                                 source=src, playback_fps=(Fraction(self.cadence_combo.currentData())
                                                           if self.cadence_combo.currentData() else None),
                                 deflicker=self.flicker_check.isChecked() and src != "video",
                                 dust=self.dust_check.isChecked() and src == "film" and self.tools.dust_available,
                                 tape_noise=self.tape_check.isChecked() and src != "film",
                                 chroma_repair=self.chroma_check.isChecked() and src != "film",
                                 dropouts=self.dropout_check.isChecked() and src != "film",
                                 scan=self.scan_combo.currentData(), dar=self.dar_combo.currentData(),
                                 use_ai=self.ai_check.isChecked(),
                                 deinterlacer=self.deint_combo.currentData(),
                                 stabilize=self.stab_check.isChecked(),
                                 denoise_hq=self.hq_check.isChecked(),
                                 restore_audio=self.audio_check.isChecked(),
                                 use_rnnoise=self.rnnoise_check.isChecked(),
                                 **self.lumiere.reglages(),
                                 audio_offset_ms=float(self.offset_spin.value()),
                                 audio_drift_ms_per_min=float(self.drift_spin.value()),
                                 audio_mains_hz=int(self.mains_combo.currentData() or 0),
                                 audio_copy=str(self.copy_combo.currentData() or ""),
                                 audio_channel_fix=str(self.channel_combo.currentData() or ""),
                                 audio_declip=self.declip_check.isChecked(),
                                 audio_highpass=self.wind_check.isChecked(),
                                 audio_presence=self.presence_check.isChecked(),
                                 chroma_shift=int(self.chroma_spin.value()),
                                 gain_r=gains[0], gain_g=gains[1], gain_b=gains[2],
                                 mask_bottom=int(self.mask_spin.value()) if src == "video" else 0,
                                 mask_sides=int(self.edge_spin.value()),
                                 colorize=(getattr(self, "is_photo", False) and self.s_colorize.isChecked()
                                           and self.tools.colorize_available))

    def _choisir_comparaison(self, mode: str) -> None:
        self.s_compare.montrer_position = False
        self.s_compare.set_mode(mode)
        noms = {"before": "Avant", "split": "Les deux", "after": "Après"}   # à la souris
        self.status.setText(f"Affichage : {noms.get(mode, mode)}.")

    def _dossier_depart(self, images: bool = False) -> str:
        """Dernier dossier utilisé, sinon Vidéos ou Images."""
        s = self._prefs()
        if s is not None:
            last = str(s.value("dernier_dossier", "") or "")
            if last and Path(last).is_dir():
                return last
        kind = QStandardPaths.PicturesLocation if images else QStandardPaths.MoviesLocation
        return QStandardPaths.writableLocation(kind) or ""

    def _retenir_dossier(self, dossier: str) -> None:
        if not dossier:
            return
        s = self._prefs()
        if s is not None:
            s.setValue("dernier_dossier", dossier)

    def _deposer(self, path: str) -> None:
        if Path(path).is_dir():                 # un dossier déposé : tous ses films et photos
            if self._busy():
                return
            if self._question("Dossier", f"Restaurer tous les films et photos du dossier "
                              f"« {Path(path).name} » ?\n\nLes originaux ne sont pas modifiés.",
                              "Oui, tout restaurer", "Non", oui_par_defaut=True):
                self._retenir_dossier(path)
                self.restore_folder(Path(path))
            return
        self._retenir_dossier(str(Path(path).parent))
        self.load_file(path)

    def _memoriser_recent(self, path: str) -> None:
        s = self._prefs()
        if s is None:
            return
        brut = s.value("recents", []) or []
        if isinstance(brut, str):
            brut = [brut]
        liste = ergonomie.memoriser_recent([str(p) for p in list(brut)], path)
        s.setValue("recents", liste)
        self._afficher_recents(liste)

    def _afficher_recents(self, liste: list[str]) -> None:
        """Met à jour les boutons sans les détruire. Le fichier déjà ouvert n'est pas
        reproposé : le bouton ne servirait à rien."""
        liste = [p for p in liste if p]
        courant = ""
        if getattr(self, "info", None) is not None:
            try:
                courant = str(Path(self.info.path).resolve())
            except OSError:
                courant = str(self.info.path)
        while len(self._recent_btns) < len(liste):
            b = QPushButton()
            b.setObjectName("secondaire")
            b.setMinimumHeight(44)
            b.setMinimumWidth(0)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(self._clic_recent)
            self._recents_lay.addWidget(b)
            self._recent_btns.append(b)
        for i, b in enumerate(self._recent_btns):
            if i < len(liste):
                chemin = liste[i]
                try:
                    meme = str(Path(chemin).resolve()) == courant
                except OSError:
                    meme = False
                nom = Path(chemin).name
                b.setProperty("chemin", chemin)
                b.setText(nom.replace("&", "&&"))      # « Papa & Maman.avi » : le « & » reste visible
                b.setAccessibleName(f"Rouvrir {nom}")
                b.setVisible(not meme)
            else:
                b.setVisible(False)
        self._recents_box.setVisible(any(not b.isHidden() for b in self._recent_btns))

    def _clic_recent(self) -> None:
        bouton = self.sender()
        chemin = str(bouton.property("chemin") or "") if bouton is not None else ""
        if chemin:
            self._rouvrir_recent(chemin)

    def _rouvrir_recent(self, path: str) -> None:
        if not Path(path).is_file():
            self.status.setText("Ce fichier n'est plus là.")
            ergonomie.montrer_erreur(self, f"Fichier introuvable : {path}")
            return
        if self.info is not None and Path(self.info.path).resolve() == Path(path).resolve():
            self.status.setText("Ce fichier est déjà ouvert.")
            return
        self._retenir_dossier(str(Path(path).parent))
        self.load_file(path)

    def taille_texte_max(self) -> int:
        """Le plus grand texte qui tient sans défilement de côté. Écran étroit (moins de 1280 px
        utiles : 1024 × 768, 1366 × 768 à 125 %…) ou bas (moins de 600 px) : 100 % seulement."""
        return 100 if self.width() < 1280 or self.height() < 600 else 150

    def set_taille_texte(self, pct: int, annoncer: bool = True) -> None:
        pct = 150 if pct >= 140 else 125 if pct >= 110 else 100
        self._texte_voulu = pct                      # gardé : il revient sur un écran plus grand
        self._texte_plafond = self.taille_texte_max()
        pct = min(pct, self._texte_plafond)
        self._echelle = pct / 100
        self._simple.setStyleSheet(
            f"QLabel, QPushButton, QCheckBox, QComboBox, QLineEdit, QAbstractSpinBox "
            f"{{font-size: {10 * self._echelle}pt;}}"
            f"QLabel#nomFilm {{font-size: {16 * self._echelle}pt; font-weight: bold;}}"
            "QPushButton {padding: 3px 6px;} QCheckBox {spacing: 4px;}"
            f"QPushButton[conseille=true] {{border: 2px solid {theme.ACCENT};}}"
            + ecran.regles(self._echelle)
        )
        if getattr(self, "run_btn", None) is not None:
            self.run_btn.setFixedWidth(400)
            self._serre = None
            ecran.adapter(self)                      # hauteur du bouton selon l'écran
        if getattr(self, "profile_buttons", None):
            ecran.ajuster_qualite(self)
            ecran.ajuster_son(self)
        for valeur, bouton in self._taille_btns.items():
            bouton.setChecked(valeur == pct)
            bouton.setEnabled(valeur <= self._texte_plafond)
            bouton.setToolTip("" if valeur <= self._texte_plafond else
                              "L'écran est trop petit pour un texte plus grand.")
        pref = self._prefs()
        if pref is not None:
            pref.setValue("texte", self._texte_voulu)
        if annoncer:
            self.status.setText(f"Taille du texte : {pct} %." + (
                " L'écran est trop petit pour l'agrandir davantage." if pct < self._texte_voulu else ""))

    def _expliquer_conseil(self) -> None:
        detail = self.s_advice.toolTip() or "Aucun défaut particulier n'a été repéré."
        self.status.setText("Explication des défauts affichée.")
        QMessageBox.information(self, "Ces défauts", detail)

    def _expliquer_couleur(self) -> None:
        detail = self.s_colorize.toolTip() or (
            "L'intelligence artificielle invente des couleurs plausibles. "
            "Elles peuvent être fausses. Une copie à part est créée, le noir et blanc est gardé.")
        self.status.setText("La colorisation est expliquée.")
        QMessageBox.information(self, "Coloriser", detail)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            focus = QApplication.focusWidget()
            if not self.s_fini.isHidden() and not self._busy():   # « C'est prêt » : Entrée = regarder
                if self.s_voir.isVisible():
                    self.s_voir.click()
                return
            if not isinstance(focus, (QLineEdit, QAbstractSpinBox, QComboBox, BarreFilm)):
                for b in (self.s_choose, self.s_preview, self.s_run):
                    if b.suggested and b.isEnabled():
                        b.click()
                        return
        super().keyPressEvent(e)

    # ------------------------------------------------------------ actions
    def _choose_file(self) -> None:
        images = bool(getattr(self, "is_photo", False) and self.info is not None)
        f, _ = QFileDialog.getOpenFileName(self, "Choisir un film ou une photo",
                                           self._dossier_depart(images=images), VIDEO_FILTER)
        if f:
            self._retenir_dossier(str(Path(f).parent))
            self.load_file(f)

    def _choose_outdir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier de sortie", self.out_edit.text())
        if d:
            self.out_edit.setText(d)
            self._out_manual = True        # choisi exprès : gardé pour les fichiers suivants

    def load_file(self, path: str) -> None:
        if self._busy():
            self.status.setText("Un traitement est en cours : attendez la fin ou cliquez sur « Arrêter ».")
            return
        self.s_fini.setVisible(False)
        self._fini_fichier = None              # montage / passages vides : sur ce nouveau film
        self._montage_en_attente = None
        self.progress.setRange(0, 0)  # animation indéterminée
        if photo.is_photo(path):
            self.status.setText("Analyse de la photo…")
            self._launch(lambda c, p: photo.analyze_photo(path, self.tools), self._photo_loaded)
            return
        self.status.setText("Analyse de la vidéo…")
        self._launch(lambda c, p: open_media(path, self.tools), self._loaded)

    def _photo_loaded(self, info: MediaInfo) -> None:
        """Photo : description simple, conseils de contraste et de couleur, mêmes boutons."""
        self.info, self.is_photo, self.preview = info, True, None
        self.compare.clear()
        self.still_combo.clear()
        for k, lab in self.info_labels.items():
            lab.setText("—")
        self.info_labels["Fichier"].setText(info.path.name)
        self.info_labels["Résolution"].setText(f"{info.width} × {info.height} (photo)")
        if "Couleur" in self.info_labels:
            self.info_labels["Couleur"].setText("Noir et blanc" if info.black_and_white else "Couleur")
        self.out_note = ""
        if (not self._out_manual or not self.out_edit.text()
                or not pipeline.is_writable(Path(self.out_edit.text()))):
            # sauf choix exprès : à côté du fichier d'origine (comme le promet le mode d'emploi)
            try:
                out, fallback = pipeline.output_dir_for(info.path.parent)
                self.out_edit.setText(str(out))
                if fallback:
                    self.out_note = (f"ℹ Le dossier de la photo ne peut pas être modifié : la photo restaurée "
                                     f"sera enregistrée dans {out}")
            except ToolError as exc:
                self.out_note = f"⚠ {exc}"
        self.advice = advise(info)
        kind = "Photo noir et blanc" if info.black_and_white else "Photo en couleur"
        self._info_debut = f"<b>{info.path.name}</b><br>{kind}."
        self._info_suite()
        self.s_advice.setChecked(bool(self.advice))      # défauts repérés : corrigés d'office, avec prudence
        self.s_advice.setVisible(bool(self.advice))
        self.s_colorize.setChecked(False)                     # jamais coché d'avance
        self.s_colorize.setVisible(info.black_and_white)
        self.s_aide_conseil.setVisible(bool(self.advice))
        self.s_aide_couleur.setVisible(info.black_and_white)
        ecran.ajuster_qualite(self)
        self.drop.setText(info.path.name)
        self._memoriser_recent(str(info.path))
        self._update_state()
        self._couper_images()
        self.s_compare.poser_moment(str(info.path), None)
        self._refresh_hints()
        self.status.setText(f"Photo analysée : {info.path.name}. "
                            "Étape suivante : « Voir l'avant / après ».")

    def _loaded(self, info: MediaInfo) -> None:
        self.is_photo = False
        self.s_colorize.setChecked(False)
        self.s_colorize.setVisible(False)
        self.info = info
        self.preview = None
        self.compare.clear()
        self.still_combo.clear()
        for k, val in info.summary().items():
            self.info_labels[k].setText(val)
        self.info_labels["Norme probable"].setToolTip(info.standard_reason)
        self.scan_combo.setCurrentIndex(0)
        self.dar_combo.setCurrentIndex(0)
        self.source_combo.setItemText(0, "Automatique : "
                                      + {"video": "vidéo", "film": "pellicule",
                                         "transfer": "copie"}[info.suggested_source])
        self.source_combo.setCurrentIndex(0)
        fps = f"{float(info.fps):.3f}".rstrip("0").rstrip(".")
        self.cadence_combo.setItemText(0, f"Celle du fichier ({fps} i/s)")
        self.cadence_combo.setCurrentIndex(0)
        self._update_state()
        self._plage_coupe(info.duration)
        self.start_spin.setRange(0, max(0.0, info.duration))
        self.start_spin.setValue(min(info.duration * 0.1, max(0.0, info.duration - 10)))
        self.out_note = ""
        if (not self._out_manual or not self.out_edit.text()
                or not pipeline.is_writable(Path(self.out_edit.text()))):
            # sauf choix exprès : à côté du fichier d'origine (comme le promet le mode d'emploi)
            try:
                out, fallback = pipeline.output_dir_for(info.path.parent)
                self.out_edit.setText(str(out))
                if fallback:
                    self.out_note = (f"ℹ Le dossier du film ne peut pas être modifié (DVD, clé protégée…) : "
                                     f"le film restauré sera enregistré dans {out}")
            except ToolError as exc:
                self.out_note = f"⚠ {exc}"
        self._refresh_hints()
        self.drop.setText(info.summary()["Fichier"])
        self._memoriser_recent(str(info.path))
        kind = {"video": "Film de caméscope ou de magnétoscope", "film": "Film sur pellicule (Super 8, 8 mm…)",
                "transfer": "Film sur pellicule, copié sur vidéo"}[info.suggested_source]
        traits = [_duree(info.duration)]
        if info.black_and_white:
            traits.append("noir et blanc")
        if not info.has_audio:
            traits.append("sans son (il restera muet)")
        self.advice = advise(info)
        self._info_debut = f"<b>{info.summary()['Fichier']}</b><br>{kind}, {', '.join(traits)}."
        self._info_suite()
        self.s_advice.setChecked(bool(self.advice))      # défauts repérés : corrigés d'office, avec prudence
        self.s_advice.setVisible(bool(self.advice))
        self.s_aide_conseil.setVisible(bool(self.advice))
        self.s_aide_couleur.setVisible(False)
        ecran.ajuster_qualite(self)
        self.channel_combo.setCurrentIndex(0)
        self.declip_check.setChecked(False)
        self._refresh_hints()
        self.status.setText(f"Vidéo analysée : {info.path.name}. "
                            "Étape suivante : « Voir l'avant / après ».")
        self._lancer_images()

    def _question_vitesse(self, demande):
        from .eta import describe
        secondes, en_4k, inconnue, reponse, pret = demande
        texte = ("La durée du film est inconnue." if inconnue else
                 f"L’amélioration IA prendra {describe(secondes)}.")
        if en_4k:
            texte += " Sans l’IA, le film sera en Full HD."
        box = QMessageBox(QMessageBox.Question, "Amélioration IA", texte, parent=self)
        sans = box.addButton("Continuer sans l'IA", QMessageBox.ActionRole)
        avec = box.addButton("Continuer avec l'IA", QMessageBox.AcceptRole)
        annuler = box.addButton("Annuler", QMessageBox.RejectRole)
        box.setDefaultButton(annuler)
        box.exec()
        bouton = box.clickedButton()
        reponse.append("sans" if bouton is sans else "avec" if bouton is avec else "annuler")
        pret.set()

    def _choix_ia(self, info, s, duree, c, p, apercu=False):
        return pipeline.essayer_ia(info, s, self.tools, duree, self.worker.demander_ia, c, p,
                                   apercu=apercu)

    def start_preview(self) -> None:
        if not self.info or self._busy():
            return
        info, s, start = self.info, self.settings(), self.start_spin.value()
        self.status.setText("Préparation de l'aperçu…")
        # un dossier neuf à chaque aperçu : l'aperçu précédent peut être encore ouvert dans le
        # lecteur vidéo (« Écouter »), et Windows refuse alors de l'effacer
        for vieux in self.preview_dir.glob("*"):
            shutil.rmtree(vieux, ignore_errors=True)
        travail = Path(tempfile.mkdtemp(prefix="apercu_", dir=self.preview_dir))
        if getattr(self, "is_photo", False):
            self._launch(lambda c, p: photo.make_photo_preview(info, self._choix_ia(info, s, 1, c, p, apercu=True), self.tools, travail / "photo",
                                                               cancel=c, progress=p), self._preview_done)
            return
        self._launch(lambda c, p: pipeline.make_preview(info, self._choix_ia(info, s, min(info.duration or 10, 10), c, p, apercu=True), self.tools, travail, start,
                                                        cancel=c, progress=p), self._preview_done)

    def _preview_done(self, res: pipeline.PreviewResult) -> None:
        self.preview = res
        self.compare.set_after_label("COULEURS IA (inventées)" if res.restored.name.endswith("_colorisee_ia.png")
                                     else "APRÈS")
        self.still_combo.blockSignals(True)
        self.still_combo.clear()
        for i, _ in enumerate(res.stills):
            self.still_combo.addItem(f"Image {i + 1}/{len(res.stills)}")
        self.still_combo.blockSignals(False)
        idx = min(1, len(res.stills) - 1)
        self.still_combo.setCurrentIndex(idx)
        self._show_still(idx)
        self.segments["split"].setChecked(True)
        self.compare.montrer_position = False
        self.compare.set_mode("split")
        self._info_suite()
        if getattr(self, "_ecoute_demandee", False):
            self._ecoute_demandee = False
            self._play_restored()
        quand = "" if getattr(self, "is_photo", False) else \
            f" (extrait de {res.start:.0f} s à {res.start + res.duration:.0f} s)"
        texte = f"Aperçu prêt{quand}. Comparez avec les boutons « Avant » et « Après »."
        assistant = getattr(self, "assistant", None)
        if not getattr(self, "is_photo", False) and (assistant is None or not assistant.actif):
            # réglages libres : la durée et la place ici (l'assistant les met dans son résumé)
            from . import estimation
            annonce = estimation.annonce(self)
            if annonce:
                texte += " " + annonce
        self.status.setText(texte)

    def _ecouter_extrait(self) -> None:
        self._ecoute_demandee = True
        self.start_preview()
        if not self._busy():
            self._ecoute_demandee = False

    def _show_still(self, idx: int) -> None:
        if self.preview and 0 <= idx < len(self.preview.stills):
            self.compare.set_still(self.preview.stills[idx])

    def _play_compare(self) -> None:
        if self.preview:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.preview.compare)))

    def _play_original(self) -> None:
        if self.preview and self.preview.original:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.preview.original)))

    def _play_restored(self) -> None:
        if self.preview:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.preview.restored)))

    def _plage_coupe(self, duree: float) -> None:
        """Tout garder, et la même plage sur les deux pages. Un nouveau film repart sans coupe."""
        self._coupes = []
        self._coupe_ouverte = None
        self._texte_couper("Couper ici")
        for sp in (self.trim_start, self.trim_end):
            sp.blockSignals(True)
            sp.setRange(0, max(0.0, duree))
            sp.setValue(0)
            sp.blockSignals(False)
        self._dire_coupe()

    def _dire_coupe(self) -> None:
        if not getattr(self, "info", None) or getattr(self, "is_photo", False):
            texte = ("Pour enlever la neige du début ou la fin de bande. "
                     "L'original n'est pas modifié : seule la copie est découpée.")
        else:
            debut, fin = self.trim_start.value(), self.trim_end.value()
            duree = self.info.duration
            if debut <= 0 and fin <= 0:
                texte = f"Tout le film est gardé ({_duree(duree)}). L'original n'est pas modifié."
            else:
                fin_eff = fin if fin > 0 else duree
                garde = max(0.0, fin_eff - debut)
                morceaux = [f"La copie gardera {_duree(garde)}."]
                if debut > 0:
                    morceaux.append(f"Les {_duree(debut)} du début ne seront pas dedans.")
                if fin > 0 and (not duree or fin < duree - 0.5):
                    morceaux.append(f"Après {_duree(fin)}, la fin ne sera pas dedans.")
                morceaux.append("L'original n'est pas modifié.")
                texte = " ".join(morceaux)
        self.s_trim_note.setText(texte)
        self._rafraichir_passages()

    def _barres(self) -> list[_Ruban]:
        return [self.barre] if hasattr(self, "barre") else []

    def _rafraichir_barre(self) -> None:
        barres = self._barres()
        if not barres:
            return
        if not self._film_pour_coupe() or not hasattr(self, "start_spin") or not hasattr(self, "trim_start"):
            for barre in barres:
                barre.definir(0, 0, 0, 0, [])
            return
        for barre in barres:
            barre.definir(self.info.duration, self.start_spin.value(),
                          self.trim_start.value(), self.trim_end.value(), self._coupes)
        if hasattr(self, "_attente_moment"):
            self._attente_moment.start()

    def _sur_largeur_barre(self, px: int) -> None:
        """Le nombre de petites images suit la largeur. On ne relance que si ce nombre change."""
        if not self._film_pour_coupe() or not getattr(self.info, "duration", 0):
            return
        if not hasattr(self, "_replan_images"):
            return
        n = len(vignettes.instants(self.info.duration, max(int(px), 1)))
        if n and n != len(self.barre._vignettes):
            self._replan_images.start()

    def _arreter_images(self) -> None:
        """Coupe les fils et tue FFmpeg. N'attend pas : l'écran ne se bloque pas."""
        self._gen_images = getattr(self, "_gen_images", 0) + 1
        fab = getattr(self, "_fab", None)
        dossier = getattr(self, "_dossier_images", None)
        self._fab = None
        self._dossier_images = None
        if fab is not None:
            fab.stop()

        def _nettoyer() -> None:
            if fab is not None:
                for fil in fab.fils:
                    fil.join(8)
            if dossier is not None:
                shutil.rmtree(dossier, ignore_errors=True)

        if fab is not None or dossier is not None:
            fil = threading.Thread(target=_nettoyer, name="vhs-vignettes-fin", daemon=True)
            _NETTOYEURS.append(fil)
            fil.start()
        pompe = getattr(self, "_pompe", None)
        if pompe is not None:
            pompe.stop()

    def _couper_images(self) -> None:
        """Arrête la fabrication et remet l'écran. Le dossier part une fois les fils arrêtés."""
        self._arreter_images()
        for barre in self._barres():
            barre.vider_images(0)
        image = getattr(self, "s_moment", None)
        if image is not None:
            image.vider()
        heure = getattr(self, "s_moment_heure", None)
        if heure is not None:
            heure.setText("")
        vue = getattr(self, "compare", None)
        if vue is not None and hasattr(vue, "oublier_moment"):
            vue.oublier_moment()

    def _lancer_images(self) -> None:
        """Petites images et image du moment, dans un fil à part (pas self.worker)."""
        self._couper_images()
        if not self._film_pour_coupe() or not self.info.duration or self.info.duration <= 0:
            return
        ffmpeg = self.tools.ffmpeg.path if self.tools.ffmpeg else None
        if not ffmpeg:
            return
        largeur = max(self.barre.width(), self.barre.sizeHint().width(), 400)
        moments = vignettes.instants(self.info.duration, largeur)
        if not moments:
            return
        dossier = Path(tempfile.mkdtemp(prefix="vhsrestore_vignettes_"))
        self._dossier_images = dossier
        generation = self._gen_images
        lw, lh = vignettes.taille(self.info, vignettes.HAUTEUR_VIGNETTE)
        mw, mh = vignettes.taille(self.info, vignettes.HAUTEUR_MOMENT)
        for barre in self._barres():
            barre.vider_images(len(moments))
        self._fab = _Fab(ffmpeg, self.info, dossier, moments, lw, lh, mw, mh, generation, self._boite)
        self._pompe.start()
        self._demander_moment()

    def _pomper_images(self) -> None:
        boite = getattr(self, "_boite", None)
        if boite is None:
            return
        vignettes_pretes, moments = boite.prendre()
        for index, chemin, generation in vignettes_pretes:
            self._vignette_prete(index, chemin, generation)
        for instant, chemin, generation in moments:
            self._moment_pret(instant, chemin, generation)

    def _vignette_prete(self, index: int, chemin: str, generation: int) -> None:
        if generation != self._gen_images:
            return
        for barre in self._barres():
            barre.poser_image(index, chemin)

    def _moment_pret(self, instant: float, chemin: str, generation: int) -> None:
        if generation != self._gen_images:
            return
        heure = getattr(self, "s_moment_heure", None)
        if heure is not None:
            heure.setText(_duree(instant))
        self.s_compare.poser_moment(chemin, instant)

    def _demander_moment(self) -> None:
        fab = getattr(self, "_fab", None)
        if fab is None or not self._film_pour_coupe():
            return
        fab.demander(float(self.start_spin.value()), self._gen_images)

    def _barre_cliquee(self, secondes: float) -> None:
        if not self._film_pour_coupe():
            self.status.setText("Choisissez d'abord un film.")
            return
        self.s_compare.montrer_position = True
        self.start_spin.setValue(float(secondes))
        self.status.setText(
            f"Vous êtes à {_duree(secondes)}. Cliquez sur « Couper ici », "
            "puis une seconde fois là où le film reprend.")
        self._rafraichir_barre()

    def _texte_guide(self) -> str:
        """Texte du guide selon l'état actuel des coupes."""
        return _texte_guide_coupes(self._coupe_ouverte is not None, len(self._coupes))

    def _rafraichir_guide_coupes(self) -> None:
        guide = getattr(self, "s_guide_coupes", None)
        if guide is not None:
            guide.setText(self._texte_guide())

    def _comment_faire_coupes(self) -> None:
        """Fenêtre d'aide : les trois étapes, les carrés blancs, un schéma dessiné."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Comment enlever une scène")
        dlg.setStyleSheet("QLabel, QPushButton { font-size: 13pt; }")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)
        etapes = QLabel(_insecables(
            GUIDE_COUPES_AUCUNE + "\n\n"
            "Après le premier clic : " + GUIDE_COUPES_OUVERTE + "\n\n"
            "Après une coupe : " + GUIDE_COUPES_FAITE))
        etapes.setWordWrap(True)
        etapes.setMinimumWidth(0)
        lay.addWidget(etapes)
        carres = QLabel(_insecables(GUIDE_COUPES_CARRES))
        carres.setWordWrap(True)
        carres.setObjectName("note")
        lay.addWidget(carres)
        lay.addWidget(SchemaCoupe())
        legende = QLabel("Doré : ce qui est enlevé. Les carrés blancs se tirent.")
        legende.setWordWrap(True)
        legende.setObjectName("note")
        lay.addWidget(legende)
        ok = QPushButton("J'ai compris")
        ok.setObjectName("action")
        ok.setMinimumHeight(44)
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(dlg.accept)
        lay.addWidget(ok)
        dlg.exec()

    def _texte_couper(self, texte: str) -> None:
        for nom in ("s_couper",):
            bouton = getattr(self, nom, None)
            if bouton is not None:
                bouton.setText(texte)

    def _couper_ici(self) -> None:
        """Un clic : le passage commence. Le clic suivant : le film reprend."""
        if self._coupe_ouverte is None:
            self._passage_commence()
            if self._coupe_ouverte is not None:
                self._texte_couper("Le film reprend ici")
            return
        self._passage_reprend()
        if self._coupe_ouverte is None:
            self._texte_couper("Couper ici")

    def _bord_bouge(self, index: int, est_fin: bool, temps: float) -> None:
        """Déplace un seul bord, sans fusionner tant que la souris n'est pas relâchée."""
        if not self._film_pour_coupe():
            self.status.setText("Choisissez d'abord un film.")
            return
        if index < 0 or index >= len(self._coupes):
            return
        duree = float(self.info.duration or 0.0)
        a, b = self._coupes[index]
        if est_fin:
            b = max(a + _MIN_COUPE, min(float(temps), duree))
        else:
            a = min(b - _MIN_COUPE, max(float(temps), 0.0))
        self._coupes[index] = (a, b)
        self._rafraichir_passages()
        self.status.setText(f"Ce passage va de {_duree(a)} à {_duree(b)}.")

    def _bord_fini(self) -> None:
        self._coupes = self._coupes_normalisees(self._coupes)
        self._rafraichir_passages()
        self.status.setText("Le passage est ajusté. Ce temps ne sera pas restauré.")

    def _film_pour_coupe(self) -> bool:
        return self.info is not None and not getattr(self, "is_photo", False)

    def _passage_commence(self) -> None:
        if not self._film_pour_coupe():
            self.status.setText("Choisissez d'abord un film.")
            return
        ici = float(self.start_spin.value())
        self._coupe_ouverte = ici
        self._rafraichir_guide_coupes()
        self.status.setText(
            f"Le passage inutile commence à {_duree(ici)}. "
            "Placez l'extrait là où le film reprend, puis cliquez sur « Le film reprend ici ».")

    def _passage_reprend(self) -> None:
        if not self._film_pour_coupe():
            self.status.setText("Choisissez d'abord un film.")
            return
        if self._coupe_ouverte is None:
            self.status.setText("Indiquez d'abord où le passage inutile commence.")
            return
        debut = float(self._coupe_ouverte)
        fin = float(self.start_spin.value())
        if fin < debut + _MIN_COUPE:
            self.status.setText("Avancez un peu : un passage doit durer au moins une demi-seconde.")
            return
        nouveau = self._avec_nouvelle_coupe(debut, fin)
        if nouveau is None:
            self._coupe_ouverte = None
            self._texte_couper("Couper ici")
            self.status.setText(
                "Huit passages suffisent. Restaurez cette copie, puis recommencez dessus si besoin.")
            return
        self._coupes = nouveau
        self._coupe_ouverte = None
        self._rafraichir_passages()
        self.status.setText(f"De {_duree(debut)} à {_duree(fin)} ne sera pas dans la copie.")

    def _passage_duree(self, secondes: float) -> None:
        """Enlève d'un coup quelques secondes à partir de l'endroit choisi sur la barre."""
        if not self._film_pour_coupe():
            self.status.setText("Choisissez d'abord un film.")
            return
        debut = float(self.start_spin.value())
        fin = min(debut + float(secondes), float(self.info.duration))
        if fin < debut + 0.5:
            self.status.setText("Vous êtes trop près de la fin. Reculez un peu sur la barre.")
            return
        nouveau = self._avec_nouvelle_coupe(debut, fin)
        if nouveau is None:
            self._coupe_ouverte = None
            self._texte_couper("Couper ici")
            self.status.setText(
                "Huit passages suffisent. Restaurez cette copie, puis recommencez dessus si besoin.")
            return
        self._coupes = nouveau
        self._coupe_ouverte = None
        self._rafraichir_passages()
        self.status.setText(
            f"De {_duree(debut)} à {_duree(fin)} ne sera pas restauré. "
            "Le travail sera plus court d'autant.")

    def _passage_annuler(self) -> None:
        if not self._film_pour_coupe():
            self.status.setText("Choisissez d'abord un film.")
            return
        if self._coupe_ouverte is not None:
            self._coupe_ouverte = None
            self._texte_couper("Couper ici")
            self._rafraichir_guide_coupes()
            self.status.setText("La coupe commencée est annulée.")
            return
        if not self._coupes:
            self.status.setText("Aucun passage à remettre.")
            return
        self._coupes.pop()
        self._rafraichir_passages()
        self.status.setText("Le dernier passage est remis dans la copie.")

    def _remettre_depuis_bouton(self) -> None:
        btn = self.sender()
        valeur = btn.property("indice") if btn is not None else 0
        self._passage_remettre(int(valeur) if valeur is not None else 0)

    def _passage_remettre(self, index: int) -> None:
        if not self._film_pour_coupe():
            self.status.setText("Choisissez d'abord un film.")
            return
        if index < 0 or index >= len(self._coupes):
            self.status.setText("Aucun passage à remettre.")
            return
        del self._coupes[index]
        self._rafraichir_passages()
        self.status.setText("Ce passage est remis dans la copie.")

    def _coupes_normalisees(self, coupes: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Les passages à enlever, fusionnés. On ne stocke pas les morceaux gardés."""
        info = self.info if self._film_pour_coupe() else None
        duree = float(info.duration) if info is not None else 0.0
        if duree <= 0:
            return _fusionner_coupes(coupes)
        try:
            gardes = pipeline.passages_gardes(duree, 0, 0, coupes)
        except ToolError:
            return _fusionner_coupes(coupes)
        return _coupes_depuis_gardes(duree, gardes)

    def _avec_nouvelle_coupe(self, debut: float, fin: float) -> list[tuple[float, float]] | None:
        avant = list(self._coupes)
        apres = self._coupes_normalisees([*avant, (debut, fin)])
        if len(apres) > _MAX_COUPES:
            return None
        if _memes_coupes(avant, apres):
            return avant
        cible = next((iv for iv in apres if iv[0] <= debut + 1e-3 and iv[1] >= fin - 1e-3), None)
        if cible is None:
            return apres
        return [iv for iv in apres if iv != cible] + [cible]

    def _phrase_passages(self) -> str:
        n = len(self._coupes)
        if n == 0:
            return "Aucun passage du milieu n'est enlevé."
        base = ("1 passage ne sera pas dans la copie." if n == 1
                else f"{n} passages ne seront pas dans la copie.")
        avertissement = ""
        if not self._film_pour_coupe() or not hasattr(self, "trim_start"):
            phrase = base
        else:
            try:
                gardes = pipeline.passages_gardes(
                    self.info.duration, self.trim_start.value(), self.trim_end.value(), self._coupes)
            except ToolError as exc:
                phrase = f"{base} {ergonomie.expliquer(str(exc))[0]}"
            else:
                reste = sum(max(0.0, fin - debut) for debut, fin in gardes)
                phrase = f"{base} La copie gardera {_duree(reste)}."
                if len(gardes) >= 2:                      # coupe au milieu : morceaux assemblés
                    avertissement = self._options_contre_coupe()
        return f"{phrase} Ce temps ne sera pas restauré.{avertissement}"

    def _options_contre_coupe(self) -> str:
        """Prévient AVANT « Restaurer » : ces options ne vont pas avec une coupe au milieu
        (pipeline.export la refuserait). Nommées comme à l'écran ; rien n'est décoché."""
        try:
            s = self.settings()
        except Exception:            # réglage pas encore prêt : pas d'avertissement plutôt qu'une erreur
            return ""
        cases = []
        if s.use_ai:
            cases.append("« Amélioration IA »")
        if s.dust:
            cases.append("« Enlever les poussières et rayures »")
        if s.source != "film":
            for actif, nom in ((s.tape_noise, "« Bruit de bande »"), (s.chroma_repair, "« Couleur des décrochages »"),
                               (s.dropouts, "« Taches d'une seule image »")):
                if actif:
                    cases.append(nom)
        cadence = bool(pipeline.retime(self.info, s))
        if not cases and not cadence:
            return ""
        noms = cases + (["« Cadence de tournage »"] if cadence else [])
        liste = noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]
        gestes = []
        if cases:
            gestes.append("décochez " + (cases[0] if len(cases) == 1 else "ces cases"))
        if cadence:
            gestes.append("remettez « Cadence de tournage » sur « Celle du fichier »")
        return (f" Attention : cette coupe ne partira pas avec {liste}. "
                f"Pour la garder, {' et '.join(gestes)} ; ou bien n'enlevez que le début et la fin.")

    def _rafraichir_passages(self) -> None:
        self._rafraichir_guide_coupes()
        note = getattr(self, "s_passages_note", None)
        if note is not None:
            note.setText(self._phrase_passages())
        lignes = getattr(self, "_passage_lignes", None)
        if not lignes:
            return
        for i, (lab, btn, row) in enumerate(lignes):
            if i < len(self._coupes):
                a, b = self._coupes[i]
                lab.setText(f"De {_duree(a)} à {_duree(b)}")
                btn.setAccessibleName(f"Remettre le passage {i + 1}")
                row.setVisible(True)
            else:
                row.setVisible(False)
        self._rafraichir_barre()

    def _coupe_tout(self) -> None:
        self._coupes = []
        self._coupe_ouverte = None
        self._texte_couper("Couper ici")
        for sp in (self.trim_start, self.trim_end):
            sp.setValue(0)
        self._rafraichir_passages()
        self.status.setText("Tout le film sera gardé. L'original n'est pas modifié.")

    def _coupe_depuis_extrait(self, fin: bool) -> None:
        """Le début de l'aperçu (ou sa fin, 10 s plus loin) devient le début ou la fin de la copie."""
        if not self.info or getattr(self, "is_photo", False):
            self.status.setText("Choisissez d'abord un film, puis placez l'extrait.")
            return
        ici = self.start_spin.value()
        if not fin:
            if self.trim_end.value() and ici >= self.trim_end.value() - 0.5:
                self.status.setText("Ce moment est après la fin choisie. Reculez l'extrait, ou repoussez la fin.")
                return
            self.trim_start.setValue(ici)
            if ici <= 0:
                self.status.setText("Le film commencera dès le début. Avancez « Début de l'extrait » pour couper la neige.")
            else:
                self.status.setText(f"Le film commencera à {_duree(ici)}.")
            return
        stop = min(self.info.duration or ici + 10, ici + 10)
        if stop <= self.trim_start.value() + 0.5:
            self.status.setText("Placez l'extrait plus loin : la fin doit être après le début.")
            return
        if self.info.duration and stop >= self.info.duration - 0.5:
            self.trim_end.setValue(0)
            self.status.setText("Le film ira jusqu'à la fin. Reculez l'extrait pour enlever la fin de bande.")
            return
        self.trim_end.setValue(stop)
        self.status.setText(f"Le film s'arrêtera à {_duree(stop)}.")

    def _montrer_debut_garde(self) -> None:
        if not self.info or getattr(self, "is_photo", False):
            self.status.setText("Choisissez d'abord un film pour placer l'aperçu.")
            return
        self.start_spin.setValue(min(self.trim_start.value(), self.start_spin.maximum()))
        self.status.setText(f"L'aperçu partira à {_duree(self.start_spin.value())}. "
                            "Cliquez sur « Voir l'avant / après ».")

    def start_export(self) -> None:
        if not self.info or self._busy():
            return
        out_dir = Path(self.out_edit.text() or self.info.path.parent)
        if not out_dir.is_dir() or not pipeline.is_writable(out_dir):
            try:
                new_dir, _ = pipeline.output_dir_for(out_dir)
            except ToolError as exc:
                self.status.setText(ergonomie.expliquer(str(exc))[0])
                ergonomie.montrer_erreur(self, str(exc))
                return
            QMessageBox.information(self, "Dossier de sortie",
                                    f"Impossible d'enregistrer dans :\n{out_dir}\n\n"
                                    f"Le film restauré sera enregistré dans :\n{new_dir}")
            out_dir = new_dir
            self.out_edit.setText(str(out_dir))
        info, s = self.info, self.settings()
        if getattr(self, "is_photo", False):
            out = photo.output_path(info, s, out_dir)
            self.status.setText(f"Restauration vers {out.name}…")
            def restaurer_photo(c, p):
                choix = self._choix_ia(info, s, 1, c, p)
                return photo.restore_photo(info, choix, photo.output_path(info, choix, out_dir),
                                           self.tools, cancel=c, progress=p)
            self._launch(restaurer_photo,
                         self._export_done, job="export")
            return
        try:
            out = pipeline.unique_output_path(info, s, out_dir)
            gardes, start, length = pipeline.bornes_a_exporter(
                info.duration, self.trim_start.value(), self.trim_end.value(), self._coupes)
        except ToolError as exc:
            self.status.setText(ergonomie.expliquer(str(exc))[0])
            ergonomie.montrer_erreur(self, str(exc))
            return
        self.status.setText(f"Restauration vers {out.name}…")
        def restaurer(c, p):
            duree = sum(b - a for a, b in gardes) if gardes else info.duration
            choix = self._choix_ia(info, s, duree, c, p)
            cible = pipeline.unique_output_path(info, choix, out_dir)
            return pipeline.export(info, choix, cible, self.tools, cancel=c, progress=p,
                                   start=start, duration=length, passages=gardes if len(gardes) > 1 else None)
        self._launch(restaurer, self._export_done, job="export")

    def check_install(self) -> None:
        """Lance l'autotest (le même que celui de la fabrication Windows) et montre le rapport."""
        if self._busy():
            return
        from .__main__ import autotest
        folder = Path(tempfile.mkdtemp(prefix="vhsrestore_verif_"))

        def job(cancel, progress):
            progress(0.02, "Vérification de l'installation…")
            try:
                code = autotest(str(folder), progress=lambda f, m: progress(f, f"Vérification : {m}"),
                                cancel=cancel)
                text = (folder / "autotest.txt").read_text(encoding="utf-8", errors="replace")
            finally:
                shutil.rmtree(folder, ignore_errors=True)
            return code, text
        self.status.setText("Vérification de l'installation…")
        self.check_btn.setText("Vérification en cours…")
        self._launch(job, self._check_done)

    def _check_done(self, res) -> None:
        code, text = res
        ok = code == 0
        self.status.setText("Installation vérifiée : tout fonctionne." if ok else
                            "Vérification : un problème a été trouvé.")
        box = QMessageBox(QMessageBox.Information if ok else QMessageBox.Warning, "Vérifier l'installation",
                          "Tout fonctionne : une vidéo d'essai a été analysée puis restaurée."
                          if ok else "Un problème a été trouvé. Le rapport ci-dessous aide à le corriger.",
                          parent=self)
        box.setDetailedText(text)
        box.exec()

    def _annexe_interrompue(self, exc):
        photo = getattr(self, "is_photo", False)
        texte = "Votre photo restaurée est prête." if photo else "Votre film restauré est prêt."
        p = exc.principal
        self._montrer_fini(f"{texte} {exc}\n\n{p.name}", p.parent, p, "photo" if photo else "film")
        self.status.setText(texte)

    def _export_done(self, out: Path) -> None:
        extra = ""
        kind = self.settings().audio_copy
        if kind in ("wav", "flac"):
            side = out.with_suffix(".wav" if kind == "wav" else ".flac")
            if side.is_file():
                extra = f"\n\nCopie du son restauré :\n{side.name}"
        if getattr(self, "is_photo", False):
            colored = photo.colorized_path(out)
            more = (f"\n\nCopie colorisée par l'IA (couleurs inventées) :\n{colored.name}"
                    if colored.is_file() else "")
            self._montrer_fini(
                f"Votre photo restaurée est prête :\n{out.name}{more}\n\n"
                f"Elle se trouve dans le dossier :\n{out.parent}\n\n"
                "La photo d'origine n'a pas été modifiée.",
                out.parent, out, "photo")
        else:
            self._montrer_fini(
                f"Votre film restauré est prêt :\n{out.name}\n\n"
                f"Il se trouve dans le dossier :\n{out.parent}{extra}\n\n"
                "Le film d'origine n'a pas été modifié.",
                out.parent, out, "film")
        self.status.setText(f"Terminé : {out.name}")

    def _montrer_fini(self, texte: str, dossier: Path, fichier: Path | None, genre: str) -> None:
        """Écran « C'est prêt », pas une petite boîte. Trois grands boutons."""
        self.options.hide()
        self.s_fini_texte.setText(texte)
        self.bilan.setVisible(bool(texte))
        self.s_info.setText("<b>Terminé.</b> Le résultat est prêt : regardez-le ou ouvrez son dossier "
                            "avec les boutons ci-dessous.")
        self.s_info.setToolTip("")
        self._fini_dossier = Path(dossier)
        self._fini_fichier = Path(fichier) if fichier else None
        if genre == "photo":
            self.s_voir.setText("Voir la photo")
            self.s_autre.setText("Restaurer une autre photo")
            self.s_voir.setVisible(True)
        elif genre == "films":                            # cassette séparée : déjà nommés
            self.s_voir.setText("Regarder le premier film")
            self.s_autre.setText("Restaurer un autre film")
            self.s_voir.setVisible(True)
        elif genre == "dossier":
            self.s_voir.setVisible(False)
            self.s_autre.setText("Restaurer un autre dossier")
        else:
            self.s_voir.setText("Regarder le film")
            self.s_autre.setText("Restaurer un autre film")
            self.s_voir.setVisible(True)
        for b in (self.s_vides, self.s_montage, self.s_separer, self.s_partager):   # outils de film seulement
            b.setVisible(genre == "film")
        self.s_nommer.setVisible(genre in ("film", "photo") and self._fini_fichier is not None)
        self.s_nommer.setText("Nommer cette photo" if genre == "photo" else "Nommer ce film")
        self.s_nommer.setAccessibleName(self.s_nommer.text())
        self.s_voir.setAccessibleName(self.s_voir.text())
        self.s_ouvrir.setAccessibleName("Ouvrir le dossier du résultat")
        self.s_autre.setAccessibleName(self.s_autre.text())
        self.s_fini.setVisible(True)
        self._update_state()                              # « Nommer le résultat… » suit le résultat
        self._signaler_fin()

    def _afficher_bilan(self):
        dialogue = QDialog(self)
        dialogue.setWindowTitle("Bilan de la restauration")
        disposition = QVBoxLayout(dialogue)
        texte = QPlainTextEdit(self.s_fini_texte.text())
        texte.setReadOnly(True)
        disposition.addWidget(texte)
        fermer = QPushButton("Fermer")
        fermer.clicked.connect(dialogue.accept)
        disposition.addWidget(fermer)
        dialogue.resize(640, 360)
        dialogue.exec()
        dialogue.deleteLater()

    def _signaler_fin(self) -> None:
        """Son bref et clignotement dans la barre des tâches : le travail est fini."""
        QApplication.beep()
        QApplication.alert(self, 8000)

    def _voir_resultat(self) -> None:
        cible = getattr(self, "_fini_fichier", None)
        if cible and Path(cible).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(cible)))
            self.status.setText("Ouverture du résultat…")
        else:
            self.status.setText("Le fichier résultat n'est plus là.")
            ergonomie.montrer_erreur(self, "Fichier introuvable : " + str(cible or ""))

    def _ouvrir_dossier_fini(self) -> None:
        dossier = getattr(self, "_fini_dossier", None)
        if dossier and Path(dossier).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dossier)))
            self.status.setText("Ouverture du dossier…")
        else:
            self.status.setText("Le dossier n'est plus là.")
            ergonomie.montrer_erreur(self, "Dossier introuvable : " + str(dossier or ""))

    def _restaurer_autre(self) -> None:
        self.s_fini.setVisible(False)
        self.status.setText("Choisissez le suivant.")
        if "dossier" in self.s_autre.text().lower():
            self.start_folder()
        else:
            self._choose_file()
        if self.s_fini.isHidden() and not self._busy():   # fenêtre de choix fermée sans rien choisir
            self._info_suite()
        self._update_state()

    def _done_box(self, title: str, text: str, folder: Path) -> None:
        """Ancien nom : l'écran « C'est prêt » remplace la boîte."""
        genre = "photo" if "photo" in title.lower() else "film"
        self._montrer_fini(text, folder, None, genre)

    def settings_for(self, info: MediaInfo) -> pipeline.Settings:
        """Réglages d'un film du dossier : options choisies, origine propre à chaque film
        (choix manuel s'il y en a un, sinon suggestion de l'analyse)."""
        return self._reglages_dossier()(info)

    def _reglages_dossier(self) -> Callable[[MediaInfo], pipeline.Settings]:
        """Les cases sont lues ici, dans le fil de l'interface ; la fonction rendue sert ensuite
        dans le fil de travail sans toucher aux widgets (Qt ne le permet pas)."""
        base = self.settings(with_advice=False)
        # conseils propres à CHAQUE film du dossier : appliqués d'office, sauf si l'utilisateur
        # a décoché la case pour le fichier ouvert
        conseils = self.s_advice.isChecked() or self.s_advice.isHidden()
        dominante = self.cast_check.isChecked()
        choix = self.source_combo.currentData()
        cases = {k: getattr(self, k).isChecked() for k in ("flicker_check", "dust_check", "tape_check",
                                                           "chroma_check", "dropout_check")}

        def pour(info: MediaInfo) -> pipeline.Settings:
            s = apply_advice(base, advise(info)) if conseils else base
            if dominante:
                if info.cast_rgb:
                    gr, gg, gb = cast_gains(info.cast_rgb)
                    s = dataclasses.replace(s, gain_r=gr, gain_g=gg, gain_b=gb)
                else:
                    s = dataclasses.replace(s, gain_r=1.0, gain_g=1.0, gain_b=1.0)
            src = choix or info.suggested_source
            return dataclasses.replace(s, profile=profile_for(s.profile.key, src), source=src,
                                       scan=None, dar=None, playback_fps=None,
                                       deflicker=cases["flicker_check"] and src != "video",
                                       dust=cases["dust_check"] and src == "film",
                                       tape_noise=cases["tape_check"] and src != "film",
                                       chroma_repair=cases["chroma_check"] and src != "film",
                                       dropouts=cases["dropout_check"] and src != "film",
                                       mask_bottom=s.mask_bottom if src == "video" else 0)
        return pour

    def start_folder(self) -> None:
        if self._busy():
            return
        d = QFileDialog.getExistingDirectory(self, "Dossier contenant les films à restaurer",
                                             self._dossier_depart())
        if d:
            self._retenir_dossier(d)
            self.restore_folder(Path(d))

    def restore_folder(self, folder: Path) -> None:
        self.s_fini.setVisible(False)
        # les coupes du film ouvert ne partent JAMAIS avec un dossier (chaque cassette est différente) :
        # on le dit en haut de la page (la ligne d'état est aussitôt remplacée par « Film 1 sur … »)
        # et dans le résumé « C'est prêt » ; pas de fenêtre à fermer
        coupes = bool(getattr(self, "_coupes", None))
        self._remarque_dossier = ergonomie.PHRASE_COUPES_DOSSIER if coupes else ""
        self.status.setText(ergonomie.PHRASE_COUPES_DOSSIER if coupes else "Restauration du dossier…")
        reglages = self._reglages_dossier()
        self._launch(lambda c, p: pipeline.restore_folder(
                            folder, self.tools, reglages,
                            demander=self.worker.demander_ia,
                            cancel=c, progress=p), self._folder_done,
                     job="dossier")
        if coupes:
            self.s_info.setText(_insecables(f"<b>Travail en cours.</b> {ergonomie.PHRASE_COUPES_DOSSIER} "
                                            f"{ergonomie.PHRASE_PATIENCE}"))

    def _folder_done(self, res: pipeline.BatchResult) -> None:
        n = len(res.done)
        remarque, self._remarque_dossier = getattr(self, "_remarque_dossier", ""), ""
        texte = ergonomie.resume_dossier(n, len(res.skipped), list(res.errors), remarque=remarque)
        if n == 0 and not res.skipped:          # rien de fait : pas d'écran « C'est prêt »
            self.status.setText("Aucun fichier du dossier n'a pu être restauré.")
            self._info_suite("<b>Aucun fichier du dossier n'a pu être restauré.</b> ")
            QMessageBox.warning(self, "Dossier", texte)
            return
        if res.fallback:
            texte += "\nLe dossier d'origine ne pouvait pas être modifié : le résultat est ailleurs."
        self._montrer_fini(texte, res.out_dir, None, "dossier")
        self.status.setText(f"Terminé : {n} fichier{'s' if n != 1 else ''} restauré{'s' if n != 1 else ''} "
                            f"dans « {res.out_dir.name} ».")

    def cancel(self, confirmer: bool = False) -> None:
        if not self._busy():
            return
        if confirmer and self._travail_long():
            texte = "Arrêter maintenant ?\n\nLe travail déjà fait sur ce film sera perdu."
            if getattr(self, "_job", "") == "dossier":
                texte += "\nLes films déjà terminés, eux, restent."
            if not self._question("Arrêter", texte, "Oui, arrêter", "Non, continuer"):
                if self._busy():
                    self.status.setText("Le travail continue.")
                return
            if not self._busy():                    # fini pendant la question : rien à arrêter
                return
        self.worker.cancel_event.set()
        self.status.setText("Annulation en cours…")

    def _travail_long(self) -> bool:
        """Un arrêt après quelques secondes, ou sur un film entier, demande confirmation."""
        debut = getattr(self, "_debut_travail", None)
        ecoule = 0.0 if debut is None else time.monotonic() - debut
        if ecoule >= 20:
            return True
        return getattr(self, "_job", "") in _TRAVAUX_LONGS and ecoule >= 8

    # ------------------------------------------------------------ worker
    def _launch(self, fn: Callable, on_success: Callable[[Any], None], job: str = "") -> None:
        self._job = job
        self._debut_travail = time.monotonic()
        self._fini_a_rendre = job in ("vides", "vides_copie", "separation", "installation", "nommer",
                                      "partage") and self.s_fini.isVisible()
        if job and job not in ("vides", "installation", "nommer", "partage"):   # le film reste le même :
            self.s_fini.setVisible(False)                                          # « C'est prêt » reste
        self.worker = w = Worker(fn)
        # On garde les fils terminés : PySide plante si le QThread est détruit
        # pendant que l'interface traite encore ses signaux.
        self._fils = getattr(self, "_fils", [])
        self._fils.append(w)
        w.choix_ia.connect(self._question_vitesse)
        w.progressed.connect(self._on_progress)
        w.succeeded.connect(on_success)
        if job == "export":
            w.copie_incomplete.connect(self._annexe_interrompue)
        else:
            w.copie_incomplete.connect(lambda exc: self._on_failed(str(exc)))
        w.failed.connect(self._on_failed)
        w.cancelled.connect(self._on_cancelled)
        w.finished.connect(self._on_finished)
        if self.progress.maximum() != 0:
            self.progress.setValue(0)
        self.eta = Eta()
        w.start()
        if job in _TRAVAUX_LONGS:
            self.s_info.setText("<b>Travail en cours.</b> L'avancement s'affiche juste sous les boutons. "
                                + ergonomie.PHRASE_PATIENCE)
        self._update_state()

    def _on_progress(self, frac: float, msg: str) -> None:
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1000)
        self.progress.setValue(int(frac * 1000))
        left = self.eta.update(frac) if getattr(self, "eta", None) else ""
        texte = f"{msg} — encore {left}" if left else f"{msg} {frac * 100:.0f} %"
        if getattr(self, "_job", "") in _TRAVAUX_LONGS:
            texte += "\n" + ergonomie.PHRASE_PATIENCE
        self.status.setText(texte)

    def _on_failed(self, msg: str) -> None:
        clair, _ = ergonomie.expliquer(msg)
        self.status.setText(clair)
        self.s_fini.setVisible(False)
        self._rendre_fini()
        self._montage_en_attente = None
        if self.s_fini.isHidden():
            self._info_suite("<b>Cela n'a pas abouti.</b> ")
        ergonomie.montrer_erreur(self, msg)

    def _on_cancelled(self) -> None:
        job = getattr(self, "_job", "")
        if job == "export":                     # « Restaurer » ne vaut que pour une restauration
            quoi = "Votre photo n'a pas été modifiée." if getattr(self, "is_photo", False) \
                else "Votre film n'a pas été modifié."
            texte = f"Arrêté. {quoi} Pour recommencer, cliquez sur « Lancer la restauration »."
        elif job == "dossier":
            texte = "Arrêté. Les originaux n'ont pas été modifiés ; les fichiers déjà terminés restent."
        elif job in ("vides", "vides_copie", "separation", "partage"):
            texte = "Arrêté. Votre film n'a pas été modifié."
        elif job == "nommer":
            texte = "Arrêté. Le nom n'a pas changé."
        elif job == "installation":
            texte = "Arrêté. Rien n'a été installé."
        else:                                   # aperçu, analyse, vérification
            texte = "Arrêté. Rien n'a été modifié."
        self.status.setText(texte)
        self._rendre_fini()
        self._montage_en_attente = None
        if self.s_fini.isHidden():
            self._info_suite("<b>Arrêté.</b> Rien n'a été modifié. ")

    def _rendre_fini(self) -> None:
        """Copie sans passages vides annulée ou impossible : l'écran « C'est prêt » du film revient
        (ses boutons Regarder, Ouvrir le dossier, Montage restent utiles)."""
        fini = getattr(self, "_fini_fichier", None)
        if getattr(self, "_fini_a_rendre", False) and fini and Path(fini).is_file():
            self.s_fini.setVisible(True)
        self._fini_a_rendre = False

    def _on_finished(self) -> None:
        fini = self.sender()
        if fini in self._fils:
            self._fils.remove(fini)
            fini.fn = None  # libère les médias et les fonctions capturés
        if fini is not self.worker:
            return
        if getattr(self, "_fermeture_demandee", False):
            QTimer.singleShot(0, self.close)
            return
        self._ecoute_demandee = False
        self.check_btn.setText("Vérifier l'installation")
        self.progress.setRange(0, 1000)
        if not self.status.text().startswith(("Terminé", "Aperçu prêt", "Comparez avec les boutons",
                                              "Vidéo analysée", "Photo analysée")):
            self.progress.setValue(0)
        else:
            self.progress.setValue(1000)
        self._update_state()

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if hasattr(self, "run_btn"):
            ecran.adapter(self)          # écran bas : boutons et petites images resserrés

    def closeEvent(self, e) -> None:  # noqa: N802
        assistant = getattr(self, "assistant", None)
        if assistant is not None:                   # images du rendu en préparation : FFmpeg arrêté
            assistant.arreter()
        self.lumiere.arreter()
        if self._busy():
            if getattr(self, "_fermeture_demandee", False):
                e.ignore()
                return
            if not self._question("Quitter", "Un travail est en cours. L'arrêter et quitter ?",
                                  "Oui, arrêter et quitter", "Non, continuer"):
                e.ignore()
                return
            if self._busy():                        # le travail a pu finir pendant la question
                self._fermeture_demandee = True
                self.worker.cancel_event.set()
                self.status.setText("Arrêt en cours. La fenêtre va se fermer.")
                e.ignore()
                return
        self._save_prefs()
        self._couper_images()
        self.lumiere.fermer()
        shutil.rmtree(self.preview_dir, ignore_errors=True)
        e.accept()

    def _prefs(self) -> QSettings | None:
        # Les tests lancent plusieurs fenêtres dans le même compte : ils ne doivent
        # pas se transmettre le profil ou le dossier de sortie.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return None
        return QSettings("VHSRestoreAI", "VHSRestoreAI")

    def _load_prefs(self) -> None:
        s = self._prefs()
        if s is None:
            return
        key = s.value("profile")
        if key in self.profile_buttons:
            self.profile_buttons[str(key)].setChecked(True)
        if s.contains("restore_audio"):
            self.audio_check.setChecked(bool(s.value("restore_audio", True, type=bool)))
        if s.contains("use_rnnoise"):
            self.rnnoise_check.setChecked(bool(s.value("use_rnnoise", False, type=bool)))
        if s.contains("audio_highpass"):
            self.wind_check.setChecked(bool(s.value("audio_highpass", False, type=bool)))
        if s.contains("audio_presence"):
            self.presence_check.setChecked(bool(s.value("audio_presence", False, type=bool)))
        if s.contains("correct_cast"):
            self.cast_check.setChecked(bool(s.value("correct_cast", False, type=bool)))
        # décalage et dérive du son : propres à chaque cassette, plus gardés d'un film à l'autre
        # (une dérive réglée une fois pour un essai ralentissait tous les films suivants)
        s.remove("audio_offset_ms")
        s.remove("audio_drift_ms_per_min")
        mains = int(float(s.value("audio_mains_hz", 0) or 0))
        idx = self.mains_combo.findData(mains)
        if idx >= 0:
            self.mains_combo.setCurrentIndex(idx)
        copy = str(s.value("audio_copy", "") or "")
        idx = self.copy_combo.findData(copy)
        if idx >= 0:
            self.copy_combo.setCurrentIndex(idx)
        self.mask_spin.setValue(int(float(s.value("mask_bottom", 0) or 0)))
        self.edge_spin.setValue(int(float(s.value("mask_sides", 0) or 0)))
        self.chroma_spin.setValue(int(float(s.value("chroma_shift", 0) or 0)))
        if s.contains("tape_noise"):
            self.tape_check.setChecked(bool(s.value("tape_noise", False, type=bool)))
            self.chroma_check.setChecked(bool(s.value("chroma_repair", False, type=bool)))
            self.dropout_check.setChecked(bool(s.value("dropouts", False, type=bool)))
        out = str(s.value("out_dir", "") or "")
        if out and s.value("out_dir_manual", False, type=bool):   # ancien réglage automatique : ignoré
            self.out_edit.setText(out)
            self._out_manual = True
        try:
            choisi = s.value("texte", None)
            if choisi is None:               # premier lancement : selon la taille de l'écran
                ecr = self.screen().availableGeometry() if self.screen() is not None else None
                pct = ecran.texte_selon_ecran(ecr.width(), ecr.height()) if ecr is not None else 100
            else:
                pct = int(float(choisi or 100))
        except (TypeError, ValueError):
            pct = 100
        self.set_taille_texte(pct, annoncer=False)
        brut = s.value("recents", []) or []
        if isinstance(brut, str):
            brut = [brut]
        self._afficher_recents([str(p) for p in list(brut)])

    def _save_prefs(self) -> None:
        s = self._prefs()
        if s is None:
            return
        key = next((k for k, b in self.profile_buttons.items() if b.isChecked()), "equilibre")
        s.setValue("profile", key)
        s.setValue("restore_audio", self.audio_check.isChecked())
        s.setValue("use_rnnoise", self.rnnoise_check.isChecked())
        s.setValue("audio_highpass", self.wind_check.isChecked())
        s.setValue("audio_presence", self.presence_check.isChecked())
        s.setValue("correct_cast", self.cast_check.isChecked())
        s.setValue("audio_mains_hz", int(self.mains_combo.currentData() or 0))
        s.setValue("audio_copy", str(self.copy_combo.currentData() or ""))
        s.setValue("mask_bottom", self.mask_spin.value())
        s.setValue("mask_sides", self.edge_spin.value())
        s.setValue("chroma_shift", self.chroma_spin.value())
        s.setValue("tape_noise", self.tape_check.isChecked())
        s.setValue("chroma_repair", self.chroma_check.isChecked())
        s.setValue("dropouts", self.dropout_check.isChecked())
        s.setValue("out_dir", self.out_edit.text() if self._out_manual else "")
        s.setValue("out_dir_manual", bool(self._out_manual))


def main() -> int:
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("VHS Restore AI")
    app.aboutToQuit.connect(_eteindre_a_la_sortie)
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    traduction = QTranslator(app)           # textes standard de Qt en français (« Annuler », « Ouvrir »…)
    if traduction.load(QLocale(QLocale.French, QLocale.France), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(traduction)
    choix = QSettings("VHSRestoreAI", "VHSRestoreAI").value("affichage")
    # Sans choix enregistré : clair, comme la maquette. Seul « sombre » explicite reste sombre.
    theme.set_mode("sombre" if str(choix) == "sombre" else "clair")
    theme.apply(app)
    win = MainWindow()
    win.showMaximized()
    if not (win.tools.ffmpeg.path and win.tools.ffprobe.path):
        QMessageBox.critical(win, "FFmpeg manquant",
                             "FFmpeg est nécessaire et n'a pas été trouvé.\n\n"
                             "Lancez « installer.bat » (il télécharge FFmpeg dans le dossier tools), "
                             "ou installez FFmpeg et ajoutez-le au PATH.")
    elif win.tools.missing_filters:
        QMessageBox.critical(win, "FFmpeg trop ancien",
                             "Filtres manquants : " + ", ".join(win.tools.missing_filters))
    else:
        QTimer.singleShot(400, win.maybe_welcome)       # premier lancement : mode d'emploi
    return app.exec()
