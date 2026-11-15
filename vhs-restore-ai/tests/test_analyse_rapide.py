"""L'analyse du son ne lit le fichier qu'une fois, et conclut comme avant.
Opposition de phase : une deuxième lecture groupée, parce que la somme des côtés s'annule."""
import subprocess

from conftest import ff
from vhs_restore.audio_check import measure


def _count(monkeypatch):
    calls = []
    real = subprocess.run

    def wrapped(cmd, *args, **kwargs):
        if cmd and "ffmpeg" in str(cmd[0]):
            calls.append(list(cmd))
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr("vhs_restore.tools.subprocess.run", wrapped)
    return calls


def test_measure_reads_the_file_once(tools, tmp_path, monkeypatch):
    path = tmp_path / "son.mkv"
    ff("-f", "lavfi", "-i", "sine=f=440:sample_rate=48000,pan=stereo|c0=c0|c1=c0",
       "-t", "2", "-c:a", "pcm_s16le", str(path))
    calls = _count(monkeypatch)
    got = measure(tools.ffmpeg.path, path, 2)
    assert len(calls) == 1 and "-filter_complex" in calls[0]
    assert got.channel_issue == "" and got.hum_hz == 0 and got.wind is False


def test_phase_uses_a_second_grouped_read(tools, tmp_path, monkeypatch):
    path = tmp_path / "phase.mkv"
    # 440 Hz en opposition, plus un ronflement 50 Hz lui aussi inversé d'un côté.
    ff("-f", "lavfi", "-i",
       "sine=f=440:sample_rate=48000,pan=stereo|c0=c0|c1=c0,aeval=exprs=val(0)|-val(1):channel_layout=stereo",
       "-f", "lavfi", "-i",
       "sine=f=50:sample_rate=48000,volume=0.4,pan=stereo|c0=c0|c1=c0,aeval=exprs=val(0)|-val(1):channel_layout=stereo",
       "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first",
       "-t", "3", "-c:a", "pcm_s16le", str(path))
    calls = _count(monkeypatch)
    got = measure(tools.ffmpeg.path, path, 2)
    assert got.channel_issue == "phase"
    assert got.hum_hz == 50
    assert len(calls) == 2
    assert all("-filter_complex" in c for c in calls)
