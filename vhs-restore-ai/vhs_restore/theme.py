"""Habillage de l'interface : salle de montage, sombre, lisible.

Couleurs fixes (pas celles du thème Windows). Le texte principal fait au moins
12 pt, les gros boutons au moins 13 pt, et chaque couple texte/fond listé dans
CONTRASTES atteint 4,5:1 (WCAG AA). Les polices OFL sont embarquées ; si un
fichier manque, on retombe sur la police du système.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPalette
from PySide6.QtWidgets import QApplication, QProgressBar

# Anthracite, pas noir pur. Cyan en filet, ambre seulement pour l'action principale.
FOND = "#14181e"
CARTE = "#1e242d"
CARTE_SUR = "#262e39"
BORD = "#3c4c5e"
TEXTE = "#f3f6fa"
TEXTE_DOUX = "#c5d0dc"
TEXTE_DESACTIVE = "#d5dde6"
FOND_DESACTIVE = "#10141a"
ACCENT = "#7ee7f7"
ACCENT_SOURD = "#9aa7b5"
BANDEAU = "#0c2c34"
MONITEUR = "#0e1218"
MONITEUR_TEXTE = "#d5dde8"
AMBRE = "#e8b15a"
AMBRE_SURVOL = "#f0c36a"
AMBRE_PRESSE = "#c98a32"
AMBRE_TEXTE = "#1a1206"
AMBRE_ETEINT = "#5c4a2c"
AMBRE_ETEINT_TEXTE = "#f3e6c8"
PISTE = "#2a313c"

# Couples réellement peints. Le test de contraste lit cette liste, pas le QSS.
CONTRASTES = (
    ("texte / fond", TEXTE, FOND),
    ("texte secondaire / fond", TEXTE_DOUX, FOND),
    ("texte / carte", TEXTE, CARTE),
    ("texte secondaire / carte", TEXTE_DOUX, CARTE),
    ("texte / champ", TEXTE, CARTE_SUR),
    ("titre / bandeau", "#ffffff", BANDEAU),
    ("marque / bandeau", "#9ae7f5", BANDEAU),
    ("accent / fond", ACCENT, FOND),
    ("bouton / carte", TEXTE, CARTE),
    ("bouton désactivé", TEXTE_DESACTIVE, FOND_DESACTIVE),
    ("restaurer", AMBRE_TEXTE, AMBRE),
    ("restaurer survol", AMBRE_TEXTE, AMBRE_SURVOL),
    ("restaurer pressé", AMBRE_TEXTE, AMBRE_PRESSE),
    ("restaurer désactivé", AMBRE_ETEINT_TEXTE, AMBRE_ETEINT),
    ("moniteur", MONITEUR_TEXTE, MONITEUR),
    ("pastille", "#f3f6fa", "#102028"),
    ("avertissement / fond", AMBRE, FOND),
    ("avertissement / carte", AMBRE, CARTE),
)

BODY_FAMILY = ""
DISPLAY_FAMILY = ""
_FONTS_LOADED = False

_ROOT = Path(__file__).resolve().parent
_FONTS = _ROOT / "assets" / "fonts"
_ICONS = _ROOT / "assets" / "icons"


def contraste(fg: str, bg: str) -> float:
    """Rapport WCAG entre deux couleurs #rrggbb."""
    def lum(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        vals = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            vals.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        r, g, b = vals
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _icon(name: str) -> str:
    return (_ICONS / name).as_posix()


def load_fonts() -> tuple[str, str]:
    """Charge Inter (texte) et Rajdhani (bandeau). Familles vides si le fichier manque."""
    global _FONTS_LOADED, BODY_FAMILY, DISPLAY_FAMILY
    if _FONTS_LOADED:
        return BODY_FAMILY, DISPLAY_FAMILY
    _FONTS_LOADED = True
    body = display = ""
    for fname in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf"):
        path = _FONTS / fname
        if not path.is_file():
            continue
        fid = QFontDatabase.addApplicationFont(str(path))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams and not body:
            body = fams[0]
    for fname in ("Rajdhani-Medium.ttf", "Rajdhani-SemiBold.ttf", "Rajdhani-Bold.ttf"):
        path = _FONTS / fname
        if not path.is_file():
            continue
        fid = QFontDatabase.addApplicationFont(str(path))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams and not display:
            display = fams[0]
    BODY_FAMILY, DISPLAY_FAMILY = body, display
    return body, display


def _family(name: str, fallback: str) -> str:
    return f'"{name}", "{fallback}", sans-serif' if name else f'"{fallback}", sans-serif'


def _qss() -> str:
    body = _family(BODY_FAMILY, "Segoe UI")
    display = _family(DISPLAY_FAMILY or BODY_FAMILY, "Segoe UI")
    down, up = _icon("chevron-down.svg"), _icon("chevron-up.svg")
    return f"""
QMainWindow, QWidget#page, QDialog, QMessageBox {{
    background: {FOND}; color: {TEXTE}; font-family: {body}; font-size: 12.5pt;
}}
QWidget {{ color: {TEXTE}; font-family: {body}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ border: none; background: {FOND}; }}

QFrame#bandeau {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #081c22, stop:0.55 {BANDEAU}, stop:1 #123028);
    border: 1px solid #1d5c68;
    border-radius: 14px;
}}
QFrame#filet {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:0.55 {AMBRE}, stop:1 transparent);
    border: none; min-height: 2px; max-height: 2px;
}}
QLabel#marque {{
    color: #9ae7f5; font-family: {display}; font-size: 13pt; font-weight: 600;
    letter-spacing: 3px;
}}
QLabel#titre {{
    color: white; font-family: {display}; font-size: 22pt; font-weight: 600;
    letter-spacing: 1px;
}}
QLabel#infos {{
    color: {TEXTE}; font-size: 13pt; background: {CARTE};
    border: 1px solid {BORD}; border-radius: 10px; padding: 10px 14px;
}}
QLabel#statut {{ color: {TEXTE}; font-size: 13pt; }}
QLabel#note {{ color: {TEXTE_DOUX}; font-size: 12pt; }}
QLabel#depot {{
    color: {TEXTE}; font-size: 13pt;
    border: 1px dashed {ACCENT}; border-radius: 10px;
    background: {CARTE}; padding: 12px;
}}

QPushButton {{
    background: {CARTE}; color: {TEXTE}; border: 1px solid {BORD};
    border-radius: 8px; padding: 8px 14px; font-size: 12.5pt;
}}
QPushButton:hover {{ border-color: {ACCENT}; background: #24303a; }}
QPushButton:pressed {{ background: #182026; }}
QPushButton:disabled {{
    color: {TEXTE_DESACTIVE}; background: {FOND_DESACTIVE}; border-color: #3a4452;
}}
QPushButton#etape {{
    font-size: 15pt; font-weight: 600; min-height: 58px; border-radius: 12px;
    border: 1px solid #2f6f7c; background: {CARTE}; color: {TEXTE};
    padding-left: 58px;
}}
QPushButton#etape:hover {{ border-color: {ACCENT}; background: #24323a; }}
QPushButton#etape:disabled {{
    border-color: #3a4452; color: {TEXTE_DESACTIVE}; background: {FOND_DESACTIVE};
}}
QPushButton#principal, QPushButton#action {{
    font-size: 15pt; font-weight: 700; min-height: 58px; border-radius: 12px;
    border: none; color: {AMBRE_TEXTE}; background: {AMBRE}; padding-left: 58px;
}}
QPushButton#action {{ padding-left: 18px; padding-right: 18px; }}
QPushButton#principal:hover, QPushButton#action:hover {{ background: {AMBRE_SURVOL}; }}
QPushButton#principal:pressed, QPushButton#action:pressed {{ background: {AMBRE_PRESSE}; }}
QPushButton#principal:disabled, QPushButton#action:disabled {{
    background: {AMBRE_ETEINT}; color: {AMBRE_ETEINT_TEXTE};
}}
QPushButton#lien {{
    border: none; background: transparent; color: {ACCENT}; font-weight: 600;
    font-size: 13pt; padding: 6px 4px;
}}
QPushButton#lien:hover {{ color: #b8f4ff; }}
QPushButton#secondaire {{ font-size: 13pt; padding: 8px 12px; }}

QGroupBox {{
    background: {CARTE}; border: 1px solid {BORD}; border-radius: 12px;
    margin-top: 16px; padding: 16px 12px 12px 12px; font-weight: 600; font-size: 13pt;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 14px; padding: 0 8px; color: {ACCENT};
    background: {FOND}; border-radius: 4px; font-family: {display}; font-size: 13pt;
}}
QGroupBox QLabel {{ font-weight: 400; }}

QProgressBar {{
    background: transparent; border: none; min-height: 10px; max-height: 14px;
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QAbstractSpinBox {{
    background: {CARTE_SUR}; color: {TEXTE}; border: 1px solid {BORD};
    border-radius: 6px; padding: 4px 8px; min-height: 26px; font-size: 12.5pt;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {TEXTE_DESACTIVE}; background: {FOND_DESACTIVE};
}}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 28px; border: none; background: transparent;
}}
QComboBox::down-arrow {{ image: url("{down}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {CARTE}; color: {TEXTE}; border: 1px solid {BORD};
    selection-background-color: #164852; selection-color: {TEXTE}; outline: 0;
}}
QAbstractSpinBox {{ padding-right: 8px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border; width: 22px; border: none; background: {CARTE};
}}
QAbstractSpinBox::up-button {{
    subcontrol-position: top right; height: 16px; border-top-right-radius: 6px;
}}
QAbstractSpinBox::down-button {{
    subcontrol-position: bottom right; height: 16px; border-bottom-right-radius: 6px;
}}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
    background: #31404c;
}}
QAbstractSpinBox::up-arrow {{ image: url("{up}"); width: 12px; height: 12px; }}
QAbstractSpinBox::down-arrow {{ image: url("{down}"); width: 12px; height: 12px; }}

QCheckBox, QRadioButton {{ spacing: 8px; font-size: 12.5pt; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 20px; height: 20px; }}
QCheckBox::indicator:unchecked {{ image: url("{_icon("check-off.svg")}"); }}
QCheckBox::indicator:checked {{ image: url("{_icon("check-on.svg")}"); }}
QCheckBox::indicator:disabled {{ image: url("{_icon("check-off-off.svg")}"); }}
QCheckBox::indicator:checked:disabled {{ image: url("{_icon("check-on.svg")}"); }}
QRadioButton::indicator:unchecked {{ image: url("{_icon("radio-off.svg")}"); }}
QRadioButton::indicator:checked {{ image: url("{_icon("radio-on.svg")}"); }}
QRadioButton::indicator:disabled {{ image: url("{_icon("radio-off-off.svg")}"); }}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #4a596b; border-radius: 4px; min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: #6a7d92; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: #4a596b; border-radius: 4px; min-width: 36px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ background: {CARTE}; border-top: 1px solid {BORD}; color: {TEXTE_DOUX}; }}
QToolTip {{
    background: {BANDEAU}; color: {TEXTE}; border: 1px solid {ACCENT};
    padding: 6px; font-size: 12pt;
}}
QMessageBox QLabel {{ color: {TEXTE}; font-size: 13pt; }}
QMessageBox QPushButton {{ font-size: 13pt; min-width: 96px; min-height: 36px; }}
"""


def apply(app: QApplication) -> None:
    """Palette sombre fixe + feuille de style. Indépendant du mode Windows."""
    body, _display = load_fonts()
    font = QFont(body or app.font().family())
    font.setPointSizeF(12.5)
    app.setFont(font)
    app.setStyle("Fusion")
    pal = QPalette()
    roles = (
        (QPalette.Window, FOND), (QPalette.Base, CARTE_SUR), (QPalette.AlternateBase, CARTE),
        (QPalette.Text, TEXTE), (QPalette.WindowText, TEXTE), (QPalette.Button, CARTE),
        (QPalette.ButtonText, TEXTE), (QPalette.Highlight, "#164852"),
        (QPalette.HighlightedText, TEXTE), (QPalette.ToolTipBase, BANDEAU),
        (QPalette.ToolTipText, TEXTE), (QPalette.PlaceholderText, TEXTE_DOUX),
        (QPalette.Mid, BORD), (QPalette.Dark, FOND), (QPalette.Shadow, "#0a0d11"),
        (QPalette.Light, CARTE_SUR),
    )
    for role, color in roles:
        pal.setColor(role, QColor(color))
    for role, color in ((QPalette.WindowText, TEXTE_DOUX), (QPalette.Text, TEXTE_DESACTIVE),
                        (QPalette.ButtonText, TEXTE_DESACTIVE), (QPalette.Button, FOND_DESACTIVE)):
        pal.setColor(QPalette.Disabled, role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(_qss())


class SweepBar(QProgressBar):
    """Barre fine. Un balayage léger seulement pendant le traitement, jamais au repos."""

    def __init__(self) -> None:
        super().__init__()
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self.setTextVisible(False)
        self.setMinimumHeight(16)
        self.setRange(0, 1000)

    def _busy(self) -> bool:
        if self.minimum() == self.maximum():
            return True
        return self.minimum() < self.value() < self.maximum()

    def _sync(self) -> None:
        if self._busy():
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()
        self.update()

    def setValue(self, value: int) -> None:  # noqa: N802
        super().setValue(value)
        self._sync()

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        super().setRange(minimum, maximum)
        self._sync()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.035) % 1.0
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        track = self.rect().adjusted(0, 4, 0, -4)
        p.setBrush(QColor("#10161c"))
        p.drawRoundedRect(track, 3, 3)
        if self.minimum() == self.maximum():
            w = max(48, track.width() // 5)
            x = track.x() + int(self._phase * max(1, track.width() - w))
            chunk = track.adjusted(0, 0, 0, 0)
            chunk.setX(x)
            chunk.setWidth(w)
        else:
            span = max(1, self.maximum() - self.minimum())
            frac = (self.value() - self.minimum()) / span
            chunk = track.adjusted(0, 0, 0, 0)
            chunk.setWidth(max(0, int(track.width() * frac)))
        if chunk.width() <= 0:
            return
        grad = QLinearGradient(chunk.topLeft(), chunk.topRight())
        grad.setColorAt(0, QColor("#1a8a98"))
        grad.setColorAt(1, QColor("#d7fbff"))
        p.setBrush(grad)
        p.drawRoundedRect(chunk, 3, 3)
        if self._timer.isActive() and chunk.width() > 8:
            hx = chunk.x() + int(self._phase * chunk.width())
            shine = QLinearGradient(hx - 28, 0, hx + 28, 0)
            shine.setColorAt(0, QColor(255, 255, 255, 0))
            shine.setColorAt(0.5, QColor(255, 255, 255, 110))
            shine.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(shine)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(chunk, 3, 3)
