# Usage : python scripts/audit_interface.py FILM PHOTO_NB PHOTO_COULEUR (QT_QPA_PLATFORM=offscreen)
"""Robot d'audit : chaque bouton/réglage, dans chaque état, actif ? visible ? branché ? efficace ?"""
import sys, time, threading
from pathlib import Path
from PySide6.QtCore import SIGNAL, QUrl
from PySide6.QtWidgets import (QApplication, QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit,
                               QMessageBox, QFileDialog, QCheckBox)
from PySide6.QtGui import QDesktopServices
app = QApplication(sys.argv)
from vhs_restore import theme; theme.apply(app)
from vhs_restore import gui
from vhs_restore.gui import MainWindow

VIDEO, PHOTO_NB, PHOTO_COUL = sys.argv[1:4]
events = []
QMessageBox.exec = lambda self: events.append(("boîte", self.windowTitle(), self.text()[:60])) or 0
QMessageBox.warning = staticmethod(lambda *a, **k: events.append(("avertissement", a[1], a[2][:60])) or 0)
QMessageBox.information = staticmethod(lambda *a, **k: events.append(("info", a[1], a[2][:60])) or 0)
QMessageBox.critical = staticmethod(lambda *a, **k: events.append(("ERREUR", a[1], a[2][:80])) or 0)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (events.append(("dialogue fichier",)) or ("", "")))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: (events.append(("dialogue dossier",)) or ""))
QDesktopServices.openUrl = staticmethod(lambda u: events.append(("ouvre", Path(u.toLocalFile()).name)) or True)

w = MainWindow(); w.resize(1366, 768); w.show()
def pump(s=0.2):
    t = time.time()
    while time.time() - t < s:
        app.processEvents(); time.sleep(0.02)
def wait_idle(limit=120):
    t = time.time()
    while w._busy() and time.time() - t < limit:
        pump(0.2)
    pump(0.3)

def name(wd):
    for k, v in w.__dict__.items():
        if v is wd: return k
    t = wd.text() if hasattr(wd, "text") and callable(wd.text) else ""
    return f"<{type(wd).__name__} « {t[:30]} »>"

def widgets():
    out = []
    for page in (w.pages.widget(0).widget(), w.pages.widget(1).widget()):
        for cls in (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit):
            out += [x for x in page.findChildren(cls) if not x.objectName().startswith("qt_")
                    and type(x).__name__ not in ("QLineEdit",) or isinstance(x, QLineEdit) and x is w.out_edit]
    seen, res = set(), []
    for x in out:
        if id(x) not in seen and x.parent() is not None and not type(x.parent()).__name__.startswith(("QAbstractSpinBox", "QDoubleSpinBox", "QSpinBox", "QComboBox")):
            seen.add(id(x)); res.append(x)
    return res

def page_of(x):
    return "simple" if w.pages.widget(0).widget().isAncestorOf(x) else "avancé"

def snapshot(label):
    rows = {}
    for x in widgets():
        root = w.pages.widget(0).widget() if page_of(x) == "simple" else w.pages.widget(1).widget()
        vis = x.isVisibleTo(root)
        rows[name(x)] = (page_of(x), x.isEnabled(), vis)
    return label, rows

states = []
states.append(snapshot("vide"))
w.load_file(VIDEO); wait_idle()
states.append(snapshot("film chargé"))
w.start_preview(); wait_idle(180)
states.append(snapshot("film + aperçu"))
# occupé : un faux travail long
stop = threading.Event()
w._launch(lambda c, p: (stop.wait(30), None)[1], lambda r: None); pump(0.5)
states.append(snapshot("OCCUPÉ"))
stop.set(); wait_idle()
w.load_file(PHOTO_NB); wait_idle()
states.append(snapshot("photo N&B"))
w.load_file(PHOTO_COUL); wait_idle()
states.append(snapshot("photo couleur"))

# tableau
names = list(states[0][1])
for _, rows in states[1:]:
    for n in rows:
        if n not in names: names.append(n)
hdr = "| réglage | page | " + " | ".join(s[0] for s in states) + " |"
print(hdr); print("|" + "---|" * (len(states) + 2))
for n in names:
    cells = []
    for _, rows in states:
        r = rows.get(n)
        cells.append("—" if r is None else ("caché" if not r[2] else ("actif" if r[1] else "grisé")))
    pg = next((rows[n][0] for _, rows in states if n in rows), "?")
    print(f"| {n} | {pg} | " + " | ".join(cells) + " |")

# branchements : boutons sans aucune action connectée
print("\nSANS ACTION BRANCHÉE (clicked/toggled) :")
for x in widgets():
    if isinstance(x, QAbstractButton):
        n = x.receivers(SIGNAL("clicked()")) + x.receivers(SIGNAL("clicked(bool)")) + x.receivers(SIGNAL("toggled(bool)"))
        if n == 0:
            print("  ", name(x), page_of(x))

# EFFICACITÉ : chaque bouton actif est cliqué ; il doit se passer quelque chose
def effect_test(label):
    print(f"\nCLICS sans effet visible ({label}) :")
    for x in widgets():
        if not isinstance(x, QAbstractButton) or isinstance(x, QCheckBox) or type(x).__name__ == "ProfileTile":
            continue
        root = w.pages.widget(0).widget() if page_of(x) == "simple" else w.pages.widget(1).widget()
        if not (x.isEnabled() and x.isVisibleTo(root)):
            continue
        before = (len(events), w.status.text(), w.pages.currentIndex(), w._busy())
        x.click(); pump(0.3)
        after = (len(events), w.status.text(), w.pages.currentIndex(), w._busy())
        if w._busy():
            w.cancel(); wait_idle(60)
        if before == after:
            print("   ", name(x), page_of(x))
        w.pages.setCurrentIndex(0)
w.load_file(VIDEO); wait_idle()
effect_test("film chargé, sans aperçu")
w.start_preview(); wait_idle(180)
effect_test("film + aperçu")
w.load_file(PHOTO_NB); wait_idle()
effect_test("photo N&B")
print("ÉVÉNEMENTS (extrait) :", events[-12:])
print("FIN")
