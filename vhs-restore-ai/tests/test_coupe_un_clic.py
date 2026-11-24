"""Coupe d'un clic : le passage est retiré, et la restauration ne traite pas le trou."""
import pytest

from conftest import probe_json
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for


def _couvre_le_trou(start, duration) -> bool:
    """Vrai si cet appel d'export traite le trou ]1 s, 2 s[ au lieu d'un morceau gardé."""
    if duration is None:
        return True
    duree = float(duration)
    if abs(duree - 4.0) <= 0.2:
        return True
    debut = 0.0 if start is None else float(start)
    if abs(debut - 1.0) <= 0.2 and abs(duree - 1.0) <= 0.2:
        return True
    fin = debut + duree
    return min(fin, 2.0) - max(debut, 1.0) > 0.05


def test_export_ne_traite_pas_le_trou(samples, tools, tmp_path, monkeypatch):
    info = analyze(samples["pal_tff"], tools)       # 4 s : on garde 0–1 et 2–4
    s = pipeline.Settings(profile_for("equilibre", "video"), deinterlacer="bwdif")
    assert s.profile.key == "equilibre" and s.deinterlacer == "bwdif" and not s.use_ai

    origine = pipeline.export
    vus: list[tuple] = []

    def espion(*args, **kwargs):
        # L'appel avec passages= doit aller à l'export d'origine : sinon la
        # recherche du nom global « export » rappelle l'espion sans fin.
        # Les morceaux (sans passages) sont notés, puis restaurés pour de vrai.
        if kwargs.get("passages") is not None:
            return origine(*args, **kwargs)
        vus.append((kwargs.get("start"), kwargs.get("duration")))
        return origine(*args, **kwargs)

    monkeypatch.setattr("vhs_restore.pipeline.export", espion)
    out = pipeline.export(info, s, tmp_path / "sans-trou.mp4", tools,
                          passages=[(0.0, 1.0), (2.0, 4.0)])

    assert len(vus) == 2, vus
    debut, duree = vus[0]
    assert duree == pytest.approx(1.0, abs=0.05)
    assert debut is None or debut == pytest.approx(0.0, abs=0.05)
    ensuite, duree_2 = vus[1]
    assert ensuite == pytest.approx(2.0, abs=0.05)
    assert duree_2 == pytest.approx(2.0, abs=0.05)
    assert not any(_couvre_le_trou(a, b) for a, b in vus), vus

    assert out.is_file()
    flux = probe_json(out)["streams"]
    video = next(x for x in flux if x["codec_type"] == "video")
    assert float(video["duration"]) == pytest.approx(3.0, abs=0.2)


def _est(coupe, debut: float, fin: float) -> bool:
    a, b = coupe
    return a == pytest.approx(debut, abs=0.05) and b == pytest.approx(fin, abs=0.05)


def _attendre(app, win) -> None:
    while win.worker is not None and win.worker.isRunning():
        app.processEvents()
        win.worker.wait(20)
    for _ in range(5):
        app.processEvents()


def _cliquer(win, texte: str) -> None:
    from PySide6.QtWidgets import QPushButton

    boutons = [b for b in win.findChildren(QPushButton) if texte in b.text()]
    if not boutons:
        vus = sorted({b.text() for b in win.findChildren(QPushButton)})
        pytest.fail(
            f"Bouton introuvable : le texte doit contenir « {texte} ». "
            f"Il n'est pas encore dans l'interface. Boutons présents : {vus}")
    visibles = [b for b in boutons if not b.isHidden()]
    (visibles or boutons)[0].click()


def test_coupe_un_clic(tools, samples):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from vhs_restore.gui import BarreFilm, MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.load_file(str(samples["long"]))
    _attendre(app, win)
    assert win.info is not None

    win.start_spin.setValue(10)
    _cliquer(win, "Enlever 30 secondes ici")
    assert len(win._coupes) == 1
    assert _est(win._coupes[0], 10, 40)
    assert "restaur" in win.status.text().lower()
    barre = win.findChild(BarreFilm)
    assert barre is not None
    assert any(_est(c, 10, 40) for c in barre.coupes)

    win.start_spin.setValue(50)
    _cliquer(win, "Enlever 10 secondes ici")
    assert len(win._coupes) == 2
    assert _est(win._coupes[-1], 50, 60)

    # L'aperçu ne va que jusqu'à 10 s de la fin : on ouvre le champ pour se placer
    # vraiment à 0,2 s de la fin, là où une minute entière ne tient plus.
    win.start_spin.setDecimals(1)
    win.start_spin.setMaximum(max(win.start_spin.maximum(), float(win.info.duration)))
    win.start_spin.setValue(win.info.duration - 0.2)
    _cliquer(win, "Enlever 1 minute ici")
    assert len(win._coupes) == 2
    assert _est(win._coupes[0], 10, 40)
    assert _est(win._coupes[-1], 50, 60)
    assert "fin" in win.status.text().lower()
    win.close()
