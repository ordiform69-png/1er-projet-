from pathlib import Path


def test_publication_apres_les_controles():
    texte = (Path(__file__).resolve().parents[2] / ".github/workflows/vhs-restore-windows.yml").read_text()
    suite = texte.split("uses: actions/upload-artifact@v4")[1]
    assert "if: success() && steps.tests.outcome == 'success'" in suite
    assert "github.run_number" in suite and "github.sha" in suite
    assert "Get-FileHash" in texte and "-Algorithm SHA256" in texte
