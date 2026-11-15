"""Point d'entrée : python -m vhs_restore (ou VHSRestoreAI.exe une fois empaqueté).

Option --autotest DOSSIER : vérifie l'installation sans ouvrir de fenêtre (FFmpeg trouvé,
analyse puis restauration d'une courte vidéo générée), écrit autotest.txt dans DOSSIER
et renvoie 0 si tout va bien. Utilisé par l'intégration continue Windows."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/state")
    d = Path(base) / "VHSRestoreAI" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logging() -> Path:
    path = log_dir() / "vhs_restore.log"
    h = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger("vhs_restore")
    root.setLevel(logging.INFO)
    root.addHandler(h)
    return path


def autotest(folder: str) -> int:
    from vhs_restore import pipeline
    from vhs_restore.probe import analyze
    from vhs_restore.profiles import profile_for
    from vhs_restore.tools import detect_tools, run_capture
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    report, code = [f"VHS Restore AI — autotest ({sys.executable})"], 1
    try:
        import PySide6.QtWidgets  # noqa: F401  (bibliothèques Qt présentes et chargeables)
        report.append("Qt : OK")
        ts = detect_tools()
        ts.require_ffmpeg()
        report.append(f"FFmpeg {ts.ffmpeg.version} : {ts.ffmpeg.path}")
        report.append(f"Stabilisation : {'oui' if ts.stab_available else 'non'} ; "
                      f"QTGMC : {'oui' if ts.qtgmc_available else 'non'} ; "
                      f"IA : {'oui' if ts.ai_available else 'non'} ; "
                      f"DeepFilterNet : {'oui' if ts.deepfilter_available else 'non'}")
        sample = out / "échantillon été 1975.avi"
        r = run_capture([ts.ffmpeg.path, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                         "testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,setfield=tff,"
                         "setsar=16/15", "-f", "lavfi", "-i", "sine=sample_rate=48000", "-t", "2",
                         "-c:v", "mpeg2video", "-flags", "+ilme+ildct", "-b:v", "8M",
                         "-c:a", "pcm_s16le", str(sample)], timeout=120)
        if r.returncode:
            raise RuntimeError("génération de l'échantillon : " + r.stderr[-300:])
        info = analyze(sample, ts)
        report.append(f"Analyse : {info.width}x{info.height}, {float(info.fps):g} i/s, balayage {info.scan}, "
                      f"origine suggérée {info.suggested_source}, son {'oui' if info.has_audio else 'non'}")
        s = pipeline.Settings(profile_for("equilibre", info.suggested_source), source=info.suggested_source,
                              resolution="1080", stabilize=ts.stab_available)
        res = pipeline.export(info, s, out / "résultat restauré.mp4", ts)
        after = analyze(res, ts)
        report.append(f"Export : {res.name}, {after.width}x{after.height}, {float(after.fps):g} i/s, "
                      f"{after.dar.numerator}:{after.dar.denominator}, son {'oui' if after.has_audio else 'non'}")
        ok = (after.width, after.height, after.has_audio) == (1440, 1080, True) and after.fps == 50
        report.append(f"Poussières et rayures : {'oui' if ts.dust_available else 'non installé'}")
        if ts.dust_available:   # essai réel du moteur externe (sous-processus --poussieres)
            film = out / "pellicule 18 is.mkv"
            run_capture([ts.ffmpeg.path, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                         "testsrc2=size=720x540:rate=18", "-t", "2", "-c:v", "ffv1", str(film)], timeout=120)
            finfo = analyze(film, ts)
            fres = pipeline.export(finfo, pipeline.Settings(profile_for("fidele", "film"), source="film",
                                                            dust=True), out / "pellicule nettoyée.mp4", ts)
            fafter = analyze(fres, ts)
            dust_ok = fafter.fps == 18 and abs(fafter.duration - 2) < 0.2
            report.append(f"Export poussières : {fafter.width}x{fafter.height}, {float(fafter.fps):g} i/s, "
                          f"{fafter.duration:.1f} s")
            ok = ok and dust_ok
        # Mode Photo : une carte postale noir et blanc compressée en JPEG
        import hashlib
        from vhs_restore import photo
        card = out / "carte postale été.jpg"
        run_capture([ts.ffmpeg.path, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                     "mandelbrot=size=320x240", "-frames:v", "1", "-vf", "format=gray", "-q:v", "20",
                     str(card)], timeout=120)
        before = hashlib.sha256(card.read_bytes()).hexdigest()
        pinfo = photo.analyze_photo(card, ts)
        pres = photo.restore_photo(pinfo, pipeline.Settings(profile_for("equilibre")),
                                   out / "carte postale restaurée.png", ts)
        pafter = photo.analyze_photo(pres, ts)
        photo_ok = ((pafter.width, pafter.height) == (320, 240) and pafter.black_and_white
                    and hashlib.sha256(card.read_bytes()).hexdigest() == before)
        report.append(f"Photo : {pres.name}, {pafter.width}x{pafter.height}, "
                      f"{'noir et blanc conservé' if pafter.black_and_white else 'COULEUR AJOUTÉE'}, "
                      f"original {'intact' if hashlib.sha256(card.read_bytes()).hexdigest() == before else 'MODIFIÉ'}")
        ok = ok and photo_ok
        report.append("RÉSULTAT : OK" if ok else "RÉSULTAT : ÉCHEC (sortie inattendue)")
        code = 0 if ok else 1
    except Exception as exc:  # le rapport doit toujours être écrit
        import traceback
        report.append("RÉSULTAT : ÉCHEC\n" + "".join(traceback.format_exception(exc)))
    (out / "autotest.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    return code


def run() -> int:
    p = setup_logging()
    logging.getLogger("vhs_restore").info("Démarrage, journal : %s", p)
    if len(sys.argv) >= 3 and sys.argv[1] == "--autotest":
        return autotest(sys.argv[2])
    if len(sys.argv) >= 3 and sys.argv[1] == "--poussieres":   # sous-processus Analog Repair
        # Aucune exception ne doit remonter : dans l'exe Windows sans console, elle ouvrirait
        # une boîte d'erreur qui bloquerait le traitement en attendant un clic.
        try:
            from vhs_restore.dust import bridge_main
            return bridge_main(sys.argv[2])
        except BaseException as exc:  # noqa: BLE001
            import json
            logging.getLogger("vhs_restore").exception("Échec du module poussières")
            print(json.dumps({"kind": "error", "message": f"{type(exc).__name__}: {exc}"}), flush=True)
            return 1
    from vhs_restore.gui import main
    return main()


if __name__ == "__main__":
    sys.exit(run())
