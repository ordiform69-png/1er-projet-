"""Voix plus claires : +3 dB vers 3 kHz, jamais par défaut.
L'énergie 2–4 kHz monte dans le fichier exporté, sans créer d'écrêtage."""
from conftest import ff
from vhs_restore import pipeline
from vhs_restore.audio_check import _levels
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for


def band(ffmpeg, path):
    chans = _levels(ffmpeg, path, "highpass=f=2000,lowpass=f=4000,")
    return max(c["RMS level dB"] for c in chans), max(c["Peak level dB"] for c in chans)


def test_presence_raises_band_without_clipping(tools, tmp_path):
    src = tmp_path / "etouffe.mkv"
    # Voix étouffée de synthèse : énergie autour de 1 kHz, un peu à 3 kHz, loin du plafond.
    ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-filter_complex",
       "sine=f=1000:sample_rate=48000,volume=0.1[a];sine=f=3000:sample_rate=48000,volume=0.05[b];"
       "[a][b]amix=inputs=2:duration=first,pan=stereo|c0=c0|c1=c0[a]",
       "-map", "0:v", "-map", "[a]", "-t", "3", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(src))
    info = analyze(src, tools)
    plain = pipeline.Settings(profile_for("fidele", "video"), restore_audio=False,
                              preset="ultrafast", scan="progressive")
    assert "equalizer=" not in ",".join(pipeline.audio_filters(info, plain))
    before_rms, before_peak = band(tools.ffmpeg.path, src)
    out = pipeline.export(info, pipeline.Settings(plain.profile, restore_audio=False,
                                                  audio_presence=True, preset="ultrafast",
                                                  scan="progressive"),
                          tmp_path / "o.mp4", tools)
    after_rms, after_peak = band(tools.ffmpeg.path, out)
    assert after_rms > before_rms + 1.5          # 2–4 kHz plus fort
    assert after_peak < -3                       # pas d'écrêtage créé
    assert after_peak < before_peak + 3.5        # le gain ne dépasse pas +3 dB
