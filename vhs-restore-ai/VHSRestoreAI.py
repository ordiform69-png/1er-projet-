"""Lanceur utilisé pour fabriquer l'exécutable Windows (PyInstaller)."""
import sys

from vhs_restore.__main__ import run

sys.exit(run())
