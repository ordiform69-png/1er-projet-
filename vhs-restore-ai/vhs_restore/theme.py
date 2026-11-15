"""Habillage de l'interface : couleurs, cartes, gros boutons lisibles.

Couleurs fixes (pas celles du thème Windows) pour garder un bon contraste, même si
Windows est en mode sombre. Textes grands, boutons hauts : pensé pour une personne
qui n'utilise pas souvent l'ordinateur."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#1f5fa8"        # bleu « archive »
ACCENT_FONCE = "#174a84"
VERT = "#2e7d4f"          # action principale : Restaurer
VERT_FONCE = "#256742"
FOND = "#eef2f6"
CARTE = "#ffffff"
BORD = "#d5dde6"
TEXTE = "#1d2633"
TEXTE_DOUX = "#556275"

QSS = f"""
QMainWindow, QWidget#page {{ background: {FOND}; }}
QWidget {{ color: {TEXTE}; }}
QScrollArea {{ border: none; background: {FOND}; }}

QFrame#bandeau {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_FONCE}, stop:1 {ACCENT});
    border-radius: 12px;
}}
QLabel#marque {{ color: #cfe0f5; font-size: 11pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#titre {{ color: white; font-size: 21pt; font-weight: 700; }}
QLabel#infos {{ color: {TEXTE}; font-size: 13pt; background: {CARTE}; border: 1px solid {BORD};
               border-radius: 10px; padding: 10px 14px; }}

QPushButton {{
    background: {CARTE}; border: 1px solid {BORD}; border-radius: 8px; padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; background: #f5f9fe; }}
QPushButton:pressed {{ background: #e3edf9; }}
QPushButton:disabled {{ color: #9aa5b3; background: #f3f5f8; border-color: #e1e6ec; }}
QPushButton#etape {{
    font-size: 15pt; font-weight: 600; min-height: 56px; border-radius: 12px;
    border: 2px solid {ACCENT}; color: {ACCENT_FONCE}; background: {CARTE};
}}
QPushButton#etape:hover {{ background: #eaf2fc; }}
QPushButton#etape:disabled {{ border-color: #c6d0dc; color: #9aa5b3; background: #f5f7fa; }}
QPushButton#principal {{
    font-size: 15pt; font-weight: 700; min-height: 56px; border-radius: 12px;
    border: none; color: white; background: {VERT};
}}
QPushButton#principal:hover {{ background: {VERT_FONCE}; }}
QPushButton#principal:disabled {{ background: #b9c8bf; color: #eef2ef; }}
QPushButton#lien {{ border: none; background: transparent; color: {ACCENT}; font-weight: 600;
                   padding: 6px 4px; }}
QPushButton#lien:hover {{ text-decoration: underline; }}

QGroupBox {{
    background: {CARTE}; border: 1px solid {BORD}; border-radius: 10px;
    margin-top: 14px; padding: 12px 10px 10px 10px; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {ACCENT_FONCE};
                    background: {FOND}; border-radius: 4px; }}
QGroupBox QLabel {{ font-weight: normal; }}

QProgressBar {{ background: #dfe6ee; border: none; border-radius: 9px; min-height: 18px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 9px; }}

QLineEdit {{ background: {CARTE}; border: 1px solid {BORD}; border-radius: 6px; padding: 4px 8px; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QPushButton#action {{ border: none; color: white; background: {VERT}; font-weight: 700; padding: 8px 18px; }}
QPushButton#action:hover {{ background: {VERT_FONCE}; }}
QPushButton#action:disabled {{ background: #b9c8bf; color: #eef2ef; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; }}
QLabel#statut {{ color: {TEXTE}; font-size: 13pt; }}
QLabel#note {{ color: {TEXTE_DOUX}; font-size: 11.5pt; }}
QStatusBar {{ background: {CARTE}; border-top: 1px solid {BORD}; color: {TEXTE_DOUX}; }}
QToolTip {{ background: {TEXTE}; color: white; border: none; padding: 6px; }}
"""


def apply(app: QApplication) -> None:
    """Palette claire fixe + feuille de style pour toute l'application."""
    pal = QPalette()
    for role, color in ((QPalette.Window, FOND), (QPalette.Base, CARTE), (QPalette.AlternateBase, FOND),
                        (QPalette.Text, TEXTE), (QPalette.WindowText, TEXTE), (QPalette.Button, CARTE),
                        (QPalette.ButtonText, TEXTE), (QPalette.Highlight, ACCENT),
                        (QPalette.HighlightedText, "#ffffff"), (QPalette.ToolTipBase, TEXTE),
                        (QPalette.ToolTipText, "#ffffff"), (QPalette.PlaceholderText, "#8a96a6")):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
