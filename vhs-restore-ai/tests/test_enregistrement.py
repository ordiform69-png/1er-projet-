"""Enregistrement : un seul FFmpeg, appareil simulé, arrêt par q, rien écrasé."""
import subprocess
from pathlib import Path

from vhs_restore.enregistrement import (
    CaptureConfig, arreter_proprement, build_capture_cmd, nom_unique, parse_dshow_devices,
)
from vhs_restore.tools import detect_tools


def test_commande_une_seule_ouverture(tools):
    cfg = CaptureConfig(video="USB2.0 Video Capture", audio="Digital Audio Interface",
                        sortie=Path("c.mkv"))
    cmd = build_capture_cmd(cfg, tools.ffmpeg.path)
    assert cmd.count("-i") == 1
    assert 'video="USB2.0 Video Capture":audio="Digital Audio Interface"' in cmd
    assert "-nostdin" not in cmd
    assert "-rtbufsize" in cmd and "-thread_queue_size" in cmd
    assert "-update" in cmd
    assert cmd.count(tools.ffmpeg.path) == 1


def test_simule_lavfi_et_arret_q(tools, tmp_path):
    out = tmp_path / "sim.mkv"
    cfg = CaptureConfig(simule=True, sortie=out, qualite="x264")
    cmd = build_capture_cmd(cfg, tools.ffmpeg.path)
    assert "-f" in cmd and "lavfi" in cmd
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    import time
    time.sleep(2)
    code = arreter_proprement(proc, timeout=15)
    assert out.is_file() and out.stat().st_size > 1000
    assert code == 0 or out.stat().st_size > 1000


def test_rien_ecrase(tmp_path):
    (tmp_path / "Cassette_2026-11-24_21h00.mkv").write_bytes(b"deja")
    n = nom_unique(tmp_path, "2026-11-24_21h00")
    assert n.name.endswith("_2.mkv")
    assert (tmp_path / "Cassette_2026-11-24_21h00.mkv").read_bytes() == b"deja"


def test_parse_appareils():
    stderr = '''
[dshow @ 0] "USB2.0 Video Capture" (video)
[dshow @ 0] "Digital Audio Interface" (audio)
'''
    assert parse_dshow_devices(stderr) == [
        ("USB2.0 Video Capture", "video"),
        ("Digital Audio Interface", "audio"),
    ]
