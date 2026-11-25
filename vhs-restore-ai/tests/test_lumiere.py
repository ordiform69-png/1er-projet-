"""Lumière et couleurs avant de lancer (demande de l'utilisateur : image sombre et terne, et la
restauration est trop longue pour essayer au hasard). Quatre réglages, une image tout de suite."""
import dataclasses
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore import lumiere, photo, pipeline
from vhs_restore.probe import MediaInfo
from vhs_restore.profiles import profile_for


def reglages(**valeurs):
    return dataclasses.replace(pipeline.Settings(profile_for("equilibre", "video"), source="video",
                                                 scan="progressive"), **valeurs)


def info_video():
    return MediaInfo(path=Path("x.mp4"), width=720, height=576, fps=Fraction(25), duration=10,
                     dar=Fraction(4, 3), sar=Fraction(16, 15))


def test_sans_reglage_la_chaine_ne_change_pas():
    f = pipeline.pre_filters(info_video(), reglages())
    eq = [x for x in f if x.startswith("eq=")]
    assert eq == ["eq=contrast=1.04:saturation=1.08"]              # le profil, comme avant
    assert not any("colorchannelmixer" in x for x in f)


def test_chaque_cran_va_dans_la_chaine():
    f = pipeline.pre_filters(info_video(), reglages(lumiere=2, contraste=-1, couleurs=3, teinte=2))
    eq = next(x for x in f if x.startswith("eq="))
    assert "gamma=1.2" in eq and "contrast=0.9776" in eq and "saturation=1.469" in eq, eq
    mix = next(x for x in f if x.startswith("colorchannelmixer"))
    assert "rr=1.0600" in mix and "bb=0.9400" in mix, mix
    # bornes : jamais plus de trois crans, quoi qu'on demande
    assert pipeline.reglages_image(reglages(lumiere=9, couleurs=-9)) == pipeline.reglages_image(
        reglages(lumiere=3, couleurs=-3))


def test_photo_recoit_les_memes_reglages():
    info = MediaInfo(path=Path("p.jpg"), width=640, height=480)
    s = dataclasses.replace(reglages(), source="video")
    assert not any("gamma" in x for x in photo.photo_chain(info, s))
    chaine = photo.photo_chain(info, dataclasses.replace(s, lumiere=1, couleurs=1))
    assert any(x.startswith("eq=") and "gamma=1.1" in x and "saturation=1.12" in x for x in chaine), chaine


def test_les_niveaux_ne_sont_etires_qu_a_moitie():
    s = reglages(level_black=0.2, level_white=0.7)
    lo, hi = pipeline.safe_levels(0.2, 0.7)
    flt = pipeline._levels_filter(s)
    assert f"rimin={lo / 2:.4f}" in flt and f"rimax={hi + (1 - hi) / 2:.4f}" in flt, flt


def moyennes(path):
    """Moyennes R, V, B (0-255) d'une image ou de la moitié droite (« après ») d'un avant / après."""
    t = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(path), "-vf",
                        "format=rgb24,extractplanes=r+g+b[r][g][b];[r]signalstats,metadata=print:key=lavfi.signalstats.YAVG[r2];"
                        "[g]signalstats,metadata=print:key=lavfi.signalstats.YAVG[g2];"
                        "[b]signalstats,metadata=print:key=lavfi.signalstats.YAVG[b2];[r2][g2][b2]hstack=3",
                        "-frames:v", "1", "-f", "null", "-"], capture_output=True, text=True).stderr
    return [float(v) for v in re.findall(r"YAVG=([\d.]+)", t)[:3]]


@pytest.fixture(scope="module")
def film_sombre(tmp_path_factory):
    d = tmp_path_factory.mktemp("lumiere")
    f = d / "film sombre.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=720x576:r=25:d=4,eq=brightness=-0.12:saturation=0.6,setsar=16/15",
       "-f", "lavfi", "-i", "sine=f=300:sample_rate=48000:d=4",
       "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", str(f))
    return f


def test_l_apercu_rapide_montre_ce_que_le_film_recevra(tools, film_sombre, tmp_path):
    """L'image instantanée (réglages appliqués à une image déjà restaurée) ressemble à la même
    image passée dans la chaîne complète avec ces réglages : l'aperçu ne ment pas."""
    from vhs_restore.probe import analyze
    info = analyze(film_sombre, tools)
    base_s = reglages()
    original, base = lumiere.faire_base(info, base_s, tools.ffmpeg.path, tmp_path / "base", 1.0, False)
    w, h = lumiere.taille(info, False)
    assert (w, h) == (720, 540)
    valeurs = {"lumiere": 3, "contraste": 0, "couleurs": 2, "teinte": 1}
    apercu = lumiere.composer(tools.ffmpeg.path, original, base, valeurs, tmp_path / "image.png")
    droite = tmp_path / "droite.png"
    ff("-i", str(apercu), "-vf", f"crop={w}:{h}:{w}:0", "-frames:v", "1", "-update", "1", str(droite))
    # la même image dans la chaîne complète, avec les réglages : ce que le film recevra
    chaine = pipeline.filter_chain(info, dataclasses.replace(lumiere.sans_reglages(base_s), **valeurs))
    vrai = tmp_path / "vrai.png"
    ff(*pipeline._seek(1.0, None), "-i", str(film_sombre), "-vf", f"{chaine},scale={w}:{h},setsar=1,format=rgb24",
       "-frames:v", "13", "-update", "1", str(vrai))
    sans = moyennes(base)
    rapide, juste = moyennes(droite), moyennes(vrai)
    assert sum(rapide) > sum(sans) + 30                          # plus clair, vraiment
    assert all(abs(a - b) < 6 for a, b in zip(rapide, juste)), (rapide, juste)
    assert rapide[0] - rapide[2] > sans[0] - sans[2]             # plus chaud : plus de rouge que de bleu


@pytest.mark.parametrize("cle,sens", [("lumiere", 1), ("lumiere", -1)])
def test_lumiere_eclaircit_ou_assombrit_le_film(tools, film_sombre, tmp_path, cle, sens):
    from vhs_restore.probe import analyze
    info = analyze(film_sombre, tools)
    sorties = {}
    for v in (0, 3 * sens):
        chaine = pipeline.filter_chain(info, reglages(**{cle: v}))
        out = tmp_path / f"{v}.png"
        ff(*pipeline._seek(1.0, None), "-i", str(film_sombre), "-vf", f"{chaine},format=rgb24",
           "-frames:v", "3", "-update", "1", str(out))
        sorties[v] = sum(moyennes(out))
    assert (sorties[3 * sens] - sorties[0]) * sens > 30, sorties


def test_phrase_du_resume():
    assert lumiere.phrase({"lumiere": 0, "contraste": 0, "couleurs": 0, "teinte": 0}) == ""
    assert lumiere.phrase({"lumiere": 2, "contraste": 0, "couleurs": -1, "teinte": 0}) == "lumière +2, couleurs −1"


@pytest.fixture()
def fenetre(tools):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    win = MainWindow(tools)
    win.show()
    win.resize(1280, 641)

    def attendre():
        import time
        fin = time.monotonic() + 120
        while time.monotonic() < fin:
            app.processEvents()
            time.sleep(0.02)
            if (win.worker is None or not win.worker.isRunning()) and not win.assistant._en_cours \
                    and not win.lumiere.occupe():
                for _ in range(5):
                    app.processEvents()
                return
    yield win, attendre
    win.close()


@pytest.mark.assistant
def test_etape_lumiere_de_l_assistant(fenetre, film_sombre):
    win, attendre = fenetre
    win.load_file(str(film_sombre))
    attendre()
    a = win.assistant
    a.suivant.click()
    attendre()
    assert a.titre.text() == "Lumière et couleurs" and a.compteur.text() == "Étape 2 sur 5"
    p = a._page_lumiere
    premiere = win.lumiere.dernier
    assert premiere is not None and premiere.exists() and not win.lumiere.erreur
    assert win.s_compare.before is not None and win.s_compare.after is not None    # la grande image
    plus_clair = p.lignes["lumiere"][2]
    for _ in range(5):                                       # trois crans au plus
        plus_clair.click()
    attendre()
    assert p.lignes["lumiere"][1].text() == "+3" and not plus_clair.isEnabled()
    assert win.settings().lumiere == 3 and win.lumiere.dernier != premiere
    assert win.panneau_lumiere.lignes["lumiere"][1].text() == "+3"           # même valeur partout
    p.remettre.click()
    attendre()
    assert win.settings().lumiere == 0 and p.lignes["lumiere"][1].text() == "Normal"
    p.lignes["couleurs"][2].click()
    for _ in range(3):                                       # coupes, son, « Vérifier et lancer »
        a.suivant.click()
        attendre()
    assert "Lumière et couleurs : couleurs +1." in a.resume.text()
    a.voir.click()
    attendre()
    assert win.run_btn.isEnabled()
    a.aller(1)                                               # retour aux couleurs
    attendre()
    p.lignes["couleurs"][0].click()                          # réglage changé : avant / après à revoir
    attendre()
    assert not win.run_btn.isEnabled()


def test_nouveau_film_repart_de_zero(fenetre, film_sombre, tmp_path):
    win, attendre = fenetre
    win.load_file(str(film_sombre))
    attendre()
    win.lumiere.changer("teinte", 2)
    assert win.settings().teinte == 2
    autre = tmp_path / "autre.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=3", "-c:v", "libx264", str(autre))
    win.load_file(str(autre))
    attendre()
    assert win.settings().teinte == 0 and win.lumiere.dernier is None
