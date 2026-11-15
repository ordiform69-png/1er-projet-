"""Dominante de couleur : une teinte verte ajoutée est retirée dans le fichier exporté.
Un noir et blanc reste neutre, une couleur pâle n'est pas ravivée. Rien par défaut."""
import dataclasses
import re
import subprocess

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.advice import advise, apply
from vhs_restore.probe import analyze, cast_gains, rgb_mean
from vhs_restore.profiles import profile_for


def medians(ffmpeg, path):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-vf",
                        "signalstats,metadata=print:key=lavfi.signalstats.UAVG,"
                        "metadata=print:key=lavfi.signalstats.VAVG,"
                        "metadata=print:key=lavfi.signalstats.SATAVG",
                        "-frames:v", "8", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    out = {}
    for key in ("UAVG", "VAVG", "SATAVG"):
        vals = sorted(float(x) for x in re.findall(rf"signalstats\.{key}=([\d.]+)", r.stderr))
        assert vals, r.stderr[-400:]
        out[key] = vals[len(vals) // 2]
    return out


def plain():
    bare = dataclasses.replace(profile_for("fidele", "video"), denoise=None)
    return pipeline.Settings(bare, restore_audio=False, preset="ultrafast", scan="progressive")


def test_green_cast_removed_bw_and_pale_stay(tools, tmp_path):
    base = tmp_path / "base.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-t", "1", "-c:v", "ffv1", str(base))
    green = tmp_path / "vert.mkv"
    ff("-i", str(base), "-vf", "lutrgb=r='val*0.82':g='clip(val*0.82+36,0,255)':b='val*0.82'",
       "-c:v", "ffv1", str(green))
    bw = tmp_path / "nb.mkv"
    ff("-i", str(base), "-vf", "hue=s=0", "-c:v", "ffv1", str(bw))
    pale = tmp_path / "pale.mkv"
    ff("-i", str(base), "-vf", "eq=saturation=0.25", "-c:v", "ffv1", str(pale))

    info_g, info_n, info_b, info_p = (analyze(p, tools) for p in (green, base, bw, pale))
    assert info_g.cast_rgb and max(info_g.cast_rgb) - min(info_g.cast_rgb) > 15
    tips = [a for a in advise(info_g) if a.key == "cast"]
    assert tips and not any(a.key == "levels" for a in advise(info_g))
    for info in (info_n, info_b, info_p):
        assert not any(a.key == "cast" for a in advise(info)), info.cast_rgb

    s0 = plain()
    assert "colorchannelmixer=" not in pipeline.filter_chain(info_g, s0)
    fixed = apply(s0, tips)
    assert "colorchannelmixer=" in pipeline.filter_chain(info_g, fixed)
    out = pipeline.export(info_g, fixed, tmp_path / "vert.mp4", tools)
    raw = pipeline.export(info_g, s0, tmp_path / "vert_brut.mp4", tools)

    before = rgb_mean(tools.ffmpeg.path, raw)
    after = rgb_mean(tools.ffmpeg.path, out)
    assert before and after
    span = lambda rgb: max(rgb) - min(rgb)
    assert span(after) < span(before) / 2          # la teinte verte est retirée
    assert span(after) < 8
    uv = lambda st: abs(st["UAVG"] - 128) + abs(st["VAVG"] - 128)
    assert uv(medians(tools.ffmpeg.path, out)) < uv(medians(tools.ffmpeg.path, raw)) - 5

    # Noir et blanc : même en forçant la correction, le filtre est absent et l'image reste grise.
    gains_b = cast_gains(info_b.cast_rgb)
    forced_b = dataclasses.replace(s0, gain_r=gains_b[0], gain_g=gains_b[1], gain_b=gains_b[2])
    assert "colorchannelmixer=" not in pipeline.filter_chain(info_b, forced_b)
    out_b = pipeline.export(info_b, forced_b, tmp_path / "nb.mp4", tools)
    assert medians(tools.ffmpeg.path, out_b)["SATAVG"] < 2

    # Couleur pâle : pas de conseil, et forcer les gains ne ravive pas la saturation.
    sat0 = medians(tools.ffmpeg.path, pale)["SATAVG"]
    gains_p = cast_gains(info_p.cast_rgb)
    forced_p = dataclasses.replace(s0, gain_r=gains_p[0], gain_g=gains_p[1], gain_b=gains_p[2])
    out_p = pipeline.export(info_p, forced_p, tmp_path / "pale.mp4", tools)
    assert medians(tools.ffmpeg.path, out_p)["SATAVG"] < sat0 + 3
