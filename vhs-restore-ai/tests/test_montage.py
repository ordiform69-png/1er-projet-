"""Passages enlevés au milieu du film : une seule compression."""
from fractions import Fraction

import pytest

from conftest import probe_json
from vhs_restore import pipeline
from vhs_restore.probe import MediaInfo, analyze
from vhs_restore.profiles import profile_for
from vhs_restore.tools import ToolError


def test_passages_gardes_sans_coupe():
    assert pipeline.passages_gardes(4, 0, 0, []) == [(0.0, 4.0)]
    assert pipeline.passages_gardes(4, 1, 0, []) == [(1.0, 4.0)]
    assert pipeline.passages_gardes(4, 0, 2.5, []) == [(0.0, 2.5)]
    assert pipeline.passages_gardes(4, 1, 99, []) == [(1.0, 4.0)]   # fin ramenée au film
    with pytest.raises(ToolError, match="après le début"):
        pipeline.passages_gardes(4, 2, 2.2, [])
    with pytest.raises(ToolError, match="après la fin"):
        pipeline.passages_gardes(4, 5, 0, [])


def test_passages_gardes_coupe_au_milieu():
    assert pipeline.passages_gardes(10, 0, 0, [(3, 5)]) == [(0.0, 3.0), (5.0, 10.0)]
    # la coupe est ramenée dans la fenêtre (le film va de 1 s à 9 s)
    assert pipeline.passages_gardes(10, 1, 9, [(0, 4)]) == [(4.0, 9.0)]


def test_passages_gardes_coupes_fusionnees():
    # recouvrement (2–4 et 3–5) puis contact (5–6) : une seule coupe de 2 à 6
    assert pipeline.passages_gardes(12, 0, 0, [(2, 4), (3, 5), (5, 6)]) == [(0.0, 2.0), (6.0, 12.0)]
    # 0,4 s entre deux coupes : ce morceau gardé est trop court, il est abandonné
    assert pipeline.passages_gardes(10, 0, 0, [(1, 3), (3.4, 5)]) == [(0.0, 1.0), (5.0, 10.0)]


def test_passages_gardes_coupe_hors_fenetre():
    assert pipeline.passages_gardes(10, 2, 8, [(0, 1.5), (9, 10)]) == [(2.0, 8.0)]


def test_passages_gardes_tout_coupe():
    with pytest.raises(ToolError, match="Il ne resterait plus rien du film"):
        pipeline.passages_gardes(8, 0, 0, [(0, 3), (3, 8)])
    with pytest.raises(ToolError, match="au moins un passage"):
        pipeline.passages_gardes(5, 0, 0, [(0, 2.3), (2.6, 5)])


def test_passages_gardes_coupe_trop_courte():
    # moins de 0,5 s : ignorée, le film entier reste
    assert pipeline.passages_gardes(10, 0, 0, [(4, 4.4)]) == [(0.0, 10.0)]
    # 0,5 s pile : la coupe est prise en compte
    assert pipeline.passages_gardes(10, 0, 0, [(4, 4.5)]) == [(0.0, 4.0), (4.5, 10.0)]


def test_filtres_passages():
    chaine = "hqdn3d=3:5:4.5:7,format=yuv420p"
    graphe = pipeline.filtres_passages(chaine, [(0, 1), (2, 4)], audio=False)
    assert graphe.count("hqdn3d") == 1
    assert graphe.count("split=") == 1
    assert graphe.count("concat=") == 1
    assert "trim=" in graphe and "setpts=PTS-STARTPTS" in graphe
    assert "trim=start=0.000:end=1.000" in graphe
    assert "trim=start=2.000:end=4.000" in graphe
    assert graphe.endswith("concat=n=2:v=1:a=0")
    assert not graphe.split(";")[-1].endswith("]")

    son = pipeline.filtres_passages("", [(0, 1), (2, 4)], audio=True)
    assert son.startswith("asplit=2")
    assert son.count("asplit=") == 1
    assert "atrim=start=0.000:end=1.000" in son
    assert "asetpts=PTS-STARTPTS" in son
    assert son.endswith("concat=n=2:v=0:a=1")
    assert not son.split(";")[-1].endswith("]")

    # la chaîne audio d'origine n'est pas répétée sur chaque passage
    enveloppe = pipeline.filtres_passages("afftdn=nr=10", [(0, 1), (1.5, 3), (3.5, 4)], audio=True)
    assert enveloppe.count("afftdn") == 1
    assert enveloppe.endswith("concat=n=3:v=0:a=1")


def _v_a(path):
    d = probe_json(path)
    v = next(x for x in d["streams"] if x["codec_type"] == "video")
    a = [x for x in d["streams"] if x["codec_type"] == "audio"]
    return v, a


def test_export_passages_milieu(samples, tools, tmp_path):
    info = analyze(samples["pal_tff"], tools)       # 4 s, entrelacé, avec son
    s = pipeline.Settings(profile_for("equilibre", "video"), deinterlacer="bwdif")
    assert not s.use_ai
    out = pipeline.export(info, s, tmp_path / "milieu.mp4", tools,
                          passages=[(0, 1), (2, 4)])
    v, a = _v_a(out)
    # Les pistes du PAL de test commencent à des dates différentes. Comparer leurs fins.
    fin_image = float(v["start_time"]) + float(v["duration"])
    assert abs(fin_image - 3.0) < 0.04
    assert len(a) == 1
    fin_son = float(a[0]["start_time"]) + float(a[0]["duration"])
    assert abs(fin_image - fin_son) < 0.04


def test_export_milieu_refuse_les_options(tools, tmp_path):
    info = MediaInfo(path=tmp_path / "film.mkv", duration=8, width=720, height=576,
                     fps=Fraction(18), has_audio=True)
    passages = [(1.0, 2.0), (3.0, 5.0)]
    cas = [
        pipeline.Settings(profile_for("equilibre", "video"), use_ai=True),
        pipeline.Settings(profile_for("fidele", "film"), source="film", dust=True),
        pipeline.Settings(profile_for("equilibre", "video"), tape_noise=True),
        pipeline.Settings(profile_for("equilibre", "video"), chroma_repair=True),
        pipeline.Settings(profile_for("equilibre", "video"), dropouts=True),
        pipeline.Settings(profile_for("fidele", "film"), source="film", playback_fps=Fraction(24)),
    ]
    for s in cas:
        with pytest.raises(ToolError, match="passage au milieu"):
            pipeline.export(info, s, tmp_path / "out.mp4", tools, passages=passages)


def test_fin_inconnue():
    _, debut, longueur = pipeline.bornes_a_exporter(0, 5, 0, [])
    assert debut == 5 and longueur is None
    assert pipeline._seek(debut, longueur) == ["-ss", "5.000"]


@pytest.mark.parametrize("offset,derive", [(400, 0), (-400, 0), (0, 600)])
def test_clap_apres_raccord(tmp_path, tools, offset, derive):
    from conftest import ff
    from vhs_restore.probe import analyze
    import subprocess
    import numpy as np
    # La piste source comporte deux bips dont l'avance reproduit le défaut à réparer.
    facteur = 1 / (1 - derive / 60000)
    bips = [(t - offset / 1000) * facteur for t in (1, 5)]
    signal = "+".join(f"between(t,{t},{t+0.08})" for t in bips)
    src = tmp_path / "clap.mkv"
    ff("-f", "lavfi", "-i", "color=black:s=128x96:r=25:d=6,"
       "drawbox=color=white:t=fill:enable='eq(n,25)+eq(n,125)'",
       "-f", "lavfi", "-i", f"aevalsrc='0.5*sin(2*PI*440*t)*({signal})':s=48000:d=6",
       "-c:v", "ffv1", "-c:a", "flac", str(src))
    info = analyze(src, tools)
    s = pipeline.Settings(profile_for("fidele"), restore_audio=False, scan="progressive",
                          audio_offset_ms=offset, audio_drift_ms_per_min=derive)
    dst = pipeline.export(info, s, tmp_path / "coupe.mp4", tools, passages=[(0, 2), (4, 6)])
    def lire(*args):
        return subprocess.check_output([tools.ffmpeg.path, "-v", "error", "-i", str(dst), *args, "-"])
    niveaux = np.frombuffer(lire("-an", "-vf", "scale=1:1,format=gray", "-f", "rawvideo"), np.uint8)
    son = np.frombuffer(lire("-vn", "-ac", "1", "-ar", "48000", "-f", "f32le"), "<f4")
    flashs = np.flatnonzero(niveaux > 160) / 25
    assert len(flashs) == 2
    for flash in flashs:
        debut = int((flash - 0.15) * 48000)
        attaque = np.flatnonzero(abs(son[debut:debut + 14400]) > 0.1)[0]
        assert abs((debut + attaque) / 48000 - flash) <= 0.04
    pts = subprocess.check_output([tools.ffprobe.path, "-v", "error", "-select_streams", "v",
          "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(dst)], text=True)
    assert np.diff(sorted(map(float, pts.split()))).max() <= 0.040001
    assert abs(float(probe_json(dst)["format"]["duration"]) - 4.02) < 0.04
