"""Bugs d'écran au zoom Windows (demande n°20, agent C).

Chaque test décrit le comportement attendu et échoue tant que le bug est là.
`xfail(strict=True)` garde la suite verte ; un correctif qui fait passer le test
devient un xpass, donc un échec, le temps de retirer la marque.

Le zoom ne se règle qu'au démarrage de Qt : petit programme à part, comme
`test_petite_image_du_rendu_entiere_et_centree`.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_RACINE = str(Path(__file__).resolve().parents[1])

# Le plus petit écran de tests/test_ecrans.py, et l'écran du père (1920×1080 à 150 %).
_HAUTEUR_COURTE = 535
_HAUTEUR_PERE = 641
_LARGEUR_ETROITE = 1024


def _lancer(zoom: str, source: str) -> dict:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=zoom, PYTHONPATH=_RACINE)
    r = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


_AIDE = r"""
import json
from PySide6.QtWidgets import QApplication, QDialog
from vhs_restore.gui import MainWindow
from vhs_restore.tools import detect_tools
app = QApplication([])
win = MainWindow(detect_tools())
win.show()
app.processEvents()
vu = {}
orig = QDialog.exec
def faux(self):
    self.show()
    for _ in range(4):
        app.processEvents()
    vu = {
        "w": self.width(), "h": self.height(),
        "min_w": self.minimumSizeHint().width(), "min_h": self.minimumSizeHint().height(),
        "escape": self.escapeButton() is not None,
    }
    print(json.dumps(vu))
    return QDialog.Rejected
QDialog.exec = faux
win.show_welcome()
"""


@pytest.mark.parametrize("zoom", ["1.25", "1.5"])
@pytest.mark.xfail(strict=True, reason="L'aide du premier lancement est plus haute que l'écran : "
                    "« C'est parti » tombe en dehors, et Échap ne ferme pas.")
def test_aide_du_premier_lancement_tient_sur_l_ecran(zoom):
    """1280×641 (père) et 1093×535 : le mode d'emploi modal doit tenir en entier,
    bouton compris. Mesuré : environ 1169 px de haut, 801 au minimum."""
    m = _lancer(zoom, _AIDE)
    assert m["h"] <= _HAUTEUR_COURTE and m["min_h"] <= _HAUTEUR_COURTE, m


_DETAILS = r"""
import json
from PySide6.QtWidgets import QApplication, QDialog
from vhs_restore.gui import MainWindow
from vhs_restore.tools import detect_tools
app = QApplication([])
win = MainWindow(detect_tools())
win.show()
win.resize(1093, 535)
for _ in range(4):
    app.processEvents()
win.details.click()
for _ in range(4):
    app.processEvents()
dlg = next(d for d in win.findChildren(QDialog) if d.windowTitle() == "Détails du fichier")
print(json.dumps({"w": dlg.width(), "h": dlg.height(),
                  "hint_h": dlg.sizeHint().height()}))
"""


@pytest.mark.parametrize("zoom", ["1.25", "1.5"])
@pytest.mark.xfail(strict=True, reason="« Détails du fichier » est forcé à 580 px : "
                    "il dépasse l'écran de 535 px de haut.")
def test_details_du_fichier_tiennent_sur_l_ecran_bas(zoom):
    """1366×768 à 125 % et 1920×1080 à 175 % : 1093×535 utiles."""
    m = _lancer(zoom, _DETAILS)
    assert m["h"] <= _HAUTEUR_COURTE and m["w"] <= 1093, m


_GEOMETRIE = r"""
import json
from PySide6.QtWidgets import QApplication
from vhs_restore.gui import MainWindow
from vhs_restore.tools import detect_tools
app = QApplication([])
win = MainWindow(detect_tools())
win.showMaximized()
for _ in range(6):
    app.processEvents()
win.showNormal()
for _ in range(6):
    app.processEvents()
print(json.dumps({"w": win.width(), "h": win.height()}))
"""


@pytest.mark.parametrize("zoom", ["1.25", "1.5"])
@pytest.mark.xfail(strict=True, reason="La taille de repos après la fenêtre agrandie "
                    "reste 1100×760, plus haute que 641 et plus large que 1024.")
def test_fenetre_restauree_tient_sur_les_petits_ecrans(zoom):
    """Double-clic sur la barre de titre : la fenêtre reprend la taille du constructeur."""
    m = _lancer(zoom, _GEOMETRIE)
    assert m["w"] <= _LARGEUR_ETROITE and m["h"] <= _HAUTEUR_PERE, m


_BARRE = r"""
import json
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from vhs_restore.gui import BarreFilm

def meilleur(img, x0, x1):
    meilleur_c = 0.0
    x0, x1 = int(x0), int(x1)
    for y in range(img.height()):
        vals = [img.pixelColor(x, y).lightness() for x in range(x0, min(x1, img.width()))]
        if len(vals) < 8:
            continue
        c = sum(abs(vals[i + 1] - vals[i]) for i in range(len(vals) - 1)) / (len(vals) - 1)
        if c > meilleur_c:
            meilleur_c = c
    return meilleur_c

app = QApplication([])
pix = QPixmap(90, 72)
pix.fill(QColor(0, 0, 0))
dessin = QPainter(pix)
for x in range(0, 90, 2):
    dessin.fillRect(x, 0, 1, 72, QColor(255, 255, 255))
dessin.end()
barre = BarreFilm()
barre.resize(640, 56)
barre._vignettes = [pix, pix, pix, pix]
barre.duree = 10.0
barre.show()
app.processEvents()
grab = barre.grab().toImage()
z = barre.devicePixelRatioF()
print(json.dumps({"dpr": z, "contraste": round(meilleur(grab, 30 * z, 220 * z), 2)}))
"""


@pytest.mark.parametrize("zoom", ["1.25", "1.5"])
@pytest.mark.xfail(strict=True, reason="Les petites images de la barre sont préparées à la taille "
                    "logique : au zoom Windows elles sont floues.")
def test_petites_images_de_la_barre_nettes_au_zoom(zoom):
    """Barres d'un pixel. Plus de pixels devraient garder des bords au moins aussi nets qu'à 100 %."""
    base = _lancer("1", _BARRE)
    m = _lancer(zoom, _BARRE)
    assert m["contraste"] >= 0.95 * base["contraste"], (base, m)


_MONITEUR = r"""
import json, tempfile
from pathlib import Path
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
from vhs_restore.gui import CompareView

def meilleur(img, x0, x1):
    meilleur_c = 0.0
    x0, x1 = int(x0), int(x1)
    for y in range(img.height()):
        vals = [img.pixelColor(x, y).lightness() for x in range(x0, min(x1, img.width()))]
        if len(vals) < 8:
            continue
        c = sum(abs(vals[i + 1] - vals[i]) for i in range(len(vals) - 1)) / (len(vals) - 1)
        if c > meilleur_c:
            meilleur_c = c
    return meilleur_c

app = QApplication([])
img = QImage(320, 240, QImage.Format_RGB32)
img.fill(QColor(0, 0, 0))
for x in range(0, 320, 2):
    for y in range(240):
        img.setPixelColor(x, y, QColor(255, 255, 255))
chemin = Path(tempfile.mkdtemp()) / "moment.png"
img.save(str(chemin))
vue = CompareView()
vue.resize(480, 300)
vue.poser_moment(str(chemin), 1.0)
vue.show()
app.processEvents()
grab = vue.grab().toImage()
z = vue.devicePixelRatioF()
print(json.dumps({"dpr": z, "contraste": round(meilleur(grab, 60 * z, 420 * z), 2)}))
"""


@pytest.mark.parametrize("zoom", ["1.25", "1.5"])
@pytest.mark.xfail(strict=True, reason="L'image du moniteur est dessinée à la taille logique : "
                    "au zoom Windows elle est floue.")
def test_image_du_moniteur_nette_au_zoom(zoom):
    """Image du film dans le cadre (poser_moment). Les bords ne doivent pas s'adoucir quand le zoom augmente."""
    base = _lancer("1", _MONITEUR)
    m = _lancer(zoom, _MONITEUR)
    assert m["contraste"] >= 0.95 * base["contraste"], (base, m)
