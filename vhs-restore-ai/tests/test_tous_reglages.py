"""Chaque réglage des cartes « Image » et « Son », un par un, restauré POUR DE VRAI avec FFmpeg.

Constat (version n°61) : « Souffle de la voix (RNNoise) » plantait sous Windows. Les tests ne
vérifiaient que le texte de la commande ; aucun ne la faisait tourner avec un chemin « C:\\… ».
Ici, chaque réglage produit un vrai film de 1,5 s, dans des dossiers au nom piégeux (accents,
apostrophe, virgule, crochets, point-virgule) : le film, le dossier de travail et le modèle RNNoise.
Sous Linux, un « C: » est ajouté au nom pour imiter le lecteur Windows ; sous Windows (les tests
tournent aussi à chaque fabrication de l'exe), les vrais chemins « C:\\… » sont utilisés.
"""
import dataclasses
import os
import shutil
from fractions import Fraction

import pytest

from conftest import ff
from vhs_restore import pipeline
from vhs_restore.probe import analyze
from vhs_restore.profiles import profile_for

PIEGE = "Vacances d'été, 1988 [essai]; ok"
LECTEUR = "" if os.name == "nt" else "C:"        # Windows : le « C: » est déjà dans le chemin


@pytest.fixture(scope="module")
def cassette(tmp_path_factory, tools):
    d = tmp_path_factory.mktemp("reglages") / (LECTEUR + PIEGE)
    d.mkdir()
    f = d / "Noël chez mémé l'année 1988.avi"
    ff("-f", "lavfi", "-i", "testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,setfield=tff,"
       "setsar=16/15", "-f", "lavfi", "-i", "sine=f=440:sample_rate=48000",
       "-f", "lavfi", "-i", "sine=f=660:sample_rate=48000",
       "-filter_complex", "[1:a][2:a]join=inputs=2:channel_layout=stereo[a]", "-map", "0:v", "-map", "[a]",
       "-t", "3", "-c:v", "mpeg2video", "-flags", "+ilme+ildct", "-b:v", "8M", "-c:a", "pcm_s16le", str(f))
    travail = d.parent / (LECTEUR + "travail l'été, [tmp]; x")
    travail.mkdir()
    modele = None
    if tools.rnnoise_model:                         # modèle rangé lui aussi dans un dossier piégeux
        md = d.parent / (LECTEUR + "logiciel d'Angèle, [v62]; modèles")
        md.mkdir()
        modele = str(shutil.copy(tools.rnnoise_model, md / "rnnoise_std.rnnn"))
    return {"film": f, "info": analyze(f, tools), "travail": travail, "modele": modele}


# (nom, origine, réglages modifiés) : un réglage à la fois, comme un clic dans les options avancées
REGLAGES = [
    ("fidele", "video", {"profile": "fidele"}),
    ("equilibre", "video", {}),
    ("maximum", "video", {"profile": "maximum"}),
    ("full_hd", "video", {"resolution": "1080"}),
    ("balayage_progressif", "video", {"scan": "progressive"}),
    ("balayage_bff", "video", {"scan": "bff"}),
    ("format_16_9", "video", {"dar": Fraction(16, 9)}),
    ("debruitage_hq", "video", {"denoise_hq": True}),
    ("stabiliser", "video", {"stabilize": True}),
    ("bruit_de_bande", "video", {"tape_noise": True}),
    ("couleur_decrochages", "video", {"chroma_repair": True}),
    ("taches_une_image", "video", {"dropouts": True}),
    ("niveaux", "video", {"level_black": 0.15, "level_white": 0.8}),
    ("dominante", "video", {"gain_r": 0.95, "gain_g": 1.0, "gain_b": 1.06}),
    ("bande_du_bas", "video", {"mask_bottom": 8}),
    ("bords", "video", {"mask_sides": 12}),
    ("bords_full_hd", "video", {"mask_sides": 12, "resolution": "1080"}),
    ("decalage_couleur", "video", {"chroma_shift": -3}),
    ("sans_son_restaure", "video", {"restore_audio": False}),
    ("son_retarde", "video", {"audio_offset_ms": 120}),
    ("son_avance", "video", {"audio_offset_ms": -120}),
    ("derive", "video", {"audio_drift_ms_per_min": 100}),
    ("ronflement_50", "video", {"audio_mains_hz": 50}),
    ("ronflement_60", "video", {"audio_mains_hz": 60}),
    ("canal_gauche", "video", {"audio_channel_fix": "left"}),
    ("canal_droit", "video", {"audio_channel_fix": "right"}),
    ("phase", "video", {"audio_channel_fix": "phase"}),
    ("son_sature", "video", {"audio_declip": True}),
    ("vent", "video", {"audio_highpass": True}),
    ("voix_claires", "video", {"audio_presence": True}),
    ("rnnoise", "video", {"use_rnnoise": True}),
    ("rnnoise_maximum", "video", {"profile": "maximum", "use_rnnoise": True}),
    ("copie_wav", "video", {"audio_copy": "wav"}),
    ("copie_flac", "video", {"audio_copy": "flac"}),
    # la chaîne du son de l'utilisateur (n°61) : tout coché en même temps
    ("tout_le_son", "video", {"audio_mains_hz": 50, "audio_presence": True, "use_rnnoise": True,
                              "audio_offset_ms": -40, "audio_drift_ms_per_min": -120,
                              "audio_declip": True, "audio_highpass": True}),
    ("pellicule", "film", {}),
    ("pellicule_18_is", "film", {"playback_fps": Fraction(18)}),
    ("pellicule_scintillement", "film", {"deflicker": True}),
    ("pellicule_bords", "film", {"mask_sides": 10}),
    ("transfert", "transfer", {}),
    ("transfert_scintillement", "transfer", {"deflicker": True}),
]


@pytest.mark.parametrize("nom,origine,changes", REGLAGES, ids=[r[0] for r in REGLAGES])
def test_reglage_restaure_pour_de_vrai(nom, origine, changes, cassette, tools, monkeypatch):
    changes = dict(changes)
    if changes.get("stabilize") and not tools.stab_available:
        pytest.skip("FFmpeg sans vid.stab")
    if any(changes.get(k) for k in ("tape_noise", "chroma_repair", "dropouts")) and not tools.dust_available:
        pytest.skip("module Analog Repair absent")
    if changes.get("use_rnnoise") and not cassette["modele"]:
        pytest.skip("modèle RNNoise absent")
    monkeypatch.setenv("VHSRA_TMP", str(cassette["travail"]))
    t = dataclasses.replace(tools, rnnoise_model=cassette["modele"])
    profil = profile_for(changes.pop("profile", "equilibre"), origine)
    s = dataclasses.replace(pipeline.Settings(profil, source=origine), **changes)
    info = cassette["info"]
    out = cassette["film"].with_name(f"résultat {nom} l'été.mp4")
    res = pipeline.export(info, s, out, t, start=0.5, duration=1.5)
    apres = analyze(res, tools)
    assert apres.has_audio and 1.0 < apres.duration < 2.6, (nom, apres.duration)
    if s.resolution == "1080":
        assert apres.height == 1080
    if s.audio_copy:
        assert res.with_suffix("." + s.audio_copy).is_file()
    assert not list(cassette["film"].parent.glob("*.partiel*"))         # rien d'inachevé laissé
    assert not list(cassette["travail"].iterdir())                       # dossier de travail rangé


def test_apercu_avec_reglages(cassette, tools, monkeypatch, tmp_path):
    """L'aperçu avant / après passe par d'autres commandes : essayé avec le son et les bords."""
    if not cassette["modele"]:
        pytest.skip("modèle RNNoise absent")
    monkeypatch.setenv("VHSRA_TMP", str(cassette["travail"]))
    t = dataclasses.replace(tools, rnnoise_model=cassette["modele"])
    s = dataclasses.replace(pipeline.Settings(profile_for("equilibre", "video")), use_rnnoise=True,
                            audio_mains_hz=50, mask_sides=12, level_black=0.1, level_white=0.9)
    d = tmp_path / (LECTEUR + PIEGE)
    d.mkdir()
    prev = pipeline.make_preview(cassette["info"], s, t, d, 0.5)
    assert prev.stills and all(p.is_file() for p in prev.stills)
