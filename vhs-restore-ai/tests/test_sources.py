"""Origines VIDÉO / PELLICULE / TRANSFERT (échantillons de synthèse, pas de vraies archives).

Couvre les points 1 à 8 du cahier des charges « films familiaux 1970-1995 »."""
import dataclasses
import re
import shutil
import subprocess
from fractions import Fraction

import pytest

from conftest import probe_json
from vhs_restore import pipeline
from vhs_restore.probe import analyze, parse_signals, suggest_source
from vhs_restore.profiles import PROFILES, profile_for


def S(key="equilibre", source="video", **kw):
    return pipeline.Settings(profile_for(key, source), source=source, **kw)


def streams(path):
    d = probe_json(path)
    v = next(x for x in d["streams"] if x["codec_type"] == "video")
    return d, v, [x for x in d["streams"] if x["codec_type"] == "audio"]


@pytest.fixture(scope="module")
def A(samples, tools):
    cache = {}

    def get(name):
        if name not in cache:
            cache[name] = analyze(samples[name], tools)
        return cache[name]
    return get


# ---- analyse : suggestion d'origine (jamais une certitude)
def test_suggestions(A):
    assert A("film18").suggested_source == "film" and "18 i/s" in A("film18").source_reason
    assert A("transfert").scan == "tff" and A("transfert").suggested_source == "transfer"
    assert A("pal_tff").suggested_source == "video"
    assert A("prog").suggested_source == "video" and "à confirmer" in A("prog").source_reason
    assert A("film_nb").black_and_white and not A("film18").black_and_white
    assert not A("film18").pale_colors and not A("film18_son").audio_silent


def test_parse_signals():
    txt = ("Repeated Fields: Neither: 90 Top: 5 Bottom: 5\n"
           + "".join(f"lavfi.signalstats.YDIF={v}\nlavfi.signalstats.SATAVG=3\n"
                     for v in [0, 8, 8, 0.5, 8, 8, 0.4, 8, 8, 8, 0.3, 8]))
    s = parse_signals(txt)
    assert s["repeated_fields"] == pytest.approx(0.10)
    assert s["repeated_frames"] == pytest.approx(3 / 11)
    assert s["saturation"] == 3


def test_silent_track_and_pale_colors(samples, tools, tmp_path):
    """Cas rencontrés sur une vraie archive : piste son vide, couleurs décolorées."""
    import subprocess as sp
    src = tmp_path / "pâle muet.mkv"
    sp.run([shutil.which("ffmpeg"), "-loglevel", "error", "-f", "lavfi", "-i",
            "testsrc2=size=720x540:rate=18,hue=s=0.12,noise=alls=8:allf=t", "-f", "lavfi", "-i",
            "anullsrc=r=48000:cl=stereo", "-t", "3", "-c:v", "ffv1", "-c:a", "flac", str(src)], check=True)
    i = analyze(src, tools)
    assert i.has_audio and i.audio_silent and "silencieuse" in i.summary()["Audio"]
    assert i.pale_colors and not i.black_and_white
    out = pipeline.export(i, S(source="film"), tmp_path / "o.mp4", tools)
    assert streams(out)[2]                                # piste conservée, pas supprimée


# ---- 1. la vidéo analogique garde exactement le pipeline existant
def test_video_pipeline_unchanged(A):
    pal = A("pal_tff")
    assert pipeline.filter_chain(pal, pipeline.Settings(PROFILES["maximum"], resolution="1080")) == (
        "bwdif=mode=send_field:parity=tff:deint=all,removegrain=m0=1:m1=1:m2=1,hqdn3d=4:7:6:10,"
        "eq=contrast=1.06:saturation=1.12,scale=1440:1080:flags=lanczos:in_color_matrix=bt601:"
        "out_color_matrix=bt709,cas=strength=0.45,setsar=1/1,format=yuv420p")
    assert profile_for("equilibre", "video") == PROFILES["equilibre"]


# ---- 2. une pellicule progressive n'est jamais désentrelacée automatiquement
def test_film_never_auto_deinterlaced(A, tools, tmp_path):
    for info in (A("film18"), A("pal_tff")):            # même si l'analyse mesure des trames
        chain = pipeline.filter_chain(info, S(source="film"))
        assert "bwdif" not in chain and "fieldmatch" not in chain
        assert pipeline.output_fps(info, S(source="film")) == info.fps
    assert "bwdif" in pipeline.filter_chain(A("pal_tff"), S(source="film", scan="tff"))  # choix manuel
    out = pipeline.export(A("film18"), S(source="film"), tmp_path / "f.mp4", tools)
    _, v, _ = streams(out)
    assert v["avg_frame_rate"] == "18/1" and int(v["nb_read_frames"]) == 108


# ---- 3. cadence historique renseignée manuellement, sans créer ni supprimer d'image
@pytest.mark.parametrize("rate,dur", [(24, 4.5), (16, 6.75)])
def test_manual_shooting_rate(A, tools, tmp_path, rate, dur):
    s = S(source="film", playback_fps=Fraction(rate))
    out = pipeline.export(A("film18"), s, tmp_path / "c.mp4", tools)
    d, v, a = streams(out)
    assert v["avg_frame_rate"] == f"{rate}/1" and int(v["nb_read_frames"]) == 108
    assert abs(float(d["format"]["duration"]) - dur) < 0.1 and not a
    assert pipeline.retime(A("film18"), S(source="video", playback_fps=Fraction(24))) is None


# ---- 4 et 5. proportions et son conservés (y compris re-cadencé : son au même tempo)
def test_aspect_and_sound(A, tools, tmp_path):
    out = pipeline.export(A("film18_son"), S(source="film", playback_fps=Fraction(24),
                                              resolution="1080"), tmp_path / "s.mp4", tools)
    d, v, a = streams(out)
    assert (v["width"], v["height"], v["display_aspect_ratio"]) == (1440, 1080, "4:3")
    assert a and abs(float(a[0]["duration"]) - float(v["duration"])) < 0.1
    assert abs(float(v["duration"]) - 4.5) < 0.1
    out2 = pipeline.export(A("transfert"), S(source="transfer"), tmp_path / "t.mp4", tools)
    _, v2, a2 = streams(out2)
    assert v2["display_aspect_ratio"] == "4:3" and v2["sample_aspect_ratio"] == "16:15" and a2


# ---- 6. un film muet reste muet (export et aperçu)
def test_silent_stays_silent(A, tools, tmp_path):
    out = pipeline.export(A("film_nb"), S(source="film"), tmp_path / "m.mp4", tools)
    assert not streams(out)[2]
    r = pipeline.make_preview(A("film18"), S(source="film", playback_fps=Fraction(24)), tools,
                              tmp_path / "ap", start=1, duration=3)
    _, v, a = streams(r.compare)
    assert not a and abs(float(v["duration"]) - 2.25) < 0.1   # 3 s à 18 i/s lues à 24 i/s


# ---- 7. transfert : traité sans hypothèse sur la cadence d'origine
def test_transfer_no_cadence_assumption(A, tools, tmp_path):
    info = A("transfert")
    chain = pipeline.filter_chain(info, S(source="transfer"))
    assert chain.startswith("fieldmatch=order=tff:combmatch=full,bwdif=mode=send_frame")
    assert "decimate" not in chain and "setpts" not in chain
    out = pipeline.export(info, S(source="transfer"), tmp_path / "t.mp4", tools)
    d, v, a = streams(out)
    assert v["avg_frame_rate"] == "25/1"                    # cadence du support conservée
    assert 150 <= int(v["nb_read_frames"]) <= 152           # aucune image supprimée
    assert a and abs(float(d["format"]["duration"]) - 6.0) < 0.15
    after = analyze(out, tools)
    assert after.scan == "progressive"                      # plus de trames mélangées


# ---- fidélité : le grain d'une pellicule est mieux conservé qu'avec les réglages vidéo
def _psnr(a, b):
    # appariement par numéro d'image (les horodatages MKV arrondis à la ms décaleraient les paires)
    r = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(a), "-i", str(b), "-lavfi",
                        "[0:v]setpts=N/TB[x];[1:v]setpts=N/TB[y];[x][y]psnr", "-f", "null", "-"],
                       capture_output=True, text=True)
    return float(re.findall(r"y:([\d.]+)", r.stderr)[-1])


def test_film_profiles_keep_grain(A, samples, tools, tmp_path):
    info = A("film18")
    as_video = pipeline.export(info, S(source="video", crf=8), tmp_path / "v.mp4", tools)
    as_film = pipeline.export(info, S(source="film", crf=8), tmp_path / "f.mp4", tools)
    fidele = pipeline.export(info, S("fidele", source="film", crf=8), tmp_path / "fi.mp4", tools)
    p_v, p_f, p_fi = (_psnr(x, samples["film18"]) for x in (as_video, as_film, fidele))
    print(f"proximité avec le scan (PSNR Y) : réglages vidéo {p_v:.1f} dB, pellicule {p_f:.1f} dB, "
          f"pellicule Fidèle {p_fi:.1f} dB")
    assert p_fi > p_f > p_v


def test_deflicker_option(A, tools, tmp_path):
    chain = pipeline.filter_chain(A("film18"), S(source="film", deflicker=True))
    assert "deflicker=size=5:mode=pm" in chain
    out = pipeline.export(A("film18"), S(source="film", deflicker=True, stabilize=tools.stab_available),
                          tmp_path / "d.mp4", tools)
    assert int(streams(out)[1]["nb_read_frames"]) == 108


def test_output_names(A, tmp_path):
    assert "_film" in pipeline.unique_output_path(A("film18"), S(source="film"), tmp_path).name
    assert "_transfert" in pipeline.unique_output_path(A("transfert"), S(source="transfer"), tmp_path).name


def test_couleur_declaree_et_mire_rgb(tmp_path, tools):
    from conftest import ff, probe_json
    import numpy as np
    src = tmp_path / "plage.mkv"
    ff("-f", "lavfi", "-i", "color=c=0x995544:s=144x108:r=25,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=limited", "-t", "0.25",
       "-c:v", "ffv1", "-colorspace", "bt709", "-color_primaries", "bt709",
       "-color_trc", "bt709", "-color_range", "tv", str(src))
    info = analyze(src, tools)
    def centre(path):
        data = subprocess.check_output([tools.ffmpeg.path, "-v", "error", "-i", str(path),
              "-vf", "format=rgb24,crop=2:2", "-frames:v", "1", "-f", "rawvideo", "-"])
        return np.frombuffer(data, np.uint8).astype(int)
    for taille in ("source", "1080"):
        dst = pipeline.export(info, pipeline.Settings(PROFILES["fidele"], resolution=taille),
                              tmp_path / (taille + ".mp4"), tools)
        v = probe_json(dst)["streams"][0]
        assert [v[k] for k in ("color_space", "color_primaries", "color_transfer", "color_range")] == [
            "bt709", "bt709", "bt709", "tv"]
        assert abs(centre(src) - centre(dst)).max() <= 4
