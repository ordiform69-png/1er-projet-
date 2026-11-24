"""Son AAC : FFmpeg 9.1 (installé par le logiciel sous Windows) tournait sans fin sur un son bref
suivi d'un silence parfait avec la méthode d'encodage par défaut. Le logiciel utilise « fast »."""
import re
import subprocess
from pathlib import Path

from vhs_restore import tools as outils


def test_bip_puis_silence_se_termine(tools, tmp_path):
    out = tmp_path / "bip.mp4"
    cmd = [tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-f", "lavfi", "-i", "color=black:s=128x96:r=25:d=2",
           "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*440*t)*between(t,0.6,0.68)':s=48000",
           "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", *outils.AAC, "-b:a", "192k", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)   # bloqué : échec, pas d'attente
    assert r.returncode == 0, r.stderr
    assert out.stat().st_size > 1000


def test_tout_encodage_aac_passe_par_la_constante():
    """Aucun « -c:a aac » écrit à la main : il oublierait la méthode « fast »."""
    dossier = Path(outils.__file__).parent
    fautifs = [f"{p.name}:{n}" for p in dossier.glob("*.py") for n, ligne in
               enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
               if re.search(r'"-c:a",\s*"aac"', ligne) and "AAC = " not in ligne]
    assert not fautifs, fautifs
