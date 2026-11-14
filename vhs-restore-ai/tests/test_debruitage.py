"""Débruitage haute qualité : mesure objective (PSNR par rapport à l'image propre)
sur une image détaillée bruitée artificiellement. Ce n'est pas une vraie cassette."""
import dataclasses
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from vhs_restore import pipeline
from vhs_restore.probe import MediaInfo, analyze
from vhs_restore.profiles import PROFILES


def S(key="equilibre", **kw):
    p = dataclasses.replace(PROFILES[key], contrast=1.0, saturation=1.0, sharpen=0.0, despeckle=False)
    return pipeline.Settings(p, **kw)


def psnr(a, b) -> float:
    r = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(a), "-i", str(b),
                        "-lavfi", "[0:v][1:v]psnr", "-f", "null", "-"], capture_output=True, text=True)
    return float(re.findall(r"average:([\d.]+)", r.stderr)[-1])


def test_chain():
    p = PROFILES["equilibre"]
    s = pipeline.Settings(p, denoise_hq=True)
    i = MediaInfo(path=Path("x.avi"), width=720, height=576, scan="progressive", fps=Fraction(25))
    chain = pipeline.filter_chain(i, s)
    assert "fftdnoiz=sigma=8:prev=1:next=1,hqdn3d=0:6:0:9" in chain
    assert chain.count("hqdn3d") == 1
    assert "fftdnoiz" not in pipeline.filter_chain(i, pipeline.Settings(p))
    assert "_hq" in pipeline.unique_output_path(i, s, Path("/nonexistent")).name


@pytest.mark.parametrize("key", ["fidele", "equilibre", "maximum"])
def test_hq_beats_standard(samples, tools, tmp_path, key):
    info = dataclasses.replace(analyze(samples["noisy"], tools), scan="progressive")
    std = pipeline.export(info, S(key, crf=10), tmp_path / "std.mp4", tools)
    hq = pipeline.export(info, S(key, crf=10, denoise_hq=True), tmp_path / "hq.mp4", tools)
    p_noisy, p_std, p_hq = psnr(samples["noisy"], samples["clean"]), psnr(std, samples["clean"]), \
        psnr(hq, samples["clean"])
    print(f"{key}: bruité {p_noisy:.2f} dB, standard {p_std:.2f} dB, haute qualité {p_hq:.2f} dB")
    assert p_hq > p_std + 1.0 and p_std >= p_noisy - 0.5
