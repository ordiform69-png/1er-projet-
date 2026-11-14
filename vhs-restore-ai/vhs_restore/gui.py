"""Interface PySide6. Les traitements tournent dans un QThread : l'interface
reste réactive, et rien ne tourne en arrière-plan quand l'application est inactive."""
from __future__ import annotations

import dataclasses
import logging
import shutil
import tempfile
import threading
import traceback
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
                               QRadioButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from . import pipeline
from .probe import MediaInfo, analyze
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
        try:
            res = self.fn(self.cancel_event, lambda f, m: self.progressed.emit(f, m))
        except Cancelled:
            self.cancelled.emit()
        except ToolError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # erreur imprévue : journalisée en détail
            log.error("Erreur inattendue\n%s", traceback.format_exc())
            self.failed.emit(f"Erreur inattendue : {exc}\nConsultez le journal pour le détail.")
        else:
            self.succeeded.emit(res)


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
        adv = QPushButton("Options avancées ▸")
        adv.setFlat(True)
        adv.clicked.connect(lambda: self.set_advanced(True))
        h.addWidget(self.s_cancel)
        h.addWidget(self.s_folder)
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
        self.play_btn = QPushButton("Lire la comparaison vidéo")
        self.play_btn.clicked.connect(self._play_compare)
        h.addWidget(QLabel("Début de l'extrait :"))
        h.addWidget(self.start_spin)
        h.addWidget(self.preview_btn)
        h.addStretch(1)
        h.addWidget(self.still_combo)
        h.addWidget(self.play_btn)
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
        self.run_btn = QPushButton("Lancer la restauration")
        self.run_btn.setStyleSheet("font-weight:bold;padding:6px 14px")
        self.run_btn.clicked.connect(self.start_export)
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.clicked.connect(self.cancel)
        h.addWidget(self.run_btn)
        h.addWidget(self.cancel_btn)
        h.addStretch(1)
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

    # ------------------------------------------------------------ état
    def _refresh_tools(self) -> None:
        t = self.tools
        ff = f"FFmpeg {t.ffmpeg.version} ✔" if t.ffmpeg.path and t.ffprobe.path and not t.missing_filters \
            else "FFmpeg ✖ (requis)"
        ai = "Real-ESRGAN ✔" if t.ai_available else "Real-ESRGAN non installé (facultatif)"
        qt = f"QTGMC ✔ ({t.vspipe.version})" if t.qtgmc_available else "QTGMC non installé (facultatif)"
        self.tools_label.setText(f"{ff}   ·   {qt}   ·   {ai}")
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
        for b, ok in ((self.s_choose, not busy), (self.s_preview, loaded and not busy),
                      (self.s_run, loaded and not busy), (self.s_folder, not busy), (self.s_cancel, busy)):
            b.setEnabled(ok)
        self.ai_check.setEnabled(self.tools.ai_available and not busy)
        self.deint_combo.setEnabled(not busy)
        self.hq_check.setEnabled(not busy)
        self.stab_check.setEnabled(self.tools.stab_available and not busy)
        # fonctions affichées selon l'origine
        src = self.source()
        self.info_form.setRowVisible(self.cadence_combo, src == "film")
        if src != "film":
            self.cadence_combo.setCurrentIndex(0)
        self.flicker_check.setVisible(src in ("film", "transfer"))
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
        self.play_btn.setEnabled(has_prev and not busy)
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
        self.warn_label.setText("\n".join(notes))

    def settings(self) -> pipeline.Settings:
        key = next(k for k, b in self.profile_buttons.items() if b.isChecked())
        src = self.source()
        return pipeline.Settings(profile=profile_for(key, src), resolution=self.res_combo.currentData(),
                                 source=src, playback_fps=(Fraction(self.cadence_combo.currentData())
                                                           if self.cadence_combo.currentData() else None),
                                 deflicker=self.flicker_check.isChecked() and src != "video",
                                 scan=self.scan_combo.currentData(), dar=self.dar_combo.currentData(),
                                 use_ai=self.ai_check.isChecked(),
                                 deinterlacer=self.deint_combo.currentData(),
                                 stabilize=self.stab_check.isChecked(),
                                 denoise_hq=self.hq_check.isChecked())

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
        self._launch(lambda c, p: analyze(path, self.tools), self._loaded)

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
        self.start_spin.setRange(0, max(0.0, info.duration - 10))
        self.start_spin.setValue(min(info.duration * 0.1, max(0.0, info.duration - 10)))
        if not self.out_edit.text():
            self.out_edit.setText(str(info.path.parent))
        self.drop.setText(info.path.name)
        src_txt = {"video": "vidéo de caméscope ou de magnétoscope", "film": "pellicule (Super 8, 8 mm…)",
                   "transfer": "pellicule copiée sur vidéo"}[info.suggested_source]
        extra = (" Noir et blanc." if info.black_and_white else "") + \
                ("" if info.has_audio else " Film muet : il restera muet.")
        self.s_info.setText(f"<b>{info.path.name}</b> — {info.summary()['Durée']} — "
                            f"semble être une {src_txt}.{extra}")
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

    def start_export(self) -> None:
        if not self.info or self._busy():
            return
        out_dir = Path(self.out_edit.text() or self.info.path.parent)
        if not out_dir.is_dir():
            QMessageBox.warning(self, "Dossier de sortie", f"Ce dossier n'existe pas :\n{out_dir}")
            return
        info, s = self.info, self.settings()
        try:
            out = pipeline.unique_output_path(info, s, out_dir)
        except ToolError as exc:
            QMessageBox.warning(self, "Réglages", str(exc))
            return
        self.status.setText(f"Restauration vers {out.name}…")
        self._launch(lambda c, p: pipeline.export(info, s, out, self.tools, cancel=c, progress=p),
                     self._export_done)

    def _export_done(self, out: Path) -> None:
        self.status.setText(f"Terminé : {out}")
        self._done_box("Votre film restauré est prêt",
                       f"Votre film restauré est prêt :\n{out.name}\n\nIl se trouve dans le dossier :\n"
                       f"{out.parent}\n\nLe film d'origine n'a pas été modifié.", out.parent)

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
        base = self.settings()
        src = self.source_combo.currentData() or info.suggested_source
        return dataclasses.replace(base, profile=profile_for(base.profile.key, src), source=src,
                                   scan=None, dar=None, playback_fps=None,
                                   deflicker=self.flicker_check.isChecked() and src != "video")

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
        w.start()
        self._update_state()

    def _on_progress(self, frac: float, msg: str) -> None:
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1000)
        self.progress.setValue(int(frac * 1000))
        self.status.setText(f"{msg} {frac * 100:.0f} %")

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
        shutil.rmtree(self.preview_dir, ignore_errors=True)
        e.accept()


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
