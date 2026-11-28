"""L'aperçu fait entendre le calage voix-lèvres que l'on retrouvera dans le film exporté.

Mesuré dans les fichiers : un éclair blanc (une image) et un bip toutes les 2 s ; l'écart
« début du bip − image de l'éclair » est relevé dans l'aperçu et dans l'export, au même instant
du film source. Constat de la vérification de bout en bout (P0) : avec une dérive (réglage au
début et à la fin), l'aperçu pris loin du début repartait de zéro pour la dérive ; à 139 s,
voix avancée de 80 ms dans l'aperçu, retardée de 130 ms dans le film exporté.
"""
import re
import shutil
import subprocess

import pytest

from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import PROFILES

FF = shutil.which("ffmpeg")


@pytest.fixture(scope="module")
def reperes(tmp_path_factory):
    """60 s, 25 images/s : éclair à 1,04 s puis toutes les 2 s ; bip 20 ms plus tard."""
    src = tmp_path_factory.mktemp("calage") / "reperes.avi"
    subprocess.run([FF, "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=0x202020:s=320x240:r=25,"
                    "drawbox=x=0:y=0:w=iw:h=ih:c=white:t=fill:enable='gte(t,1.03)*lt(mod(t-1.02,2),0.04)'",
                    "-f", "lavfi", "-i", "aevalsrc='if(gte(t,1.06)*lt(mod(t-1.06,2),0.03),"
                    "0.7*sin(2*PI*2000*t),0)':s=48000",
                    "-t", "60", "-c:v", "mpeg2video", "-b:v", "2M", "-c:a", "pcm_s16le", str(src)],
                   check=True)
    return src


def _ecarts(chemin, decalage=0.0):
    """{temps source de l'éclair (arrondi) : écart bip − éclair en ms}."""
    r = subprocess.run([FF, "-hide_banner", "-nostdin", "-i", str(chemin), "-filter_complex",
                        "[0:v:0]signalstats,metadata=print:key=lavfi.signalstats.YAVG[v];"
                        "[0:a:0]silencedetect=n=-30dB:d=0.2[a]", "-map", "[v]", "-map", "[a]",
                        "-f", "null", "-"], capture_output=True, text=True)
    eclairs, prec = [], False
    for t, y in re.findall(r"pts_time:([\d.]+)\s*\n[^\n]*?lavfi\.signalstats\.YAVG=([\d.]+)", r.stderr):
        clair = float(y) > 128
        if clair and not prec:
            eclairs.append(float(t))
        prec = clair
    bips = [float(t) for t in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    out = {}
    for e in eclairs:
        b = min(bips, key=lambda x: abs(x - e), default=None)
        if b is not None and abs(b - e) < 0.6:
            out[round(e + decalage, 1)] = (b - e) * 1000
    return out


def _comparer(info, s, tools, tmp_path, debut, nom):
    apercu = pipeline.make_preview(info, s, tools, tmp_path / f"apercu_{nom}", start=debut, duration=6)
    film = pipeline.export(info, s, tmp_path / f"film_{nom}.mp4", tools)
    dans_apercu = _ecarts(apercu.restored, decalage=apercu.start)
    dans_film = _ecarts(film)
    communs = sorted(set(dans_apercu) & set(dans_film))
    assert len(communs) >= 2, (dans_apercu, sorted(dans_film)[:5])
    return [(t, dans_apercu[t], dans_film[t]) for t in communs]


def test_calage_simple_meme_ecart_dans_l_apercu_et_le_film(reperes, tools, tmp_path):
    info = analyze(reperes, tools)
    base = pipeline.Settings(PROFILES["equilibre"])
    zero = _comparer(info, base, tools, tmp_path, 30.0, "zero")
    avance = _comparer(info, pipeline.Settings(PROFILES["equilibre"], audio_offset_ms=-80.0),
                       tools, tmp_path, 30.0, "avance")
    for (t, ap0, _f0), (_t, ap, film) in zip(zero, avance):
        assert abs(ap - film) <= 5, (t, ap, film)           # l'aperçu = le film
        assert abs((ap - ap0) - (-80)) <= 5, (t, ap0, ap)   # « Avancer la voix » × 2 : 80 ms plus tôt


def test_derive_l_apercu_du_milieu_entend_le_film(reperes, tools, tmp_path):
    """Début : voix avancée de 2 images ; fin : retardée de 3 (réglage de l'assistant)."""
    info = analyze(reperes, tools)
    reference = _ecarts(pipeline.export(info, pipeline.Settings(PROFILES["equilibre"]),
                                        tmp_path / "film_sans_reglage.mp4", tools))
    s = pipeline.Settings(PROFILES["equilibre"], audio_offset_ms=-94.0, audio_drift_ms_per_min=-92.0)
    for t, ap, film in _comparer(info, s, tools, tmp_path, 40.0, "derive"):
        assert abs(ap - film) <= 10, (t, ap, film)            # l'aperçu = le film (avant : 61 ms)
        attendu = reference[t] + (-94.0 + 92.0 * t / 60)      # correction au temps t du film
        # atempo (la dérive) avance le son d'environ 15 ms : moins d'une demi-image, mesuré
        # pareil dans l'aperçu et dans le film. Au-delà de 25 ms, quelque chose a changé.
        assert abs(film - attendu) <= 25, (t, film, attendu)
