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

from PySide6.QtCore import QObject, QPoint, QRect, QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
                               QRadioButton, QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from . import pipeline
from .dvd import open_media
from .probe import MediaInfo, cast_gains
from .advice import advise
from .eta import Eta
from .advice import apply as apply_advice
from .profiles import PROFILES, RESOLUTIONS, profile_for
from .tools import Cancelled, ToolError, Toolset, detect_tools

log = logging.getLogger("vhs_restore")
VIDEO_FILTER = "Vidéos (*.avi *.mp4 *.mkv *.mov *.mpg *.mpeg *.m2t *.mts *.ts *.dv *.vob *.wmv *.m4v);;Tous les fichiers (*)"


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
        self.setMinimumSize(480, 300)
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

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self.before is not None:
            self.split = min(1.0, max(0.0, e.position().x() / max(1, self.width())))
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        if self.before is None or self.after is None:
            p.setPen(Qt.gray)
            p.drawText(self.rect(), Qt.AlignCenter, "Générez un aperçu pour comparer\navant / après")
            return
        size = self.before.size().scaled(self.size(), Qt.KeepAspectRatio)
        r = QRect(QPoint(0, 0), size)
        r.moveCenter(self.rect().center())
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(r, self.after)
        cut = int(r.width() * self.split)
        sx = self.before.width() * self.split
        p.drawPixmap(QRect(r.x(), r.y(), cut, r.height()), self.before,
                     QRect(0, 0, int(sx), self.before.height()))
        x = r.x() + cut
        p.setPen(QPen(Qt.white, 2))
        p.drawLine(x, r.top(), x, r.bottom())
        p.drawText(r.adjusted(8, 6, 0, 0), Qt.AlignLeft | Qt.AlignTop, "Original")
        p.drawText(r.adjusted(0, 6, -8, 0), Qt.AlignRight | Qt.AlignTop, "Restauré")


class DropZone(QLabel):
    dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__("Déposez une vidéo ici\nou cliquez sur « Choisir une vidéo »")
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(60)
        self.setStyleSheet("QLabel{border:2px dashed #888;border-radius:8px;color:#555;padding:8px}")

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


class MainWindow(QMainWindow):
    def __init__(self, tools: Toolset | None = None) -> None:
        super().__init__()
        self.setWindowTitle("VHS Restore AI")
        self.resize(1100, 760)
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
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 16, 24, 12)
        title = QLabel("Restaurer un film de famille")
        title.setStyleSheet("font-size:20pt;font-weight:bold")
        v.addWidget(title)
        self.s_info = QLabel("Commencez par choisir le film à restaurer.")
        self.s_info.setWordWrap(True)
        self.s_info.setStyleSheet("font-size:13pt;color:#333")
        v.addWidget(self.s_info)
        self.advice: list = []
        self.s_advice = QCheckBox("Appliquer ces conseils")
        self.s_advice.setStyleSheet("font-size:13pt")
        self.s_advice.setToolTip("Corrige avec modération les défauts détectés par l'analyse (son, contraste, couleur). "
                                 "Décochez pour garder le son tel quel.")
        self.s_advice.setVisible(False)
        v.addWidget(self.s_advice)
        h = QHBoxLayout()
        self.s_choose = QPushButton("1. Choisir le film")
        self.s_choose.clicked.connect(self._choose_file)
        self.s_preview = QPushButton("2. Voir l'avant / après")
        self.s_preview.clicked.connect(self.start_preview)
        self.s_run = QPushButton("3. Restaurer le film")
        self.s_run.clicked.connect(self.start_export)
        for b in (self.s_choose, self.s_preview, self.s_run):
            b.setStyleSheet(BIG)
            h.addWidget(b)
        v.addLayout(h)
        note = QLabel("Le son est nettoyé avec l'image. Le film d'origine n'est pas modifié. "
                      "Décalage, dérive et copie WAV : Options avancées.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#444;font-size:12pt")
        v.addWidget(note)
        self.s_compare = CompareView()
        v.addWidget(self.s_compare, 1)
        self.s_progress = QProgressBar()
        self.s_progress.setRange(0, 1000)
        self.s_progress.setTextVisible(False)
        self.s_progress.setMinimumHeight(22)
        self.s_status = QLabel("Prêt.")
        self.s_status.setWordWrap(True)
        self.s_status.setStyleSheet("font-size:13pt")
        v.addWidget(self.s_progress)
        v.addWidget(self.s_status)
        h = QHBoxLayout()
        self.s_cancel = QPushButton("Arrêter")
        self.s_cancel.setStyleSheet("QPushButton{font-size:13pt;padding:8px}")
        self.s_cancel.clicked.connect(self.cancel)
        self.s_folder = QPushButton("Restaurer tous les films d'un dossier…")
        self.s_folder.setStyleSheet("QPushButton{font-size:13pt;padding:8px}")
        self.s_folder.clicked.connect(self.start_folder)
        self.s_hear_orig = QPushButton("Écouter l'original")
        self.s_hear_new = QPushButton("Écouter le son restauré")
        for b in (self.s_hear_orig, self.s_hear_new):
            b.setStyleSheet("QPushButton{font-size:13pt;padding:8px}")
        self.s_hear_orig.clicked.connect(self._play_original)
        self.s_hear_new.clicked.connect(self._play_restored)
        adv = QPushButton("Options avancées ▸")
        adv.setFlat(True)
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

    def _build(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        back = QPushButton("◂ Retour au mode simple")
        back.setFlat(True)
        back.clicked.connect(lambda: self.set_advanced(False))
        outer.addWidget(back, 0, Qt.AlignLeft)
        root = QHBoxLayout()
        outer.addLayout(root, 1)
        left = QVBoxLayout()
        right = QVBoxLayout()
        root.addLayout(left, 2)
        root.addLayout(right, 3)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_simple())
        self.pages.addWidget(central)
        self.setCentralWidget(self.pages)

        # Import
        g = QGroupBox("1. Vidéo numérisée")
        v = QVBoxLayout(g)
        self.drop = DropZone()
        self.drop.dropped.connect(self.load_file)
        b = QPushButton("Choisir une vidéo…")
        b.clicked.connect(self._choose_file)
        v.addWidget(self.drop)
        v.addWidget(b)
        left.addWidget(g)

        # Caractéristiques
        g = QGroupBox("Caractéristiques")
        self.info_form = QFormLayout(g)
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
        for txt, val in (("Je ne sais pas — suivre l'analyse", None),
                         ("Vidéo analogique (VHS, Video8, Hi8, Betamax…)", "video"),
                         ("Pellicule cinéma numérisée (Super 8, 8 mm, 16 mm…)", "film"),
                         ("Pellicule transférée sur vidéo (film copié sur VHS, DVD…)", "transfer")):
            self.source_combo.addItem(txt, val)
        self.source_combo.setToolTip("L'origine change les réglages appliqués (grain du film préservé, "
                                     "pas de désentrelacement automatique d'une pellicule…).")
        self.source_combo.currentIndexChanged.connect(lambda _i: self._update_state())
        self.info_form.addRow("Origine du film :", self.source_combo)
        self.cadence_combo = QComboBox()
        self.cadence_combo.addItem("Celle du fichier", None)
        for r in (16, 18, 24):
            self.cadence_combo.addItem(f"{r} images/s", r)
        self.cadence_combo.setToolTip(
            "À changer seulement si la pellicule a été numérisée image par image mais enregistrée "
            "à une autre cadence (mouvements trop rapides). Aucune image n'est créée ni supprimée : "
            "la durée change. Laissez « Celle du fichier » en cas de doute.")
        self.info_form.addRow("Cadence de tournage :", self.cadence_combo)
        self.scan_combo.currentIndexChanged.connect(lambda _i: self._update_state())
        self.info_form.addRow("Balayage à utiliser :", self.scan_combo)
        self.info_form.addRow("Format à utiliser :", self.dar_combo)
        self.warn_label = QLabel()
        self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet("color:#a05a00")
        self.info_form.addRow(self.warn_label)
        left.addWidget(g)

        # Profils
        g = QGroupBox("2. Profil de restauration")
        v = QVBoxLayout(g)
        self.profile_group = QButtonGroup(self)
        self.profile_buttons: dict[str, QRadioButton] = {}
        for p in PROFILES.values():
            rb = QRadioButton(p.name)
            rb.setToolTip(p.description)
            d = QLabel(p.description)
            d.setWordWrap(True)
            d.setStyleSheet("color:#666;margin-left:22px")
            self.profile_group.addButton(rb)
            self.profile_buttons[p.key] = rb
            rb.toggled.connect(lambda on, k=p.key: on and self._profile_changed(k))
            v.addWidget(rb)
            v.addWidget(d)
        h = QHBoxLayout()
        self.res_combo = QComboBox()
        for k, txt in RESOLUTIONS.items():
            self.res_combo.addItem(txt, k)
        self.ai_check = QCheckBox("Amélioration IA (Real-ESRGAN)")
        self.ai_check.toggled.connect(self._ai_toggled)
        h.addWidget(QLabel("Sortie :"))
        h.addWidget(self.res_combo, 1)
        v.addLayout(h)
        h = QHBoxLayout()
        self.deint_combo = QComboBox()
        self.deint_combo.addItem("bwdif (rapide)", "bwdif")
        self.deint_combo.addItem("QTGMC (meilleure qualité, plus lent)", "qtgmc")
        h.addWidget(QLabel("Désentrelaceur :"))
        h.addWidget(self.deint_combo, 1)
        v.addLayout(h)
        self.dust_check = QCheckBox("Enlever les poussières et rayures (pellicule, plus lent)")
        v.addWidget(self.dust_check)
        self.tape_check = QCheckBox("Bruit de bande (poursuite, lignes, bande du bas)")
        self.chroma_check = QCheckBox("Couleur des décrochages (arcs-en-ciel, couleur perdue)")
        self.dropout_check = QCheckBox("Taches d'une seule image (décrochages)")
        tip = ("Moteur Analog Repair, désactivé par défaut. La luminance et le grain ne sont pas "
               "lissés, le tampon date n'est pas effacé. Une cassette entrelacée est d'abord "
               "désentrelacée (bwdif, ou fieldmatch si c'est une pellicule copiée sur bande). "
               "QTGMC n'est pas refait ensuite. Sans le module : installer.bat -AvecPoussieres.")
        for box in (self.tape_check, self.chroma_check, self.dropout_check):
            box.setToolTip(tip)
            v.addWidget(box)
        self.flicker_check = QCheckBox("Réduire le scintillement lumineux (pellicule)")
        self.flicker_check.setToolTip("Lisse les variations de luminosité d'une image à l'autre "
                                      "(filtre deflicker sur 5 images). À vérifier sur l'aperçu.")
        v.addWidget(self.flicker_check)
        self.hq_check = QCheckBox("Débruitage haute qualité (environ 3 fois plus lent)")
        self.hq_check.setToolTip("Remplace le débruitage standard par fftdnoiz (FFT 3D) avec un renfort "
                                 "sur les taches de couleur. Plus efficace sur le bruit analogique ; "
                                 "intensité adaptée au profil.")
        v.addWidget(self.hq_check)
        self.stab_check = QCheckBox("Stabiliser l'image (tremblements de caméra ou de pellicule, 2 passes)")
        v.addWidget(self.stab_check)
        self.audio_check = QCheckBox("Restaurer le son (souffle, clics, volume)")
        self.audio_check.setChecked(True)
        self.audio_check.setToolTip(
            "Suit le profil image. Fidèle : souffle très léger. Équilibré : clics, souffle, volume. "
            "Maximum : DeepFilterNet si tools\\deepfilter\\deep-filter est installé "
            "(installer.bat -AvecSon), sinon le même souffle FFmpeg plus fort. "
            "Le plafond de DeepFilterNet est de 12 dB. Les rires, la musique et la rue restent. "
            "Une piste muette le reste.")
        v.addWidget(self.audio_check)
        self.rnnoise_check = QCheckBox("Souffle de la voix (RNNoise, mélangé à l'original)")
        self.rnnoise_check.setToolTip(
            "Option, désactivée par défaut : les profils ne changent pas. "
            "Remplace le souffle FFmpeg d'Équilibré (35 %) et de Maximum (55 %) par RNNoise "
            "(modèle Xiph inclus, licence BSD). Le reste du signal, donc la pièce, est conservé. "
            "Inutile si DeepFilterNet a déjà traité Maximum. Fidèle n'est pas concerné.")
        v.addWidget(self.rnnoise_check)
        self.wind_check = QCheckBox("Réduire le vent et les grondements")
        self.wind_check.setToolTip(
            "Passe-haut doux à 80 Hz (6 dB par octave). Coupe le vent sur le micro et les "
            "grondements graves. Une voix à partir de 300 Hz n'est presque pas touchée. "
            "Désactivé par défaut. L'analyse le conseille si les graves sont forts et irréguliers.")
        v.addWidget(self.wind_check)
        self.presence_check = QCheckBox("Rendre les voix plus claires")
        self.presence_check.setToolTip(
            "Légère présence autour de 3 kHz, +3 dB au plus. Pour un son étouffé. "
            "Désactivé par défaut : rien n'est ajouté si la case n'est pas cochée.")
        v.addWidget(self.presence_check)
        h = QHBoxLayout()
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-500, 500)
        self.offset_spin.setDecimals(0)
        self.offset_spin.setSingleStep(10)
        self.offset_spin.setSuffix(" ms")
        self.offset_spin.setToolTip(
            "Décalage constant entre le son et l'image. Positif : retarder le son "
            "(il était en avance). Négatif : avancer le son. 0 : ne rien changer.")
        h.addWidget(QLabel("Décalage du son :"))
        h.addWidget(self.offset_spin)
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
        h.addWidget(QLabel("Dérive :"))
        h.addWidget(self.drift_spin)
        h.addStretch(1)
        v.addLayout(h)
        h = QHBoxLayout()
        self.mains_combo = QComboBox()
        self.mains_combo.addItem("Pas de ronflement à enlever", 0)
        self.mains_combo.addItem("Ronflement 50 Hz (Europe)", 50)
        self.mains_combo.addItem("Ronflement 60 Hz (Amérique)", 60)
        self.mains_combo.setToolTip(
            "Encoche très étroite sur la fréquence du secteur et son double. "
            "À n'activer que si un bourdonnement continu est audible. La musique grave reste.")
        self.copy_combo = QComboBox()
        self.copy_combo.addItem("Pas de copie séparée du son", "")
        self.copy_combo.addItem("Aussi un fichier WAV", "wav")
        self.copy_combo.addItem("Aussi un fichier FLAC", "flac")
        self.copy_combo.setToolTip(
            "Enregistre le son restauré à côté du film, sans modifier l'original. "
            "C'est le même son que dans la vidéo.")
        h.addWidget(self.mains_combo, 1)
        h.addWidget(self.copy_combo, 1)
        v.addLayout(h)
        h = QHBoxLayout()
        self.channel_combo = QComboBox()
        self.channel_combo.addItem("Canaux du son inchangés", "")
        self.channel_combo.addItem("Son gauche mis des deux côtés", "left")
        self.channel_combo.addItem("Son droit mis des deux côtés", "right")
        self.channel_combo.addItem("Remettre les deux côtés en phase", "phase")
        self.channel_combo.setToolTip("Pour un son enregistré d'un seul côté, ou dont les deux côtés "
                                      "s'annulent. L'analyse le détecte et le conseille.")
        self.declip_check = QCheckBox("Réparer le son saturé")
        self.declip_check.setToolTip("Reconstruit les crêtes coupées d'un son enregistré trop fort "
                                     "(cris, fêtes, vent). L'analyse le détecte et le conseille.")
        h.addWidget(self.channel_combo, 1)
        h.addWidget(self.declip_check, 1)
        v.addLayout(h)
        self.mask_spin = QDoubleSpinBox()
        self.mask_spin.setRange(0, 32)
        self.mask_spin.setDecimals(0)
        self.mask_spin.setSingleStep(2)
        self.mask_spin.setSuffix(" lignes")
        self.mask_spin.setToolTip(
            "Bande parasite en bas de certaines VHS (commutation des têtes). "
            "Ces lignes deviennent noires. L'image n'est ni agrandie ni déformée. 0 = ne rien masquer.")
        self.mask_label = QLabel("Masquer la bande du bas :")
        h = QHBoxLayout()
        h.addWidget(self.mask_label)
        h.addWidget(self.mask_spin)
        h.addStretch(1)
        v.addLayout(h)
        self.edge_spin = QDoubleSpinBox()
        self.edge_spin.setRange(0, 64)
        self.edge_spin.setDecimals(0)
        self.edge_spin.setSingleStep(2)
        self.edge_spin.setSuffix(" px")
        self.edge_spin.setToolTip(
            "Bords abîmés, remplacés par du noir. Cassette : gauche et droite. "
            "Pellicule : un cadre des quatre côtés. L'image garde la même taille "
            "et le même format (4:3 inchangé). 0 = ne rien masquer.")
        self.edge_label = QLabel("Masquer les bords :")
        h = QHBoxLayout()
        h.addWidget(self.edge_label)
        h.addWidget(self.edge_spin)
        h.addStretch(1)
        v.addLayout(h)
        h = QHBoxLayout()
        self.chroma_spin = QSpinBox()
        self.chroma_spin.setRange(-8, 8)
        self.chroma_spin.setSuffix(" px")
        self.chroma_spin.setToolTip(
            "Décalage horizontal de la couleur, typique d'une VHS (la couleur glisse "
            "par rapport au dessin). 0 = ne pas toucher. Négatif = vers la gauche.")
        h.addWidget(QLabel("Décalage de couleur :"))
        h.addWidget(self.chroma_spin)
        h.addStretch(1)
        v.addLayout(h)
        self.cast_check = QCheckBox("Corriger la dominante de couleur")
        self.cast_check.setToolTip(
            "Retire une teinte qui couvre tout le film (vert de VHS, par exemple). "
            "Les trois gains sont calculés une seule fois, pour tout le film. "
            "Un noir et blanc reste neutre, une image pâle n'est pas ravivée. "
            "Désactivé par défaut. L'analyse le conseille seulement si la dominante est forte.")
        v.addWidget(self.cast_check)
        v.addWidget(self.ai_check)
        left.addWidget(g)
        left.addStretch(1)

        # Aperçu
        g = QGroupBox("3. Aperçu avant / après (extrait de 10 s)")
        v = QVBoxLayout(g)
        h = QHBoxLayout()
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setDecimals(0)
        self.start_spin.setSuffix(" s")
        self.start_spin.setRange(0, 0)
        self.preview_btn = QPushButton("Générer l'aperçu")
        self.preview_btn.clicked.connect(self.start_preview)
        self.still_combo = QComboBox()
        self.still_combo.setMinimumContentsLength(9)
        self.still_combo.currentIndexChanged.connect(self._show_still)
        self.play_btn = QPushButton("Lire la comparaison")
        self.play_btn.clicked.connect(self._play_compare)
        self.hear_orig_btn = QPushButton("Écouter l'original")
        self.hear_orig_btn.clicked.connect(self._play_original)
        self.hear_new_btn = QPushButton("Écouter le son restauré")
        self.hear_new_btn.clicked.connect(self._play_restored)
        h.addWidget(QLabel("Début de l'extrait :"))
        h.addWidget(self.start_spin)
        h.addWidget(self.preview_btn)
        h.addStretch(1)
        h.addWidget(self.still_combo)
        h.addWidget(self.play_btn)
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
        g = QGroupBox("4. Restauration complète")
        v = QVBoxLayout(g)
        h = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Dossier de la vidéo d'origine")
        bo = QPushButton("Dossier de sortie…")
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
        h.addWidget(QLabel("Garder du début à :"))
        h.addWidget(self.trim_start)
        h.addWidget(QLabel("jusqu'à :"))
        h.addWidget(self.trim_end)
        h.addStretch(1)
        v.addLayout(h)
        h = QHBoxLayout()
        self.run_btn = QPushButton("Lancer la restauration")
        self.run_btn.setStyleSheet("font-weight:bold;padding:6px 14px")
        self.run_btn.clicked.connect(self.start_export)
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.clicked.connect(self.cancel)
        self.check_btn = QPushButton("Vérifier l'installation")
        self.check_btn.setToolTip("Restaure une courte vidéo d'essai et affiche un rapport "
                                  "(utile si quelque chose ne marche pas).")
        self.check_btn.clicked.connect(self.check_install)
        h.addWidget(self.run_btn)
        h.addWidget(self.cancel_btn)
        h.addStretch(1)
        h.addWidget(self.check_btn)
        v.addLayout(h)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.status = QLabel("Prêt.")
        self.status.setWordWrap(True)
        v.addWidget(self.progress)
        v.addWidget(self.status)
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
        ff = f"FFmpeg {t.ffmpeg.version} ✔" if t.ffmpeg.path and t.ffprobe.path and not t.missing_filters \
            else "FFmpeg ✖ (requis)"
        ai = "Real-ESRGAN ✔" if t.ai_available else "Real-ESRGAN non installé (facultatif)"
        qt = f"QTGMC ✔ ({t.vspipe.version})" if t.qtgmc_available else "QTGMC non installé (facultatif)"
        df = "DeepFilterNet ✔" if t.deepfilter_available else "DeepFilterNet non installé (facultatif)"
        self.tools_label.setText(f"{ff}   ·   {qt}   ·   {ai}   ·   {df}")
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
        self.still_combo.setEnabled(has_prev)

    def _profile_changed(self, key: str) -> None:
        p = PROFILES[key]
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
                                 mask_sides=int(self.edge_spin.value()))

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
        self.status.setText("Analyse de la vidéo…")
        self.progress.setRange(0, 0)  # animation indéterminée
        self._launch(lambda c, p: open_media(path, self.tools), self._loaded)

    def _loaded(self, info: MediaInfo) -> None:
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
        self._launch(lambda c, p: pipeline.make_preview(info, s, self.tools, self.preview_dir, start,
                                                        cancel=c, progress=p), self._preview_done)

    def _preview_done(self, res: pipeline.PreviewResult) -> None:
        self.preview = res
        self.still_combo.blockSignals(True)
        self.still_combo.clear()
        for i, _ in enumerate(res.stills):
            self.still_combo.addItem(f"Image {i + 1}/{len(res.stills)}")
        self.still_combo.blockSignals(False)
        self.still_combo.setCurrentIndex(1)
        self._show_still(1)
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
    app.setStyle("Fusion")
    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 10.5))   # lisible sans lunettes de lecture
    app.setFont(font)
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
