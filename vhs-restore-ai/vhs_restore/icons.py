"""Icônes de l'interface : traits néon, dessinées ici (SVG 24×24), sans fichier externe.

Chaque icône est un fragment SVG tracé au trait (« currentColor » est remplacé par la couleur
demandée). Rendu net à toutes les échelles Windows (100 %, 125 %, 150 %) : l'image est
dessinée à la taille réelle de l'écran. Si le module QtSvg manque, l'icône est simplement vide.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap

from . import theme

# Fragments SVG (viewBox 0 0 24 24, trait 1,8 px, bouts arrondis).
PATHS: dict[str, str] = {
    # étapes et actions
    "dossier": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "pile": '<path d="M3 9a2 2 0 0 1 2-2h3l2 2h7a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
            '<path d="M7 4h3l2 2h7a2 2 0 0 1 2 2v7"/>',
    "oeil": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "etincelle": '<path d="M11 3l1.8 5.2L18 10l-5.2 1.8L11 17l-1.8-5.2L4 10l5.2-1.8z"/>'
                 '<path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z"/>',
    "jouer": '<path d="M7 4l13 8-13 8z"/>',
    "casque": '<path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="3" y="14" width="4" height="7" rx="1.5"/>'
              '<rect x="17" y="14" width="4" height="7" rx="1.5"/>',
    "stop": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "diagnostic": '<path d="M2 12h4l2.5-6 4 12 2.5-6h7"/>',
    "retour": '<path d="M15 5l-7 7 7 7"/>',
    "reglages": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/>'
                '<circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "export": '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    "comparer": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>'
                '<path d="M7.5 9.5L5.5 12l2 2.5M16.5 9.5l2 2.5-2 2.5"/>',
    "ciseaux": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.5 7.8L20 18M8.5 16.2L20 6"/>',
    "conseil": '<path d="M9 18h6M10 21h4"/>'
               '<path d="M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z"/>',
    # sections
    "film": '<rect x="3" y="3" width="18" height="18" rx="2"/>'
            '<path d="M7 3v18M17 3v18M3 8h4M3 12h4M3 16h4M17 8h4M17 12h4M17 16h4"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.2"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/>'
             '<path d="M21 16l-5-5-9 9"/>',
    "onde": '<path d="M2 12h3l2-6 3 12 3-9 2 5 2-2h5"/>',
    # profils
    "bouclier": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "balance": '<path d="M12 4v16M8 20h8M5 7h14"/><path d="M5 7l-3 6a3 3 0 0 0 6 0z"/>'
               '<path d="M19 7l-3 6a3 3 0 0 0 6 0z"/>',
    "fusee": '<path d="M12 2c3 2.2 5 6 5 10l-1.8 4H8.8L7 12c0-4 2-7.8 5-10z"/><circle cx="12" cy="9.5" r="1.8"/>'
             '<path d="M8.8 16L7 20.5l3-1.2M15.2 16l1.8 4.5-3-1.2M12 19v3"/>',
    # image
    "ecran": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "trames": '<path d="M4 6h16M4 14h16"/><path d="M4 10h16M4 18h16" stroke-dasharray="2 3"/>',
    "poussiere": '<circle cx="7" cy="7" r="1.4"/><circle cx="16.5" cy="5.5" r="1"/><circle cx="12" cy="12.5" r="1.7"/>'
                 '<circle cx="5.5" cy="17" r="1"/><circle cx="18" cy="15" r="1.3"/><path d="M14 21l7-7"/>',
    "bande": '<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="8" cy="11.5" r="2.5"/>'
             '<circle cx="16" cy="11.5" r="2.5"/><path d="M8 9h8M6 19l2-3h8l2 3"/>',
    "arc": '<path d="M3 18a9 9 0 0 1 18 0"/><path d="M6.5 18a5.5 5.5 0 0 1 11 0"/><path d="M10 18a2 2 0 0 1 4 0"/>',
    "eclat": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8'
             'M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
    "soleil": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4'
              'M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "lisse": '<path d="M3 8.5c1.5-2.5 2.5 2.5 4 0s2.5 2.5 4 0 2.5 2.5 4 0 2.5 2.5 4 0 1.5 0 2 0"/>'
             '<path d="M3 16.5h18"/><path d="M12 11v3"/>',
    "viseur": '<circle cx="12" cy="12" r="7"/><path d="M12 2v5M12 17v5M2 12h5M17 12h5"/>'
              '<circle cx="12" cy="12" r="1.4"/>',
    "bande_bas": '<rect x="3" y="4" width="18" height="16" rx="2"/>'
                 '<rect x="5" y="15" width="14" height="3" rx="1" fill="currentColor" stroke="none"/>',
    "cadre": '<rect x="3" y="4" width="18" height="16" rx="2"/><rect x="7" y="8" width="10" height="8" rx="1"/>',
    "decalage": '<rect x="3" y="6" width="12" height="12" rx="2"/>'
                '<rect x="9" y="6" width="12" height="12" rx="2" stroke-dasharray="3 2"/>',
    "goutte": '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/><path d="M9.5 14.5a2.5 2.5 0 0 0 2.5 2.5"/>',
    "puce": '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="10" y="10" width="4" height="4"/>'
            '<path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.5 0 2-1 2-2s-1-1.5-1-2.5 1-1.5 2-1.5h2a4 4 0 0 0 4-4'
               'c0-4.5-4-8-9-8z"/><circle cx="7.5" cy="11" r="1.2"/><circle cx="10" cy="7" r="1.2"/>'
               '<circle cx="15" cy="7.5" r="1.2"/>',
    "format": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9v6M18 9v6M9 12h6"/>',
    "cadence": '<path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l4-5"/><circle cx="12" cy="17" r="1.2"/>',
    # son
    "haut_parleur": '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/>',
    "micro": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/>',
    "vent": '<path d="M3 8h11a3 3 0 1 0-3-3"/><path d="M3 12h16a3 3 0 1 1-3 3"/><path d="M3 16h7"/>',
    "egaliseur": '<path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/>',
    "horloge": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "derive": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "prise": '<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0z"/><path d="M12 17v5"/>',
    "fichier_son": '<path d="M6 2h8l4 4v16H6z"/><path d="M14 2v4h4"/><circle cx="10.5" cy="17" r="1.8"/>'
                   '<path d="M12.3 17v-6.5l3 1"/>',
    "canaux": '<circle cx="8.5" cy="12" r="5"/><circle cx="15.5" cy="12" r="5"/>',
    "sature": '<path d="M2 12c1.5 0 2-6 3.5-6h4c1.5 0 2 12 3.5 12h4c1.5 0 2-6 3.5-6h1.5"/>',
}

SIZE = 22


def _svg(name: str, color: str) -> bytes:
    body = PATHS[name].replace("currentColor", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


def _ratio() -> float:
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app else None
    return max(1.0, screen.devicePixelRatio() if screen else 1.0, 2.0)


def pixmap(name: str, size: int = SIZE, color: str | None = None) -> QPixmap:
    """Image de l'icône (vide si le nom est inconnu ou si QtSvg manque). Couleur : l'accent
    de la palette en cours si rien n'est précisé."""
    return _pixmap(name, size, color or theme.ACCENT)


@lru_cache(maxsize=512)
def _pixmap(name: str, size: int, color: str) -> QPixmap:
    ratio = _ratio()
    img = QImage(int(size * ratio), int(size * ratio), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    if name in PATHS:
        try:
            from PySide6.QtSvg import QSvgRenderer
        except ImportError:      # module absent du paquet : pas d'icône, rien d'autre ne change
            QSvgRenderer = None  # noqa: N806
        if QSvgRenderer is not None:
            r = QSvgRenderer(QByteArray(_svg(name, color)))
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            r.render(p, QRectF(0, 0, img.width(), img.height()))
            p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str | None = None, size: int = SIZE) -> QIcon:
    """Icône avec un état désactivé grisé et un état survolé plus contrasté."""
    return _icon(name, color or theme.ACCENT, size)


@lru_cache(maxsize=256)
def _icon(name: str, color: str, size: int) -> QIcon:
    ic = QIcon()
    ic.addPixmap(_pixmap(name, size, color), QIcon.Normal)
    ic.addPixmap(_pixmap(name, size, theme.ICONE_ACTIVE if color == theme.ACCENT else color), QIcon.Active)
    ic.addPixmap(_pixmap(name, size, theme.ICONE_GRISE), QIcon.Disabled)
    return ic
