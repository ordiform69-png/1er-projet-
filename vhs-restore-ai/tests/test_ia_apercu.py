"""Vérifications des traitements IA réellement effectués."""

import pytest

from test_calage_apercu_export import _ecarts, reperes
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import PROFILES


def test_deepfilter_conserve_les_reperes(reperes, tools, tmp_path):
    if not tools.deepfilter.ok:
        pytest.skip("DeepFilterNet absent")
    info = analyze(reperes, tools)
    s = pipeline.Settings(PROFILES["maximum"])
    wav = pipeline._try_deepfilter(info, s, tools, tmp_path, 0, 8, None)
    assert wav is not None
    import subprocess
    film = tmp_path / "repere.mkv"
    subprocess.run([tools.ffmpeg.path, "-v", "error", "-i", str(reperes), "-i", str(wav),
                    "-map", "0:v", "-map", "1:a", "-c:v", "ffv1", "-c:a", "copy", "-t", "8", str(film)], check=True)
    # Même conteneur et horloge vidéo pour les deux pistes.
    avant = tmp_path / "source.mkv"
    subprocess.run([tools.ffmpeg.path, "-v", "error", "-i", str(reperes), "-i",
                    str(tmp_path / "son_source.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "ffv1", "-c:a", "copy", "-t", "8", str(avant)], check=True)
    ref, traite = _ecarts(avant), _ecarts(film)
    communs = ref.keys() & traite.keys()
    assert len(communs) >= 2
    assert max(abs(traite[t] - ref[t]) for t in communs) <= 5


@pytest.mark.parametrize("absent", [True, False], ids=["absent", "en-erreur"])
def test_repli_visible_dans_apercu_et_bilan(absent, tools, samples, tmp_path, monkeypatch):
    from dataclasses import replace
    import sys
    from test_apercu_perime import wait
    from PySide6.QtWidgets import QApplication, QMessageBox
    from vhs_restore.gui import MainWindow
    from vhs_restore.tools import Tool

    app = QApplication.instance() or QApplication([])
    # Python quitte en erreur sur les options du binaire DeepFilterNet.
    outils = replace(tools, deepfilter=Tool("DeepFilterNet", None if absent else sys.executable))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    win = MainWindow(outils)
    try:
        win.load_file(str(samples["pal_tff"]))
        wait(app, win)
        win.profile_buttons["maximum"].setChecked(True)
        win.ai_check.setChecked(False)
        win.audio_check.setChecked(True)
        win.out_edit.setText(str(tmp_path))
        win.start_preview()
        wait(app, win)
        message = "DeepFilterNet indisponible. Le nettoyage habituel a été utilisé."
        assert message in win.status.text()
        win.start_export()
        wait(app, win)
        assert message in win.s_fini_texte.text()
    finally:
        win.close()


def test_apercu_sans_ia_annonce_le_choix(tools, samples, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    import time
    from test_apercu_perime import wait
    from PySide6.QtWidgets import QApplication, QMessageBox
    from vhs_restore.gui import MainWindow, Worker
    from vhs_restore.tools import Tool

    app = QApplication.instance() or QApplication([])
    win = MainWindow(replace(tools, realesrgan=Tool("Real-ESRGAN", tools.ffmpeg.path)))
    secondes = [0]
    demandes = []

    def mesure(moteur, src, dst, cancel=None):
        secondes[0] += 9 * len(list(src.glob("*.png")))

    def sans(worker, estimation, *args):
        demandes.append(estimation)
        return "sans"

    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(Worker, "demander_ia", sans)
    monkeypatch.setattr(pipeline.RealEsrganUpscaler, "upscale_dir", mesure)
    monkeypatch.setattr(pipeline, "time", SimpleNamespace(monotonic=lambda: time.monotonic() + secondes[0]))
    try:
        win.load_file(str(samples["pal_tff"]))
        wait(app, win)
        win.ai_check.setChecked(True)
        win.start_preview()
        wait(app, win)
        assert demandes and demandes[0] > 120
        assert win.ai_check.isChecked()
        assert win.compare.after_label == "APRÈS (sans IA)"
        assert "Aperçu prêt sans agrandissement IA." in win.status.text()
    finally:
        win.close()


@pytest.fixture
def outils_ia(tmp_path, monkeypatch):
    """Même contrat que l'exécutable portable : dossier de PNG en entrée et en sortie."""
    import os
    import sys
    from vhs_restore.tools import detect_tools

    script = tmp_path / "agrandir.py"
    script.write_text("""import subprocess, sys
from pathlib import Path
src = Path(sys.argv[sys.argv.index('-i') + 1])
dst = Path(sys.argv[sys.argv.index('-o') + 1])
subprocess.run(['ffmpeg', '-v', 'error', '-i', str(src / '%08d.png'),
                '-vf', 'scale=iw*4:ih*4', '-threads', '1', '-start_number', '0',
                str(dst / '%08d.png')], check=True)
""", encoding="utf-8")
    if os.name == "nt":
        exe = tmp_path / "agrandir.cmd"
        exe.write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        exe = script
        exe.write_text(f"#!{sys.executable}\n" + script.read_text())
        exe.chmod(0o755)
    model = tmp_path / "models" / "realesrgan-x4plus.param"
    model.parent.mkdir()
    model.touch()
    monkeypatch.setenv("VHSRA_REALESRGAN", str(exe))
    outils = detect_tools()
    assert outils.ai_available
    return outils


def test_ia_garde_chaque_image_des_paquets(outils_ia, tmp_path, monkeypatch):
    import subprocess
    from conftest import ff

    # Huit bandes codent en binaire le numéro de chaque image.
    src = tmp_path / "numeros.avi"
    ff("-f", "lavfi", "-i", "nullsrc=s=64x48:r=25,geq=lum='32+180*mod(trunc(N/pow(2,trunc(X/8))),2)':cb=128:cr=128",
       "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "5.24",
       "-c:v", "mpeg2video", "-c:a", "pcm_s16le", str(src))
    def numeros(film):
        donnees = subprocess.check_output([outils_ia.ffmpeg.path, "-v", "error", "-i", str(film),
                                          "-an", "-vf", "scale=64:48", "-fps_mode", "passthrough",
                                          "-pix_fmt", "gray", "-f", "rawvideo", "-"])
        return [sum((donnees[i + 24*64 + 8*b + 4] > 128) << b for b in range(8))
                for i in range(0, len(donnees), 64*48)]

    reference, tailles = [], []
    agrandir = pipeline.RealEsrganUpscaler.upscale_dir
    def compter(moteur, entree, sortie, **kwargs):
        if not reference:
            reference.extend(numeros(entree.parent / "inter.mkv"))
        tailles.append(len(list(entree.glob("*.png"))))
        return agrandir(moteur, entree, sortie, **kwargs)

    monkeypatch.setattr(pipeline.RealEsrganUpscaler, "upscale_dir", compter)
    s = pipeline.Settings(PROFILES["equilibre"], resolution="96", use_ai=True)
    film = pipeline.export(analyze(src, outils_ia), s, tmp_path / "film.mp4", outils_ia)
    assert reference == list(range(131))
    assert tailles == [60, 60, 11]
    assert numeros(film) == reference


@pytest.fixture(scope="module", params=["avi", "mkv"])
def court_a_reperes(request, reperes, tmp_path_factory):
    from conftest import ff

    ext = request.param
    film = tmp_path_factory.mktemp(ext) / ("court." + ext)
    ff("-i", str(reperes), "-t", "8", "-vf", "scale=64:48",
       "-c:v", "mpeg2video" if ext == "avi" else "ffv1", "-c:a", "pcm_s16le", str(film))
    return film


@pytest.mark.parametrize("derive,retard", [(0, 0), (400, 0), (-400, 0), (0, 80)])
def test_calage_ia_comme_export_normal(court_a_reperes, derive, retard, outils_ia, tmp_path):
    from dataclasses import replace

    info = analyze(court_a_reperes, outils_ia)
    s = pipeline.Settings(PROFILES["equilibre"], resolution="96", audio_drift_ms_per_min=derive,
                          audio_offset_ms=retard)
    mesures = {}
    for ia in (False, True):
        choix = replace(s, use_ai=ia)
        cible = tmp_path / f"film-{ia}.mp4"
        pipeline.export(info, choix, cible, outils_ia)
        mesures[ia, "film"] = _ecarts(cible)
        for debut in (0, 4):
            extrait = pipeline.make_preview(info, choix, outils_ia, tmp_path / f"ap-{ia}-{debut}", debut, 2)
            mesures[ia, debut] = _ecarts(extrait.restored, debut)
    for passage in ("film", 0, 4):
        avant, apres = mesures[False, passage], mesures[True, passage]
        assert avant and avant.keys() == apres.keys()
        erreurs = [abs(avant[t] - apres[t]) for t in avant]
        print(court_a_reperes.suffix, derive, retard, passage, "écart maximal", max(erreurs))
        assert max(erreurs) <= 5
