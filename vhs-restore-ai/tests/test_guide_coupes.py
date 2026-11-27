"""Guide des coupes au milieu : trois textes selon l'état, pour un homme de 76 ans."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from vhs_restore.gui import (GUIDE_COUPES_AUCUNE, GUIDE_COUPES_CARRES, GUIDE_COUPES_FAITE,
                             GUIDE_COUPES_OUVERTE, MainWindow, SchemaCoupe)  # noqa: E402


def _attendre(app, win) -> None:
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(5):
        app.processEvents()


def test_guide_coupes_trois_textes(tools, samples):
    """Aucune coupe, après le premier clic, après une coupe : le texte change."""
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.load_file(str(samples["long"]))
    _attendre(app, win)

    assert win.s_guide_coupes.text().replace("\xa0", " ") == GUIDE_COUPES_AUCUNE
    assert "«\u00a0Couper\u00a0ici\u00a0»" in win.s_guide_coupes.text()
    assert "«\u00a0Le\u00a0film\u00a0reprend\u00a0ici\u00a0»" in win.s_guide_coupes.text()

    win.start_spin.setValue(10)
    win.s_couper.click()
    assert win._coupe_ouverte is not None
    assert win.s_guide_coupes.text().replace("\xa0", " ") == GUIDE_COUPES_OUVERTE
    assert "«\u00a0Le\u00a0film\u00a0reprend\u00a0ici\u00a0»" in win.s_guide_coupes.text()

    win.start_spin.setValue(25)
    win.s_couper.click()
    assert len(win._coupes) == 1
    assert win.s_guide_coupes.text() == GUIDE_COUPES_FAITE
    assert "1 passage enlevé" in win.s_guide_coupes.text()
    assert "doré" in win.s_guide_coupes.text()
    assert "8 au plus" in win.s_guide_coupes.text()

    # bouton à côté de la barre
    assert any(b.text() == "Comment faire ?" and not b.isHidden()
               for b in win.findChildren(QPushButton))
    win.close()


def test_comment_faire_schema_et_aide(tools, samples, monkeypatch):
    """La fenêtre « Comment faire ? » et « Aide » portent le même texte, plus le schéma."""
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.load_file(str(samples["long"]))
    _attendre(app, win)

    vus: list[str] = []

    def capturer(dlg):
        textes = " ".join(lb.text() for lb in dlg.findChildren(QLabel))
        vus.append(textes)
        assert dlg.findChild(SchemaCoupe) is not None
        return 0

    monkeypatch.setattr("PySide6.QtWidgets.QDialog.exec", capturer)
    win._comment_faire_coupes()
    assert vus
    assert "«\u00a0Couper\u00a0ici\u00a0»" in vus[0]
    assert "«\u00a0Le\u00a0film\u00a0reprend\u00a0ici\u00a0»" in vus[0]
    vu = vus[0].replace("\xa0", " ")
    assert GUIDE_COUPES_AUCUNE in vu
    assert GUIDE_COUPES_OUVERTE in vu
    assert GUIDE_COUPES_FAITE in vu
    assert GUIDE_COUPES_CARRES in vu
    assert "carrés blancs" in vu
    assert "Annuler la dernière coupe" in vu

    # l'aide est une fenêtre qui défile (n°20, C1) : même texte, lu dans la fenêtre
    from PySide6.QtWidgets import QDialog
    boites: list[str] = []
    monkeypatch.setattr(QDialog, "exec", lambda self: boites.append(getattr(self, "texte", "")) or 0)
    win.show_welcome()
    assert boites
    assert GUIDE_COUPES_AUCUNE in boites[0]
    assert GUIDE_COUPES_OUVERTE in boites[0]
    assert GUIDE_COUPES_FAITE in boites[0]
    assert GUIDE_COUPES_CARRES in boites[0]
    assert "Ce que le logiciel ne peut pas faire" in boites[0]
    assert "détail absent de la bande" in boites[0]
    assert "mauvais tracking" in boites[0]
    assert "qualité de la numérisation" in boites[0]
    assert "couleurs restaurées sont une estimation" in boites[0]
    assert "inventer des textures" in boites[0]
    win.close()
