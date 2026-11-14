"""Interface PySide6. Les traitements tournent dans un QThread : l'interface
reste réactive, et rien ne tourne en arrière-plan quand l'application est inactive."""
from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import traceback
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
                               QRadioButton, QSizePolicy, QVBoxLayout, QWidget)

from . import pipeline
from .probe import MediaInfo, analyze
from .profiles import PROFILES, RESOLUTIONS
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
    def _build(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        left = QVBoxLayout()
        right = QVBoxLayout()
        root.addLayout(left, 2)
        root.addLayout(right, 3)
        self.setCentralWidget(central)

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
                    "Format d'affichage", "Balayage", "Norme probable", "Audio"):
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
        self.stab_check = QCheckBox("Stabiliser l'image (caméra tenue à la main, 2 passes)")
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
        self.ai_check.setEnabled(self.tools.ai_available and not busy)
        self.deint_combo.setEnabled(not busy)
        self.stab_check.setEnabled(self.tools.stab_available and not busy)
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

    def settings(self) -> pipeline.Settings:
        key = next(k for k, b in self.profile_buttons.items() if b.isChecked())
        return pipeline.Settings(profile=PROFILES[key], resolution=self.res_combo.currentData(),
                                 scan=self.scan_combo.currentData(), dar=self.dar_combo.currentData(),
                                 use_ai=self.ai_check.isChecked(),
                                 deinterlacer=self.deint_combo.currentData(),
                                 stabilize=self.stab_check.isChecked())

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
        self.warn_label.setText("\n".join("⚠ " + w for w in info.warnings))
        self.scan_combo.setCurrentIndex(0)
        self.dar_combo.setCurrentIndex(0)
        self.start_spin.setRange(0, max(0.0, info.duration - 10))
        self.start_spin.setValue(min(info.duration * 0.1, max(0.0, info.duration - 10)))
        if not self.out_edit.text():
            self.out_edit.setText(str(info.path.parent))
        self.drop.setText(info.path.name)
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
        box = QMessageBox(QMessageBox.Information, "Restauration terminée",
                          f"Fichier créé :\n{out}\n\nL'original n'a pas été modifié.", parent=self)
        open_btn = box.addButton("Ouvrir le dossier", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out.parent)))

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
