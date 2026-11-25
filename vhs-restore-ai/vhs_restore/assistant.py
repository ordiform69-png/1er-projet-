"""Assistant pas à pas : une restauration réussie, une étape à la fois.

L'utilisateur (76 ans) ne peut pas « faire n'importe quoi » : une seule chose à faire par
écran, « Retour » et « Suivant », et « Lancer la restauration » n'est possible qu'après avoir vu
l'avant / après avec les réglages choisis. Les réglages par défaut sont sûrs : en cliquant
toujours sur « Suivant », on obtient déjà un bon résultat. « Réglages libres » ouvre l'écran
complet (les sections), pour le fils ou plus tard.

Film : 1. Choisir le rendu (trois images côte à côte) · 2. Début, fin et passages à enlever
(neige, écran bleu ou noir trouvés par le logiciel) · 3. Le son (la voix colle-t-elle aux
lèvres ? au début et à la fin) · 4. Vérifier et lancer. Photo : 1. Choisir le rendu · 2. Vérifier
et lancer. Le moteur de restauration n'est pas modifié : l'assistant règle les mêmes commandes
que l'écran complet.
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QSize, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QSpinBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from . import photo, pipeline, scenes, theme, vides
from .profiles import PROFILES, profile_for
from .tools import AAC, ToolError, ff_input, run, run_capture

RENDUS = ("fidele", "equilibre", "maximum")
# Une phrase sous chaque image : les noms seuls (« Fidèle », « Équilibré ») ne disent rien.
PHRASES_RENDU = {
    "original": "Tel qu'il est",
    "fidele": "Garde l'aspect d'origine",
    "equilibre": "Conseillé",
    "maximum": "Le plus beau, plus long",
}
# L'assistant s'ouvre d'office avec un film. Les tests de l'écran complet l'éteignent
# (tests/conftest.py) ; ceux de l'assistant le rallument (marque « assistant »).
PAR_DEFAUT = True
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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(6)
        haut = QHBoxLayout()
        self.compteur = QLabel()
        self.compteur.setObjectName("etapeAssistant")
        self.titre = _texte(nom="titreAssistant")
        haut.addWidget(self.compteur)
        haut.addWidget(self.titre, 1)
        lay.addLayout(haut)
        self.pages = QStackedWidget()
        lay.addWidget(self.pages, 1)
        nav = QHBoxLayout()
        self.retour = _bouton("Retour")
        self.suivant = _bouton("Suivant", "action")
        for b in (self.retour, self.suivant):
            b.setMinimumWidth(170)
            b.setMinimumHeight(52)
        nav.addWidget(self.retour)
        nav.addStretch(1)
        nav.addWidget(self.suivant)
        lay.addLayout(nav)
        self.retour.clicked.connect(lambda: self.aller(self.pages.currentIndex() - 1))
        self.suivant.clicked.connect(lambda: self.aller(self.pages.currentIndex() + 1))
        self._page_rendu = self._construire_rendu()
        self._page_coupe = self._construire_coupe()
        self._page_son = self._construire_son()
        self._page_fin = self._construire_fin()
        for p in (self._page_rendu, self._page_coupe, self._page_son, self._page_fin):
            self.pages.addWidget(p)

    # ------------------------------------------------------------ étapes
    def _construire_rendu(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(_texte("Quel résultat préférez-vous ? Cliquez sur l'image qui vous plaît. "
                           "Si vous hésitez, prenez « Équilibré »."))
        grille = QGridLayout()
        grille.setSpacing(8)
        self.tuiles: dict[str, QToolButton] = {}
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        for col, cle in enumerate(("original", *RENDUS)):
            t = QToolButton()
            t.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            t.setIconSize(QSize(160, 120))
            t.setMinimumSize(150, 170)
            t.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            t.setObjectName("tuileRendu")
            nom = "Aujourd'hui" if cle == "original" else PROFILES[cle].name
            phrase = PHRASES_RENDU.get(cle, "")
            t.setText(f"{nom}\n{phrase}" if phrase else nom)
            t.setAccessibleName(nom)
            if cle != "original":
                t.setCheckable(True)
                t.setCursor(Qt.PointingHandCursor)
                self._groupe.addButton(t)
                t.clicked.connect(lambda _c=False, k=cle: self._choisir_rendu(k))
            else:                       # repère seulement ; désactivée, l'image serait grisée
                t.setFocusPolicy(Qt.NoFocus)
                t.setObjectName("tuileOriginal")
            grille.addWidget(t, 0, col)
            self.tuiles[cle] = t
        v.addLayout(grille)
        self.note_rendu = _texte()
        v.addWidget(self.note_rendu)
        self.grand = _bouton("Voir ces images en grand")
        self.grand.clicked.connect(self._voir_en_grand)
        v.addWidget(self.grand)
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
        self.trouver = _bouton("Trouver les changements")
        self.trouver.setToolTip("Repère où l'image change nettement. Rien n'est coupé.")
        self.trouver.clicked.connect(self._chercher_scenes)
        ligne.addWidget(self.trouver)
        self.note_coupe = _texte("Le logiciel trouve la neige, l'écran bleu ou noir du début, de la fin et "
                                 "entre deux scènes. Ces moments ne seront pas restaurés. Vous pouvez aussi "
                                 "passer cette étape.")
        ligne.addWidget(self.note_coupe, 1)
        v.addLayout(ligne)
        self.note_scenes = _texte()
        self.note_scenes.hide()
        v.addWidget(self.note_scenes)
        self.moments = QWidget()
        self.moments_lay = QHBoxLayout(self.moments)
        self.moments_lay.setContentsMargins(0, 0, 0, 0)
        self.moments_lay.setSpacing(6)
        self.moments.hide()
        v.addWidget(self.moments)
        self._scenes: list[float] = []
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
        self.resume = _texte()
        self.resume.setObjectName("resumeAssistant")
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
        """Gros titres, rendu choisi entouré ; suit le thème et la taille du texte."""
        e = float(getattr(self.w, "_echelle", 1.0) or 1.0)
        cle = (theme.ACCENT, theme.BORD, theme.CARTE, e)
        if getattr(self, "_style_cle", None) == cle:
            return
        self._style_cle = cle
        self.setStyleSheet(
            f"QLabel#etapeAssistant {{font-weight:bold; color:{theme.ACCENT}; font-size:{16 * e:.0f}pt;}}"
            f"QLabel#consigneAssistant {{font-weight:bold; font-size:{13 * e:.0f}pt;}}"
            f"QLabel#titreAssistant {{font-weight:bold; font-size:{15 * e:.0f}pt;}}"
            f"QLabel#resumeAssistant {{font-size:{12 * e:.0f}pt;}}"
            f"QToolButton#tuileRendu, QToolButton#tuileOriginal {{border:2px solid {theme.BORD}; border-radius:8px;"
            f"background:{theme.CARTE}; font-size:{12 * e:.0f}pt; padding:4px;}}"
            f"QToolButton#tuileRendu:checked {{border:4px solid {theme.ACCENT}; font-weight:bold;}}")

    # ------------------------------------------------------------ navigation
    def _film(self) -> bool:
        return not getattr(self.w, "is_photo", False)

    def _liste(self) -> list[tuple[str, QWidget]]:
        if not self._film():
            return [("Choisir le rendu", self._page_rendu), ("Vérifier et lancer", self._page_fin)]
        etapes = [("Choisir le rendu", self._page_rendu),
                  ("Début, fin et passages à enlever", self._page_coupe)]
        if self.w.info is not None and self.w.info.has_audio:
            etapes.append(("Le son", self._page_son))
        return etapes + [("Vérifier et lancer", self._page_fin)]

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
                                            "ou passez à l'étape suivante : « Équilibré » est conseillé.")
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
        self._vider_scenes()
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
        for nom in ("bornes_coupe", "trim_tout"):     # début / fin et « Ici » : écran complet seulement
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
            pix = QPixmap(str(chemin))
            if not pix.isNull():
                self.tuiles[cle].setIcon(QIcon(pix))
        self.note_rendu.setText("Choisissez en regardant : le rendu entouré sera utilisé. « Équilibré » est "
                                "conseillé si vous hésitez.")

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

    def _vider_scenes(self) -> None:
        self._scenes = []
        self.note_scenes.hide()
        self.note_scenes.setText("")
        while self.moments_lay.count():
            item = self.moments_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.moments.hide()
        barre = getattr(self.w, "barre", None)
        if barre is not None and hasattr(barre, "poser_scenes"):
            barre.poser_scenes([])

    def _chercher_scenes(self) -> None:
        w = self.w
        if w.info is None or w._busy() or not self._film():
            return
        self._vider_scenes()
        self.note_scenes.setText("Recherche des changements : le film est lu en entier.")
        self.note_scenes.show()
        ffmpeg = w.tools.ffmpeg.path
        info = w.info
        w._launch(lambda c, p: scenes.detecter(ffmpeg, info.path, info.duration, cancel=c, progress=p),
                  self._scenes_trouvees)

    def _scenes_trouvees(self, moments) -> None:
        self._scenes = list(moments)
        barre = getattr(self.w, "barre", None)
        if barre is not None and hasattr(barre, "poser_scenes"):
            barre.poser_scenes(self._scenes)
        while self.moments_lay.count():
            item = self.moments_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not moments:
            self.note_scenes.setText("Aucun changement net trouvé. Le film semble d'un seul tenant.")
            self.moments.hide()
            return
        n = len(moments)
        self.note_scenes.setText(
            f"{n} changement{'s' if n > 1 else ''} trouvé{'s' if n > 1 else ''}. "
            "Cliquez sur un moment pour vous y placer, puis « Couper ici » si vous voulez l'enlever.")
        for t in moments:
            b = _bouton(scenes.phrase(t))
            b.setMinimumWidth(0)
            b.clicked.connect(lambda _c=False, moment=t: self.w._barre_cliquee(moment))
            self.moments_lay.addWidget(b)
        self.moments_lay.addStretch(1)
        self.moments.show()

    def _vides_trouves(self, res) -> None:
        passages, duree = res
        w = self.w
        w.status.setText("Recherche terminée.")
        if not passages:
            self.note_coupe.setText("Aucune neige ni écran vide trouvé : le film est gardé en entier.")
            return
        dits, milieu = [], []
        for p in passages:
            if p.debut <= 1.0:
                w.trim_start.setValue(p.fin)
                dits.append(f"au début ({hms(p.debut)} à {hms(p.fin)})")
            elif p.fin >= duree - 1.0:
                w.trim_end.setValue(p.debut)
                dits.append(f"à la fin ({hms(p.debut)} à {hms(p.fin)})")
            else:
                milieu.append((p.debut, p.fin))
        refus = ""
        if milieu:
            if w.tape_check.isChecked() or w.chroma_check.isChecked():
                refus = (f" {len(milieu)} passage(s) au milieu ne sont pas enlevés : « Bruit de bande » et "
                         "« Couleur des décrochages » ne le permettent pas.")
            else:
                from .gui import _MAX_COUPES
                w._coupes = w._coupes_normalisees(w._coupes + milieu)[:_MAX_COUPES]
                w._rafraichir_passages()
                dits.append(f"{len(milieu)} passage(s) entre deux scènes")
        self.note_coupe.setText("Trouvé : " + ", ".join(dits) + ". En doré sur la barre : ce ne sera pas "
                                "restauré. Les carrés blancs se tirent pour ajuster." + refus)

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
        w = self.w
        s = w.settings(with_advice=True)
        morceaux = [f"Rendu : {s.profile.name}."]
        if self._film():
            if w.info is not None and w.info.has_audio:
                morceaux.append("Son : " + ("nettoyé" if s.restore_audio else "gardé tel quel")
                                + (f", {phrase_son(s.audio_offset_ms, s.audio_drift_ms_per_min)}" if
                                   phrase_son(s.audio_offset_ms, s.audio_drift_ms_per_min) else "") + ".")
            coupes = []
            if w.trim_start.value():
                coupes.append(f"début à {hms(w.trim_start.value())}")
            if w.trim_end.value():
                coupes.append(f"fin à {hms(w.trim_end.value())}")
            if w._coupes:
                coupes.append(f"{len(w._coupes)} passage(s) enlevé(s)")
            morceaux.append("Coupes : " + (", ".join(coupes) if coupes else "aucune, le film est gardé en entier") + ".")
        self.resume.setText(" ".join(morceaux))
        self.actualiser()

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
            self.consigne.setText("Vous avez vu l'avant / après. Si le résultat vous plaît, cliquez sur "
                                  "« Lancer la restauration », en bas à droite. Sinon, « Retour ».")
        else:
            self.voir.setText("Voir l'avant / après")
            self.voir.setObjectName("action")
            self.voir.setMinimumHeight(56)
            self.consigne.setText("Regardez d'abord l'avant / après. « Lancer la restauration » s'allume ensuite.")
        self.voir.style().unpolish(self.voir)
        self.voir.style().polish(self.voir)

    def peut_lancer(self) -> bool:
        return self.pages.currentWidget() is self._page_fin and self.apercu_vu()

    def phrase_attente(self) -> str:
        """Pourquoi « Lancer » est éteint, à côté du bouton."""
        if self.pages.currentWidget() is self._page_fin:
            return "Regardez d'abord l'avant / après."
        return "Pas encore. Terminez les étapes."


__all__ = ["Assistant", "faire_ecoute", "faire_rendus", "phrase_son", "son_depuis_debut_fin", "suggestion_derive"]
