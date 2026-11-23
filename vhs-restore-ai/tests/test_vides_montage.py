"""Passages vides (neige, écran bleu, noir) et montage dans un logiciel libre."""
import dataclasses
import hashlib
import http.server
import io
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore import installer, vides
from vhs_restore.tools import Tool


@pytest.fixture(scope="module")
def cassette(tmp_path_factory):
    """3 s de neige, 4 s d'image, 3 s d'écran bleu, 3 s d'image noir et blanc qui bouge, 2 s de noir."""
    d = tmp_path_factory.mktemp("cassette")
    f = d / "cassette de 1986.mp4"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x240:r=25:d=3,noise=alls=100:allf=t+u",
       "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=4",
       "-f", "lavfi", "-i", "color=c=0x1030c8:s=320x240:r=25:d=3",
       "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=3,hue=s=0",
       "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=2",
       "-f", "lavfi", "-i", "sine=f=300:sample_rate=48000:d=15",
       "-filter_complex", "[0:v][1:v][2:v][3:v][4:v]concat=n=5:v=1:a=0,format=yuv420p[v]",
       "-map", "[v]", "-map", "5:a", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-shortest", str(f))
    return f


def test_passages_trouves(tools, cassette):
    ps = vides.detecter(tools.ffmpeg.path, cassette, 15.0)
    assert [p.genre for p in ps] == ["neige ou écran gris", "écran bleu ou coloré", "écran noir"]
    for p, (a, b) in zip(ps, ((0, 3), (7, 10), (13, 15))):
        assert abs(p.debut - a) <= 0.5 and abs(p.fin - b) <= 0.5, (p, a, b)


def test_copie_sans_passages(tools, cassette, tmp_path):
    src = tmp_path / cassette.name
    shutil.copy(cassette, src)
    avant = hashlib.sha256(src.read_bytes()).hexdigest()
    ps = vides.detecter(tools.ffmpeg.path, src, 15.0)
    out = vides.retirer(tools.ffmpeg.path, src, vides.sortie_sans_vides(src), ps, 15.0, True)
    r = subprocess.run([tools.ffprobe.path, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                        "-of", "default=nw=1", str(out)], capture_output=True, text=True)
    duree = float(next(x.split("=")[1] for x in r.stdout.split() if x.startswith("duration=")))
    assert abs(duree - 7.0) < 0.3 and "codec_type=audio" in r.stdout
    assert hashlib.sha256(src.read_bytes()).hexdigest() == avant          # original intact
    assert out.name.endswith("_sans_vides.mp4") and not list(tmp_path.glob("*.partiel.*"))


def test_regroupement():
    def m(t, ecart, haut=120.0, sat=0.0):
        return {"t": t, "YLOW": haut - ecart, "YHIGH": haut, "SATAVG": sat}
    pleins = [m(i * 0.25, 120) for i in range(40)]                    # 10 s de vraie image
    assert vides.regrouper(pleins, 10) == []
    court = [m(i * 0.25, 5 if i < 6 else 120) for i in range(40)]     # 1,5 s vide : trop court
    assert vides.regrouper(court, 10) == []
    trou = [m(i * 0.25, 5 if i != 6 else 120) for i in range(16)] + [m(4 + i * 0.25, 120) for i in range(24)]
    assert len(vides.regrouper(trou, 10)) == 1                          # une image isolée ne coupe pas
    tout_vide = [m(i * 0.25, 5) for i in range(40)]
    assert vides.regrouper(tout_vide, 10) == []                         # tout le film : rien proposé


@pytest.fixture()
def fenetre(tools, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from vhs_restore.gui import MainWindow
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: None))

    def attendre(win):
        while win.worker is not None and win.worker.isRunning():
            app.processEvents()
            win.worker.wait(20)
        for _ in range(5):
            app.processEvents()
    return MainWindow, attendre


def test_bouton_retirer_les_vides(fenetre, tools, cassette, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    MainWindow, attendre = fenetre
    src = tmp_path / cassette.name
    shutil.copy(cassette, src)
    vus = []

    def exec_(self):
        vus.append(self.text())
        return 0
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: next((b for b in self.buttons() if b.text() == "Créer la copie"), None))
    win = MainWindow(tools)
    win.load_file(str(src))
    attendre(win)
    win.retirer_vides()
    attendre(win)
    attendre(win)
    assert "3 passages vides" in vus[0] and "neige" in vus[0]
    assert "_sans_vides" in win.s_fini_texte.text() and not win.s_fini.isHidden()
    assert (tmp_path / "cassette de 1986_sans_vides.mp4").is_file()
    win.close()


def test_bouton_montage(fenetre, tools, cassette, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from vhs_restore import gui
    MainWindow, attendre = fenetre
    lances, fiches = [], []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: next((b for b in self.buttons() if b.text() == "Couper ou assembler"), None))
    monkeypatch.setattr(gui, "_demarrer", lambda prog, args, dossier: lances.append((prog, args)) or True)
    sans = dataclasses.replace(tools, losslesscut=Tool("LosslessCut"))
    win = MainWindow(sans)
    monkeypatch.setattr(win, "show_tool", lambda key: fiches.append(key))
    win.load_file(str(cassette))
    attendre(win)
    win.faire_montage()                                 # pas installé : la fiche « Installer » s'ouvre
    assert fiches == ["losslesscut"] and win._montage_en_attente[0] == "losslesscut" and not lances
    exe = tmp_path / "LosslessCut"
    exe.write_text("")
    win.tools = dataclasses.replace(sans, losslesscut=Tool("LosslessCut", str(exe)))
    win.faire_montage()                                 # installé : il s'ouvre avec le film
    assert lances == [(str(exe), [str(cassette)])]
    win.close()


def test_installation_7z(tmp_path, monkeypatch):
    """LosslessCut est publié en 7z : l'extracteur 7-Zip est installé d'abord, puis utilisé."""
    root = tmp_path / "www"
    root.mkdir()
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:                  # contenu de l'archive (simulé en zip)
        f.writestr("LosslessCut.exe", b"exe")
        f.writestr("resources/ffmpeg.exe", b"ff")
    (root / "lc.7z").write_bytes(z.getvalue())
    (root / "7zr.exe").write_bytes(b"7zr factice")

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    sha = lambda n: hashlib.sha256((root / n).read_bytes()).hexdigest()   # noqa: E731
    p = dict(installer.PAQUETS)
    p["sevenzip"] = dataclasses.replace(p["sevenzip"], url=f"{base}/7zr.exe", sha256=sha("7zr.exe"))
    p["losslesscut"] = dataclasses.replace(p["losslesscut"], url=f"{base}/lc.7z", sha256=sha("lc.7z"))
    monkeypatch.setattr(installer, "PAQUETS", p)
    monkeypatch.setattr(installer, "IS_WIN", True)
    commandes = []

    def faux_run(cmd, **k):                             # 7zr.exe x archive -o<dossier> : on décompresse
        commandes.append(cmd)
        dest = Path(next(a[2:] for a in cmd if a.startswith("-o")))
        with zipfile.ZipFile(cmd[2]) as f:
            f.extractall(dest)
        return []
    monkeypatch.setattr(installer, "run", faux_run)
    try:
        exe = installer.install("losslesscut", root=tmp_path / "profil")
    finally:
        srv.shutdown()
    assert exe == tmp_path / "profil" / "losslesscut" / "LosslessCut.exe" and exe.is_file()
    assert (tmp_path / "profil" / "7zip" / "7zr.exe").is_file()          # extracteur installé d'abord
    assert commandes and commandes[0][0].endswith("7zr.exe") and commandes[0][1] == "x"
    assert sorted(x.name for x in (tmp_path / "profil").iterdir()) == ["7zip", "losslesscut"]
