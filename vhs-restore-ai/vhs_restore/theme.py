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

# Deux palettes : « clair » (par défaut, comme la maquette) et « sombre » (au choix,
# bouton « Affichage sombre »). Le bandeau et l'écran d'aperçu restent sombres dans les deux.
SOMBRE = {
    "FOND": "#14181e", "CARTE": "#1e242d", "CARTE_SUR": "#262e39", "CARTE_HAUT": "#212833",
    "BORD": "#3c4c5e", "TEXTE": "#f3f6fa", "TEXTE_DOUX": "#c5d0dc",
    "TEXTE_DESACTIVE": "#8e9bab",      # nettement plus terne que TEXTE : un bouton grisé doit se voir
    "FOND_DESACTIVE": "#10141a", "BORD_DESACTIVE": "#262d37",
    "ACCENT": "#7ee7f7", "ACCENT_SOURD": "#9aa7b5", "LIEN_SURVOL": "#b8f4ff",
    "AMBRE": "#e8b15a", "AMBRE_SURVOL": "#f0c36a", "AMBRE_PRESSE": "#c98a32", "AMBRE_TEXTE": "#1a1206",
    "AMBRE_ETEINT": "#3d3324", "AMBRE_ETEINT_TEXTE": "#c9b893",   # Restaurer indisponible : terne
    "AVERT": "#e8b15a",
    "PISTE": "#10161c", "BARRE_DEBUT": "#1a8a98", "BARRE_FIN": "#d7fbff",
    "TUILE_ACTIVE": "#123a44",
    "SURVOL": "#24303a", "PRESSE": "#182026", "SELECTION": "#164852",
    "ETAPE_BORD": "#2f6f7c", "ETAPE_SURVOL": "#24323a", "ETAPE_CADRE": "#49c3d4", "ETAPE_ETEINT": "#2a3340",
    "SPIN_SURVOL": "#31404c", "POIGNEE": "#4a596b", "POIGNEE_SURVOL": "#6a7d92",
    "FILET_MILIEU": "#2c6f7b", "ICONE_FOND": "#0e2a31", "ICONE_BORD": "#1d5c68", "VOYANT_SURVOL": "#1b2a33",
    "HALO_PAGE": "#173842", "FOND_BAS": "#0f1217", "ICONE_GRISE": "#6b7887", "ICONE_ACTIVE": "#d7fbff",
    "SEGMENT_CHOISI": "#0e4e58",
    "CHEVRONS": "", "INTERRUPTEURS": "",
}
CLAIR = {
    "FOND": "#eef2f6", "CARTE": "#ffffff", "CARTE_SUR": "#f4f7fa", "CARTE_HAUT": "#ffffff",
    "BORD": "#aeb9c6", "TEXTE": "#141b24", "TEXTE_DOUX": "#3d4856",
    "TEXTE_DESACTIVE": "#5c6673", "FOND_DESACTIVE": "#e9edf2", "BORD_DESACTIVE": "#d3dae2",
    "ACCENT": "#0a6577", "ACCENT_SOURD": "#56626f", "LIEN_SURVOL": "#06424e",
    "AMBRE": "#e8b15a", "AMBRE_SURVOL": "#f0c36a", "AMBRE_PRESSE": "#c98a32", "AMBRE_TEXTE": "#1a1206",
    "AMBRE_ETEINT": "#efe6d4", "AMBRE_ETEINT_TEXTE": "#6b5a3a",
    "AVERT": "#8a5300",
    "PISTE": "#dbe2e9", "BARRE_DEBUT": "#0a6577", "BARRE_FIN": "#2fb3c8",
    "TUILE_ACTIVE": "#d8eff3",
    "SURVOL": "#e6f3f6", "PRESSE": "#d3e7ec", "SELECTION": "#cfe9ef",
    "ETAPE_BORD": "#7fb3bd", "ETAPE_SURVOL": "#e6f3f6", "ETAPE_CADRE": "#0a6577", "ETAPE_ETEINT": "#d3dae2",
    "SPIN_SURVOL": "#dbe8ec", "POIGNEE": "#b3bfcb", "POIGNEE_SURVOL": "#8d9cab",
    "FILET_MILIEU": "#7fb3bd", "ICONE_FOND": "#e3f2f5", "ICONE_BORD": "#9cc9d1", "VOYANT_SURVOL": "#e3f2f5",
    "HALO_PAGE": "#dcecf1", "FOND_BAS": "#e7ecf1", "ICONE_GRISE": "#8a95a2", "ICONE_ACTIVE": "#06424e",
    "SEGMENT_CHOISI": "#d8eff3",
    "CHEVRONS": "-sombre", "INTERRUPTEURS": "-clair",
}
# Communs aux deux : bandeau, écran d'aperçu.
BANDEAU = "#0c2c34"
MONITEUR = "#0e1218"
MONITEUR_TEXTE = "#d5dde8"
MONITEUR_ACCENT = "#7ee7f7"     # repères sur l'écran d'aperçu (toujours sombre)

MODE = "clair"
# Valeurs en cours (palette claire au départ ; set_mode() les remplace toutes).
FOND: str = CLAIR["FOND"]
CARTE: str = CLAIR["CARTE"]
CARTE_SUR: str = CLAIR["CARTE_SUR"]
CARTE_HAUT: str = CLAIR["CARTE_HAUT"]
BORD: str = CLAIR["BORD"]
TEXTE: str = CLAIR["TEXTE"]
TEXTE_DOUX: str = CLAIR["TEXTE_DOUX"]
TEXTE_DESACTIVE: str = CLAIR["TEXTE_DESACTIVE"]
FOND_DESACTIVE: str = CLAIR["FOND_DESACTIVE"]
BORD_DESACTIVE: str = CLAIR["BORD_DESACTIVE"]
ACCENT: str = CLAIR["ACCENT"]
ACCENT_SOURD: str = CLAIR["ACCENT_SOURD"]
LIEN_SURVOL: str = CLAIR["LIEN_SURVOL"]
AMBRE: str = CLAIR["AMBRE"]
AMBRE_SURVOL: str = CLAIR["AMBRE_SURVOL"]
AMBRE_PRESSE: str = CLAIR["AMBRE_PRESSE"]
AMBRE_TEXTE: str = CLAIR["AMBRE_TEXTE"]
AMBRE_ETEINT: str = CLAIR["AMBRE_ETEINT"]
AMBRE_ETEINT_TEXTE: str = CLAIR["AMBRE_ETEINT_TEXTE"]
AVERT: str = CLAIR["AVERT"]
PISTE: str = CLAIR["PISTE"]
BARRE_DEBUT: str = CLAIR["BARRE_DEBUT"]
BARRE_FIN: str = CLAIR["BARRE_FIN"]
TUILE_ACTIVE: str = CLAIR["TUILE_ACTIVE"]
SURVOL: str = CLAIR["SURVOL"]
PRESSE: str = CLAIR["PRESSE"]
SELECTION: str = CLAIR["SELECTION"]
ETAPE_BORD: str = CLAIR["ETAPE_BORD"]
ETAPE_SURVOL: str = CLAIR["ETAPE_SURVOL"]
ETAPE_CADRE: str = CLAIR["ETAPE_CADRE"]
ETAPE_ETEINT: str = CLAIR["ETAPE_ETEINT"]
SPIN_SURVOL: str = CLAIR["SPIN_SURVOL"]
POIGNEE: str = CLAIR["POIGNEE"]
POIGNEE_SURVOL: str = CLAIR["POIGNEE_SURVOL"]
FILET_MILIEU: str = CLAIR["FILET_MILIEU"]
ICONE_FOND: str = CLAIR["ICONE_FOND"]
ICONE_BORD: str = CLAIR["ICONE_BORD"]
VOYANT_SURVOL: str = CLAIR["VOYANT_SURVOL"]
HALO_PAGE: str = CLAIR["HALO_PAGE"]
FOND_BAS: str = CLAIR["FOND_BAS"]
ICONE_GRISE: str = CLAIR["ICONE_GRISE"]
ICONE_ACTIVE: str = CLAIR["ICONE_ACTIVE"]
SEGMENT_CHOISI: str = CLAIR["SEGMENT_CHOISI"]
CHEVRONS: str = CLAIR["CHEVRONS"]
INTERRUPTEURS: str = CLAIR["INTERRUPTEURS"]


def set_mode(mode: str) -> None:
    """Choisit la palette (« sombre » ou « clair »). À appeler avant de construire la fenêtre."""
    global MODE, CONTRASTES
    MODE = "clair" if mode == "clair" else "sombre"
    globals().update(CLAIR if MODE == "clair" else SOMBRE)
    CONTRASTES = contrastes()


def contrastes() -> tuple:
    """Couples réellement peints, pour la palette en cours. Le test de contraste lit cette liste."""
    return (
        ("texte / fond", TEXTE, FOND),
        ("texte secondaire / fond", TEXTE_DOUX, FOND),
        ("texte / carte", TEXTE, CARTE),
        ("texte secondaire / carte", TEXTE_DOUX, CARTE),
        ("texte / champ", TEXTE, CARTE_SUR),
        ("titre / bandeau", "#ffffff", BANDEAU),
        ("marque / bandeau", "#9ae7f5", BANDEAU),
        ("accent / fond", ACCENT, FOND),
        ("accent / carte", ACCENT, CARTE),
        ("bouton / carte", TEXTE, CARTE),
        ("bouton désactivé", TEXTE_DESACTIVE, FOND_DESACTIVE),
        ("restaurer", AMBRE_TEXTE, AMBRE),
        ("restaurer survol", AMBRE_TEXTE, AMBRE_SURVOL),
        ("restaurer pressé", AMBRE_TEXTE, AMBRE_PRESSE),
        ("restaurer désactivé", AMBRE_ETEINT_TEXTE, AMBRE_ETEINT),
        ("moniteur", MONITEUR_TEXTE, MONITEUR),
        ("pastille", "#f3f6fa", "#102028"),
        ("avertissement / fond", AVERT, FOND),
        ("avertissement / carte", AVERT, CARTE),
        ("tuile choisie", TEXTE, TUILE_ACTIVE),
        ("tuile choisie, phrase", TEXTE_DOUX, TUILE_ACTIVE),
        ("tuile, phrase", TEXTE_DOUX, CARTE_SUR),
        ("titre de carte", ACCENT, CARTE),
        ("numéro de carte", ACCENT_SOURD, CARTE),
        ("bouton survolé", TEXTE, SURVOL),
        ("segment choisi", TEXTE, SEGMENT_CHOISI),
        ("lien survolé", LIEN_SURVOL, FOND),
    )


CONTRASTES = contrastes()

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
    down, up = _icon(f"chevron-down{CHEVRONS}.svg"), _icon(f"chevron-up{CHEVRONS}.svg")
    return f"""
QMainWindow, QWidget#page, QDialog, QMessageBox {{
    background: {FOND}; color: {TEXTE}; font-family: {body}; font-size: 12.5pt;
}}
QWidget#page {{
    background: qradialgradient(cx:0.12, cy:0.0, radius:1.15, fx:0.12, fy:0.0,
        stop:0 {HALO_PAGE}, stop:0.38 {FOND}, stop:1 {FOND_BAS});
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
    color: {TEXTE}; font-size: 15pt; background: {CARTE};
    border: 1px solid {BORD}; border-radius: 10px; padding: 10px 14px;
}}
QLabel#statut {{ color: {TEXTE}; font-size: 14.5pt; }}
QLabel#note {{ color: {TEXTE_DOUX}; font-size: 13pt; }}
QLabel#depot {{
    color: {TEXTE}; font-size: 13pt;
    border: 1px dashed {ACCENT}; border-radius: 10px;
    background: {CARTE}; padding: 12px;
}}

QPushButton {{
    background: {CARTE}; color: {TEXTE}; border: 1px solid {BORD};
    border-radius: 8px; padding: 8px 14px; font-size: 12.5pt;
}}
QPushButton:hover {{ border-color: {ACCENT}; background: {SURVOL}; }}
QPushButton:pressed {{ background: {PRESSE}; }}
QPushButton:disabled {{
    color: {TEXTE_DESACTIVE}; background: {FOND_DESACTIVE}; border-color: {BORD_DESACTIVE};
}}
QPushButton#etape {{
    font-size: 15pt; font-weight: 600; min-height: 58px; border-radius: 12px;
    border: 1px solid {ETAPE_BORD}; background: {CARTE}; color: {TEXTE};
    padding-left: 58px;
}}
QPushButton#etape:hover {{ border-color: {ACCENT}; background: {ETAPE_SURVOL}; }}
QPushButton#etape:disabled {{
    border-color: {BORD_DESACTIVE}; color: {TEXTE_DESACTIVE}; background: {FOND_DESACTIVE};
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
QPushButton#lien:hover {{ color: {LIEN_SURVOL}; }}
QPushButton#secondaire {{ font-size: 14pt; padding: 9px 14px; }}
QPushButton#segment {{
    font-size: 14pt; padding: 8px 18px; min-width: 120px; border-radius: 10px;
}}
QPushButton#segment:checked {{
    background: {SEGMENT_CHOISI}; border: 2px solid {ACCENT}; color: {TEXTE}; font-weight: 700;
}}
QPushButton#lienDiscret {{
    border: none; background: transparent; color: {TEXTE_DOUX}; font-size: 12.5pt; padding: 6px 4px;
}}
QPushButton#lienDiscret:hover {{ color: {ACCENT}; text-decoration: underline; }}
QPushButton#bandeauBouton {{
    background: transparent; color: #d7f6fb; border: 1px solid #2c6f7b; border-radius: 8px;
    font-size: 12.5pt; padding: 5px 12px; text-align: left;
}}
QPushButton#bandeauBouton:hover {{ background: #123b45; border-color: #9ae7f5; }}
QPushButton#bandeauBouton:checked {{ background: #123b45; border: 2px solid #9ae7f5; color: #ffffff; font-weight: bold; }}
QPushButton#bandeauBouton:disabled {{ color: #7d98a0; border-color: #1d3d44; }}
QPushButton#aide {{
    min-width: 44px; max-width: 48px; min-height: 44px; max-height: 48px;
    font-size: 16pt; font-weight: 700; padding: 0; border-radius: 22px;
}}
QFrame#fini {{
    background: {CARTE}; color: {TEXTE};
    border: 2px solid {AMBRE}; border-radius: 14px;
}}
QLabel#finiTitre {{
    color: {TEXTE}; font-size: 22pt; font-weight: 700; background: transparent;
}}
QLabel#finiTexte {{
    color: {TEXTE}; font-size: 16pt; background: transparent;
}}
QCheckBox#caseSimple {{ font-size: 14pt; }}

QFrame#carte {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {CARTE_HAUT}, stop:1 {CARTE});
    border: 1px solid {BORD}; border-radius: 14px;
}}
QFrame#carteFilet {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:0.4 {FILET_MILIEU}, stop:1 transparent);
    border: none; min-height: 1px; max-height: 1px;
}}
QLabel#carteTitre {{
    color: {ACCENT}; font-family: {display}; font-size: 15pt; font-weight: 700;
    letter-spacing: 2px; background: transparent;
}}
QLabel#carteSous {{ color: {TEXTE_DOUX}; font-size: 12pt; background: transparent; }}
QLabel#carteNumero {{
    color: {ACCENT_SOURD}; font-family: {display}; font-size: 18pt; font-weight: 700;
    letter-spacing: 1px; background: transparent;
}}
QLabel#carteIcone {{
    background: {ICONE_FOND}; border: 1px solid {ICONE_BORD}; border-radius: 8px;
}}
QFrame#carte QLabel {{ background: transparent; }}

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
QPushButton:focus {{
    border: 2px solid {AMBRE}; outline: none;
}}
QPushButton#bandeauBouton:focus, QPushButton#aide:focus {{
    border: 2px solid #f3d7a1;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {ACCENT};
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
    selection-background-color: {SELECTION}; selection-color: {TEXTE}; outline: 0;
}}
QAbstractSpinBox {{ padding-left: 8px; padding-right: 26px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border; width: 22px; border: none; background: {CARTE};
}}
QAbstractSpinBox::up-button {{
    subcontrol-position: top right; top: 1px; right: 1px; height: 14px; border-top-right-radius: 6px;
}}
QAbstractSpinBox::down-button {{
    subcontrol-position: bottom right; bottom: 1px; right: 1px; height: 14px; border-bottom-right-radius: 6px;
}}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
    background: {SPIN_SURVOL};
}}
QAbstractSpinBox::up-arrow {{ image: url("{up}"); width: 12px; height: 12px; }}
QAbstractSpinBox::down-arrow {{ image: url("{down}"); width: 12px; height: 12px; }}

QCheckBox, QRadioButton {{ spacing: 8px; font-size: 12.5pt; }}
QCheckBox {{ spacing: 10px; padding: 2px 0; }}
QCheckBox::indicator {{ width: 40px; height: 22px; }}
QCheckBox::indicator:unchecked {{ image: url("{_icon(f"switch-off{INTERRUPTEURS}.svg")}"); }}
QCheckBox::indicator:checked {{ image: url("{_icon(f"switch-on{INTERRUPTEURS}.svg")}"); }}
QCheckBox::indicator:unchecked:disabled {{ image: url("{_icon(f"switch-off-off{INTERRUPTEURS}.svg")}"); }}
QCheckBox::indicator:checked:disabled {{ image: url("{_icon(f"switch-on-off{INTERRUPTEURS}.svg")}"); }}
QCheckBox:hover {{ color: {LIEN_SURVOL}; }}
QRadioButton::indicator {{ width: 20px; height: 20px; }}
QRadioButton::indicator:unchecked {{ image: url("{_icon("radio-off.svg")}"); }}
QRadioButton::indicator:checked {{ image: url("{_icon("radio-on.svg")}"); }}
QRadioButton::indicator:disabled {{ image: url("{_icon("radio-off-off.svg")}"); }}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {POIGNEE}; border-radius: 4px; min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: {POIGNEE_SURVOL}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {POIGNEE}; border-radius: 4px; min-width: 36px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QStatusBar {{ background: {CARTE}; border-top: 1px solid {BORD}; color: {TEXTE_DOUX}; }}
QPushButton#voyant {{
    border: none; background: transparent; color: {TEXTE_DOUX}; padding: 2px 6px;
    font-size: 11.5pt; border-radius: 6px;
}}
QPushButton#voyant:hover {{ color: {ACCENT}; background: {VOYANT_SURVOL}; }}
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
        (QPalette.ButtonText, TEXTE), (QPalette.Highlight, SELECTION),
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
        p.setBrush(QColor(PISTE))
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
        grad.setColorAt(0, QColor(BARRE_DEBUT))
        grad.setColorAt(1, QColor(BARRE_FIN))
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
