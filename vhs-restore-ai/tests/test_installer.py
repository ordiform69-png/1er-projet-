"""Installation des outils facultatifs depuis l'application (voyants ○ cliquables).

Un petit serveur HTTP local remplace GitHub / Hugging Face : on vérifie la mise en place,
le refus d'un fichier à la mauvaise empreinte, l'annulation (rien d'installé à moitié), le
refus d'une archive piégée, et que l'outil installé dans le profil est bien trouvé.
"""
import dataclasses
import hashlib
import http.server
import io
import os
import shutil
import ssl
import threading
import urllib.error
import zipfile
from pathlib import Path

import pytest

from vhs_restore import installer, tools as tools_mod
from vhs_restore.tools import EXE, Cancelled, ToolError


@pytest.fixture()
def serveur(tmp_path):
    root = tmp_path / "www"
    root.mkdir()
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("realesrgan-ncnn-vulkan.exe", b"exe factice")
        f.writestr("models/realesrgan-x4plus.param", b"param")
        f.writestr("models/realesrgan-x4plus.bin", b"poids")
    (root / "re.zip").write_bytes(z.getvalue())
    (root / "df.exe").write_bytes(b"deep filter factice" * 1000)
    piege = io.BytesIO()
    with zipfile.ZipFile(piege, "w") as f:
        f.writestr("../../hors_du_dossier.txt", b"x")
        f.writestr("realesrgan-ncnn-vulkan.exe", b"x")
    (root / "piege.zip").write_bytes(piege.getvalue())

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    sha = {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in ("re.zip", "df.exe", "piege.zip")}
    yield base, sha
    srv.shutdown()


@pytest.fixture()
def paquets(serveur, monkeypatch):
    base, sha = serveur
    monkeypatch.setattr(installer, "IS_WIN", True)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    p = dict(installer.PAQUETS)
    p["realesrgan"] = dataclasses.replace(p["realesrgan"], url=f"{base}/re.zip", sha256=sha["re.zip"])
    p["deepfilter"] = dataclasses.replace(p["deepfilter"], url=f"{base}/df.exe", sha256=sha["df.exe"])
    monkeypatch.setattr(installer, "PAQUETS", p)
    return base, sha


def test_installe_et_range(paquets, tmp_path):
    root = tmp_path / "profil"
    msgs = []
    exe = installer.install("realesrgan", root=root, progress=lambda f, m: msgs.append((f, m)))
    assert exe == root / "realesrgan" / "realesrgan-ncnn-vulkan.exe" and exe.is_file()
    assert (root / "realesrgan" / "models" / "realesrgan-x4plus.param").is_file()
    assert msgs[-1][0] == 1.0
    df = installer.install("deepfilter", root=root)
    assert df.read_bytes().startswith(b"deep filter factice")
    assert sorted(p.name for p in root.iterdir()) == ["deepfilter", "realesrgan"]   # pas de reste temporaire
    installer.install("realesrgan", root=root)                                        # réinstaller : remplace
    assert exe.is_file()


def test_mauvaise_empreinte_refusee(paquets, tmp_path, monkeypatch):
    p = dict(installer.PAQUETS)
    p["deepfilter"] = dataclasses.replace(p["deepfilter"], sha256="0" * 64)
    monkeypatch.setattr(installer, "PAQUETS", p)
    root = tmp_path / "profil"
    with pytest.raises(ToolError, match="empreinte"):
        installer.install("deepfilter", root=root)
    assert not (root / "deepfilter").exists() and list(root.iterdir()) == []


def test_annulation_rien_a_moitie(paquets, tmp_path):
    root = tmp_path / "profil"
    stop = threading.Event()
    stop.set()
    with pytest.raises(Cancelled):
        installer.install("deepfilter", root=root, cancel=stop)
    assert list(root.iterdir()) == []


def test_archive_piegee_refusee(paquets, tmp_path, monkeypatch):
    base, sha = paquets
    p = dict(installer.PAQUETS)
    p["realesrgan"] = dataclasses.replace(p["realesrgan"], url=f"{base}/piege.zip", sha256=sha["piege.zip"])
    monkeypatch.setattr(installer, "PAQUETS", p)
    root = tmp_path / "profil"
    with pytest.raises(ToolError, match="suspect"):
        installer.install("realesrgan", root=root)
    assert not (tmp_path / "hors_du_dossier.txt").exists() and list(root.iterdir()) == []


def test_qtgmc_et_ffmpeg_ne_s_installent_pas():
    assert not installer.can_install("qtgmc") and not installer.can_install("ffmpeg")


def test_outil_du_profil_trouve(tmp_path, monkeypatch):
    """Un outil installé dans le profil sert encore après une nouvelle version du logiciel."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("VHSRA_REALESRGAN", raising=False)
    monkeypatch.setattr(tools_mod, "TOOLS_DIR", tmp_path / "application" / "tools")   # nouvelle version vide
    d = tools_mod.user_tools_dir() / "realesrgan"
    (d / "models").mkdir(parents=True)
    exe = d / f"realesrgan-ncnn-vulkan{EXE}"
    exe.write_bytes(b"x")
    os.chmod(exe, 0o755)
    (d / "models" / "realesrgan-x4plus.param").write_text("p")
    t = tools_mod.detect_tools()
    assert t.realesrgan.path == str(exe) and t.ai_available


def test_voyant_cliquable_propose_installer(paquets, tools, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from vhs_restore.gui import MainWindow
    QApplication.instance() or QApplication([])
    vus = []

    def exec_(self):
        vus.append((self.windowTitle(), [b.text() for b in self.buttons()]))
        return 0
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    sans = dataclasses.replace(tools, deepfilter=tools_mod.Tool("DeepFilterNet"))
    win = MainWindow(sans)
    assert win.voyants["deepfilter"].text().startswith("○")
    win.voyants["deepfilter"].click()
    titre, boutons = vus[-1]
    assert titre == "DeepFilterNet" and any(b.startswith("Installer") for b in boutons)
    win.voyants["qtgmc"].click()                          # QTGMC : explication, pas d'installation
    assert not any(b.startswith("Installer") for b in vus[-1][1])
    win.close()


def test_telechargement_coupe_reessaye(tmp_path, monkeypatch):
    """Connexion coupée au milieu (gros paquets de 150 à 225 Mo) : nouvel essai, pas « fichier pas bon »."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(installer.time, "sleep", lambda _s: None)
    data = os.urandom(300_000)
    essais = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            essais.append(1)
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if len(essais) == 1:
                self.wfile.write(data[:100_000])
                self.wfile.flush()
                self.connection.shutdown(2)
                return
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        installer._download(f"http://127.0.0.1:{srv.server_address[1]}/x", tmp_path / "x",
                            hashlib.sha256(data).hexdigest(), None, None, "Essai")
    finally:
        srv.shutdown()
    assert len(essais) == 2 and (tmp_path / "x").read_bytes() == data


def _certificat_refuse(*_a, **_k):
    """Le message exact vu chez l'utilisateur (Windows, PC principal, connexion qui marche)."""
    raise urllib.error.URLError(ssl.SSLCertVerificationError(
        1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get issuer certificate "
           "(_ssl.c:1010)"))


def test_certificat_refuse_passe_par_curl_de_windows(paquets, tmp_path, monkeypatch):
    """Python refuse le certificat alors que la connexion marche : le fichier est repris par
    curl.exe (certificats de Windows), son empreinte vérifiée, sans trois essais inutiles."""
    curl = shutil.which("curl")
    if curl is None:
        pytest.skip("curl absent")
    essais = []

    def refus(*a, **k):
        essais.append(1)
        _certificat_refuse()
    monkeypatch.setattr(installer.urllib.request, "urlopen", refus)
    monkeypatch.setattr(installer, "_curl_windows", lambda: curl)
    avancees = []
    chemin = installer.install("realesrgan", root=tmp_path / "outils",
                               progress=lambda f, m: avancees.append((f, m)))
    assert chemin.is_file() and chemin.read_bytes() == b"exe factice"
    assert len(essais) == 1                              # pas trois essais ni 30 s d'attente
    assert avancees and avancees[-1][0] == 1.0


def test_certificat_refuse_sans_curl_message_juste(paquets, tmp_path, monkeypatch):
    """Sans curl.exe : on ne dit pas « Vérifiez la connexion Internet » à quelqu'un de connecté."""
    monkeypatch.setattr(installer.urllib.request, "urlopen", _certificat_refuse)
    monkeypatch.setattr(installer, "_curl_windows", lambda: None)
    with pytest.raises(ToolError) as e:
        installer.install("realesrgan", root=tmp_path / "outils")
    texte = str(e.value)
    assert "certificat" in texte and "connexion n'est pas en cause" in texte
    assert "Vérifiez la connexion Internet" not in texte
    assert not (tmp_path / "outils" / installer.PAQUETS["realesrgan"].folder).exists()


def test_certificat_refuse_curl_mauvais_fichier_refuse(paquets, tmp_path, monkeypatch):
    curl = shutil.which("curl")
    if curl is None:
        pytest.skip("curl absent")
    monkeypatch.setattr(installer.urllib.request, "urlopen", _certificat_refuse)
    monkeypatch.setattr(installer, "_curl_windows", lambda: curl)
    p = dict(installer.PAQUETS)
    p["realesrgan"] = dataclasses.replace(p["realesrgan"], sha256="0" * 64)
    monkeypatch.setattr(installer, "PAQUETS", p)
    with pytest.raises(ToolError, match="empreinte différente"):
        installer.install("realesrgan", root=tmp_path / "outils")
    assert not (tmp_path / "outils" / p["realesrgan"].folder).exists()


def test_installation_script_et_interface_partagent_le_manifeste():
    script = (Path(__file__).resolve().parents[1] / "scripts/installer_outils.ps1").read_text(encoding="utf-8-sig")
    assert "-m vhs_restore.installer" in script
    assert "Invoke-WebRequest" not in script
    for p in installer.PAQUETS.values():
        assert len(bytes.fromhex(p.sha256)) == 32


def test_validation_des_membres_avant_extraction(tmp_path):
    with pytest.raises(ToolError, match="suspect"):
        installer._membre(tmp_path / "installe", "../installe-voisin/hors.txt")
    with pytest.raises(ToolError, match="lien suspect"):
        installer._verifier_liste_7z("Path = fichier\nSymbolic Link = voisin", tmp_path)
