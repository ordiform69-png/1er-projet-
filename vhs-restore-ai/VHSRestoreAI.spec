# Fabrication de l'application Windows : pyinstaller --noconfirm VHSRestoreAI.spec
# Résultat : dist/VHSRestoreAI/ (dossier autonome). FFmpeg est ajouté ensuite dans
# dist/VHSRestoreAI/tools/ffmpeg (voir .github/workflows/vhs-restore-windows.yml).
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Module « poussières et rayures » (Analog Repair) : inclus s'il est installé.
try:
    _dust_mods, _dust_data = collect_submodules("analogrepair"), collect_data_files("analogrepair")
except Exception:
    _dust_mods, _dust_data = [], []

a = Analysis(
    ["VHSRestoreAI.py"],
    datas=[("vhs_restore/paquets.json", "vhs_restore"),
           ("vhs_restore/qtgmc.vpy", "vhs_restore"),
           ("vhs_restore/models/rnnoise_std.rnnn", "vhs_restore/models"),
           ("vhs_restore/models/RNNOISE-LICENSE.txt", "vhs_restore/models"),
           ("vhs_restore/assets/fonts", "vhs_restore/assets/fonts"),
           ("vhs_restore/assets/icons", "vhs_restore/assets/icons"),
           *_dust_data],
    hiddenimports=_dust_mods,
    # modules Qt inutiles : paquet plus léger
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtMultimedia",
              "tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VHSRestoreAI",
          console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="VHSRestoreAI", upx=False)
