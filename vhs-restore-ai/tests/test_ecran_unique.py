"""Les contrôles indispensables restent accessibles sur l'écran de la famille."""
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QScrollArea

from vhs_restore.gui import MainWindow
from vhs_restore.probe import MediaInfo


def dans_ecran(w, controle):
    return controle.isVisibleTo(w) and w.rect().contains(
        QRect(controle.mapTo(w, QPoint()), controle.size()))


@pytest.mark.parametrize("pct", [100, 125, 150])
@pytest.mark.parametrize("origine", ["video", "film"])
def test_tous_les_volets_a_1280_641(tools, pct, origine):
    app = QApplication.instance() or QApplication([])
    w = MainWindow(tools)
    try:
        w.resize(1280, 641)
        w.show()
        w.set_taille_texte(pct, annoncer=False)
        assert dans_ecran(w, w.choisir) and dans_ecran(w, w.s_folder)
        w.info = MediaInfo(Path("Noël.avi"), has_audio=True, suggested_source=origine)
        w.preview = object()
        w._update_state()
        w.plus_son.setChecked(True)
        for nom, (bouton, zone) in w.sections.items():
            if not bouton.isChecked():
                bouton.click()
            app.processEvents()
            app.processEvents()
            assert (w.width(), w.height()) == (1280, 641)
            assert not isinstance(w.centralWidget(), QScrollArea)
            assert sum(z.isVisible() for _, z in w.sections.values()) == 1
            assert zone.horizontalScrollBar().maximum() == 0, nom
            if pct <= 125:
                assert zone.verticalScrollBar().maximum() == 0, nom
            assert dans_ecran(w, w.s_compare) and dans_ecran(w, w.run_btn)
            assert all(dans_ecran(w, b) for b, _ in w.sections.values())
    finally:
        w.close()
