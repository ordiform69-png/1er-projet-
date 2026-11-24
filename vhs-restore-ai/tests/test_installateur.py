"""Installateur : sans admin, pas d'étiquette créée, SmartScreen expliqué."""
from pathlib import Path


def test_iss_sans_admin():
    iss = Path("setup.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss
    assert "{localappdata}\\Programs\\VHS Restore AI" in iss
    assert "{userdesktop}" in iss
    assert "UninstallDelete" not in iss          # tools et réglages restent


def test_workflow_ne_cree_pas_etiquette():
    yml = Path("../.github/workflows/vhs-restore-windows.yml").read_text(encoding="utf-8")
    assert "refs/tags/v" in yml
    assert "git tag" not in yml
    assert "gh release create" not in yml or "softprops/action-gh-release" in yml


def test_smartscreen_explique():
    texte = Path("LISEZMOI.txt").read_text(encoding="utf-8")
    assert "Informations complémentaires" in texte
    assert "Exécuter quand même" in texte
