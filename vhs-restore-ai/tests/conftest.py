"""Échantillons synthétiques générés par FFmpeg (aucune vraie cassette)."""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from vhs_restore.tools import Tool, detect_tools  # noqa: E402

FF = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(FF is None, reason="ffmpeg absent")


def ff(*args):
    r = subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"ffmpeg a échoué (code {r.returncode}) : {r.stderr.strip()[-800:]}\n{args}")


@pytest.fixture(scope="session")
def tools():
    t = detect_tools()
    if not t.ffmpeg.path:
        pytest.skip("ffmpeg absent")
    return t


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("échantillons à tester")
    s = {}
    # PAL entrelacé TFF, pixels 16:15 (4:3), son, nom avec accents/espaces/apostrophe
    s["pal_tff"] = d / "Vacances été 1988 l'essai.avi"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,setfield=tff,setsar=16/15",
       "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "4",
       "-c:v", "mpeg2video", "-flags", "+ilme+ildct", "-b:v", "8M",
       "-c:a", "pcm_s16le", str(s["pal_tff"]))
    # NTSC-like progressif carré, sans son
    s["prog"] = d / "progressif sans son.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=size=640x480:rate=30000/1001", "-t", "3",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", str(s["prog"]))
    # Capture SD sans information de pixel (SAR 1:1 écrit) : 4:3 doit être supposé
    s["sd_nosar"] = d / "capture_sans_sar.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25,setsar=1", "-t", "2",
       "-c:v", "ffv1", str(s["sd_nosar"]))
    # Fichier long pour l'annulation
    s["long"] = d / "long.avi"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25,setsar=16/15",
       "-f", "lavfi", "-i", "sine=sample_rate=48000", "-t", "120",
       "-c:v", "mpeg2video", "-b:v", "8M", "-c:a", "pcm_s16le", str(s["long"]))
    # Caméra « tenue à la main » : scène fixe recadrée avec un tremblement (pixels 16:15), son
    s["shaky"] = d / "caméra tremblante.avi"
    ff("-f", "lavfi", "-i", "testsrc2=size=880x700:rate=25,"
       "crop=720:576:80+40*sin(n*1.7)+18*sin(n*4.1):62+30*cos(n*2.3)+12*sin(n*3.7),setsar=16/15",
       "-f", "lavfi", "-i", "sine=sample_rate=48000", "-t", "6",
       "-c:v", "mpeg2video", "-b:v", "10M", "-c:a", "pcm_s16le", str(s["shaky"]))
    # Image détaillée propre + même image avec un bruit analogique (fort sur la chroma, temporel)
    s["clean"] = d / "propre.mkv"
    ff("-f", "lavfi", "-i", "mandelbrot=size=720x576:rate=25,format=yuv420p,setsar=16/15", "-t", "2",
       "-c:v", "ffv1", str(s["clean"]))
    s["noisy"] = d / "bruité.mkv"
    ff("-i", str(s["clean"]), "-vf", "noise=c0s=10:c1s=22:c2s=22:allf=t", "-c:v", "ffv1", str(s["noisy"]))
    # Pellicules de synthèse : 18 i/s progressif avec grain, muet / sonore / noir et blanc
    grain = "noise=c0s=14:c1s=4:c2s=4:allf=t"
    s["film18"] = d / "super 8 été 1975.mkv"
    ff("-f", "lavfi", "-i", f"testsrc2=size=720x540:rate=18,{grain}", "-t", "6",
       "-c:v", "ffv1", str(s["film18"]))
    s["film18_son"] = d / "super 8 sonore.mkv"
    ff("-f", "lavfi", "-i", f"testsrc2=size=720x540:rate=18,{grain}",
       "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000", "-t", "6",
       "-c:v", "ffv1", "-c:a", "flac", str(s["film18_son"]))
    s["film_nb"] = d / "film noir et blanc.mkv"
    ff("-f", "lavfi", "-i", f"testsrc2=size=720x540:rate=16,hue=s=0,{grain}", "-t", "4",
       "-c:v", "ffv1", str(s["film_nb"]))
    # Pellicule 18 i/s copiée sur vidéo 25i (trames réparties sur les images de film), son
    s["transfert"] = d / "super 8 copié sur VHS.avi"
    ff("-f", "lavfi", "-i", f"testsrc2=size=720x576:rate=18,{grain},fps=50,"
       "tinterlace=mode=interleave_top,setfield=tff,setsar=16/15,noise=c0s=5:c1s=12:c2s=12:allf=t",
       "-f", "lavfi", "-i", "sine=sample_rate=48000", "-t", "6",
       "-c:v", "mpeg2video", "-flags", "+ilme+ildct", "-b:v", "9M",
       "-c:a", "pcm_s16le", str(s["transfert"]))
    s["corrupt"] = d / "abîmé.avi"
    s["corrupt"].write_bytes(os.urandom(20000))
    return s


@pytest.fixture()
def fake_ai(tmp_path, tools):
    """Faux realesrgan-ncnn-vulkan : agrandit x4 via ffmpeg (valide l'orchestration, pas la qualité IA)."""
    if os.name == "nt":
        pytest.skip("faux exécutable POSIX")
    d = tmp_path / "realesrgan"
    (d / "models").mkdir(parents=True)
    (d / "models" / "realesrgan-x4plus.param").write_text("fake")
    exe = d / "realesrgan-ncnn-vulkan"
    exe.write_text(f"""#!{sys.executable}
import sys, subprocess, pathlib
a = sys.argv[1:]
i, o = pathlib.Path(a[a.index('-i') + 1]), pathlib.Path(a[a.index('-o') + 1])
s = int(a[a.index('-s') + 1])
for p in sorted(i.glob('*.png')):
    subprocess.run([{FF!r}, '-loglevel', 'error', '-y', '-i', str(p), '-vf',
                    f'scale=iw*{{s}}:ih*{{s}}:flags=neighbor', str(o / p.name)], check=True)
""")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    import dataclasses
    return dataclasses.replace(tools, realesrgan=Tool("Real-ESRGAN", str(exe), "fake"))


def probe_json(path):
    import json
    out = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-count_frames", "-print_format", "json",
                          "-show_streams", "-show_format", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)
