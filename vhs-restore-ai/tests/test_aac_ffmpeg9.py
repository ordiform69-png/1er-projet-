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


def test_valeur_invalide_apres_rnnoise_devient_silence(tools, tmp_path):
    """Chez l'utilisateur, RNNoise a produit des NaN à la fin d'un film : l'encodeur AAC refusait
    tout (« Input contains (near) NaN »). La garde placée après arnndn les remplace par du silence."""
    import dataclasses
    from fractions import Fraction
    from vhs_restore import pipeline
    from vhs_restore.probe import MediaInfo
    from vhs_restore.profiles import profile_for
    info = MediaInfo(path=Path("x.mp4"), has_audio=True, duration=2, fps=Fraction(25))
    s = dataclasses.replace(pipeline.Settings(profile_for("equilibre", "video")), use_rnnoise=True)
    chaine = pipeline.audio_filters(info, s, rnnoise="/tmp/modele.rnnn")
    i = next(n for n, f in enumerate(chaine) if f.startswith("arnndn"))
    assert chaine[i + 1] == pipeline.GARDE_NAN
    source = "aevalsrc='if(lt(t,1),0.5*sin(2*PI*440*t),0/0)':s=48000:d=2:c=stereo"
    for garde, attendu in (([], False), (["-af", pipeline.GARDE_NAN], True)):
        out = tmp_path / f"nan-{attendu}.m4a"
        r = subprocess.run([tools.ffmpeg.path, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
                            "-f", "lavfi", "-i", source, *garde, *outils.AAC, "-b:a", "192k", str(out)],
                           capture_output=True, text=True, timeout=60)
        assert (r.returncode == 0) is attendu, r.stderr
