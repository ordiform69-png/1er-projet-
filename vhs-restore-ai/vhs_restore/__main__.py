"""Point d'entrée : python -m vhs_restore"""
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


if __name__ == "__main__":
    p = setup_logging()
    logging.getLogger("vhs_restore").info("Démarrage, journal : %s", p)
    from vhs_restore.gui import main
    sys.exit(main())
