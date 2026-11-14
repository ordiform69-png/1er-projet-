# Fabrication de l'application Windows : pyinstaller --noconfirm VHSRestoreAI.spec
# Résultat : dist/VHSRestoreAI/ (dossier autonome). FFmpeg est ajouté ensuite dans
# dist/VHSRestoreAI/tools/ffmpeg (voir .github/workflows/vhs-restore-windows.yml).
a = Analysis(
    ["VHSRestoreAI.py"],
    datas=[("vhs_restore/qtgmc.vpy", "vhs_restore")],
    # modules Qt inutiles : paquet plus léger
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtMultimedia",
              "tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VHSRestoreAI",
          console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="VHSRestoreAI", upx=False)
