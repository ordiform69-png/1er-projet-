"""Interface PySide6. Les traitements tournent dans un QThread : l'interface
reste réactive, et rien ne tourne en arrière-plan quand l'application est inactive."""
from __future__ import annotations

import dataclasses
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (QEvent, QObject, QPoint, QRect, QSettings, QSize, QStandardPaths, Qt, QThread,
                            QUrl, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QApplication, QBoxLayout, QButtonGroup,
                               QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from . import ergonomie, icons, installer, photo, pipeline, theme, vides
from .dvd import open_media
from .probe import MediaInfo, cast_gains
from .advice import advise
from .eta import Eta
from .advice import apply as apply_advice
from .profiles import PROFILES, RESOLUTIONS, profile_for
from .tools import Cancelled, ToolError, Toolset, detect_tools, run_capture

log = logging.getLogger("vhs_restore")
VIDEO_FILTER = ("Vidéos et photos (*.avi *.mp4 *.mkv *.mov *.mpg *.mpeg *.m2t *.mts *.ts *.dv *.vob *.wmv *.m4v "
                "*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp);;Tous les fichiers (*)")


class Worker(QThread):
    """Exécute fn(cancel, progress) hors du thread graphique."""
    progressed = Signal(float, str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: Callable[[threading.Event, Callable[[float, str], None]], Any]):
        super().__init__()
        self.fn = fn
        self.cancel_event = threading.Event()

    def run(self) -> None:
        _keep_awake(True)
        try:
            res = self.fn(self.cancel_event, lambda f, m: self.progressed.emit(f, m))
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
        self.after_label = "RESTAURÉ"
        self.setMinimumSize(480, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def set_still(self, path: Path) -> None:
        pm = QPixmap(str(path))
        half = pm.width() // 2
        self.before, self.after = pm.copy(0, 0, half, pm.height()), pm.copy(half, 0, half, pm.height())
        self.update()

    def clear(self) -> None:
        self.before = self.after = None
        self.update()

    def set_mode(self, mode: str) -> None:
        """Comparer sans geste précis : original seul, restauré seul, ou les deux (souris)."""
        self.mode = mode if mode in ("before", "after") else "split"
        if self.mode == "split":
            self.split = 0.5
        self.update()

    def set_after_label(self, text: str) -> None:
        """Étiquette de droite : « RESTAURÉ », ou « COULEURS IA » pour une photo colorisée."""
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
        if self.before is None or self.after is None:
            p.setPen(QColor(theme.MONITEUR_TEXTE))
            f = p.font()
            f.setPointSizeF(max(f.pointSizeF(), 13))
            p.setFont(f)
            p.drawText(inner, Qt.AlignCenter,
                       "L'avant / après apparaîtra ici\n\n"
                       "(choisissez un film ou une photo, puis « 2. Voir l'avant / après »)")
            return
        size = self.before.size().scaled(inner.size(), Qt.KeepAspectRatio)
        r = QRect(QPoint(0, 0), size)
        r.moveCenter(inner.center())
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.mode in ("before", "after"):          # une seule image, plein cadre
            p.drawPixmap(r, self.before if self.mode == "before" else self.after)
            self._badges(p, r, ("ORIGINAL",) if self.mode == "before" else (self.after_label,))
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
        self._badges(p, r, ("ORIGINAL", self.after_label))

    def _badges(self, p: QPainter, r: QRect, texts: tuple) -> None:
        """Pastilles « ORIGINAL » (à gauche) et « RESTAURÉ » (à droite) sur l'image."""
        f = p.font()
        f.setPointSizeF(max(f.pointSizeF(), 13))
        f.setBold(True)
        p.setFont(f)
        fm = p.fontMetrics()
        h = fm.height() + 10
        largeur = sum(fm.horizontalAdvance(t) + 22 for t in ("ORIGINAL", self.after_label)) + 36
        etroit = r.width() < largeur    # photo en hauteur : « Restauré » passe en bas
        for text in texts:
            left = text == "ORIGINAL"
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


class _Mirror:
    """Relaie les appels à plusieurs widgets identiques (page simple + page avancée) ;
    les lectures (text(), maximum(), attributs) viennent du premier."""

    def __init__(self, *widgets: QWidget) -> None:
        self._w = widgets

    def __getattr__(self, name: str) -> Any:
        first = getattr(self._w[0], name)
        if not callable(first):
            return first

        def call(*a: Any, **k: Any) -> Any:
            out = first(*a, **k)
            for w in self._w[1:]:
                getattr(w, name)(*a, **k)
            return out
        return call


BIG = "QPushButton{font-size:15pt;padding:12px;min-height:44px}"


class _ReelMark(QWidget):
    """Cassette dessinée : deux bobines et une fenêtre de bande. Pas d'image externe."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(68, 48)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.ACCENT), 1.4))
        p.setBrush(QColor("#0a2228"))
        p.drawRoundedRect(1, 6, 66, 36, 6, 6)
        p.setBrush(QColor("#12343c"))
        p.drawRoundedRect(18, 14, 32, 16, 2, 2)
        p.setBrush(Qt.NoBrush)
        for cx in (16, 52):
            p.setPen(QPen(QColor("#e8b15a"), 1.6))
            p.drawEllipse(QPoint(cx, 24), 7, 7)
            p.drawEllipse(QPoint(cx, 24), 2, 2)
        p.setPen(QPen(QColor(theme.ACCENT), 1))
        p.drawLine(23, 24, 45, 24)


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


class StepButton(QPushButton):
    """Grand bouton d'étape : numéro dans un cercle, texte aligné à gauche."""

    def __init__(self, number: str, text: str, icon: str = "") -> None:
        super().__init__(text)
        self.number = number
        self.icon_name = icon
        self.suggested = False           # étape suivante conseillée : cadre plus épais
        self._echelle = 1.0
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(64)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_echelle(self, echelle: float) -> None:
        self._echelle = echelle
        self.setMinimumHeight(max(64, int(64 * echelle)))
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        principal = self.objectName() == "principal"
        on = self.isEnabled()
        if principal and on:
            bg, fg, border = QColor(theme.AMBRE), QColor(theme.AMBRE_TEXTE), QColor(theme.AMBRE)
        elif principal:
            bg, fg = QColor(theme.AMBRE_ETEINT), QColor(theme.AMBRE_ETEINT_TEXTE)
            border = bg
        elif on:
            bg, fg, border = QColor(theme.CARTE), QColor(theme.TEXTE), QColor(theme.ETAPE_CADRE)
            if self.underMouse():
                border = QColor(theme.ACCENT)
                bg = QColor(theme.ETAPE_SURVOL)
        else:
            bg, fg, border = QColor(theme.FOND_DESACTIVE), QColor(theme.TEXTE_DESACTIVE), QColor(theme.ETAPE_ETEINT)
        width = 1.4
        if self.suggested and on:        # « c'est ici maintenant »
            width = 3.2
            border = QColor(theme.TEXTE if principal else theme.ACCENT)
        p.setPen(QPen(border, width))
        p.setBrush(bg)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 12, 12)
        cx, cy, r = 30, self.height() // 2, 15
        if principal:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.AMBRE_TEXTE if on else theme.AMBRE_ETEINT_TEXTE))
            p.drawEllipse(QPoint(cx, cy), r, r)
            p.setPen(QColor(theme.AMBRE if on else theme.AMBRE_ETEINT))
        else:
            p.setPen(QPen(QColor(theme.ACCENT if on else theme.ACCENT_SOURD), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPoint(cx, cy), r, r)
            p.setPen(fg)
        f = QFont(theme.BODY_FAMILY or p.font().family())     # police large, plus lisible
        f.setPointSizeF(14 * self._echelle)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRect(cx - r, cy - r, r * 2, r * 2), Qt.AlignCenter, self.number)
        x = 56
        if self.icon_name:
            col = (theme.AMBRE_TEXTE if on else theme.AMBRE_ETEINT_TEXTE) if principal else \
                (theme.ACCENT if on else theme.ICONE_GRISE)
            p.drawPixmap(x, cy - 12, icons.pixmap(self.icon_name, 24, col))
            x += 34
        f.setPointSizeF(16 * self._echelle)
        f.setBold(True)
        p.setFont(f)
        p.setPen(fg)
        p.drawText(QRect(x, 0, self.width() - x - 12, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        if self.hasFocus():
            p.setPen(QPen(QColor("#f3d7a1"), 3))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(self.rect().adjusted(3, 3, -4, -4), 10, 10)


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
        if subtitle:
            st = QLabel(subtitle)
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
    """Tuile de profil (Fidèle / Équilibré / Maximum) : icône, nom, petite phrase."""

    def __init__(self, name: str, icon: str, tagline: str) -> None:
        super().__init__(name)
        self.icon_name, self.tagline = icon, tagline
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(88)
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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
        p.drawPixmap(14, 14, icons.pixmap(self.icon_name, 28, col))
        f = QFont(theme.DISPLAY_FAMILY or p.font().family())
        f.setPointSizeF(15)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXTE))
        p.drawText(QRect(50, 10, r.width() - 56, 34), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        f = QFont(theme.BODY_FAMILY or p.font().family())
        f.setPointSizeF(11.5)
        p.setFont(f)
        p.setPen(QColor(theme.TEXTE_DOUX))
        p.drawText(QRect(14, 46, r.width() - 22, r.height() - 50), Qt.AlignLeft | Qt.TextWordWrap, self.tagline)
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
    "realesrgan": ("Real-ESRGAN", "Agrandissement par intelligence artificielle (profil Maximum, photos). "
                                  "Demande une carte graphique compatible Vulkan. L'IA peut inventer des "
                                  "détails, surtout sur les petits visages : vérifiez toujours l'aperçu."),
    "deepfilter": ("DeepFilterNet", "Nettoyage poussé des voix pour le profil Maximum, sur le processeur. "
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

PROFILE_LOOK = {"fidele": ("bouclier", "Doux et fidèle"),
                "equilibre": ("balance", "Conseillé"),
                "maximum": ("fusee", "Nettoyage fort")}


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
        self._build()
        self._refresh_tools()
        self._update_state()

    # ------------------------------------------------------------ construction
    def _build_simple(self) -> QWidget:
        """Page d'accueil : trois étapes, gros boutons, aucun réglage technique."""
        page = QWidget()
        page.setObjectName("page")
        v = QVBoxLayout(page)
        v.setContentsMargins(20, 14, 20, 10)
        v.setSpacing(10)
        band = QFrame()
        band.setObjectName("bandeau")
        bh = QHBoxLayout(band)
        bh.setContentsMargins(18, 12, 22, 14)
        bh.setSpacing(14)
        bh.addWidget(_ReelMark(), 0, Qt.AlignVCenter)
        bv = QVBoxLayout()
        bv.setSpacing(2)
        brand = QLabel("VHS RESTORE AI")
        brand.setObjectName("marque")
        title = QLabel("Restaurer un film ou une photo de famille")
        title.setObjectName("titre")
        title.setWordWrap(True)
        title.setMinimumWidth(80)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        filet = QFrame()
        filet.setObjectName("filet")
        bv.addWidget(brand)
        bv.addWidget(title)
        bv.addWidget(filet)
        bh.addLayout(bv, 1)
        coin = QVBoxLayout()                 # aide et affichage clair / sombre, toujours à portée
        coin.setSpacing(6)
        haut = QHBoxLayout()                 # deux lignes seulement : le bandeau laisse de la place à l'aperçu
        haut.setSpacing(6)
        coin.addLayout(haut)
        self.help_btn = QPushButton("Aide")
        self.help_btn.setIcon(icons.icon("info", "#9ae7f5"))
        self.help_btn.clicked.connect(self.show_welcome)
        self.help_btn.setAccessibleName("Aide")
        self.help_btn.setAccessibleDescription("Explique les trois étapes. Le bouton entouré est celui à utiliser.")
        self.theme_btn = QPushButton("Affichage clair" if theme.MODE == "sombre" else "Affichage sombre")
        self.theme_btn.setIcon(icons.icon("soleil", "#9ae7f5"))
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
            haut.addWidget(b)
        tailles = QHBoxLayout()
        tailles.setSpacing(4)
        self._taille_btns: dict[int, QPushButton] = {}
        self._echelle = 1.0
        for pct, lib in ((100, "A−"), (125, "A"), (150, "A+")):
            b = QPushButton(lib)
            b.setObjectName("bandeauBouton")
            b.setMinimumSize(44, 44)
            b.setCursor(Qt.PointingHandCursor)
            b.setAccessibleName(f"Taille du texte {pct} %")
            b.setAccessibleDescription("Agrandit ou réduit les textes du mode simple.")
            b.clicked.connect(lambda _=False, p=pct: self.set_taille_texte(p))
            tailles.addWidget(b, 1)
            self._taille_btns[pct] = b
        coin.addLayout(tailles)
        bh.addLayout(coin)
        v.addWidget(band)
        self.s_info = QLabel("Pour commencer, cliquez sur le bouton 1 « Choisir le film ou la photo ».")
        self.s_info.setWordWrap(True)
        self.s_info.setObjectName("infos")
        self.s_info.setMinimumWidth(80)
        v.addWidget(self.s_info)
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
        # boutons avant le texte : sur un portable, « Regarder le film » reste visible sans défiler
        self._fini_boutons = QBoxLayout(QBoxLayout.LeftToRight)
        self._fini_boutons.setSpacing(8)
        self._fini_boutons.addWidget(self.s_voir, 2)
        self._fini_boutons.addWidget(self.s_ouvrir, 1)
        self._fini_boutons.addWidget(self.s_autre, 1)
        fv.addLayout(self._fini_boutons)
        self.s_vides = _with_icon(QPushButton("Retirer les passages vides"), "ciseaux")
        self.s_vides.setToolTip("Neige, écran bleu ou noir en début, en fin ou au milieu de la cassette : "
                                "le logiciel les repère et propose une copie sans eux.")
        self.s_montage = _with_icon(QPushButton("Faire un montage"), "film")
        self.s_montage.setToolTip("Couper, assembler, ajouter un titre : ouvre votre film dans un "
                                  "logiciel de montage gratuit.")
        rangee2 = QHBoxLayout()
        rangee2.setSpacing(8)
        for b in (self.s_vides, self.s_montage):
            b.setObjectName("secondaire")
            b.setMinimumHeight(48)
            b.setCursor(Qt.PointingHandCursor)
            rangee2.addWidget(b, 1)
        self.s_vides.clicked.connect(self.retirer_vides)
        self.s_montage.clicked.connect(self.faire_montage)
        fv.addLayout(rangee2)
        fv.addWidget(self.s_fini_texte)
        self.s_fini.setVisible(False)
        v.addWidget(self.s_fini)
        self._recents_box = QWidget()
        self._recents_lay = QVBoxLayout(self._recents_box)
        self._recents_lay.setContentsMargins(0, 0, 0, 0)
        self._recents_lay.setSpacing(6)
        rec_titre = QLabel("Derniers fichiers")
        rec_titre.setObjectName("note")
        self._recents_lay.addWidget(rec_titre)
        self._recent_btns: list[QPushButton] = []
        self._recents_box.setVisible(False)
        v.addWidget(self._recents_box)
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
        conseil_l = QHBoxLayout()
        conseil_l.setContentsMargins(0, 0, 0, 0)
        conseil_l.addWidget(self.s_advice, 1)
        conseil_l.addWidget(self.s_aide_conseil, 0, Qt.AlignTop)
        v.addLayout(conseil_l)
        self.s_colorize = QCheckBox("Coloriser aussi — couleurs inventées par l'IA, pas les vraies "
                                    "(copie à part, le noir et blanc est gardé)")
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
        couleur_l = QHBoxLayout()
        couleur_l.setContentsMargins(0, 0, 0, 0)
        couleur_l.addWidget(self.s_colorize, 1)
        couleur_l.addWidget(self.s_aide_couleur, 0, Qt.AlignTop)
        v.addLayout(couleur_l)
        self._steps = QBoxLayout(QBoxLayout.LeftToRight)
        self._steps.setSpacing(8)
        self.s_choose = StepButton("1", "Choisir le film ou la photo", "dossier")
        self.s_choose.clicked.connect(self._choose_file)
        self.s_preview = StepButton("2", "Voir l'avant / après", "oeil")
        self.s_preview.clicked.connect(self.start_preview)
        self.s_run = StepButton("3", "Restaurer", "etincelle")
        self.s_run.clicked.connect(self.start_export)
        halo_cyan = _HoverHalo(theme.ACCENT)
        halo_ambre = _HoverHalo(theme.AMBRE)
        self._halos = (halo_cyan, halo_ambre)
        for b in (self.s_choose, self.s_preview, self.s_run):
            b.setObjectName("principal" if b is self.s_run else "etape")
            b.installEventFilter(halo_ambre if b is self.s_run else halo_cyan)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._steps.addWidget(b)
        self.s_choose.setAccessibleName("Étape 1, choisir le film ou la photo")
        self.s_choose.setAccessibleDescription("Ouvre la fenêtre pour choisir un fichier.")
        self.s_preview.setAccessibleName("Étape 2, voir l'avant et l'après")
        self.s_preview.setAccessibleDescription("Montre un extrait avant et après restauration.")
        self.s_run.setAccessibleName("Étape 3, restaurer")
        self.s_run.setAccessibleDescription("Lance la restauration. Le fichier d'origine n'est pas modifié.")
        v.addLayout(self._steps)
        self.s_note = note = QLabel("Votre fichier d'origine n'est jamais modifié : le résultat est enregistré "
                                    "à côté, avec « restaure » dans son nom.")
        note.setWordWrap(True)
        note.setObjectName("note")
        v.addWidget(note)
        self.s_compare = CompareView()
        v.addWidget(self.s_compare, 1)
        # comparer sans geste précis : trois gros boutons sous l'image
        self.s_segments = QWidget()
        hs = self._segments_row = QHBoxLayout(self.s_segments)
        hs.setContentsMargins(0, 0, 0, 0)
        hs.addStretch(1)
        self.segment_group = QButtonGroup(self)
        self.segments: dict[str, QPushButton] = {}
        for mode, txt, ic in (("before", "Original", "film"), ("split", "Comparer les deux", "comparer"),
                              ("after", "Restauré", "etincelle")):
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
        self.segments["before"].setAccessibleName("Voir seulement l'original")
        self.segments["split"].setAccessibleName("Comparer l'original et le restauré")
        self.segments["after"].setAccessibleName("Voir seulement le restauré")
        self.segments["split"].setChecked(True)
        self.s_segments.setVisible(False)
        v.addWidget(self.s_segments)
        self.s_progress = theme.SweepBar()
        self.s_status = QLabel("Prêt.")
        self.s_status.setWordWrap(True)
        self.s_status.setObjectName("statut")
        v.addWidget(self.s_progress)
        v.addWidget(self.s_status)
        h = QHBoxLayout()
        self.s_cancel = QPushButton("Arrêter")
        self.s_cancel.setObjectName("secondaire")
        self.s_cancel.clicked.connect(lambda: self.cancel(confirmer=True))
        self.s_cancel.setMinimumHeight(44)
        self.s_cancel.setAccessibleName("Arrêter le travail en cours")
        self.s_cancel.setAccessibleDescription("Demande confirmation si le travail a déjà commencé depuis un moment.")
        self.s_folder = QPushButton("Restaurer tout un dossier (films et photos)…")
        self.s_folder.setObjectName("secondaire")
        self.s_folder.clicked.connect(self.start_folder)
        self.s_folder.setMinimumHeight(48)
        self.s_folder.setMinimumWidth(0)
        self.s_folder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.s_folder.setAccessibleName("Restaurer tous les films et toutes les photos d'un dossier")
        self.s_folder.setAccessibleDescription("Les fichiers d'origine ne sont pas modifiés.")
        self.s_hear_orig = QPushButton("Écouter l'original")
        self.s_hear_new = QPushButton("Écouter le son restauré")
        for b in (self.s_hear_orig, self.s_hear_new):
            b.setObjectName("secondaire")
            b.setMinimumHeight(44)
            _with_icon(b, "casque")
        self.s_hear_orig.setAccessibleName("Écouter le son d'origine")
        self.s_hear_new.setAccessibleName("Écouter le son restauré")
        _with_icon(self.s_cancel, "stop")
        _with_icon(self.s_folder, "pile")
        self.s_hear_orig.clicked.connect(self._play_original)
        self.s_hear_new.clicked.connect(self._play_restored)
        adv = QPushButton("Options avancées")
        _with_icon(adv, "reglages")
        adv.setToolTip("Réglages détaillés de l'image et du son, pour les connaisseurs. "
                       "« Retour au mode simple » en haut de la page.")
        adv.setAccessibleName("Options avancées")
        adv.setAccessibleDescription("Réglages détaillés. Le bouton « Retour au mode simple » ramène ici.")
        adv.setObjectName("lienDiscret")
        adv.setCursor(Qt.PointingHandCursor)
        adv.clicked.connect(lambda: self.set_advanced(True))
        h.addWidget(self.s_cancel)
        h.addWidget(self.s_hear_orig)
        h.addWidget(self.s_hear_new)
        h.addStretch(1)
        v.addLayout(h)
        v.addWidget(self.s_folder)
        v.addWidget(adv, 0, Qt.AlignLeft)
        return page

    def set_advanced(self, on: bool) -> None:
        idx = 1 if on else 0
        deja = self.pages.currentIndex() == idx
        self.pages.setCurrentIndex(idx)
        self.statusBar().setVisible(on)      # noms d'outils : seulement pour les connaisseurs
        if deja:
            self.status.setText("Options avancées." if on else "Mode simple.")

    COLONNE_UNIQUE_SOUS = 1240     # px : portable à 125 % / 150 %, ou fenêtre réduite

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        cols = getattr(self, "_colonnes", None)
        if cols is not None:
            sens = (QBoxLayout.TopToBottom if self.width() < self.COLONNE_UNIQUE_SOUS
                    else QBoxLayout.LeftToRight)
            if cols.direction() != sens:
                cols.setDirection(sens)
        self._ranger_etapes()

    def _compacter_options(self) -> None:
        """Les listes aux libellés longs ne doivent pas élargir la page des options au-delà
        d'un écran de portable : le texte complet reste visible quand la liste est ouverte."""
        page = self.pages.widget(1).widget()
        for combo in page.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(min(combo.minimumContentsLength() or 14, 14))
            combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 24)

    def _build(self) -> None:
        central = QWidget()
        central.setObjectName("page")
        outer = QVBoxLayout(central)
        back = QPushButton("Retour au mode simple")
        _with_icon(back, "retour")
        back.setObjectName("lien")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(lambda: self.set_advanced(False))
        outer.addWidget(back, 0, Qt.AlignLeft)
        root = self._colonnes = QBoxLayout(QBoxLayout.LeftToRight)
        outer.addLayout(root, 1)
        left = QVBoxLayout()
        right = QVBoxLayout()
        root.addLayout(left, 2)
        root.addLayout(right, 3)
        self.pages = QStackedWidget()
        accueil = QScrollArea()
        accueil.setWidgetResizable(True)
        accueil.setFrameShape(QFrame.NoFrame)
        simple = self._build_simple()
        self._simple = simple
        accueil.setWidget(simple)
        self._drop_filter = _DropFilter(self._deposer)
        for cible in (accueil, accueil.viewport(), simple):
            cible.setAcceptDrops(True)
            cible.installEventFilter(self._drop_filter)
        self.pages.addWidget(accueil)
        scroll = QScrollArea()          # la page des options est plus haute qu'un écran de portable
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(central)
        self.pages.addWidget(scroll)
        self.setCentralWidget(self.pages)
        self.setTabOrder(self.help_btn, self.theme_btn)
        self.setTabOrder(self.theme_btn, self._taille_btns[100])
        self.setTabOrder(self._taille_btns[100], self._taille_btns[125])
        self.setTabOrder(self._taille_btns[125], self._taille_btns[150])
        self.setTabOrder(self._taille_btns[150], self.s_choose)
        self.setTabOrder(self.s_choose, self.s_preview)
        self.setTabOrder(self.s_preview, self.s_run)
        self.setTabOrder(self.s_run, self.s_folder)
        self.setTabOrder(self.s_folder, self.s_cancel)

        # Import
        g = self._card_media = Carte("Film ou photo", "film", "1")
        v = g.body
        self.drop = DropZone()
        self.drop.dropped.connect(self.load_file)
        b = _with_icon(QPushButton("Choisir un film ou une photo…"), "dossier")
        b.clicked.connect(self._choose_file)
        v.addWidget(self.drop)
        v.addWidget(b)
        left.addWidget(g)

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
        for txt, val, ic in (("Je ne sais pas — suivre l'analyse", None, "info"),
                             ("Vidéo analogique (VHS, Video8, Hi8, Betamax…)", "video", "bande"),
                             ("Pellicule cinéma numérisée (Super 8, 8 mm, 16 mm…)", "film", "film"),
                             ("Pellicule transférée sur vidéo (film copié sur VHS, DVD…)", "transfer", "pile")):
            self.source_combo.addItem(icons.icon(ic), txt, val)
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
        left.addWidget(g)

        # Profils : trois tuiles
        g = self._card_profil = Carte("Profil de restauration", "etincelle", "2")
        self.profile_group = QButtonGroup(self)
        self.profile_buttons: dict[str, QAbstractButton] = {}
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        for p in PROFILES.values():
            ic, tag = PROFILE_LOOK.get(p.key, ("etincelle", ""))
            tile = ProfileTile(p.name, ic, tag)
            tile.setToolTip(p.description)
            tile.installEventFilter(self._halos[0])
            self.profile_group.addButton(tile)
            self.profile_buttons[p.key] = tile
            tile.toggled.connect(lambda on, k=p.key: on and self._profile_changed(k))
            tiles.addWidget(tile)
        g.body.addLayout(tiles)
        self.profile_desc = QLabel()
        self.profile_desc.setWordWrap(True)
        self.profile_desc.setObjectName("note")
        g.body.addWidget(self.profile_desc)
        left.addWidget(g)

        # Image
        gi = self._card_image = Carte("Image", "image")
        vi = gi.body
        h = QHBoxLayout()
        self.res_combo = QComboBox()
        for k, txt in RESOLUTIONS.items():
            self.res_combo.addItem(icons.icon("ecran"), txt, k)
        self.ai_check = _with_icon(QCheckBox("Amélioration IA (Real-ESRGAN)"), "puce")
        self.ai_check.toggled.connect(self._ai_toggled)
        h.addWidget(_ilabel("Sortie :", "ecran"))
        h.addWidget(self.res_combo, 1)
        self._row_res = _wrap(h)
        vi.addWidget(self._row_res)
        h = QHBoxLayout()
        self.deint_combo = QComboBox()
        self.deint_combo.addItem("bwdif (rapide)", "bwdif")
        self.deint_combo.addItem("QTGMC (meilleure qualité, plus lent)", "qtgmc")
        h.addWidget(_ilabel("Désentrelaceur :", "trames"))
        h.addWidget(self.deint_combo, 1)
        self._row_deint = _wrap(h)
        vi.addWidget(self._row_deint)
        self.dust_check = _with_icon(QCheckBox("Enlever les poussières et rayures (pellicule, plus lent)"),
                                     "poussiere")
        vi.addWidget(self.dust_check)
        self.tape_check = _with_icon(QCheckBox("Bruit de bande (poursuite, lignes, bande du bas)"), "bande")
        self.chroma_check = _with_icon(QCheckBox("Couleur des décrochages (arcs-en-ciel, couleur perdue)"), "arc")
        self.dropout_check = _with_icon(QCheckBox("Taches d'une seule image (décrochages)"), "eclat")
        tip = ("Moteur Analog Repair, désactivé par défaut. La luminance et le grain ne sont pas "
               "lissés, le tampon date n'est pas effacé. Une cassette entrelacée est d'abord "
               "désentrelacée (bwdif, ou fieldmatch si c'est une pellicule copiée sur bande). "
               "QTGMC n'est pas refait ensuite. Sans le module : installer.bat -AvecPoussieres.")
        for box in (self.tape_check, self.chroma_check, self.dropout_check):
            box.setToolTip(tip)
            vi.addWidget(box)
        self.flicker_check = _with_icon(QCheckBox("Réduire le scintillement lumineux (pellicule)"), "soleil")
        self.flicker_check.setToolTip("Lisse les variations de luminosité d'une image à l'autre "
                                      "(filtre deflicker sur 5 images). À vérifier sur l'aperçu.")
        vi.addWidget(self.flicker_check)
        self.hq_check = _with_icon(QCheckBox("Débruitage haute qualité (environ 3 fois plus lent)"), "lisse")
        self.hq_check.setToolTip("Remplace le débruitage standard par fftdnoiz (FFT 3D) avec un renfort "
                                 "sur les taches de couleur. Plus efficace sur le bruit analogique ; "
                                 "intensité adaptée au profil.")
        vi.addWidget(self.hq_check)
        self.stab_check = _with_icon(
            QCheckBox("Stabiliser l'image (tremblements, 2 passes)"), "viseur")
        vi.addWidget(self.stab_check)
        self.cast_check = _with_icon(QCheckBox("Corriger la dominante de couleur"), "goutte")
        self.cast_check.setToolTip(
            "Retire une teinte qui couvre tout le film (vert de VHS, par exemple). "
            "Les trois gains sont calculés une seule fois, pour tout le film. "
            "Un noir et blanc reste neutre, une image pâle n'est pas ravivée. "
            "Désactivé par défaut. L'analyse le conseille seulement si la dominante est forte.")
        vi.addWidget(self.cast_check)
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
        vi.addWidget(self._row_mask)
        self.edge_spin = QDoubleSpinBox()
        self.edge_spin.setRange(0, 64)
        self.edge_spin.setDecimals(0)
        self.edge_spin.setSingleStep(2)
        self.edge_spin.setSuffix(" px")
        self.edge_spin.setToolTip(
            "Bords abîmés, remplacés par du noir. Cassette : gauche et droite. "
            "Pellicule : un cadre des quatre côtés. L'image garde la même taille "
            "et le même format (4:3 inchangé). 0 = ne rien masquer.")
        self.edge_label = _ilabel("Masquer les bords :", "cadre")
        h = QHBoxLayout()
        h.addWidget(self.edge_label)
        h.addWidget(self.edge_spin)
        h.addStretch(1)
        self._row_edge = _wrap(h)
        vi.addWidget(self._row_edge)
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
        vi.addWidget(self._row_chroma)
        vi.addWidget(self.ai_check)
        left.addWidget(gi)

        # Son
        gs = self._card_son = Carte("Son", "onde")
        vs = gs.body
        self.audio_check = _with_icon(QCheckBox("Restaurer le son (souffle, clics, volume)"), "haut_parleur")
        self.audio_check.setChecked(True)
        self.audio_check.setToolTip(
            "Suit le profil image. Fidèle : souffle très léger. Équilibré : clics, souffle, volume. "
            "Maximum : DeepFilterNet si tools\\deepfilter\\deep-filter est installé "
            "(installer.bat -AvecSon), sinon le même souffle FFmpeg plus fort. "
            "Le plafond de DeepFilterNet est de 12 dB. Les rires, la musique et la rue restent. "
            "Une piste muette le reste.")
        vs.addWidget(self.audio_check)
        self.rnnoise_check = _with_icon(QCheckBox("Souffle de la voix (RNNoise, mélangé à l'original)"), "micro")
        self.rnnoise_check.setToolTip(
            "Option, désactivée par défaut : les profils ne changent pas. "
            "Remplace le souffle FFmpeg d'Équilibré (35 %) et de Maximum (55 %) par RNNoise "
            "(modèle Xiph inclus, licence BSD). Le reste du signal, donc la pièce, est conservé. "
            "Inutile si DeepFilterNet a déjà traité Maximum. Fidèle n'est pas concerné.")
        vs.addWidget(self.rnnoise_check)
        self.wind_check = _with_icon(QCheckBox("Réduire le vent et les grondements"), "vent")
        self.wind_check.setToolTip(
            "Passe-haut doux à 80 Hz (6 dB par octave). Coupe le vent sur le micro et les "
            "grondements graves. Une voix à partir de 300 Hz n'est presque pas touchée. "
            "Désactivé par défaut. L'analyse le conseille si les graves sont forts et irréguliers.")
        vs.addWidget(self.wind_check)
        self.presence_check = _with_icon(QCheckBox("Rendre les voix plus claires"), "egaliseur")
        self.presence_check.setToolTip(
            "Légère présence autour de 3 kHz, +3 dB au plus. Pour un son étouffé. "
            "Désactivé par défaut : rien n'est ajouté si la case n'est pas cochée.")
        vs.addWidget(self.presence_check)
        self.declip_check = _with_icon(QCheckBox("Réparer le son saturé"), "sature")
        self.declip_check.setToolTip("Reconstruit les crêtes coupées d'un son enregistré trop fort "
                                     "(cris, fêtes, vent). L'analyse le détecte et le conseille.")
        vs.addWidget(self.declip_check)
        h = QHBoxLayout()
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-500, 500)
        self.offset_spin.setDecimals(0)
        self.offset_spin.setSingleStep(10)
        self.offset_spin.setSuffix(" ms")
        self.offset_spin.setToolTip(
            "Décalage constant entre le son et l'image. Positif : retarder le son "
            "(il était en avance). Négatif : avancer le son. 0 : ne rien changer.")
        h.addWidget(_ilabel("Décalage du son :", "horloge"))
        h.addWidget(self.offset_spin)
        h.addStretch(1)
        vs.addLayout(h)
        h = QHBoxLayout()
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
        h.addWidget(_ilabel("Dérive :", "derive"))
        h.addWidget(self.drift_spin)
        h.addStretch(1)
        vs.addLayout(h)
        h = QHBoxLayout()
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
        h.addWidget(self.mains_combo, 1)
        h.addWidget(self.copy_combo, 1)
        vs.addLayout(h)
        self.channel_combo = QComboBox()
        for txt, val in (("Canaux du son inchangés", ""), ("Son gauche mis des deux côtés", "left"),
                         ("Son droit mis des deux côtés", "right"), ("Remettre les deux côtés en phase", "phase")):
            self.channel_combo.addItem(icons.icon("canaux"), txt, val)
        self.channel_combo.setToolTip("Pour un son enregistré d'un seul côté, ou dont les deux côtés "
                                      "s'annulent. L'analyse le détecte et le conseille.")
        vs.addWidget(self.channel_combo)
        left.addWidget(gs)
        left.addStretch(1)

        # Aperçu
        g = Carte("Aperçu avant / après", "comparer", "3", "extrait de 10 s")
        v = g.body
        h = QHBoxLayout()
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setDecimals(0)
        self.start_spin.setSuffix(" s")
        self.start_spin.setRange(0, 0)
        self.preview_btn = _with_icon(QPushButton("Générer l'aperçu"), "oeil")
        self.preview_btn.clicked.connect(self.start_preview)
        self.still_combo = QComboBox()
        self.still_combo.setMinimumContentsLength(9)
        self.still_combo.currentIndexChanged.connect(self._show_still)
        self.play_btn = _with_icon(QPushButton("Lire la comparaison"), "jouer")
        self.play_btn.clicked.connect(self._play_compare)
        self.hear_orig_btn = _with_icon(QPushButton("Écouter l'original"), "casque")
        self.hear_orig_btn.clicked.connect(self._play_original)
        self.hear_new_btn = _with_icon(QPushButton("Écouter le son restauré"), "casque")
        self.hear_new_btn.clicked.connect(self._play_restored)
        self.start_label = _ilabel("Début de l'extrait :", "horloge")
        h.addWidget(self.start_label)
        h.addWidget(self.start_spin)
        h.addWidget(self.preview_btn)
        h.addStretch(1)
        v.addLayout(h)
        h = QHBoxLayout()               # deuxième ligne : la page tient sur un écran de portable
        h.addWidget(self.still_combo)
        h.addWidget(self.play_btn)
        h.addStretch(1)
        v.addLayout(h)
        h = QHBoxLayout()
        h.addWidget(self.hear_orig_btn)
        h.addWidget(self.hear_new_btn)
        h.addStretch(1)
        v.addLayout(h)
        self.compare = CompareView()
        v.addWidget(self.compare, 1)
        right.addWidget(g, 1)

        # Export
        g = Carte("Restauration complète", "export", "4")
        v = g.body
        h = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("À côté du fichier d'origine")
        self.out_edit.textEdited.connect(lambda t: setattr(self, "_out_manual", bool(t.strip())))
        bo = self._out_btn = _with_icon(QPushButton("Dossier de sortie…"), "dossier")
        bo.clicked.connect(self._choose_outdir)
        h.addWidget(self.out_edit, 1)
        h.addWidget(bo)
        v.addLayout(h)
        h = QHBoxLayout()
        self.trim_start = QDoubleSpinBox()
        self.trim_end = QDoubleSpinBox()
        for sp in (self.trim_start, self.trim_end):
            sp.setDecimals(1)
            sp.setRange(0, 0)
            sp.setSuffix(" s")
        self.trim_end.setSpecialValueText("jusqu'au bout")
        self.trim_start.setToolTip("Pour ne pas garder la neige ou l'écran bleu du début.")
        self.trim_end.setToolTip("Pour ne pas garder la fin de bande. « jusqu'au bout » = tout garder.")
        h.addWidget(_ilabel("Garder du début à :", "ciseaux"))
        h.addWidget(self.trim_start)
        h.addWidget(QLabel("jusqu'à :"))
        h.addWidget(self.trim_end)
        h.addStretch(1)
        self._row_trim = _wrap(h)
        v.addWidget(self._row_trim)
        h = QHBoxLayout()
        self.run_btn = QPushButton("Lancer la restauration")
        self.run_btn.setObjectName("action")
        self.run_btn.setIcon(icons.icon("etincelle", theme.AMBRE_TEXTE, 24))
        self.run_btn.setIconSize(QSize(24, 24))
        self.run_btn.clicked.connect(self.start_export)
        self.run_btn.installEventFilter(self._halos[1])
        self.cancel_btn = _with_icon(QPushButton("Annuler"), "stop")
        self.cancel_btn.clicked.connect(lambda: self.cancel(confirmer=True))
        self.cancel_btn.setMinimumHeight(44)
        self.cancel_btn.setAccessibleName("Arrêter le travail en cours")
        self.cancel_btn.setAccessibleDescription("Demande confirmation si le travail dure déjà depuis un moment.")
        self.check_btn = _with_icon(QPushButton("Vérifier l'installation"), "diagnostic")
        self.check_btn.setToolTip("Restaure une courte vidéo d'essai et affiche un rapport "
                                  "(utile si quelque chose ne marche pas).")
        self.check_btn.clicked.connect(self.check_install)
        h.addWidget(self.run_btn)
        h.addWidget(self.cancel_btn)
        h.addStretch(1)
        v.addLayout(h)
        self.progress = theme.SweepBar()
        self.status = QLabel("Prêt.")
        self.status.setWordWrap(True)
        v.addWidget(self.progress)
        v.addWidget(self.status)
        h = QHBoxLayout()
        self.vides_btn = _with_icon(QPushButton("Retirer les passages vides…"), "ciseaux")
        self.vides_btn.clicked.connect(self.retirer_vides)
        self.montage_btn = _with_icon(QPushButton("Faire un montage…"), "film")
        self.montage_btn.clicked.connect(self.faire_montage)
        for b in (self.vides_btn, self.montage_btn):
            b.setToolTip("Sur le dernier film restauré, ou sinon sur le film ouvert.")
            h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        h = QHBoxLayout()                    # ligne à part : la carte tient sur un écran de 1280 px
        h.addStretch(1)
        h.addWidget(self.check_btn)
        v.addLayout(h)
        right.addWidget(g)

        # les deux pages affichent la même progression, le même état, le même aperçu
        self.status = _Mirror(self.status, self.s_status)
        self.progress = _Mirror(self.progress, self.s_progress)
        self.compare = _Mirror(self.compare, self.s_compare)
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
        self.statusBar().addPermanentWidget(self.tools_label)
        self.statusBar().setVisible(False)       # mode simple : pas de noms d'outils techniques
        self._compacter_options()       # avant tout calcul de mise en page (Qt garde les tailles)
        self.profile_buttons["equilibre"].setChecked(True)
        self._out_manual = False        # dossier de sortie choisi exprès par l'utilisateur ?
        self._load_prefs()
        self._ranger_etapes()

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
                                 "Real-ESRGAN n'est pas installé : cliquez sur « ○ Real-ESRGAN » en bas "
                                 "de la fenêtre "
                                 + (f"({t.realesrgan.problem})" if t.realesrgan.problem else ""))

    def show_welcome(self) -> None:
        """Mode d'emploi en trois étapes (au premier lancement, puis par le bouton « Aide »)."""
        box = QMessageBox(QMessageBox.Information, "Bienvenue dans VHS Restore AI",
                          "Restaurer un film ou une photo se fait en trois étapes :\n\n"
                          "1.  « Choisir le film ou la photo » : sélectionnez le fichier.\n"
                          "2.  « Voir l'avant / après » : regardez le résultat sur un petit extrait.\n"
                          "3.  « Restaurer » : le logiciel travaille, cela peut prendre du temps. "
                          "Vous pouvez laisser l'ordinateur faire.\n\n"
                          "Le bouton à utiliser est entouré d'un cadre plus épais. "
                          "La touche Entrée l'active.\n\n"
                          "Votre fichier d'origine n'est jamais modifié : le résultat est enregistré "
                          "à côté, avec « restaure » dans son nom. À la fin, l'écran « C'est prêt » "
                          "propose de le regarder ou d'ouvrir le dossier.\n\n"
                          "« A− », « A » et « A+ » en haut à droite agrandissent le texte.", parent=self)
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
        box = QMessageBox(QMessageBox.Question, "Affichage",
                          f"Passer à l'affichage {nouveau} ? Le logiciel va redémarrer "
                          "(rien n'est perdu).",
                          QMessageBox.Yes | QMessageBox.No, self)
        box.setDefaultButton(QMessageBox.No)
        if box.exec() != QMessageBox.Yes:
            return
        s = self._prefs()
        if s is not None:
            s.setValue("affichage", nouveau)
            s.sync()
        args = [] if getattr(sys, "frozen", False) else ["-m", "vhs_restore"]
        dossier = str(Path(sys.executable).parent) if getattr(sys, "frozen", False) else os.getcwd()
        if _demarrer(sys.executable, args, dossier):
            self.close()

    def _set_simple_info(self, text: str) -> None:
        """Texte du mode simple : des mots de tous les jours ; le détail technique en infobulle."""
        if self.advice:
            text += "<br>Défauts repérés : " + ", ".join(dict.fromkeys(_en_clair(a) for a in self.advice)) + "."
        detail = "\n".join("• " + a.text for a in self.advice)
        self.s_info.setText(text)
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
        self._launch(job, self._tool_installed)

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
        """Le dernier film restauré, sinon le film ouvert (pas une photo)."""
        fini = getattr(self, "_fini_fichier", None)
        if fini and Path(fini).is_file() and not photo.is_photo(fini):
            return Path(fini)
        if self.info is not None and not getattr(self, "is_photo", False):
            return Path(self.info.path)
        return None

    def retirer_vides(self) -> None:
        """Repère neige, écran bleu et noir, puis propose une copie sans ces passages."""
        if self._busy():
            return
        cible = self._cible_montage()
        if cible is None:
            self.status.setText("Choisissez d'abord un film (bouton 1).")
            return
        t = self.tools

        def job(cancel, progress):
            r = run_capture([t.ffprobe.path, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                             "-of", "default=nw=1", str(cible)], timeout=60)
            duree = float(next((x.split("=")[1] for x in r.stdout.split() if x.startswith("duration=")), 0) or 0)
            son = "codec_type=audio" in r.stdout
            return cible, duree, son, vides.detecter(t.ffmpeg.path, cible, duree, cancel=cancel, progress=progress)
        self.status.setText("Recherche des passages vides…")
        self._launch(job, self._vides_trouves, job="vides")

    def _vides_trouves(self, res) -> None:
        cible, duree, son, passages = res
        if not passages:
            self.status.setText("Aucun passage vide trouvé.")
            QMessageBox.information(self, "Passages vides", "Aucun passage vide (neige, écran bleu ou noir) "
                                    "n'a été trouvé. Le film est gardé tel quel.")
            return
        total = sum(p.duree for p in passages)
        liste = "\n".join("•  " + vides.decrire(p) for p in passages)
        box = QMessageBox(QMessageBox.Question, "Passages vides",
                          f"{len(passages)} passage{'s' if len(passages) > 1 else ''} vide"
                          f"{'s' if len(passages) > 1 else ''} trouvé{'s' if len(passages) > 1 else ''} "
                          f"({vides._hms(total)} en tout) :\n\n{liste}\n\n"
                          "Créer une copie du film sans ces passages ? Le film actuel n'est pas modifié.",
                          parent=self)
        box.setStyleSheet("QLabel#qt_msgbox_label { min-width: 520px; font-size: 14pt; }")
        oui = box.addButton("Créer la copie", QMessageBox.AcceptRole)
        box.addButton("Garder le film tel quel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not oui:
            self.status.setText("Le film est gardé tel quel.")
            return
        dst = vides.sortie_sans_vides(cible)
        ffmpeg = self.tools.ffmpeg.path
        self.status.setText("Copie sans les passages vides…")
        self._launch(lambda c, p: (vides.retirer(ffmpeg, cible, dst, passages, duree, son, cancel=c, progress=p),
                                   total), self._vides_retires, job="export")

    def _vides_retires(self, res) -> None:
        out, total = res
        self._montrer_fini(f"Copie sans les passages vides :\n{out.name}\n\n{vides._hms(total)} retirées "
                           f"(neige, écran bleu ou noir).\n\nElle se trouve dans le dossier :\n{out.parent}\n\n"
                           "Le film précédent n'a pas été modifié.", out.parent, out, "film")
        self.status.setText(f"Terminé : {out}")

    def faire_montage(self) -> None:
        """Ouvre le film dans LosslessCut (simple) ou Shotcut (complet), installés d'un clic si besoin."""
        cible = self._cible_montage()
        if cible is None:
            self.status.setText("Choisissez d'abord un film (bouton 1).")
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
        self.info_form.setRowVisible(self.cadence_combo, src == "film")
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
        sound = bool(self.info is not None and self.info.has_audio and not self.info.audio_silent)
        self.play_btn.setEnabled(has_prev and not busy)
        self.play_btn.setVisible(not photo_mode)
        for b in (self.hear_orig_btn, self.hear_new_btn, self.s_hear_orig, self.s_hear_new):
            b.setEnabled(has_prev and sound and not busy)          # film muet : rien à écouter
            b.setVisible(not photo_mode)                            # une photo n'a pas de son
            b.setToolTip("" if sound or not loaded else "Ce film n'a pas de son.")
        self.still_combo.setEnabled(has_prev and not busy)
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
        nxt = None if busy else (self.s_choose if not loaded else self.s_preview if not has_prev else self.s_run)
        for b in (self.s_choose, self.s_preview, self.s_run):
            if b.suggested != (b is nxt):
                b.suggested = b is nxt
                b.update()
            if b is nxt:
                b.setAccessibleDescription("Étape conseillée. La touche Entrée l'active.")
            elif not b.isEnabled():
                b.setAccessibleDescription("Pas encore disponible.")
        # Pendant un traitement, les réglages ne servent plus (ils ont été lus au lancement) :
        # on les grise pour ne pas laisser croire qu'ils changent le travail en cours.
        for card in (self._card_media, self._card_info, self._card_profil, self._card_image, self._card_son):
            card.setEnabled(not busy)
        for wd in (self.start_spin, self.out_edit, self._out_btn, self._row_trim, self.s_advice):
            wd.setEnabled(not busy)
        # Photo : seuls le profil, la dominante, l'IA et la colorisation comptent. Les réglages
        # propres aux films sont cachés (ils n'auraient aucun effet).
        self._card_son.setVisible(not photo_mode)
        for wd in (self._row_res, self._row_deint, self._row_edge, self._row_chroma, self.hq_check,
                   self.stab_check, self.start_label, self.start_spin, self._row_trim):
            wd.setVisible(not photo_mode)
        for box in (self.tape_check, self.chroma_check, self.dropout_check):
            box.setVisible(src != "film" and not photo_mode)
        self.flicker_check.setVisible(src in ("film", "transfer") and not photo_mode)
        self.dust_check.setVisible(src == "film" and not photo_mode)
        self._row_mask.setVisible(src == "video" and not photo_mode)
        for combo in (self.source_combo, self.scan_combo, self.dar_combo):
            self.info_form.setRowVisible(combo, not photo_mode)
        self.info_form.setRowVisible(self.cadence_combo, src == "film" and not photo_mode)
        self._masquer_recent_courant()

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

    def _refresh_hints(self) -> None:
        if not self.info:
            return
        notes = ["⚠ " + w for w in self.info.warnings]
        if getattr(self, "is_photo", False):          # une photo : pas de son, pas de « film »
            if self.info.black_and_white:
                notes.append("ℹ Photo noir et blanc : elle le restera"
                             + (". La case « Coloriser aussi » du mode simple peut ajouter une copie "
                                "colorisée par l'IA (couleurs inventées)." if self.tools.colorize_available else "."))
            for a in getattr(self, "advice", []):
                notes.append(f"💡 Conseil : {a.text} (case « Corriger aussi ces défauts » du mode simple)")
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
            notes.append("ℹ La piste son est vide (silence) : elle est conservée telle quelle.")
        for a in getattr(self, "advice", []):
            notes.append(f"💡 Conseil : {a.text} (case « Corriger aussi ces défauts » du mode simple, "
                         "ou réglages du son ci-dessous)")
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
                                 dust=self.dust_check.isChecked() and src == "film",
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
        self.compare.set_mode(mode)
        noms = {"before": "Original", "split": "Comparer les deux", "after": "Restauré"}
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
                b.setText(nom)
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

    def _ranger_etapes(self) -> None:
        """Trois boutons côte à côte seulement s'ils tiennent ; sinon l'un sous l'autre."""
        steps = getattr(self, "_steps", None)
        if steps is None:
            return
        empiler = self._echelle >= 1.24 or self.width() < 1200
        sens = QBoxLayout.TopToBottom if empiler else QBoxLayout.LeftToRight
        if steps.direction() != sens:
            steps.setDirection(sens)
        fini = getattr(self, "_fini_boutons", None)
        if fini is not None and fini.direction() != sens:
            fini.setDirection(sens)
        row = getattr(self, "_segments_row", None)
        if row is not None and self._echelle >= 1.24:
            if row.direction() != QBoxLayout.TopToBottom:
                row.setDirection(QBoxLayout.TopToBottom)
        elif row is not None and row.direction() != QBoxLayout.LeftToRight:
            row.setDirection(QBoxLayout.LeftToRight)

    def set_taille_texte(self, pct: int, annoncer: bool = True) -> None:
        """100, 125 ou 150 %. Mémorisé. N'agrandit que le mode simple."""
        pct = 150 if int(pct) >= 140 else 125 if int(pct) >= 110 else 100
        self._echelle = {100: 1.0, 125: 1.25, 150: 1.5}[pct]
        for b in (self.s_choose, self.s_preview, self.s_run):
            b.set_echelle(self._echelle)
        page = self.pages.widget(0).widget()
        page.setStyleSheet("" if pct == 100 else self._feuille_simple(self._echelle))
        for valeur, bouton in self._taille_btns.items():
            bouton.setAccessibleDescription("Taille actuelle." if valeur == pct
                                            else "Changer la taille du texte du mode simple.")
        self._ranger_etapes()
        s = self._prefs()
        if s is not None:
            s.setValue("texte", pct)
        if annoncer:
            self.status.setText(f"Taille du texte : {pct} %.")

    def _feuille_simple(self, echelle: float) -> str:
        def pt(base: float) -> str:
            return f"{base * echelle:.1f}pt"
        return (
            f"QLabel#infos {{ font-size: {pt(15)}; }}"
            f"QLabel#statut {{ font-size: {pt(14.5)}; }}"
            f"QLabel#note {{ font-size: {pt(13)}; }}"
            f"QLabel#titre {{ font-size: {pt(22)}; }}"
            f"QLabel#marque {{ font-size: {pt(13)}; }}"
            f"QLabel#finiTitre {{ font-size: {pt(22)}; }}"
            f"QLabel#finiTexte {{ font-size: {pt(16)}; }}"
            f"QPushButton#secondaire {{ font-size: {pt(14)}; }}"
            f"QPushButton#segment {{ font-size: {pt(14)}; }}"
            f"QPushButton#lienDiscret {{ font-size: {pt(12.5)}; }}"
            f"QPushButton#bandeauBouton {{ font-size: {pt(12.5)}; }}"
            f"QPushButton#action {{ font-size: {pt(15)}; min-height: {int(58 * echelle)}px; }}"
            f"QCheckBox#caseSimple {{ font-size: {pt(14)}; }}"
        )

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
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.pages.currentIndex() == 0:
            focus = QApplication.focusWidget()
            if not isinstance(focus, (QLineEdit, QAbstractSpinBox, QComboBox)):
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
        kind = "Photo noir et blanc (elle le restera)" if info.black_and_white else "Photo en couleur"
        self._set_simple_info(f"<b>{info.path.name}</b><br>{kind}. Prête : cliquez sur le bouton 2 "
                              "« Voir l'avant / après ».")
        self.s_advice.setChecked(bool(self.advice))      # défauts repérés : corrigés d'office, avec prudence
        self.s_advice.setVisible(bool(self.advice))
        self.s_colorize.setChecked(False)                     # jamais coché d'avance
        self.s_colorize.setVisible(info.black_and_white)
        self.s_aide_conseil.setVisible(bool(self.advice))
        self.s_aide_couleur.setVisible(info.black_and_white)
        self.drop.setText(info.path.name)
        self._memoriser_recent(str(info.path))
        self._update_state()
        self._refresh_hints()
        self.status.setText(f"Photo analysée : {info.path.name}. "
                            "Étape suivante : bouton 2 « Voir l'avant / après ».")

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
        self.source_combo.setItemText(0, "Je ne sais pas — suggestion : "
                                      + {"video": "vidéo", "film": "pellicule",
                                         "transfer": "pellicule transférée"}[info.suggested_source])
        self.source_combo.setCurrentIndex(0)
        fps = f"{float(info.fps):.3f}".rstrip("0").rstrip(".")
        self.cadence_combo.setItemText(0, f"Celle du fichier ({fps} images/s)")
        self.cadence_combo.setCurrentIndex(0)
        self._update_state()
        for sp in (self.trim_start, self.trim_end):     # tout garder par défaut
            sp.setRange(0, max(0.0, info.duration))
            sp.setValue(0)
        self.start_spin.setRange(0, max(0.0, info.duration - 10))
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
        if not (info.has_audio and not info.audio_silent):
            traits.append("sans son (il restera muet)")
        self.advice = advise(info)
        self._set_simple_info(f"<b>{info.summary()['Fichier']}</b><br>{kind}, {', '.join(traits)}. "
                              "Prêt : cliquez sur le bouton 2 « Voir l'avant / après ».")
        self.s_advice.setChecked(bool(self.advice))      # défauts repérés : corrigés d'office, avec prudence
        self.s_advice.setVisible(bool(self.advice))
        self.s_aide_conseil.setVisible(bool(self.advice))
        self.s_aide_couleur.setVisible(False)
        self.channel_combo.setCurrentIndex(0)
        self.declip_check.setChecked(False)
        self._refresh_hints()
        self.status.setText(f"Vidéo analysée : {info.path.name}. "
                            "Étape suivante : bouton 2 « Voir l'avant / après ».")

    def start_preview(self) -> None:
        if not self.info or self._busy():
            return
        info, s, start = self.info, self.settings(), self.start_spin.value()
        self.status.setText("Préparation de l'aperçu…")
        if getattr(self, "is_photo", False):
            self._launch(lambda c, p: photo.make_photo_preview(info, s, self.tools, self.preview_dir / "photo",
                                                               cancel=c, progress=p), self._preview_done)
            return
        self._launch(lambda c, p: pipeline.make_preview(info, s, self.tools, self.preview_dir, start,
                                                        cancel=c, progress=p), self._preview_done)

    def _preview_done(self, res: pipeline.PreviewResult) -> None:
        self.preview = res
        self.compare.set_after_label("COULEURS IA (inventées)" if res.restored.name.endswith("_colorisee_ia.png")
                                     else "RESTAURÉ")
        self.still_combo.blockSignals(True)
        self.still_combo.clear()
        for i, _ in enumerate(res.stills):
            self.still_combo.addItem(f"Image {i + 1}/{len(res.stills)}")
        self.still_combo.blockSignals(False)
        idx = min(1, len(res.stills) - 1)
        self.still_combo.setCurrentIndex(idx)
        self._show_still(idx)
        self.segments["split"].setChecked(True)
        self.compare.set_mode("split")
        quand = "" if getattr(self, "is_photo", False) else \
            f" (extrait de {res.start:.0f} s à {res.start + res.duration:.0f} s)"
        self.status.setText(f"Aperçu prêt{quand}. Comparez avec les boutons « Original » et « Restauré » "
                            "sous l'image. Si cela vous plaît : bouton 3 « Restaurer ».")

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
            self._launch(lambda c, p: photo.restore_photo(info, s, out, self.tools, cancel=c, progress=p),
                         self._export_done, job="export")
            return
        try:
            out = pipeline.unique_output_path(info, s, out_dir)
            start, length = pipeline.trim_window(info, self.trim_start.value(), self.trim_end.value())
        except ToolError as exc:
            self.status.setText(ergonomie.expliquer(str(exc))[0])
            ergonomie.montrer_erreur(self, str(exc))
            return
        self.status.setText(f"Restauration vers {out.name}…")
        self._launch(lambda c, p: pipeline.export(info, s, out, self.tools, cancel=c, progress=p,
                                                  start=start, duration=length),
                     self._export_done, job="export")

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
        self.status.setText(f"Terminé : {out}")

    def _montrer_fini(self, texte: str, dossier: Path, fichier: Path | None, genre: str) -> None:
        """Écran « C'est prêt », pas une petite boîte. Trois grands boutons."""
        self.s_fini_texte.setText(texte)
        self.s_info.setText("<b>Terminé.</b> Le résultat est prêt : regardez-le ou ouvrez son dossier "
                            "avec les boutons ci-dessous.")
        self.s_info.setToolTip("")
        self._fini_dossier = Path(dossier)
        self._fini_fichier = Path(fichier) if fichier else None
        if genre == "photo":
            self.s_voir.setText("Voir la photo")
            self.s_autre.setText("Restaurer une autre photo")
            self.s_voir.setVisible(True)
        elif genre == "dossier":
            self.s_voir.setVisible(False)
            self.s_autre.setText("Restaurer un autre dossier")
        else:
            self.s_voir.setText("Regarder le film")
            self.s_autre.setText("Restaurer un autre film")
            self.s_voir.setVisible(True)
        for b in (self.s_vides, self.s_montage):          # outils de film seulement
            b.setVisible(genre == "film")
        self.s_voir.setAccessibleName(self.s_voir.text())
        self.s_ouvrir.setAccessibleName("Ouvrir le dossier du résultat")
        self.s_autre.setAccessibleName(self.s_autre.text())
        self.s_fini.setVisible(True)
        self.set_advanced(False)
        zone = self.pages.widget(0)
        if isinstance(zone, QScrollArea):
            zone.ensureWidgetVisible(self.s_fini)
        self._signaler_fin()

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

    def _done_box(self, title: str, text: str, folder: Path) -> None:
        """Ancien nom : l'écran « C'est prêt » remplace la boîte."""
        genre = "photo" if "photo" in title.lower() else "film"
        self._montrer_fini(text, folder, None, genre)

    def settings_for(self, info: MediaInfo) -> pipeline.Settings:
        """Réglages d'un film du dossier : options choisies, origine propre à chaque film
        (choix manuel s'il y en a un, sinon suggestion de l'analyse)."""
        base = self.settings(with_advice=False)
        # conseils propres à CHAQUE film du dossier : appliqués d'office, sauf si l'utilisateur
        # a décoché la case pour le fichier ouvert
        if self.s_advice.isChecked() or self.s_advice.isHidden():
            base = apply_advice(base, advise(info))
        if self.cast_check.isChecked():
            if info.cast_rgb:
                gr, gg, gb = cast_gains(info.cast_rgb)
                base = dataclasses.replace(base, gain_r=gr, gain_g=gg, gain_b=gb)
            else:
                base = dataclasses.replace(base, gain_r=1.0, gain_g=1.0, gain_b=1.0)
        src = self.source_combo.currentData() or info.suggested_source
        return dataclasses.replace(base, profile=profile_for(base.profile.key, src), source=src,
                                   scan=None, dar=None, playback_fps=None,
                                   deflicker=self.flicker_check.isChecked() and src != "video",
                                   dust=self.dust_check.isChecked() and src == "film",
                                   tape_noise=self.tape_check.isChecked() and src != "film",
                                   chroma_repair=self.chroma_check.isChecked() and src != "film",
                                   dropouts=self.dropout_check.isChecked() and src != "film",
                                   mask_bottom=base.mask_bottom if src == "video" else 0)

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
        self.status.setText("Restauration du dossier…")
        self._launch(lambda c, p: pipeline.restore_folder(folder, self.tools, self.settings_for,
                                                          cancel=c, progress=p), self._folder_done,
                     job="dossier")

    def _folder_done(self, res: pipeline.BatchResult) -> None:
        n = len(res.done)
        texte = ergonomie.resume_dossier(n, len(res.skipped), list(res.errors))
        if res.fallback:
            texte += "\nLe dossier d'origine ne pouvait pas être modifié : le résultat est ailleurs."
        self._montrer_fini(texte, res.out_dir, None, "dossier")
        self.status.setText(f"Terminé : {n} film{'s' if n != 1 else ''} restauré{'s' if n != 1 else ''} "
                            f"dans {res.out_dir}")

    def cancel(self, confirmer: bool = False) -> None:
        if not self._busy():
            return
        if confirmer and self._travail_long():
            box = QMessageBox(QMessageBox.Question, "Arrêter",
                              "Arrêter maintenant ?\n\nLe travail déjà fait sur ce film sera perdu.\n"
                              "Les films déjà terminés, eux, restent.",
                              QMessageBox.Yes | QMessageBox.No, self)
            box.setDefaultButton(QMessageBox.No)
            if box.exec() != QMessageBox.Yes:
                self.status.setText("Le travail continue.")
                return
        self.worker.cancel_event.set()
        self.status.setText("Annulation en cours…")

    def _travail_long(self) -> bool:
        """Un arrêt après quelques secondes, ou sur un film entier, demande confirmation."""
        debut = getattr(self, "_debut_travail", None)
        ecoule = 0.0 if debut is None else time.monotonic() - debut
        if ecoule >= 20:
            return True
        return getattr(self, "_job", "") in ("export", "dossier") and ecoule >= 8

    # ------------------------------------------------------------ worker
    def _launch(self, fn: Callable, on_success: Callable[[Any], None], job: str = "") -> None:
        self._job = job
        self._debut_travail = time.monotonic()
        if job:
            self.s_fini.setVisible(False)
        self.worker = w = Worker(fn)
        # On garde les fils terminés : PySide plante si le QThread est détruit
        # pendant que l'interface traite encore ses signaux.
        self._fils = getattr(self, "_fils", [])
        self._fils.append(w)
        w.progressed.connect(self._on_progress)
        w.succeeded.connect(on_success)
        w.failed.connect(self._on_failed)
        w.cancelled.connect(lambda: self.status.setText("Opération annulée. Fichiers temporaires supprimés."))
        w.finished.connect(self._on_finished)
        if self.progress.maximum() != 0:
            self.progress.setValue(0)
        self.eta = Eta()
        w.start()
        self._update_state()

    def _on_progress(self, frac: float, msg: str) -> None:
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1000)
        self.progress.setValue(int(frac * 1000))
        left = self.eta.update(frac) if getattr(self, "eta", None) else ""
        texte = f"{msg} — {left}" if left else f"{msg} {frac * 100:.0f} %"
        if getattr(self, "_job", "") in ("export", "dossier"):
            texte += "\n" + ergonomie.PHRASE_PATIENCE
        self.status.setText(texte)

    def _on_failed(self, msg: str) -> None:
        clair, _ = ergonomie.expliquer(msg)
        self.status.setText(clair)
        self.s_fini.setVisible(False)
        ergonomie.montrer_erreur(self, msg)

    def _on_finished(self) -> None:
        self.check_btn.setText("Vérifier l'installation")
        self.progress.setRange(0, 1000)
        if not self.status.text().startswith(("Terminé", "Aperçu prêt", "Vidéo analysée", "Photo analysée")):
            self.progress.setValue(0)
        else:
            self.progress.setValue(1000)
        self._update_state()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self._busy():
            box = QMessageBox(QMessageBox.Question, "Quitter",
                              "Un traitement est en cours. L'annuler et quitter ?",
                              QMessageBox.Yes | QMessageBox.No, self)
            if box.exec() != QMessageBox.Yes:
                e.ignore()
                return
            self.worker.cancel_event.set()
            self.worker.wait(15000)
        self._save_prefs()
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
        self.offset_spin.setValue(float(s.value("audio_offset_ms", 0) or 0))
        self.drift_spin.setValue(float(s.value("audio_drift_ms_per_min", 0) or 0))
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
            pct = int(float(s.value("texte", 100) or 100))
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
        s.setValue("audio_offset_ms", self.offset_spin.value())
        s.setValue("audio_drift_ms_per_min", self.drift_spin.value())
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
    theme.set_mode(str(QSettings("VHSRestoreAI", "VHSRestoreAI").value("affichage", "sombre") or "sombre"))
    theme.apply(app)
    win = MainWindow()
    win.show()
    if not (win.tools.ffmpeg.path and win.tools.ffprobe.path):
        QMessageBox.critical(win, "FFmpeg manquant",
                             "FFmpeg est nécessaire et n'a pas été trouvé.\n\n"
                             "Lancez « installer.bat » (il télécharge FFmpeg dans le dossier tools), "
                             "ou installez FFmpeg et ajoutez-le au PATH.")
    elif win.tools.missing_filters:
        QMessageBox.critical(win, "FFmpeg trop ancien",
                             "Filtres manquants : " + ", ".join(win.tools.missing_filters))
    else:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(400, win.maybe_welcome)       # premier lancement : mode d'emploi
    return app.exec()
