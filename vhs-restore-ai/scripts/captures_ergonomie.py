# Usage : QT_QPA_PLATFORM=offscreen python scripts/captures_ergonomie.py DOSSIER
"""Captures hors écran (widget.grab) pour la revue d'ergonomie. Pas du logiciel."""
from __future__ import annotations

import inspect
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
film = Path(sys.argv[2]) if len(sys.argv) > 2 else None

app = QApplication(sys.argv)
from vhs_restore import theme
from vhs_restore.gui import MainWindow
from vhs_restore.tools import detect_tools


def pump(n=8):
    for _ in range(n):
        app.processEvents()


def grab(win, name: str) -> None:
    pump()
    pix = win.grab()
    pix.save(str(OUT / name))
    print(name, pix.width(), pix.height())


def wait_idle(win, limit=80):
    import time
    t = time.time()
    while win._busy() and time.time() - t < limit:
        app.processEvents()
        if win.worker:
            win.worker.wait(30)


tools = detect_tools()
# Captures comparables : pas la taille ni les fichiers gardés d'une session précédente.
prefs = QSettings("VHSRestoreAI", "VHSRestoreAI")
prefs.setValue("texte", 100)
prefs.setValue("recents", [])
prefs.sync()
for mode in ("sombre", "clair"):
    theme.set_mode(mode)
    theme.apply(app)
    win = MainWindow(tools)
    win.resize(1366, 768)
    win.show()
    if hasattr(win, "set_taille_texte"):
        win.set_taille_texte(100, annoncer=False)
    pump(12)
    grab(win, f"{mode}-simple-vide.png")
    if film and film.is_file():
        win.load_file(str(film))
        wait_idle(win)
        pump()
        grab(win, f"{mode}-simple-film.png")
    stop = threading.Event()
    if "job" in inspect.signature(win._launch).parameters:
        win._launch(lambda c, p: stop.wait(30), lambda r: None, job="export")
    else:
        win._launch(lambda c, p: stop.wait(30), lambda r: None)
    pump(15)
    if hasattr(win, "_on_progress"):
        eta = getattr(win, "eta", None)
        if eta is not None:
            eta.start = time.monotonic() - 800   # assez d'historique pour « environ 25 minutes »
            eta.points.clear()
        win._on_progress(0.35, "Restauration")
    grab(win, f"{mode}-simple-en-cours.png")
    stop.set()
    win.cancel()
    wait_idle(win)
    if hasattr(win, "_montrer_fini"):
        win._montrer_fini(
            "Votre film restauré est prêt :\nvacances.mp4\n\n"
            "Il se trouve dans le dossier :\nFilms\n\n"
            "Le film d'origine n'a pas été modifié.",
            Path("."), film, "film")
        grab(win, f"{mode}-simple-fini.png")
    else:
        box = QMessageBox(QMessageBox.Information, "Votre film restauré est prêt",
                          "Votre film restauré est prêt :\nvacances.mp4", parent=win)
        box.show()
        pump()
        box.grab().save(str(OUT / f"{mode}-boite-fini.png"))
        box.hide()
    win.status.setText("Ce fichier semble abîmé, ou ce n'est pas une vidéo ni une photo. "
                       "Essayez une autre copie du fichier.")
    if hasattr(win, "s_fini"):
        win.s_fini.setVisible(False)
    grab(win, f"{mode}-simple-erreur.png")
    win._update_state()
    for nom, (bouton, _) in win.sections.items():
        if not bouton.isChecked():
            bouton.click()
        pump()
        grab(win, f"{mode}-{nom}.png")
    if hasattr(win, "set_taille_texte"):
        win.resize(1093, 600)
        win.set_taille_texte(150, annoncer=False)
        pump()
        grab(win, f"{mode}-simple-texte-150.png")
    win.close()
    pump()

print("dossier", OUT)
