"""Essai du lecteur réellement livré par PyInstaller, sans écran ni périphérique audio."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from .tools import detect_tools, run_capture


def autotest_lecteur(dossier: Path) -> int:
    dossier.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    bilan = []
    code = 1
    try:
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication

        from .lecteur import Lecteur

        app = QApplication.instance() or QApplication([])
        lecteur = Lecteur(app)
        if lecteur.video is None:
            raise RuntimeError("Modules Qt du lecteur indisponibles.")
        ts = detect_tools()
        ts.require_ffmpeg()
        formats = (
            ("DVD.mpg", "720x576", ["-target", "pal-dvd"]),
            ("DV.avi", "720x576", ["-c:v", "dvvideo", "-pix_fmt", "yuv420p", "-threads:v", "1",
                                   "-aspect", "4:3", "-c:a", "pcm_s16le", "-ac", "2"]),
            ("Archive.mkv", "320x240", ["-c:v", "ffv1", "-c:a", "pcm_s16le"]),
        )
        with TemporaryDirectory(prefix="lecture-", dir=dossier) as temporaire:
            for nom, taille, options in formats:
                chemin = Path(temporaire) / nom
                commande = [ts.ffmpeg.path, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"testsrc2=size={taille}:rate=25", "-f", "lavfi", "-i",
                            "sine=sample_rate=48000", "-t", "1.4", *options, str(chemin)]
                generation = run_capture(commande, timeout=30)
                if generation.returncode:
                    raise RuntimeError(f"{nom} : création impossible. {generation.stderr[-300:]}")
                duree, raisons, boucle = [], [], QEventLoop()
                timer = QTimer(singleShot=True, interval=12000)
                timer.timeout.connect(boucle.quit)

                def progression(temps: float) -> None:
                    if temps >= 0.2 and lecteur.video.videoSink().videoFrame().isValid():
                        duree.append(temps)
                        boucle.quit()

                def echec(raison: str) -> None:
                    raisons.append(raison)
                    boucle.quit()

                lecteur.position.connect(progression)
                lecteur.echec.connect(echec)
                try:
                    lecteur.ouvrir(chemin, "original")
                    if not raisons and not duree:
                        timer.start()
                        boucle.exec()
                    if not duree or not lecteur.media.hasAudio():
                        raise RuntimeError(f"{nom} : {raisons[0] if raisons else 'image ou piste sonore absente'}")
                    bilan.append(f"{nom} : image décodée à {duree[-1]:.2f} s, piste audio reconnue.")
                finally:
                    timer.stop()
                    lecteur.position.disconnect(progression)
                    lecteur.echec.disconnect(echec)
                    lecteur.fermer()
                    app.processEvents()
        bilan.append("RÉSULTAT : OK")
        code = 0
    except Exception as exc:
        bilan.append(f"RÉSULTAT : ÉCHEC. {exc}")
    (dossier / "autotest-lecteur.txt").write_text("\n".join(bilan) + "\n", encoding="utf-8")
    return code
