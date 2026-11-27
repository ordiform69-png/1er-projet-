"""Programme d'installation (Inno Setup) : une icône « VHS Restore AI » sur le bureau, sans droits
d'administrateur. Inno Setup ne tourne que sous Windows : ici, on vérifie ce qui casserait la
fabrication sans bruit (encodage pour PowerShell 5.1, empreinte figée, icône, appels)."""
import re
import struct
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def test_script_inno_setup():
    brut = (RACINE / "installateur" / "VHSRestoreAI.iss").read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf")                     # accents lus en UTF-8 par ISCC
    t = brut.decode("utf-8-sig")
    assert "PrivilegesRequired=lowest" in t                     # pas de mot de passe administrateur
    assert re.search(r"^AppId=\{\{[0-9A-F-]{36}\}\r?$", t, re.M)   # même identifiant : mise à jour par-dessus
    assert '"{autodesktop}\\VHS Restore AI"' in t and '"{autoprograms}\\VHS Restore AI"' in t
    assert "compiler:Languages\\French.isl" in t
    assert "recursesubdirs" in t and '{app}\\_internal' in t
    assert "SetupIconFile={#Icone}" in t


def test_script_powershell_pour_windows_5_1():
    brut = (RACINE / "scripts" / "installateur.ps1").read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf") and b"\r\n" in brut and b"\n" not in brut.replace(b"\r\n", b"")
    t = brut.decode("utf-8-sig")
    sha = re.search(r"\$innoSha = '([0-9A-F]+)'", t).group(1)
    assert len(sha) == 64
    url = re.search(r"\$innoUrl = '([^']+)'", t).group(1)
    assert url.endswith("innosetup-6.7.4.exe") and "is-6_7_4" in url
    assert "/CURRENTUSER" in t and "Get-FileHash" in t


def test_icone_et_appels():
    ico = (RACINE / "vhs_restore" / "assets" / "VHSRestoreAI.ico").read_bytes()
    reserve, genre, nombre = struct.unpack_from("<HHH", ico, 0)
    assert (reserve, genre) == (0, 1)                           # un vrai fichier d'icônes
    tailles = {(ico[6 + 16 * i] or 256, ico[7 + 16 * i] or 256) for i in range(nombre)}
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= tailles
    spec = (RACINE / "VHSRestoreAI.spec").read_text(encoding="utf-8")
    assert 'icon="vhs_restore/assets/VHSRestoreAI.ico"' in spec and '"vhs_restore/assets/VHSRestoreAI.ico"' in spec
    local = (RACINE / "scripts" / "fabriquer_exe.ps1").read_bytes().decode("utf-8-sig")
    assert "installateur.ps1" in local
    ci = (RACINE.parent / ".github" / "workflows" / "vhs-restore-windows.yml").read_text(encoding="utf-8")
    assert "./scripts/installateur.ps1" in ci
