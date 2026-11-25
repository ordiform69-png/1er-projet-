"""Lumière et couleurs : quatre réglages simples AVANT de lancer, avec l'avant / après tout de suite.

Demande de l'utilisateur : l'image restaurée lui paraissait sombre et terne, et la restauration est
longue ; il veut régler la lumière et les couleurs en voyant le résultat, avant de lancer.

Une image du film est restaurée une seule fois (sans IA, comme les images du choix du rendu), puis
chaque clic n'applique à cette image que les réglages de l'utilisateur : la grande image change en
une fraction de seconde. Le film reçoit les mêmes réglages dans la chaîne complète
(pipeline.reglages_image ; la teinte s'ajoute à la balance des couleurs). L'aperçu rapide n'est
qu'une image : « Voir l'avant / après » reste la vérification avant de lancer.
"""
from __future__ import annotations

import dataclasses
import shutil
import tempfile
import threading
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from . import photo, pipeline
from .tools import ff_input, run

# (clé du réglage, nom à l'écran, bouton « moins », bouton « plus »)
REGLAGES = (
    ("lumiere", "Lumière", "Plus sombre", "Plus clair"),
    ("contraste", "Contraste", "Plus doux", "Plus marqué"),
    ("couleurs", "Couleurs", "Plus pâles", "Plus vives"),
    ("teinte", "Teinte", "Plus froide", "Plus chaude"),
)
HAUTEUR = 540                       # hauteur des deux images côte à côte
MOMENTS = (0.5, 0.25, 0.75, 0.1, 0.9)   # « Autre moment du film » : dans la partie gardée
ATTENTE_MS = 250                    # clics rapprochés : une seule image refaite


def filtres_utilisateur(valeurs: dict) -> list[str]:
    """Les seuls réglages de l'utilisateur, appliqués à une image déjà restaurée (RVB)."""
    lum, con, cou, tei = (pipeline.cran(valeurs.get(k, 0)) for k, *_ in REGLAGES)
    f = []
    if tei:
        f.append(f"colorchannelmixer=rr={1 + pipeline.PAS_TEINTE * tei:.4f}:bb={1 - pipeline.PAS_TEINTE * tei:.4f}")
    if lum or con or cou:
        f += ["format=yuv444p", f"eq=contrast={1 + pipeline.PAS_CONTRASTE * con:.4g}"
                                f":saturation={1 + pipeline.PAS_COULEURS * cou:.4g}"
                                f":gamma={1 + pipeline.PAS_LUMIERE * lum:.4g}"]
    return f


def phrase(valeurs: dict) -> str:
    """« lumière +1, couleurs +2 » ; vide si rien n'est changé."""
    morceaux = []
    for cle, nom, _m, _p in REGLAGES:
        v = pipeline.cran(valeurs.get(cle, 0))
        if v:
            morceaux.append(f"{nom.lower()} {v:+d}".replace("-", "−"))
    return ", ".join(morceaux)


def taille(info, est_photo: bool) -> tuple[int, int]:
    if est_photo and info.width and info.height:
        rapport = info.width / info.height
    else:
        rapport = float(info.dar or Fraction(4, 3))
    rapport = min(3.0, max(0.33, rapport))
    return int(round(HAUTEUR * rapport / 2)) * 2, HAUTEUR


def sans_reglages(s: pipeline.Settings) -> pipeline.Settings:
    """Image de base : le rendu choisi, sans les réglages de l'utilisateur, sans IA ni stabilisation."""
    return dataclasses.replace(s, lumiere=0, contraste=0, couleurs=0, teinte=0, use_ai=False, stabilize=False,
                               deinterlacer="bwdif", colorize=False)


def faire_base(info, s: pipeline.Settings, ffmpeg: str, dossier: Path, moment: float | None, est_photo: bool,
               cancel: threading.Event | None = None) -> tuple[Path, Path]:
    """L'image d'aujourd'hui et la même restaurée (sans les réglages), à la même taille."""
    dossier.mkdir(parents=True, exist_ok=True)
    w, h = taille(info, est_photo)
    base_s = sans_reglages(s)
    if est_photo:
        chaine = ",".join(photo.photo_chain(info, base_s))
        cadre = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                 "setsar=1,format=rgb24")
        entree, images_orig, images = ff_input(info.path), "1", "1"
        cadre_orig = cadre
    else:
        chaine = pipeline.filter_chain(info, base_s)
        cadre = cadre_orig = f"scale={w}:{h},setsar=1,format=rgb24"     # format d'affichage du film
        entree = pipeline._seek(moment, None) + pipeline.dvd_input(info)
        # quelques images avant celle montrée nourrissent les filtres qui regardent les voisines ;
        # un désentrelacement image par image double leur nombre : l'original suit le même instant
        images = "13"
        images_orig = "7" if "send_field" in chaine else "13"
    original, base = dossier / "original.png", dossier / "base.png"
    run([ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *entree,
         "-filter_complex", f"[0:v:0]split[a][b];[a]{cadre_orig}[o];[b]{chaine},{cadre}[r]",
         "-map", "[o]", "-frames:v", images_orig, "-update", "1", str(original),
         "-map", "[r]", "-frames:v", images, "-update", "1", str(base)],
        cancel=cancel, what="FFmpeg (image pour régler la lumière)")
    return original, base


def composer(ffmpeg: str, original: Path, base: Path, valeurs: dict, sortie: Path,
             cancel: threading.Event | None = None) -> Path:
    """Avant à gauche, après (avec les réglages) à droite : l'image de la grande comparaison."""
    droite = ",".join([*filtres_utilisateur(valeurs), "format=rgb24"])
    run([ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", str(original), "-i", str(base),
         "-filter_complex", f"[1:v]{droite}[r];[0:v]format=rgb24[o];[o][r]hstack=inputs=2",
         "-frames:v", "1", "-update", "1", str(sortie)],
        cancel=cancel, what="FFmpeg (réglage de la lumière)")
    return sortie


class Lumiere:
    """Les quatre valeurs (une seule source pour l'assistant et l'écran complet) et l'aperçu rapide."""

    def __init__(self, w) -> None:
        self.w = w
        self.valeurs = {cle: 0 for cle, *_ in REGLAGES}
        self.panneaux: list[Panneau] = []
        self.dossier = Path(tempfile.mkdtemp(prefix="vhsrestore_lumiere_"))
        self.dernier: Path | None = None        # dernière image avant / après montrée
        self.erreur = ""
        self._moment_i = 0
        self._cache = None                      # (clé de la base, original, base)
        self._numero = 0
        self._generation = 0
        self._annuler = threading.Event()
        self._verrou = threading.Lock()
        self._arrives: list = []
        self._travail = False
        self._encore = False
        self._attente = QTimer(w)
        self._attente.setSingleShot(True)
        self._attente.setInterval(ATTENTE_MS)
        self._attente.timeout.connect(self._lancer)
        self._releve = QTimer(w)
        self._releve.setInterval(60)
        self._releve.timeout.connect(self._pomper)

    # ------------------------------------------------------------ valeurs
    def reglages(self) -> dict:
        return dict(self.valeurs)

    def changer(self, cle: str, pas: int) -> None:
        self.valeurs[cle] = pipeline.cran(self.valeurs[cle] + pas)
        self._apres_changement()

    def remettre(self) -> None:
        for cle in self.valeurs:
            self.valeurs[cle] = 0
        self._apres_changement()

    def autre_moment(self) -> None:
        self._moment_i += 1
        self.actualiser()
        self.demander()

    def _apres_changement(self) -> None:
        self.actualiser()
        self.w._update_state()                  # l'avant / après vu ne correspond plus : à revoir
        self.demander()

    def nouveau_film(self) -> None:
        """Propres à chaque film, comme le son : on repart du rendu proposé."""
        self.arreter()
        for cle in self.valeurs:
            self.valeurs[cle] = 0
        self._moment_i = 0
        self._cache, self.dernier, self.erreur = None, None, ""
        self.actualiser()

    def actualiser(self) -> None:
        for p in self.panneaux:
            p.actualiser()

    # ------------------------------------------------------------ aperçu rapide
    def visible(self) -> bool:
        return any(p.isVisible() for p in self.panneaux)

    def occupe(self) -> bool:
        return self._travail or self._attente.isActive()

    def demander(self) -> None:
        if self.w.info is not None and self.visible():
            self._attente.start()

    def moment(self) -> float | None:
        w, info = self.w, self.w.info
        if info is None or getattr(w, "is_photo", False):
            return None
        duree = float(info.duration or 0)
        debut = float(w.trim_start.value() or 0)
        fin = float(w.trim_end.value() or 0) or duree
        if fin <= debut:
            debut, fin = 0.0, duree
        if self._moment_i == 0 and w.start_spin.value():
            t = float(w.start_spin.value())        # le moment choisi pour l'avant / après
        else:
            t = debut + MOMENTS[self._moment_i % len(MOMENTS)] * (fin - debut)
        for deb, fn in getattr(w, "_coupes", ()) or ():   # jamais dans un passage enlevé (neige)
            if deb <= t < fn:
                t = fn
        return max(0.0, min(t, max(0.0, duree - 1.0)))

    def _lancer(self) -> None:
        w = self.w
        if w.info is None:
            return
        if self._travail:
            self._encore = True
            return
        info, est_photo = w.info, bool(getattr(w, "is_photo", False))
        s = w.settings(with_advice=True)
        moment = self.moment()
        cle = (str(info.path), None if moment is None else round(moment, 2),
               repr(dataclasses.astuple(sans_reglages(s))))
        cache = self._cache if self._cache is not None and self._cache[0] == cle else None
        valeurs, ffmpeg = self.reglages(), w.tools.ffmpeg.path
        self._numero += 1
        numero, generation, annuler = self._numero, self._generation, self._annuler
        dossier = self.dossier

        def corps() -> None:
            try:
                if cache is not None and cache[1].exists() and cache[2].exists():
                    original, base = cache[1], cache[2]
                else:
                    original, base = faire_base(info, s, ffmpeg, dossier / f"base_{numero}", moment, est_photo,
                                                cancel=annuler)
                sortie = composer(ffmpeg, original, base, valeurs, dossier / f"image_{numero}.png", cancel=annuler)
                res = (cle, original, base, sortie)
            except BaseException as exc:          # rapporté à l'écran, jamais perdu en silence
                res = exc
            with self._verrou:
                self._arrives.append((generation, res))
        self._travail = True
        self.erreur = ""
        self.actualiser()
        threading.Thread(target=corps, name="vhs-lumiere", daemon=True).start()
        self._releve.start()

    def _pomper(self) -> None:
        with self._verrou:
            arrives, self._arrives = self._arrives, []
        for generation, res in arrives:
            self._travail = False
            if generation != self._generation:
                continue                          # film précédent
            if isinstance(res, BaseException):
                self.erreur = ("L'image n'a pas pu être préparée. Vous pouvez quand même lancer "
                               "«\u00a0Voir l'avant\u00a0/ après\u00a0».")
            else:
                ancien = self._cache
                self._cache = res[:3]
                if ancien is not None and ancien[2].parent != res[2].parent:
                    shutil.rmtree(ancien[2].parent, ignore_errors=True)
                if self.dernier is not None and self.dernier != res[3]:
                    self.dernier.unlink(missing_ok=True)
                self.dernier = res[3]
                if self.visible():
                    self.w.s_compare.set_still(self.dernier)
                    self.w.s_compare.set_mode("split")
            self.actualiser()
        if not self._travail:
            self._releve.stop()
            if self._encore:
                self._encore = False
                self._lancer()

    def arreter(self) -> None:
        """Nouveau film ou fermeture : l'image en cours est abandonnée (FFmpeg arrêté)."""
        self._attente.stop()
        self._annuler.set()
        self._annuler = threading.Event()
        self._generation += 1
        self._travail = self._encore = False
        self._releve.stop()
        with self._verrou:
            self._arrives = []

    def fermer(self) -> None:
        self.arreter()
        shutil.rmtree(self.dossier, ignore_errors=True)


class Panneau(QWidget):
    """Quatre lignes « Plus sombre · Normal · Plus clair », etc. Deux exemplaires : l'étape de
    l'assistant et la section de l'écran complet ; les valeurs sont partagées."""

    def __init__(self, lum: Lumiere, guide: bool) -> None:
        super().__init__()
        self.lum = lum
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        if guide:
            intro = QLabel("Regardez la grande image : à gauche aujourd'hui, à droite le résultat. "
                           "Changez si besoin. Si l'image vous plaît, passez à la suite.")
            intro.setWordWrap(True)
            intro.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            v.addWidget(intro)
        grille = QGridLayout()
        grille.setHorizontalSpacing(8)
        grille.setVerticalSpacing(4 if guide else 2)
        self.lignes: dict[str, tuple[QPushButton, QLabel, QPushButton]] = {}
        for i, (cle, nom, moins, plus) in enumerate(REGLAGES):
            titre = QLabel(nom)
            titre.setObjectName("nomReglage")
            bm, bp = QPushButton(moins), QPushButton(plus)
            valeur = QLabel()
            valeur.setAlignment(Qt.AlignCenter)
            valeur.setMinimumWidth(80)
            valeur.setObjectName("valeurReglage")
            for b, pas, texte in ((bm, -1, moins), (bp, 1, plus)):
                b.setAccessibleName(f"{nom} : {texte.lower()}")
                b.setCursor(Qt.PointingHandCursor)
                b.setMinimumHeight(44 if guide else 36)
                b.clicked.connect(lambda _c=False, k=cle, n=pas: lum.changer(k, n))
            grille.addWidget(titre, i, 0)
            grille.addWidget(bm, i, 1)
            grille.addWidget(valeur, i, 2)
            grille.addWidget(bp, i, 3)
            self.lignes[cle] = (bm, valeur, bp)
        grille.setColumnStretch(1, 1)
        grille.setColumnStretch(3, 1)
        v.addLayout(grille)
        bas = QHBoxLayout()
        self.remettre = QPushButton("Remettre comme au départ")
        self.remettre.clicked.connect(lum.remettre)
        self.autre = QPushButton("Autre moment du film")
        self.autre.setToolTip("Montre une autre image du film, pour vérifier une scène plus sombre ou plus claire.")
        self.autre.clicked.connect(lum.autre_moment)
        for b in (self.remettre, self.autre):
            b.setMinimumHeight(40 if guide else 34)
            b.setCursor(Qt.PointingHandCursor)
            bas.addWidget(b)
        v.addLayout(bas)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        v.addWidget(self.note)
        v.addStretch(1)
        lum.panneaux.append(self)
        self.actualiser()

    def actualiser(self) -> None:
        lum, w = self.lum, self.lum.w
        occupe = w._busy()
        for cle, (bm, valeur, bp) in self.lignes.items():
            n = lum.valeurs[cle]
            valeur.setText("Normal" if n == 0 else f"{n:+d}".replace("-", "−"))
            bm.setEnabled(n > -pipeline.CRANS and not occupe)
            bp.setEnabled(n < pipeline.CRANS and not occupe)
        self.remettre.setEnabled(any(lum.valeurs.values()) and not occupe)
        self.autre.setVisible(not getattr(w, "is_photo", False))
        self.autre.setEnabled(not occupe)
        if lum.erreur:
            self.note.setText(lum.erreur)
        elif lum._travail and lum._cache is None:
            self.note.setText("Préparation de l'image…")
        elif lum.dernier is not None:
            self.note.setText("Aperçu rapide d'une image, sans l'amélioration IA. Vérifiez ensuite avec "
                              "«\u00a0Voir l'avant\u00a0/ après\u00a0».")
        else:
            self.note.setText("")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.lum.demander()
