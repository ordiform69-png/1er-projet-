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
import traceback
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSettings, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QApplication, QBoxLayout, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from . import icons, photo, pipeline, theme
from .dvd import open_media
from .probe import MediaInfo, cast_gains
from .advice import advise
from .eta import Eta
from .advice import apply as apply_advice
from .profiles import PROFILES, RESOLUTIONS, profile_for
from .tools import Cancelled, ToolError, Toolset, detect_tools

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

    def set_after_label(self, text: str) -> None:
        """Étiquette de droite : « RESTAURÉ », ou « COULEURS IA » pour une photo colorisée."""
        self.after_label = text
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self.before is not None:
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
        p.drawPixmap(r, self.after)
        cut = int(r.width() * self.split)
        sx = self.before.width() * self.split
        p.drawPixmap(QRect(r.x(), r.y(), cut, r.height()), self.before,
                     QRect(0, 0, int(sx), self.before.height()))
        x = r.x() + cut
        p.setPen(QPen(QColor(theme.ACCENT), 2))
        p.drawLine(x, r.top(), x, r.bottom())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        p.drawEllipse(QPoint(x, r.center().y()), 5, 5)
        fm = p.fontMetrics()
        h = fm.height() + 10
        largeur = sum(fm.horizontalAdvance(t) + 22 for t in ("ORIGINAL", self.after_label)) + 36
        etroit = r.width() < largeur    # photo en hauteur : « Restauré » passe en bas
        for text, left in (("ORIGINAL", True), (self.after_label, False)):
            w = fm.horizontalAdvance(text) + 22
            y = r.bottom() - h - 12 if (etroit and not left) else r.y() + 12
            box = QRect(r.x() + 12 if left else r.right() - w - 12, y, w, h)
            p.setPen(QPen(QColor(theme.ACCENT), 1))
            p.setBrush(QColor(16, 32, 40, 210))
            p.drawRoundedRect(box, 4, 4)
            p.setPen(QColor("#f3f6fa"))
            p.drawText(box, Qt.AlignCenter, text)


class DropZone(QLabel):
    dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__("Déposez une vidéo ici\nou cliquez sur « Choisir une vidéo »")
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


class StepButton(QPushButton):
    """Grand bouton d'étape : numéro dans un cercle, texte aligné à gauche."""

    def __init__(self, number: str, text: str, icon: str = "") -> None:
        super().__init__(text)
        self.number = number
        self.icon_name = icon
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(58)

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
            bg, fg, border = QColor(theme.CARTE), QColor(theme.TEXTE), QColor("#49c3d4")
            if self.underMouse():
                border = QColor(theme.ACCENT)
                bg = QColor("#24323a")
        else:
            bg, fg, border = QColor(theme.FOND_DESACTIVE), QColor(theme.TEXTE_DESACTIVE), QColor("#2a3340")
        p.setPen(QPen(border, 1.4))
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
        f = QFont(theme.DISPLAY_FAMILY or p.font().family())
        f.setPointSizeF(14)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRect(cx - r, cy - r, r * 2, r * 2), Qt.AlignCenter, self.number)
        x = 56
        if self.icon_name:
            col = (theme.AMBRE_TEXTE if on else theme.AMBRE_ETEINT_TEXTE) if principal else \
                (theme.ACCENT if on else "#6b7887")
            p.drawPixmap(x, cy - 12, icons.pixmap(self.icon_name, 24, col))
            x += 34
        f.setPointSizeF(15)
        f.setBold(principal)
        p.setFont(f)
        p.setPen(fg)
        p.drawText(QRect(x, 0, self.width() - x - 12, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())


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


PROFILE_LOOK = {"fidele": ("bouclier", "Doux et fidèle"),
                "equilibre": ("balance", "Conseillé"),
                "maximum": ("fusee", "Nettoyage fort")}


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
        self._compacter_options()
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
        filet = QFrame()
        filet.setObjectName("filet")
        bv.addWidget(brand)
        bv.addWidget(title)
        bv.addWidget(filet)
        bh.addLayout(bv, 1)
        v.addWidget(band)
        self.s_info = QLabel("Commencez par choisir le film à restaurer.")
        self.s_info.setWordWrap(True)
        self.s_info.setObjectName("infos")
        v.addWidget(self.s_info)
        self.advice: list = []
        self.s_advice = QCheckBox("Appliquer ces conseils")
        self.s_advice.setToolTip("Corrige avec modération les défauts détectés par l'analyse (son, contraste, couleur). "
                                 "Décochez pour garder le son tel quel.")
        self.s_advice.setVisible(False)
        _with_icon(self.s_advice, "conseil")
        v.addWidget(self.s_advice)
        self.s_colorize = QCheckBox("Coloriser aussi — couleurs inventées par l'IA, pas les vraies "
                                    "(copie à part, le noir et blanc est gardé)")
        _with_icon(self.s_colorize, "palette")
        self.s_colorize.setVisible(False)
        self.s_colorize.toggled.connect(lambda _on: self._colorize_toggled())
        v.addWidget(self.s_colorize)
        h = QHBoxLayout()
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
            h.addWidget(b)
        v.addLayout(h)
        self.s_note = note = QLabel("Le son est nettoyé avec l'image. Le film d'origine n'est pas modifié. "
                      "Décalage, dérive et copie WAV : Options avancées.")
        note.setWordWrap(True)
        note.setObjectName("note")
        v.addWidget(note)
        self.s_compare = CompareView()
        v.addWidget(self.s_compare, 1)
        self.s_progress = theme.SweepBar()
        self.s_status = QLabel("Prêt.")
        self.s_status.setWordWrap(True)
        self.s_status.setObjectName("statut")
        v.addWidget(self.s_progress)
        v.addWidget(self.s_status)
        h = QHBoxLayout()
        self.s_cancel = QPushButton("Arrêter")
        self.s_cancel.setObjectName("secondaire")
        self.s_cancel.clicked.connect(self.cancel)
        self.s_folder = QPushButton("Restaurer tout un dossier (films et photos)…")
        self.s_folder.setObjectName("secondaire")
        self.s_folder.clicked.connect(self.start_folder)
        self.s_hear_orig = QPushButton("Écouter l'original")
        self.s_hear_new = QPushButton("Écouter le son restauré")
        for b in (self.s_hear_orig, self.s_hear_new):
            b.setObjectName("secondaire")
            _with_icon(b, "casque")
        _with_icon(self.s_cancel, "stop")
        _with_icon(self.s_folder, "pile")
        self.s_hear_orig.clicked.connect(self._play_original)
        self.s_hear_new.clicked.connect(self._play_restored)
        adv = QPushButton("Options avancées ▸")
        _with_icon(adv, "reglages")
        adv.setObjectName("lien")
        adv.setCursor(Qt.PointingHandCursor)
        adv.clicked.connect(lambda: self.set_advanced(True))
        h.addWidget(self.s_cancel)
        h.addWidget(self.s_folder)
        h.addWidget(self.s_hear_orig)
        h.addWidget(self.s_hear_new)
        h.addStretch(1)
        h.addWidget(adv)
        v.addLayout(h)
        return page

    def set_advanced(self, on: bool) -> None:
        self.pages.setCurrentIndex(1 if on else 0)

    COLONNE_UNIQUE_SOUS = 1240     # px : portable à 125 % / 150 %, ou fenêtre réduite

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        cols = getattr(self, "_colonnes", None)
        if cols is not None:
            sens = (QBoxLayout.TopToBottom if self.width() < self.COLONNE_UNIQUE_SOUS
                    else QBoxLayout.LeftToRight)
            if cols.direction() != sens:
                cols.setDirection(sens)

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
        accueil.setWidget(self._build_simple())
        self.pages.addWidget(accueil)
        scroll = QScrollArea()          # la page des options est plus haute qu'un écran de portable
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(central)
        self.pages.addWidget(scroll)
        self.setCentralWidget(self.pages)

        # Import
        g = Carte("Vidéo numérisée", "film", "1")
        v = g.body
        self.drop = DropZone()
        self.drop.dropped.connect(self.load_file)
        b = _with_icon(QPushButton("Choisir une vidéo…"), "dossier")
        b.clicked.connect(self._choose_file)
        v.addWidget(self.drop)
        v.addWidget(b)
        left.addWidget(g)

        # Caractéristiques
        g = Carte("Caractéristiques", "info")
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
        self.warn_label.setStyleSheet(f"color:{theme.AMBRE}")
        self.info_form.addRow(self.warn_label)
        left.addWidget(g)

        # Profils : trois tuiles
        g = Carte("Profil de restauration", "etincelle", "2")
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
        gi = Carte("Image", "image")
        vi = gi.body
        h = QHBoxLayout()
        self.res_combo = QComboBox()
        for k, txt in RESOLUTIONS.items():
            self.res_combo.addItem(icons.icon("ecran"), txt, k)
        self.ai_check = _with_icon(QCheckBox("Amélioration IA (Real-ESRGAN)"), "puce")
        self.ai_check.toggled.connect(self._ai_toggled)
        h.addWidget(_ilabel("Sortie :", "ecran"))
        h.addWidget(self.res_combo, 1)
        vi.addLayout(h)
        h = QHBoxLayout()
        self.deint_combo = QComboBox()
        self.deint_combo.addItem("bwdif (rapide)", "bwdif")
        self.deint_combo.addItem("QTGMC (meilleure qualité, plus lent)", "qtgmc")
        h.addWidget(_ilabel("Désentrelaceur :", "trames"))
        h.addWidget(self.deint_combo, 1)
        vi.addLayout(h)
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
        vi.addLayout(h)
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
        vi.addLayout(h)
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
        vi.addLayout(h)
        vi.addWidget(self.ai_check)
        left.addWidget(gi)

        # Son
        gs = Carte("Son", "onde")
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
        h.addWidget(_ilabel("Début de l'extrait :", "horloge"))
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
        self.out_edit.setPlaceholderText("Dossier de la vidéo d'origine")
        bo = _with_icon(QPushButton("Dossier de sortie…"), "dossier")
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
        v.addLayout(h)
        h = QHBoxLayout()
        self.run_btn = QPushButton("Lancer la restauration")
        self.run_btn.setObjectName("action")
        self.run_btn.setIcon(icons.icon("etincelle", theme.AMBRE_TEXTE, 24))
        self.run_btn.setIconSize(QSize(24, 24))
        self.run_btn.clicked.connect(self.start_export)
        self.run_btn.installEventFilter(self._halos[1])
        self.cancel_btn = _with_icon(QPushButton("Annuler"), "stop")
        self.cancel_btn.clicked.connect(self.cancel)
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
        h.addStretch(1)
        h.addWidget(self.check_btn)
        v.addLayout(h)
        right.addWidget(g)

        # les deux pages affichent la même progression, le même état, le même aperçu
        self.status = _Mirror(self.status, self.s_status)
        self.progress = _Mirror(self.progress, self.s_progress)
        self.compare = _Mirror(self.compare, self.s_compare)
        self.tools_label = QLabel()
        self.statusBar().addPermanentWidget(self.tools_label)
        self.profile_buttons["equilibre"].setChecked(True)
        self._load_prefs()

    # ------------------------------------------------------------ état
    def _refresh_tools(self) -> None:
        t = self.tools
        ok_ff = bool(t.ffmpeg.path and t.ffprobe.path and not t.missing_filters)
        parts = [("FFmpeg", ok_ff, f"FFmpeg {t.ffmpeg.version}" if ok_ff else "FFmpeg manquant (requis)"),
                 ("QTGMC", t.qtgmc_available, f"QTGMC ({t.vspipe.version})"),
                 ("Real-ESRGAN", t.ai_available, "Real-ESRGAN"),
                 ("DeepFilterNet", t.deepfilter_available, "DeepFilterNet"),
                 ("Colorisation", t.colorize_available, "Colorisation (DDColor)")]
        self.tools_label.setText("   ".join(f"{'●' if ok else '○'} {name}" for name, ok, _ in parts))
        self.tools_label.setToolTip("● installé   ○ non installé (facultatif, sauf FFmpeg)\n"
                                    + "\n".join(f"{'✔' if ok else '—'} {det}" for _n, ok, det in parts))
        self.s_colorize.setToolTip(
            "Photo noir et blanc seulement. L'IA (DDColor) DEVINE des couleurs plausibles : elles peuvent "
            "être fausses (vêtements, peau, objets). Une copie « …_colorisee_ia.png » est écrite en plus ; "
            "la photo restaurée en noir et blanc est toujours gardée." if t.colorize_available else
            "Colorisation non installée : relancez installer.bat -AvecCouleurs "
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
                                 "Installez Real-ESRGAN : relancez installer.bat -AvecIA "
                                 + (f"({t.realesrgan.problem})" if t.realesrgan.problem else ""))

    def _colorize_toggled(self) -> None:
        """L'aperçu affiché ne correspond plus aux réglages : on l'efface."""
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
        self.s_colorize.setEnabled(self.tools.colorize_available and not busy)
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
        for b in (self.play_btn, self.hear_orig_btn, self.hear_new_btn,
                  self.s_hear_orig, self.s_hear_new):
            b.setEnabled(has_prev and not busy)
            b.setVisible(not getattr(self, "is_photo", False))     # une photo n'a pas de son
        self.s_note.setVisible(not getattr(self, "is_photo", False))
        self.still_combo.setEnabled(has_prev)

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
            notes.append(f"💡 Conseil : {a.text} (case « Appliquer ces conseils » du mode simple, "
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

    # ------------------------------------------------------------ actions
    def _choose_file(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Choisir une vidéo numérisée", "", VIDEO_FILTER)
        if f:
            self.load_file(f)

    def _choose_outdir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier de sortie", self.out_edit.text())
        if d:
            self.out_edit.setText(d)

    def load_file(self, path: str) -> None:
        if self._busy():
            return
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
        if not self.out_edit.text() or not pipeline.is_writable(Path(self.out_edit.text())):
            try:
                out, fallback = pipeline.output_dir_for(info.path.parent)
                self.out_edit.setText(str(out))
                if fallback:
                    self.out_note = (f"ℹ Le dossier de la photo ne peut pas être modifié : la photo restaurée "
                                     f"sera enregistrée dans {out}")
            except ToolError as exc:
                self.out_note = f"⚠ {exc}"
        self.advice = advise(info)
        tips = "".join(f"<br>💡 {a.text}" for a in self.advice)
        kind = " Noir et blanc : elle le restera." if info.black_and_white else ""
        self.s_info.setText(f"<b>{info.path.name}</b> — photo de {info.width} × {info.height} pixels.{kind}{tips}")
        self.s_advice.setChecked(False)
        self.s_advice.setVisible(bool(self.advice))
        self.s_colorize.setChecked(False)                     # jamais coché d'avance
        self.s_colorize.setVisible(info.black_and_white)
        self.drop.setText(info.path.name)
        self._update_state()
        self._refresh_hints()
        self.status.setText("Photo analysée. Choisissez un profil puis regardez l'avant / après.")

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
        if not self.out_edit.text() or not pipeline.is_writable(Path(self.out_edit.text())):
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
        src_txt = {"video": "vidéo de caméscope ou de magnétoscope", "film": "pellicule (Super 8, 8 mm…)",
                   "transfer": "pellicule copiée sur vidéo"}[info.suggested_source]
        extra = (" Noir et blanc." if info.black_and_white else
                 " Couleurs très pâles." if info.pale_colors else "") + \
                ("" if info.has_audio and not info.audio_silent else " Film muet : il restera muet.")
        self.advice = advise(info)
        tips = "".join(f"<br>💡 {a.text}" for a in self.advice)
        self.s_info.setText(f"<b>{info.summary()['Fichier']}</b> — {info.summary()['Durée']} — "
                            f"semble être une {src_txt}.{extra}{tips}")
        self.s_advice.setChecked(False)
        self.s_advice.setVisible(bool(self.advice))
        self.channel_combo.setCurrentIndex(0)
        self.declip_check.setChecked(False)
        self._refresh_hints()
        self.status.setText("Vidéo analysée. Choisissez un profil puis générez un aperçu.")

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
        if getattr(self, "is_photo", False):
            self.status.setText("Aperçu prêt. Déplacez la souris sur l'image pour comparer.")
        else:
            self.status.setText(f"Aperçu prêt (de {res.start:.0f} s à {res.start + res.duration:.0f} s). "
                                "Déplacez la souris sur l'image pour comparer.")

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
                QMessageBox.warning(self, "Dossier de sortie", str(exc))
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
                         self._export_done)
            return
        try:
            out = pipeline.unique_output_path(info, s, out_dir)
            start, length = pipeline.trim_window(info, self.trim_start.value(), self.trim_end.value())
        except ToolError as exc:
            QMessageBox.warning(self, "Réglages", str(exc))
            return
        self.status.setText(f"Restauration vers {out.name}…")
        self._launch(lambda c, p: pipeline.export(info, s, out, self.tools, cancel=c, progress=p,
                                                  start=start, duration=length),
                     self._export_done)

    def check_install(self) -> None:
        """Lance l'autotest (le même que celui de la fabrication Windows) et montre le rapport."""
        if self._busy():
            return
        from .__main__ import autotest
        folder = Path(tempfile.mkdtemp(prefix="vhsrestore_verif_"))

        def job(cancel, progress):
            progress(0.1, "Vérification de l'installation…")
            code = autotest(str(folder))
            text = (folder / "autotest.txt").read_text(encoding="utf-8", errors="replace")
            shutil.rmtree(folder, ignore_errors=True)
            return code, text
        self.status.setText("Vérification de l'installation…")
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
        self.status.setText(f"Terminé : {out}")
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
            self._done_box("Votre photo restaurée est prête",
                           f"Votre photo restaurée est prête :\n{out.name}{more}\n\nElle se trouve dans le dossier :\n"
                           f"{out.parent}\n\nLa photo d'origine n'a pas été modifiée.", out.parent)
            return
        self._done_box("Votre film restauré est prêt",
                       f"Votre film restauré est prêt :\n{out.name}\n\nIl se trouve dans le dossier :\n"
                       f"{out.parent}{extra}\n\nLe film d'origine n'a pas été modifié.", out.parent)

    def _done_box(self, title: str, text: str, folder: Path) -> None:
        box = QMessageBox(QMessageBox.Information, title, text, parent=self)
        open_btn = box.addButton("Ouvrir le dossier", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def settings_for(self, info: MediaInfo) -> pipeline.Settings:
        """Réglages d'un film du dossier : options choisies, origine propre à chaque film
        (choix manuel s'il y en a un, sinon suggestion de l'analyse)."""
        base = self.settings(with_advice=False)
        if self.s_advice.isChecked():          # conseils propres à CHAQUE film du dossier
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
        d = QFileDialog.getExistingDirectory(self, "Dossier contenant les films à restaurer")
        if d:
            self.restore_folder(Path(d))

    def restore_folder(self, folder: Path) -> None:
        self.status.setText("Restauration du dossier…")
        self._launch(lambda c, p: pipeline.restore_folder(folder, self.tools, self.settings_for,
                                                          cancel=c, progress=p), self._folder_done)

    def _folder_done(self, res: pipeline.BatchResult) -> None:
        self.status.setText(f"Terminé : {len(res.done)} film(s) restauré(s) dans {res.out_dir}")
        txt = f"{len(res.done)} film(s) restauré(s) dans le dossier :\n{res.out_dir}"
        if res.fallback:
            txt += "\n(le dossier des films ne pouvait pas être modifié : DVD ou clé protégée)"
        if res.skipped:
            txt += f"\n\n{len(res.skipped)} film(s) déjà restauré(s) auparavant, laissé(s) tel(s) quel(s)."
        if res.errors:
            txt += "\n\nCes fichiers n'ont pas pu être restaurés :\n" + "\n".join(
                f"• {name} : {msg}" for name, msg in res.errors)
        self._done_box("Dossier terminé", txt + "\n\nLes films d'origine n'ont pas été modifiés.",
                       res.out_dir)

    def cancel(self) -> None:
        if self._busy():
            self.worker.cancel_event.set()
            self.status.setText("Annulation en cours…")

    # ------------------------------------------------------------ worker
    def _launch(self, fn: Callable, on_success: Callable[[Any], None]) -> None:
        self.worker = w = Worker(fn)
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
        self.status.setText(f"{msg} {frac * 100:.0f} %" + (f" — {left}" if left else ""))

    def _on_failed(self, msg: str) -> None:
        self.status.setText("Échec.")
        QMessageBox.critical(self, "VHS Restore AI", msg)

    def _on_finished(self) -> None:
        self.progress.setRange(0, 1000)
        if not self.status.text().startswith(("Terminé", "Aperçu prêt", "Vidéo analysée")):
            self.progress.setValue(0)
        else:
            self.progress.setValue(1000)
        self._update_state()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self._busy():
            if QMessageBox.question(self, "Quitter", "Un traitement est en cours. L'annuler et quitter ?") \
                    != QMessageBox.Yes:
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
        if out:
            self.out_edit.setText(out)

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
        s.setValue("out_dir", self.out_edit.text())


def main() -> int:
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("VHS Restore AI")
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
    return app.exec()
