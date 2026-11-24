import os
import subprocess
import sys
from pathlib import Path


def test_quitter_pendant_sondage():
    script = """
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from vhs_restore.gui import MainWindow
from vhs_restore.tools import detect_tools, run_capture
app = QApplication([])
w = MainWindow(detect_tools())
w.show()
w._question = lambda *a: True
w._launch(lambda c,p: run_capture([sys.executable, '-c', 'import time; time.sleep(40)']), lambda r: None)
QTimer.singleShot(100, w.close)
app.exec()
assert not w.worker.isRunning() and not w.preview_dir.exists()
"""
    r = subprocess.run([sys.executable, "-c", script], timeout=15, capture_output=True,
                       cwd=Path(__file__).resolve().parents[1], env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    assert r.returncode == 0 and b"QThread: Destroyed" not in r.stderr, r.stderr


def test_cinquante_travaux_liberes():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QEventLoop, QTimer
    from vhs_restore.gui import MainWindow
    from vhs_restore.tools import detect_tools
    import gc
    import weakref
    app = QApplication.instance() or QApplication([])
    w = MainWindow(detect_tools())
    anciens = []
    for n in range(50):
        boucle = QEventLoop()
        w._launch(lambda c,p: None, lambda _: None)
        anciens.append(weakref.ref(w.worker))
        w.worker.finished.connect(boucle.quit)
        QTimer.singleShot(2000, boucle.quit)
        boucle.exec()
        app.processEvents()
        assert not w._fils
    gc.collect()
    assert sum(ref() is not None for ref in anciens) <= 1
    w.close()
