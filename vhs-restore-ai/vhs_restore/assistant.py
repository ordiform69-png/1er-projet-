"""Assistant pas à pas : une restauration réussie, une étape à la fois.

L'utilisateur (76 ans) ne peut pas « faire n'importe quoi » : une seule chose à faire par
écran, « ← Revenir » et « Suivant → », et « Lancer la restauration » n'est possible qu'après avoir vu
l'avant / après avec les réglages choisis. Les réglages par défaut sont sûrs : en cliquant
toujours sur « Suivant », on obtient déjà un bon résultat. « Réglages libres » ouvre l'écran
complet (les sections), pour le fils ou plus tard.

Film : 1. Choisir le rendu (liste verticale) · 2. Lumière et couleurs (la grande image
change tout de suite) · 3. Couper le film : début, fin et passages (neige, écran bleu ou noir trouvés
par le logiciel) · 4. Le son (la voix colle-t-elle aux lèvres ? au début et à la fin) ·
5. Vérifier et lancer. Photo : 1. Choisir le rendu · 2. Lumière et couleurs · 3. Vérifier et
lancer. Le moteur de restauration n'est pas modifié : l'assistant règle les mêmes commandes
que l'écran complet.
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QLayout, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

from . import estimation, lumiere, photo, pipeline, theme, vides
from .profiles import PROFILES, profile_for
from .tools import AAC, ToolError, ff_input, run, run_capture

RENDUS = ("fidele", "equilibre", "maximum")
# Sous-titre sous le nom. Le nom vient de profiles.py ; « equilibre » ajoute « (conseillé) ».
PHRASES_RENDU = {
    "original": "",
    "fidele": "Garde l'aspect d'époque",
    "equilibre": "Bon équilibre",
    "maximum": "Plus long",
}
# Petites images de l'étape 1 (4:3). L'original est un repère plus bas, pas un choix.
TAILLE_ORIGINAL = QSize(64, 48)
TAILLE_RENDU = QSize(96, 72)
# L'assistant s'ouvre d'office avec un film. Les tests de l'écran complet l'éteignent
# (tests/conftest.py) ; ceux de l'assistant le rallument (marque « assistant »).
PAR_DEFAUT = True
# Repères à gauche de la colonne. False : la même liste, sur une ligne de 30 px au-dessus du titre.
# Largeur 140 px (le plafond demandé est 150) : à 150, la fenêtre dépasse 1280 quand les images sont prêtes.
REPERES_VERTICAUX = True
LARGEUR_REPERES = 140
HAUTEUR_REPERES = 30
ECOUTE = 10.0                       # secondes écoutées au début et à la fin
PAS_SON = 40                        # ms : une image PAL


def hms(t: float) -> str:
    t = int(round(max(0.0, t)))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


# ---------------------------------------------------------------- calculs (testables sans fenêtre)
def son_depuis_debut_fin(d_debut: float, t_debut: float, d_fin: float, t_fin: float) -> tuple[float, float]:
    """Décalage (ms) et dérive (ms par minute) qui donnent d_debut à t_debut et d_fin à t_fin.

    Correction appliquée au temps t : décalage − dérive × t / 60 (voir pipeline.audio_filters :
    décalage > 0 retarde le son ; dérive > 0 l'accélère, donc l'avance peu à peu)."""
    if t_fin - t_debut < 1:
        return float(d_debut), 0.0
    derive = (d_debut - d_fin) * 60.0 / (t_fin - t_debut)
    decalage = d_debut + derive * t_debut / 60.0
    return round(decalage), round(derive)


def phrase_son(decalage: float, derive: float) -> str:
    """« son retardé de 40 ms, ralenti de 190 ms par minute » ; vide si rien n'est corrigé."""
    parts = []
    if abs(decalage) >= 1:
        parts.append(f"son {'retardé' if decalage > 0 else 'avancé'} de {abs(decalage):.0f} ms")
    if abs(derive) >= 1:
        parts.append(f"{'accéléré' if derive > 0 else 'ralenti'} de {abs(derive):.0f} ms par minute")
    return ", ".join(parts)


def suggestion_derive(ffprobe: str, chemin: Path) -> tuple[float, float] | None:
    """Dérive proposée (ms par minute) d'après la durée du son et de l'image, et l'écart (s).

    Un boîtier de numérisation dont l'horloge du son n'est pas celle de l'image donne un son plus
    long (ou plus court) que l'image : le son glisse peu à peu. Seulement pour les fichiers dont
    les durées viennent des horodatages (AVI, MKV, MP4, MOV) : celles d'un MPEG de DVD sont
    estimées. None : rien à proposer."""
    try:
        r = run_capture([ffprobe, "-v", "error", "-show_entries",
                         "format=format_name:stream=codec_type,duration:stream_tags=DURATION", "-of", "json",
                         str(chemin)], timeout=60)
        d = json.loads(r.stdout or "{}")
    except (ToolError, ValueError, OSError, subprocess.TimeoutExpired):
        return None
    if "mpeg" in d.get("format", {}).get("format_name", ""):
        return None
    durees = {}
    for st in d.get("streams", []):
        valeur = st.get("duration") or (st.get("tags") or {}).get("DURATION")   # MKV : dans les étiquettes
        try:
            if isinstance(valeur, str) and ":" in valeur:
                h, m, sec = valeur.split(":")
                valeur = int(h) * 3600 + int(m) * 60 + float(sec)
            durees.setdefault(st.get("codec_type"), float(valeur))
        except (TypeError, ValueError):
            continue
    v, a = durees.get("video"), durees.get("audio")
    if not v or not a or v < 60:
        return None
    ecart = a - v
    if abs(ecart) < 0.2 or abs(ecart) / v < 0.001:
        return None
    return round(ecart / v * 60000.0), ecart


def faire_rendus(info, base: pipeline.Settings, tools, dossier: Path, moment: float, est_photo: bool,
                 cancel: threading.Event | None = None, progress=None) -> dict[str, Path]:
    """Une image par rendu (et l'original), au même moment du film, pour choisir à l'œil.

    Quelques images avant celle montrée nourrissent les filtres qui regardent les images voisines.
    Aperçu rapide : sans IA, sans stabilisation ni réparations de bande (les mêmes pour tous)."""
    dossier.mkdir(parents=True, exist_ok=True)
    affichage = "scale='trunc(iw*sar/2)*2':ih,setsar=1,scale=480:-2"
    entree = ff_input(info.path) if est_photo else pipeline._seek(moment, None) + pipeline.dvd_input(info)
    sorties = {}
    for i, cle in enumerate(("original", *RENDUS)):
        if cancel is not None and cancel.is_set():
            from .tools import Cancelled
            raise Cancelled()
        if progress:
            progress(i / 4, "Préparation des images à comparer…")
        if cle == "original":
            chaine = affichage
        else:
            s = dataclasses.replace(base, profile=profile_for(cle, base.source), use_ai=False, stabilize=False,
                                    deinterlacer="bwdif", colorize=False)
            chaine = ",".join(photo.photo_chain(info, s)) if est_photo else pipeline.filter_chain(info, s)
            chaine = f"{chaine},{affichage}"
        out = dossier / f"{cle}.png"
        run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *entree, "-map", "0:v:0",
             "-vf", chaine, "-frames:v", "1" if est_photo else "13", "-update", "1", str(out)],
            cancel=cancel, what="FFmpeg (rendus à comparer)")
        sorties[cle] = out
    if progress:
        progress(1.0, "Images prêtes")
    return sorties


def faire_ecoute(info, tools, dossier: Path, moment: float, decalage_ms: float,
                 cancel: threading.Event | None = None) -> Path:
    """10 s du film d'origine, image et son, le son décalé de decalage_ms (> 0 : retardé)."""
    dossier.mkdir(parents=True, exist_ok=True)
    out = dossier / f"ecoute_{int(moment)}_{int(decalage_ms)}.mp4"
    debut_son = max(0.0, moment - decalage_ms / 1000.0)
    run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
         *pipeline._seek(moment, ECOUTE), *pipeline.dvd_input(info),
         *pipeline._seek(debut_son, ECOUTE), *pipeline.dvd_input(info),
         "-map", "0:v:0", "-map", "1:a:0", "-vf", "scale='trunc(iw*sar/2)*2':ih,setsar=1,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", *AAC, "-b:a", "128k",
         "-movflags", "+faststart", str(out)], cancel=cancel, what="FFmpeg (écouter)")
    return out


# ---------------------------------------------------------------- l'assistant
def _nom_etape(cle: str) -> str:
    """Nom affiché sur la ligne de l'étape 1. « equilibre » porte la mention conseillée."""
    nom = PROFILES[cle].name
    return f"{nom} (conseillé)" if cle == "equilibre" else nom


def _encre_sur(fond: QColor) -> QColor:
    """Encre lisible sur la pastille (clair ou sombre)."""
    lum = 0.2126 * fond.redF() + 0.7152 * fond.greenF() + 0.0722 * fond.blueF()
    return QColor("#102027" if lum > 0.55 else "#ffffff")


class TuileRendu(QToolButton):
    """Une ligne de l'étape 1. `text()` garde le nom et le sous-titre (les tests lisent les deux).

    L'image est celle posée par `setIcon` : la vraie image du rendu, pas un pictogramme.
    """

    def __init__(self, nom: str, phrase: str, *, original: bool) -> None:
        super().__init__()
        self._original = original
        self.setText(f"{nom}\n{phrase}" if phrase else nom)
        self.setAccessibleName(nom)
        self.setAccessibleDescription(phrase or nom)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAutoRaise(True)
        if original:
            self.setObjectName("tuileOriginal")
            self.setFocusPolicy(Qt.NoFocus)
            self.setIconSize(TAILLE_ORIGINAL)
            self.setMinimumHeight(TAILLE_ORIGINAL.height() + 8)  # ligne grise plus basse que les rendus
        else:
            self.setObjectName("tuileRendu")
            self.setCheckable(True)
            self.setCursor(Qt.PointingHandCursor)
            self.setFocusPolicy(Qt.StrongFocus)
            self.setIconSize(TAILLE_RENDU)
            self.setMinimumHeight(TAILLE_RENDU.height() + 6)
        self.setAttribute(Qt.WA_Hover, True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(280, self.minimumHeight())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, self.minimumHeight())

    def enterEvent(self, e) -> None:  # noqa: N802
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        r = self.rect().adjusted(1, 1, -2, -2)
        if self._original:
            p.setBrush(QColor(theme.FOND_DESACTIVE))
            p.setPen(QPen(QColor(theme.BORD_DESACTIVE), 1))
        elif on:
            p.setBrush(QColor(theme.TUILE_ACTIVE))
            p.setPen(QPen(QColor(theme.ACCENT), 4))
        else:
            p.setBrush(QColor(theme.CARTE))
            p.setPen(QPen(QColor(theme.ACCENT if self.underMouse() else theme.BORD), 1.5))
        p.drawRoundedRect(r, 8, 8)
        if self.hasFocus() and not self._original and not on:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(theme.ACCENT), 2, Qt.DashLine))
            p.drawRoundedRect(r.adjusted(3, 3, -3, -3), 6, 6)
        x = r.left() + 8
        if not self._original:
            centre = QPoint(x + 12, r.center().y())
            if on:
                accent = QColor(theme.ACCENT)
                p.setPen(Qt.NoPen)
                p.setBrush(accent)
                p.drawEllipse(centre, 11, 11)
                p.setPen(QPen(_encre_sur(accent), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                cx, cy = centre.x(), centre.y()
                p.drawLine(cx - 6, cy, cx - 2, cy + 5)
                p.drawLine(cx - 2, cy + 5, cx + 6, cy - 5)
            x += 30
        taille = TAILLE_ORIGINAL if self._original else TAILLE_RENDU
        cadre = QRect(x, r.center().y() - taille.height() // 2, taille.width(), taille.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.FOND_DESACTIVE))
        p.drawRoundedRect(cadre, 4, 4)
        src = self.icon().pixmap(taille * 2)
        if not src.isNull():
            image = src.scaled(taille, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(cadre.x() + (cadre.width() - image.width()) // 2,
                         cadre.y() + (cadre.height() - image.height()) // 2, image)
        lignes = self.text().split("\n", 1)
        nom, phrase = lignes[0], lignes[1] if len(lignes) > 1 else ""
        tx = cadre.right() + 12
        tw = max(40, r.right() - tx - 6)
        e = float(getattr(self.window(), "_echelle", 1.0) or 1.0)
        f = QFont(theme.BODY_FAMILY or p.font().family())
        f.setBold(True)
        f.setPointSizeF(max(11, 13 * e))
        p.setFont(f)
        p.setPen(QColor(theme.TEXTE_DOUX if self._original else theme.TEXTE))
        if self._original:
            p.drawText(QRect(tx, r.top(), tw, r.height()),
                       Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, nom)
            return
        haut_nom = p.fontMetrics().boundingRect(QRect(0, 0, tw, 80), Qt.TextWordWrap, nom).height()
        p.drawText(QRect(tx, r.top() + 6, tw, haut_nom), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, nom)
        if phrase:
            f.setBold(False)
            f.setPointSizeF(max(10, 11 * e))
            p.setFont(f)
            p.setPen(QColor(theme.TEXTE_DOUX))
            p.drawText(QRect(tx, r.top() + 8 + haut_nom, tw, r.height() - haut_nom - 12),
                       Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, phrase)


def _bouton(texte: str, nom: str = "secondaire", haut: int = 48) -> QPushButton:
    b = QPushButton(texte)
    b.setObjectName(nom)
    b.setMinimumHeight(haut)
    b.setCursor(Qt.PointingHandCursor)
    return b


def _texte(texte: str = "", nom: str = "") -> QLabel:
    lab = QLabel(texte)
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.PlainText)
    lab.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    if nom:
        lab.setObjectName(nom)
    return lab


class _Repere(QPushButton):
    """Une étape : rond numéroté, coche si elle est faite, rond plein si elle est en cours."""

    def __init__(self, vertical: bool) -> None:
        super().__init__()
        self._vertical = vertical
        self._etat = "suite"
        self._numero = 1
        self._nom = ""
        self.setObjectName("repere")
        self.setFlat(True)
        self.setCursor(Qt.ArrowCursor)
        self.setStyleSheet(
            "QPushButton#repere {background: transparent; border: none; padding: 0; text-align: left;}")
        if vertical:
            self.setMinimumHeight(42)
            self.setMaximumHeight(48)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            self.setFixedHeight(HAUTEUR_REPERES)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def regler(self, numero: int, nom: str, etat: str) -> None:
        self._numero = numero
        self._nom = nom
        self._etat = etat
        self.setEnabled(etat != "suite")
        self.setCursor(Qt.PointingHandCursor if etat == "fait" else Qt.ArrowCursor)
        self.setFocusPolicy(Qt.TabFocus if etat == "fait" else Qt.NoFocus)
        etat_lu = {"fait": "faite", "cours": "en cours", "suite": "à venir"}[etat]
        self.setAccessibleName(f"Étape {numero}, {nom}, {etat_lu}")
        self.setText(f"{'✓' if etat == 'fait' else '●' if etat == 'cours' else numero} {nom}")
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        if self._vertical:
            return QSize(LARGEUR_REPERES, 44)
        return QSize(110, HAUTEUR_REPERES)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 42 if self._vertical else HAUTEUR_REPERES)

    def enterEvent(self, e) -> None:  # noqa: N802
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._etat == "cours":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.TUILE_ACTIVE))
            p.drawRoundedRect(self.rect().adjusted(0, 1, -1, -1), 8, 8)
        elif self._etat == "fait" and self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.SURVOL))
            p.drawRoundedRect(self.rect().adjusted(0, 1, -1, -1), 8, 8)
        if self.hasFocus() and self._etat == "fait":
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 8, 8)
        d = 26 if self._vertical else 18
        cy = max(0, (self.height() - d) // 2)
        rond = QRect(4 if self._vertical else 2, cy, d, d)
        if self._etat == "suite":
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(theme.TEXTE_DESACTIVE), 2))
            p.drawEllipse(rond)
            self._ecrire(p, rond, str(self._numero), theme.TEXTE_DESACTIVE, 8 if self._vertical else 7)
            couleur_nom, gras = theme.TEXTE_DESACTIVE, False
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.VERT))
            p.drawEllipse(rond)
            if self._etat == "fait":
                self._coche(p, rond)
            else:
                self._ecrire(p, rond, str(self._numero), theme.VERT_TEXTE, 9 if self._vertical else 7)
            couleur_nom, gras = theme.TEXTE, self._etat == "cours"
        font = QFont(self.font())
        if not self._vertical:
            font.setPointSizeF(min(font.pointSizeF() or 9, 9))
        font.setBold(gras)
        p.setFont(font)
        x = rond.right() + (8 if self._vertical else 4)
        zone = QRect(x, 0, max(0, self.width() - x - 2), self.height())
        p.setPen(QColor(couleur_nom))
        p.drawText(zone, Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(font).elidedText(self._nom, Qt.ElideRight, zone.width()))
        p.end()

    def _ecrire(self, p: QPainter, rect: QRect, texte: str, couleur: str, pt: float) -> None:
        p.setPen(QColor(couleur))
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(pt)
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter, texte)

    def _coche(self, p: QPainter, rect: QRect) -> None:
        p.setPen(QPen(QColor(theme.VERT_TEXTE), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        c = rect.center()
        k = 1.0 if self._vertical else 0.7
        p.drawLine(int(c.x() - 6 * k), int(c.y()), int(c.x() - 1 * k), int(c.y() + 5 * k))
        p.drawLine(int(c.x() - 1 * k), int(c.y() + 5 * k), int(c.x() + 6 * k), int(c.y() - 5 * k))


class _Resume(QLabel):
    """Résumé enrichi de « Vérifier et lancer ».

    text() reste la lecture simple (mêmes phrases que l'écran, sans les balises) :
    les tests et un lecteur d'écran y retrouvent « Lumière et couleurs : comme proposé. ».
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWordWrap(True)
        self.setTextFormat(Qt.RichText)
        self.setObjectName("resumeAssistant")
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._lecture = ""

    def definir(self, html: str, lecture: str) -> None:
        self._lecture = lecture
        self.setText(html)
        self.setAccessibleDescription(lecture)

    def text(self) -> str:  # noqa: A003
        return self._lecture


class _Pile(QStackedWidget):
    """La taille de l'étape affichée seulement. Une pile ordinaire prend la plus large et la plus
    haute de ses pages : « Lumière et couleurs » imposait sa largeur et sa hauteur à toutes les
    étapes (fenêtre élargie après l'avant / après, défilement des coupes et du son à 125 %)."""

    def __init__(self) -> None:
        super().__init__()
        self.layout().setSizeConstraint(QLayout.SetNoConstraint)
        self.currentChanged.connect(lambda _i: self.updateGeometry())

    def sizeHint(self) -> QSize:  # noqa: N802
        p = self.currentWidget()
        return p.sizeHint() if p is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        p = self.currentWidget()
        return p.minimumSizeHint() if p is not None else super().minimumSizeHint()

    def heightForWidth(self, largeur: int) -> int:  # noqa: N802
        # la pile de Qt prend la plus haute de toutes ses pages pour cette largeur
        p = self.currentWidget()
        if p is None:
            return super().heightForWidth(largeur)
        h = p.heightForWidth(largeur)
        return h if h >= 0 else p.minimumSizeHint().height()


class _ZonePages(QScrollArea):
    """Les étapes défilent ici si elles dépassent : la fenêtre, elle, ne grandit pas."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pagesAssistant")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(0)

    def _largeur(self) -> int:
        """Largeur demandée par les étapes. La hauteur, non : la fenêtre ne s'allonge pas."""
        wd = self.widget()
        if wd is None:
            return 0
        return max(wd.minimumSizeHint().width(), wd.sizeHint().width())

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._largeur(), 0)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        wd = self.widget()
        return QSize(wd.minimumSizeHint().width() if wd is not None else 0, 0)

    def resizeEvent(self, e) -> None:  # noqa: N802
        """Coupe le débordement horizontal (barre verticale qui rétrécit la vue, à 150 %)."""
        super().resizeEvent(e)
        wd = self.widget()
        if wd is not None:
            wd.setMaximumWidth(max(0, self.viewport().width()))


class Assistant(QWidget):
    def __init__(self, w) -> None:
        super().__init__()
        self.w = w
        self.actif = PAR_DEFAUT
        self._info = None
        self._apercu = None             # l'aperçu vu (objet) et les réglages de cet aperçu
        self._sig_apercu = None
        self._rendus: dict[str, Path] = {}
        # travaux de fond (images du rendu, proposition de dérive) : fils démons, comme les petites
        # images de la timeline. Ils n'occupent pas le travail principal : « Voir l'avant / après »
        # reste possible tout de suite. Un minuteur relève les résultats dans le fil de l'écran.
        self._generation = 0
        self._annuler_fond = threading.Event()
        self._verrou = threading.Lock()
        self._fond: list[tuple[int, str, object]] = []
        self._en_cours = 0
        self._minuterie = QTimer(self)
        self._minuterie.setInterval(100)
        self._minuterie.timeout.connect(self._pomper)
        self._reperes_verticaux = REPERES_VERTICAUX
        self.reperes = QWidget()
        self.reperes.setObjectName("colonneReperes")
        self._boutons_reperes: list[_Repere] = []
        if self._reperes_verticaux:
            self.reperes.setFixedWidth(LARGEUR_REPERES)
            self._reperes_lay = QVBoxLayout(self.reperes)
            cadre = QHBoxLayout(self)
        else:
            self.reperes.setFixedHeight(HAUTEUR_REPERES)
            self._reperes_lay = QHBoxLayout(self.reperes)
            cadre = QVBoxLayout(self)
        self._reperes_lay.setContentsMargins(0, 0, 0, 0)
        self._reperes_lay.setSpacing(2 if not self._reperes_verticaux else 4)
        cadre.setContentsMargins(2, 2, 2, 2)
        cadre.setSpacing(6)
        if self._reperes_verticaux:
            cadre.addWidget(self.reperes)
            lay = QVBoxLayout()
            lay.setSpacing(6)
            cadre.addLayout(lay, 1)
        else:
            cadre.addWidget(self.reperes)
            lay = cadre
        haut = QHBoxLayout()
        haut.setSpacing(10)
        self.compteur = QLabel()
        self.compteur.setObjectName("etapeAssistant")
        self.compteur.setWordWrap(False)
        self.titre = _texte(nom="titreAssistant")
        self.titre.setWordWrap(True)                 # à 150 % : sur deux lignes plutôt que coupé
        haut.addWidget(self.compteur)
        haut.addWidget(self.titre, 1)
        lay.addLayout(haut)
        # à côté de « Suivant → », sur la ligne des boutons : la phrase est près du bouton qu'elle
        # nomme, et la page garde une ligne de plus (aucun défilement à 125 %)
        self.rien_a_changer = _texte("Rien à changer ? Cliquez sur Suivant.", "rienAChanger")
        self.rien_a_changer.setWordWrap(True)
        self.rien_a_changer.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.rien_a_changer.setVisible(False)
        self.pages = _Pile()
        self.pages_zone = _ZonePages()
        self.pages_zone.setWidget(self.pages)
        lay.addWidget(self.pages_zone, 1)
        nav = QHBoxLayout()
        self.retour = _bouton("← Revenir")
        self.suivant = _bouton("Suivant →", "action", 60)
        # largeurs minimales modestes : la fenêtre doit tenir sur un écran de 1024 px de large
        self.retour.setMinimumWidth(120)
        self.suivant.setMinimumWidth(170)
        self.serrer(False)
        nav.addWidget(self.retour)
        nav.addStretch(0)              # grand écran : la place libre va ici, « Suivant » ne s'étire pas
        nav.addWidget(self.rien_a_changer, 1)
        nav.addWidget(self.suivant)
        lay.addLayout(nav)
        self.retour.clicked.connect(lambda: self.aller(self._etape() - 1))
        self.suivant.clicked.connect(lambda: self.aller(self._etape() + 1))
        self._page_rendu = self._construire_rendu()
        self._page_lumiere = lumiere.Panneau(w.lumiere, guide=True)
        self._page_coupe = self._construire_coupe()
        self._page_son = self._construire_son()
        self._page_fin = self._construire_fin()
        for p in (self._page_rendu, self._page_lumiere, self._page_coupe, self._page_son, self._page_fin):
            self.pages.addWidget(p)
        self._montrer_reperes(0)
        self.style_assistant()

    # ------------------------------------------------------------ étapes
    def serrer(self, serre: bool) -> None:
        """Écran bas (moins de 600 px utiles : 1366 × 768 à 125 %, 1920 × 1080 à 175 %) : boutons et
        petites images un peu plus bas, pour que chaque étape tienne sans défiler."""
        self.retour.setMinimumHeight(44 if serre else 52)
        self.suivant.setMinimumHeight(46 if serre else 60)
        for t in getattr(self, "tuiles", {}).values():
            taille = TAILLE_ORIGINAL if t.objectName() == "tuileOriginal" else TAILLE_RENDU
            if serre:
                taille = QSize(taille.width() * 2 // 3, taille.height() * 2 // 3)
            t.setIconSize(taille)
            t.setMinimumHeight(taille.height() + (8 if t.objectName() == "tuileOriginal" else 6))
            t.updateGeometry()

    def _construire_rendu(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        intro = _texte("Cliquez sur la ligne qui vous plaît.")
        intro.setObjectName("introRendu")
        v.addWidget(intro)
        liste = QVBoxLayout()
        liste.setSpacing(4)
        self.tuiles: dict[str, QToolButton] = {}
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        origine = TuileRendu("Votre cassette, sans changement", "", original=True)
        liste.addWidget(origine)
        self.tuiles["original"] = origine
        for cle in RENDUS:
            t = TuileRendu(_nom_etape(cle), PHRASES_RENDU.get(cle, ""), original=False)
            self._groupe.addButton(t)
            t.clicked.connect(lambda _c=False, k=cle: self._choisir_rendu(k))
            liste.addWidget(t)
            self.tuiles[cle] = t
        v.addLayout(liste)
        self.note_rendu = _texte()
        v.addWidget(self.note_rendu)
        self.grand = QPushButton("Voir ces images en grand")
        self.grand.setObjectName("lien")
        self.grand.setFlat(True)
        self.grand.setCursor(Qt.PointingHandCursor)
        self.grand.setAccessibleName("Voir ces images en grand")
        self.grand.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.grand.clicked.connect(self._voir_en_grand)
        v.addWidget(self.grand, 0, Qt.AlignLeft)
        v.addStretch(1)
        return page

    def _construire_coupe(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        ligne = QHBoxLayout()
        self.chercher = _bouton("Chercher la neige et les écrans vides")
        self.chercher.clicked.connect(self._chercher_vides)
        ligne.addWidget(self.chercher)
        self.note_coupe = _texte("Le logiciel trouve la neige, l'écran bleu ou noir du début, de la fin et "
                                 "entre deux scènes. Ces moments ne seront pas restaurés. Vous pouvez aussi "
                                 "passer cette étape.")
        ligne.addWidget(self.note_coupe, 1)
        v.addLayout(ligne)
        self._place_coupe = v
        return page

    def _construire_son(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.addWidget(_texte("La voix colle-t-elle aux lèvres ? Écoutez le début, puis la fin. "
                           "Si c'est juste, passez à la suite."))
        self.regler_son = _bouton("Le son est en retard ?")
        self.regler_son.setCheckable(True)
        self.regler_son.clicked.connect(self._montrer_reglage_son)
        v.addWidget(self.regler_son)
        self.aide_son = _texte("Si la voix arrive après les lèvres, « Voix trop tard ». "
                               "Si elle arrive avant, « Voix trop tôt ». Puis réécoutez.")
        self.aide_son.hide()
        v.addWidget(self.aide_son)
        self.rangs_son = {}
        self._reglages_son = []
        for cle in ("debut", "fin"):
            h = QHBoxLayout()
            lab = QLabel()
            lab.setMinimumWidth(150)
            ecouter = _bouton("Écouter")
            moins, plus = _bouton("Voix trop tard"), _bouton("Voix trop tôt")
            moins.setAccessibleName("Avancer le son")
            plus.setAccessibleName("Retarder le son")
            champ = QSpinBox()
            champ.setRange(-3000, 3000)
            champ.setSingleStep(PAS_SON)
            champ.setSuffix(" ms")
            champ.setMinimumHeight(48)
            champ.setAccessibleName("Décalage " + ("au début" if cle == "debut" else "à la fin"))
            champ.hide()                       # « ms » est du jargon : les boutons suffisent
            moins.clicked.connect(champ.stepDown)
            plus.clicked.connect(champ.stepUp)
            moins.hide()
            plus.hide()
            ecouter.clicked.connect(lambda _c=False, k=cle: self._ecouter(k))
            for wd in (lab, ecouter, moins, champ, plus):
                h.addWidget(wd)
            v.addLayout(h)
            self.rangs_son[cle] = (lab, ecouter, champ)
            self._reglages_son.extend((moins, plus))
        self.note_son = _texte()
        v.addWidget(self.note_son)
        self.appliquer_derive = _bouton("Appliquer la correction proposée")
        self.appliquer_derive.clicked.connect(self._appliquer_suggestion)
        self.appliquer_derive.hide()
        v.addWidget(self.appliquer_derive)
        v.addStretch(1)
        self._suggestion = None
        return page

    def _construire_fin(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.resume = _Resume()
        v.addWidget(self.resume)
        self.voir = _bouton("Voir l'avant / après", "action", 56)
        self.voir.clicked.connect(self.w.start_preview)
        v.addWidget(self.voir)
        self.consigne = _texte()
        self.consigne.setObjectName("consigneAssistant")
        v.addWidget(self.consigne)
        v.addStretch(1)
        return page

    def style_assistant(self) -> None:
        """Gros titres, Suivant vert, rendu choisi entouré ; suit le thème et la taille du texte."""
        e = float(getattr(self.w, "_echelle", 1.0) or 1.0)
        cle = (theme.ACCENT, theme.BORD, theme.CARTE, theme.TEXTE, theme.VERT, theme.VERT_TEXTE,
               theme.VERT_SURVOL, theme.VERT_PRESSE, theme.VERT_ETEINT, theme.VERT_ETEINT_TEXTE, e)
        if getattr(self, "_style_cle", None) != cle:
            self._style_cle = cle
            self.setStyleSheet(
                f"QLabel#etapeAssistant {{font-weight:700; color:{theme.ACCENT}; font-size:{16 * e:.0f}pt;}}"
                f"QLabel#titreAssistant {{font-weight:700; font-size:{16 * e:.0f}pt;}}"
                f"QLabel#rienAChanger {{font-weight:700; font-size:{12 * e:.0f}pt; color:{theme.TEXTE};}}"
                f"QLabel#consigneAssistant {{font-weight:normal;}}"
                f"QLabel#resumeAssistant {{font-size:{12 * e:.0f}pt;}}"
                f"QLabel#nomReglage, QLabel#valeurReglage {{font-weight:bold;}}"
                f"QPushButton#action {{color:{theme.VERT_TEXTE}; background:{theme.VERT};"
                f"font-size:{16 * e:.0f}pt; font-weight:700; border:none; border-radius:12px;"
                f"padding:8px 18px; min-height:56px;}}"
                f"QPushButton#action:hover {{background:{theme.VERT_SURVOL};}}"
                f"QPushButton#action:pressed {{background:{theme.VERT_PRESSE};}}"
                f"QPushButton#action:disabled {{background:{theme.VERT_ETEINT}; color:{theme.VERT_ETEINT_TEXTE};}}"
                f"QToolButton#tuileRendu, QToolButton#tuileOriginal {{border:2px solid {theme.BORD}; border-radius:8px;"
                f"background:{theme.CARTE}; font-size:{12 * e:.0f}pt; padding:4px;}}"
                f"QToolButton#tuileRendu:checked {{border:4px solid {theme.ACCENT}; font-weight:bold;}}")
        for b in self._boutons_reperes:
            b.update()

    # ------------------------------------------------------------ navigation
    def _film(self) -> bool:
        return not getattr(self.w, "is_photo", False)

    def _liste(self) -> list[tuple[str, QWidget]]:
        debut = [("Choisir le rendu", self._page_rendu), ("Lumière et couleurs", self._page_lumiere)]
        if not self._film():
            return debut + [("Vérifier et lancer", self._page_fin)]
        etapes = debut + [("Couper le film", self._page_coupe)]        # comme la section de l'écran complet
        if self.w.info is not None and self.w.info.has_audio:
            etapes.append(("Le son", self._page_son))
        return etapes + [("Vérifier et lancer", self._page_fin)]

    def _nom_court(self, page: QWidget) -> str:
        if page is self._page_rendu:
            return "Rendu"
        if page is self._page_lumiere:
            return "Lumière"
        if page is self._page_coupe:
            return "Coupes"
        if page is self._page_son:
            return "Son"
        return "Lancer"

    def _montrer_reperes(self, index: int) -> None:
        """Repères alignés sur la liste réelle (sans Son s'il n'y a pas d'audio, sans Coupes pour une photo)."""
        liste = self._liste()
        if len(self._boutons_reperes) != len(liste):
            while self._reperes_lay.count():
                item = self._reperes_lay.takeAt(0)
                wd = item.widget()
                if wd is not None:
                    wd.setParent(None)
                    wd.deleteLater()
            self._boutons_reperes = []
            for i, (_titre, page) in enumerate(liste):
                b = _Repere(self._reperes_verticaux)
                b.clicked.connect(lambda _c=False, n=i: self._clic_repere(n))
                self._reperes_lay.addWidget(b)
                self._boutons_reperes.append(b)
            if self._reperes_verticaux:
                self._reperes_lay.addStretch(1)
        for i, (_titre, page) in enumerate(liste):
            etat = "fait" if i < index else "cours" if i == index else "suite"
            self._boutons_reperes[i].regler(i + 1, self._nom_court(page), etat)

    def _clic_repere(self, i: int) -> None:
        """Une étape déjà faite ramène en arrière. L'étape en cours et la suite ne naviguent pas."""
        if i < self._etape():
            self.aller(i)

    def _en_fond(self, genre: str, travail) -> None:
        generation, annuler = self._generation, self._annuler_fond

        def corps() -> None:
            try:
                res = travail(annuler)
            except BaseException as exc:       # rapporté à l'écran, jamais perdu en silence
                res = exc
            with self._verrou:
                self._fond.append((generation, genre, res))
        self._en_cours += 1
        threading.Thread(target=corps, name=f"vhs-assistant-{genre}", daemon=True).start()
        self._minuterie.start()

    def _pomper(self) -> None:
        with self._verrou:
            arrives, self._fond = self._fond, []
        for generation, genre, res in arrives:
            self._en_cours -= 1
            if generation != self._generation:
                continue                          # résultat d'un film précédent
            if genre == "rendus":
                if isinstance(res, BaseException):
                    self.note_rendu.setText("Les images n'ont pas pu être préparées. Choisissez d'après les noms, "
                                            "ou passez à l'étape suivante : « Bien nettoyé, naturel » est conseillé.")
                else:
                    self._rendus_prets(res)
            elif genre == "suggestion":
                self._suggestion_trouvee(None if isinstance(res, BaseException) else res)
        if self._en_cours <= 0:
            self._en_cours = 0
            self._minuterie.stop()

    def arreter(self) -> None:
        """Fermeture ou nouveau film : les travaux de fond s'arrêtent (FFmpeg tué)."""
        self._annuler_fond.set()
        self._annuler_fond = threading.Event()
        self._generation += 1

    def demarrer(self) -> None:
        """Nouveau film ou nouvelle photo : on repart de la première étape."""
        self.arreter()
        self._info = self.w.info
        self._apercu, self._sig_apercu, self._rendus = None, None, {}
        self._suggestion = None
        for t in self.tuiles.values():
            t.setIcon(QIcon())
        cle = self.w.settings(with_advice=False).profile.key
        if cle in self.tuiles:
            self.tuiles[cle].setChecked(True)
        info = self.w.info
        duree = float(info.duration or 0) if info is not None else 0.0
        self._t_son = {"debut": min(30.0, max(0.0, duree * 0.05)),
                       "fin": max(0.0, duree - ECOUTE - 30.0) if duree > 3 * ECOUTE + 60 else duree * 0.6}
        for cle_son, (lab, _e, champ) in self.rangs_son.items():
            lab.setText(("Au début" if cle_son == "debut" else "À la fin") + f" ({hms(self._t_son[cle_son])})")
            champ.setValue(int(round(self.w.offset_spin.value())))
        self.appliquer_derive.hide()
        self.note_son.setText("")
        self.regler_son.setChecked(False)
        self._montrer_reglage_son()
        self.aller(0)

    def _etape(self) -> int:
        liste = self._liste()
        page = self.pages.currentWidget()
        return next((i for i, (_t, p) in enumerate(liste) if p is page), 0)

    def aller(self, i: int) -> None:
        liste = self._liste()
        actuelle = self.pages.currentWidget()
        if actuelle is self._page_son and i > self._etape():
            self._valider_son()
        i = max(0, min(i, len(liste) - 1))
        titre, page = liste[i]
        self._rendre_coupe()
        if page is self._page_coupe:
            self._emprunter_coupe()
        self.pages.setCurrentWidget(page)
        self.compteur.setText(f"Étape {i + 1} sur {len(liste)}")
        self.titre.setText(titre)
        self.rien_a_changer.setVisible(page in (self._page_lumiere, self._page_coupe, self._page_son))
        self.pages_zone.verticalScrollBar().setValue(0)
        self._montrer_reperes(i)
        self.retour.setVisible(i > 0)
        self.suivant.setVisible(i < len(liste) - 1)
        if not self.actif:                 # écran complet : rien à préparer pour l'assistant
            self.w._update_state()
            return
        if page is self._page_rendu and not self._rendus:
            self._lancer_rendus()
        if page is self._page_son and self._suggestion is None:
            self._chercher_suggestion()
        if page is self._page_fin:
            self._preparer_fin()
        self.w._update_state()

    # la section « Couper le film » de l'écran complet sert aussi ici : mêmes commandes
    def _extras_coupe(self):
        """Boutons utiles au fils, trop denses pour le parcours guidé."""
        w = self.w
        extras = list(getattr(w, "coupes_rapides", ()))
        for nom in ("bornes_coupe", "trim_tout", "chercher_neige_libre"):     # début / fin et « Ici » : écran complet seulement
            wd = getattr(w, nom, None)
            if wd is not None:
                extras.append(wd)
        return extras

    def _emprunter_coupe(self) -> None:
        zone = self.w.sections["Couper le film"][1]
        if zone.parent() is not self._page_coupe:
            self.w.options.layout().removeWidget(zone)
            self._place_coupe.addWidget(zone, 1)
        for wd in self._extras_coupe():
            wd.hide()
        self.chercher.setText("Chercher la neige…")
        self.note_coupe.setText("Vous pouvez passer cette étape. Ou le logiciel trouve la neige "
                                "et les écrans vides pour vous.")
        zone.show()

    def _rendre_coupe(self) -> None:
        zone = self.w.sections["Couper le film"][1]
        for wd in self._extras_coupe():
            wd.show()
        self.chercher.setText("Chercher la neige et les écrans vides")
        if zone.parent() is self._page_coupe:
            self._place_coupe.removeWidget(zone)
            lay = self.w.options.layout()
            bouton = self.w.sections["Couper le film"][0]
            lay.insertWidget(lay.indexOf(bouton) + 1, zone, 1)
            zone.setVisible(bouton.isChecked())

    def quitter(self) -> None:
        """« Réglages libres » : la section empruntée retourne à l'écran complet."""
        self._rendre_coupe()

    # ------------------------------------------------------------ 1. rendu
    def _lancer_rendus(self) -> None:
        w = self.w
        if w.info is None:
            return
        info, base = w.info, w.settings(with_advice=True)
        moment = float(w.start_spin.value()) or float(info.duration or 0) * 0.3
        dossier = w.preview_dir / f"rendus_{self._generation}"
        est_photo = not self._film()
        self._rendus = {"": Path()}             # en cours : pas de second lancement
        self.note_rendu.setText("Préparation des images à comparer (quelques secondes)…")
        self._en_fond("rendus", lambda annuler: faire_rendus(info, base, w.tools, dossier, moment, est_photo,
                                                              cancel=annuler))

    def _rendus_prets(self, sorties: dict[str, Path]) -> None:
        self._rendus = sorties
        for cle, chemin in sorties.items():
            tuile = self.tuiles.get(cle)
            if tuile is None:
                continue
            pix = QPixmap(str(chemin))
            if pix.isNull():
                continue
            tuile.setIcon(QIcon(pix))
            if cle == "original":
                tuile.setAccessibleDescription("Image d'origine de votre cassette, sans changement.")
            else:
                tuile.setAccessibleDescription(f"Aperçu réel du rendu {PROFILES[cle].name}.")
        conseil = PROFILES["equilibre"].name
        self.note_rendu.setText("Le rendu entouré sera utilisé. "
                                f"« {conseil} » est conseillé si vous hésitez.")

    def _choisir_rendu(self, cle: str) -> None:
        bouton = self.w.profile_buttons.get(cle)
        if bouton is not None and not bouton.isChecked():
            bouton.click()
        self.note_rendu.setText(f"Rendu choisi : {PROFILES[cle].name}.")

    def _voir_en_grand(self) -> None:
        if self._rendus and "" not in self._rendus:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(next(iter(self._rendus.values())).parent)))

    # ------------------------------------------------------------ 2. coupes
    def _chercher_vides(self) -> None:
        w = self.w
        info = w.info
        if info is None or w._busy():
            return
        if len(getattr(info, "parts", ()) or ()) > 1:
            self.note_coupe.setText("Ce DVD est en plusieurs morceaux : réglez le début et la fin sur la barre.")
            return
        ffmpeg = w.tools.ffmpeg.path
        self.note_coupe.setText("Recherche en cours : le film est lu en entier, cela peut prendre quelques "
                                "minutes.")
        w._launch(lambda c, p: vides.detecter_tout(ffmpeg, info.path, info.duration, cancel=c, progress=p),
                  self._vides_trouves)

    def _vides_trouves(self, res) -> None:
        passages, _duree = res
        self.w._proposer_passages_vides(passages)
        if self.w.barre.passage_vide is not None:
            phrase = "Cliquez sur une zone bleue pour choisir son passage."
        elif passages:
            phrase = "Les passages détectés sont déjà hors de la copie."
        else:
            phrase = "Aucune neige ni écran vide trouvé."
        self.w.status.setText(phrase)
        self.note_coupe.setText(phrase)

    # ------------------------------------------------------------ 3. son
    def _montrer_reglage_son(self) -> None:
        """Le décalage reste caché : la plupart des cassettes n'en ont pas besoin."""
        montre = self.regler_son.isChecked()
        self.aide_son.setVisible(montre)
        for b in self._reglages_son:
            b.setVisible(montre)

    def _ecouter(self, cle: str) -> None:
        w = self.w
        if w.info is None or w._busy():
            return
        info, moment = w.info, self._t_son[cle]
        decalage = self.rangs_son[cle][2].value()
        dossier = w.preview_dir / "ecoute"
        self.note_son.setText("Préparation des 10 secondes…")
        w._launch(lambda c, p: faire_ecoute(info, w.tools, dossier, moment, decalage, cancel=c), self._ecoute_prete)

    def _ecoute_prete(self, chemin: Path) -> None:
        self.note_son.setText("Regardez les lèvres et écoutez la voix. Ajustez, puis réécoutez.")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(chemin)))

    def _chercher_suggestion(self) -> None:
        w = self.w
        info = w.info
        if info is None or len(getattr(info, "parts", ()) or ()) > 1:
            return
        ffprobe = w.tools.ffprobe.path
        self._suggestion = False
        self._en_fond("suggestion", lambda _annuler: suggestion_derive(ffprobe, info.path))

    def _suggestion_trouvee(self, res) -> None:
        self._suggestion = res or False
        if not res:
            return
        derive, ecart = res
        self.note_son.setText(
            f"Le son et l'image n'ont pas la même durée ({abs(ecart):.1f} s d'écart) : le son glisse sans "
            f"doute de {abs(derive):.0f} ms par minute. Le logiciel peut le corriger : cliquez sur « Appliquer "
            "la correction proposée », puis écoutez la fin.")
        self.appliquer_derive.show()

    def _appliquer_suggestion(self) -> None:
        if not self._suggestion:
            return
        derive, _ecart = self._suggestion
        d_debut = self.rangs_son["debut"][2].value()
        duree = self._t_son["fin"] - self._t_son["debut"]
        self.rangs_son["fin"][2].setValue(int(round(d_debut - derive * duree / 60.0)))
        self.appliquer_derive.hide()
        self.note_son.setText("Correction proposée appliquée à la fin. Écoutez la fin pour vérifier.")

    def _valider_son(self) -> None:
        d1 = self.rangs_son["debut"][2].value()
        d2 = self.rangs_son["fin"][2].value()
        decalage, derive = son_depuis_debut_fin(d1, self._t_son["debut"], d2, self._t_son["fin"])
        self.w.offset_spin.setValue(decalage)
        self.w.drift_spin.setValue(derive)

    # ------------------------------------------------------------ 4. vérifier et lancer
    def _signature(self) -> str:
        return repr(dataclasses.astuple(self.w.settings(with_advice=True)))

    def apercu_vu(self) -> bool:
        return self.w.preview is not None and self._sig_apercu == self._signature()

    def _preparer_fin(self) -> None:
        self.actualiser()

    def _ecrire_resume(self) -> None:
        """Lignes (libellé en gras), puis un trait, puis la durée et la place une seule fois."""
        import html

        w = self.w
        s = w.settings(with_advice=True)
        lecture: list[str] = []
        lignes: list[str] = []

        def ligne(libelle: str, valeur: str) -> None:
            lecture.append(f"{libelle} {valeur}")
            lignes.append(f"<b>{html.escape(libelle)}</b> {html.escape(valeur)}")

        ligne("Rendu :", f"{s.profile.name}.")
        ligne("Lumière et couleurs :", (lumiere.phrase(w.lumiere.reglages()) or "comme proposé") + ".")
        if self._film():
            morceaux = []
            if w.trim_start.value():
                morceaux.append(f"début à {hms(w.trim_start.value())}")
            if w.trim_end.value():
                morceaux.append(f"fin à {hms(w.trim_end.value())}")
            n = len(w._coupes)
            if n == 1:
                morceaux.append("1 passage au milieu")
            elif n > 1:
                morceaux.append(f"{n} passages au milieu")
            ligne("Passages enlevés :", (", ".join(morceaux) if morceaux else "aucun") + ".")
            if w.info is not None and w.info.has_audio:
                son = "nettoyé" if s.restore_audio else "gardé tel quel"
                detail = phrase_son(s.audio_offset_ms, s.audio_drift_ms_per_min)
                if detail:
                    son += ", " + detail
                ligne("Son :", son + ".")

        bas_lecture: list[str] = []
        bas: list[str] = []
        rouge = "#ff8a80" if theme.MODE == "sombre" else "#a40000"

        def annonce(texte: str, alerte: bool = False) -> None:
            bas_lecture.append(texte)
            style = "font-size:115%; font-weight:bold;"
            if alerte:
                style += f" color:{rouge};"
            bas.append(f'<span style="{style}">{html.escape(texte)}</span>')

        if not self.apercu_vu():
            annonce("La durée s'affichera après l'avant / après.")
        else:
            obtenu = estimation.lignes(w)
            if obtenu:
                temps, place = obtenu
                if place.startswith("Il manque"):
                    annonce(place, alerte=True)
                    annonce(temps)
                else:
                    annonce(temps)
                    if place:
                        annonce(place)

        html_texte = "<br>".join(lignes)
        if bas:
            html_texte += "<hr>" + "<br>".join(bas)
        self.resume.definir(html_texte, " ".join(lecture + bas_lecture))

    def actualiser(self) -> None:
        """Appelé à chaque mise à jour de l'écran : l'aperçu vu, et ce qu'il reste à faire."""
        w = self.w
        if w.preview is not None and w.preview is not self._apercu:
            self._apercu, self._sig_apercu = w.preview, self._signature()
        if self.pages.currentWidget() is not self._page_fin:
            return
        if self.apercu_vu():
            self.voir.setText("Revoir l'avant / après")
            self.voir.setObjectName("secondaire")
            self.voir.setMinimumHeight(44)
            self.consigne.setText("Si le résultat vous plaît : « Lancer la restauration », en bas à droite.")
        else:
            self.voir.setText("Voir l'avant / après")
            self.voir.setObjectName("action")
            self.voir.setMinimumHeight(56)
            self.consigne.setText("Regardez d'abord l'avant / après. « Lancer la restauration » s'allume ensuite.")
        self.voir.style().unpolish(self.voir)
        self.voir.style().polish(self.voir)
        self._ecrire_resume()

    def peut_lancer(self) -> bool:
        return self.pages.currentWidget() is self._page_fin and self.apercu_vu()

    def phrase_attente(self) -> str:
        """Pourquoi « Lancer » est éteint, à côté du bouton."""
        if self.pages.currentWidget() is self._page_fin:
            return "Regardez d'abord l'avant / après."
        return "Pas encore. Terminez les étapes."


__all__ = ["Assistant", "faire_ecoute", "faire_rendus", "phrase_son", "son_depuis_debut_fin", "suggestion_derive"]
