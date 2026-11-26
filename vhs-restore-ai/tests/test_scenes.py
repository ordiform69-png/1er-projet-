"""Lumière et couleurs scène par scène.

Film de mesure : la recette PAL 32 s de l'agent E
(`partage-grok/recette-scenes-n17.py`, identique à `mesures-n17/mesurer.py`).
La cible d'une scène est la correction du moteur mesurée sur cette scène seule
(mêmes plafonds). La correction unique est celle du film entier.
"""
import dataclasses
import importlib.util
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore import pipeline, scenes
from vhs_restore.advice import advise, apply
from vhs_restore.probe import MediaInfo, analyze
from vhs_restore.profiles import profile_for

_SPEC = importlib.util.spec_from_file_location(
    "recette_scenes_n17",
    Path(__file__).resolve().parents[1] / "partage-grok" / "recette-scenes-n17.py")
recette = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(recette)


def neutre():
    bare = dataclasses.replace(profile_for("fidele", "video"), denoise=None, sharpen=0.0, despeckle=False)
    return pipeline.Settings(bare, source="video", scan="progressive", restore_audio=False,
                             preset="ultrafast", crf=18)


def _images(suite):
    """suite : (durée en pas de 0,2 s, r, g, b, noir, blanc)."""
    images, t = [], 0.0
    for n, r, g, b, noir, blanc in suite:
        for _ in range(n):
            images.append(scenes.Image(t, r, g, b, noir, blanc))
            t += 0.2
    return images


def test_une_scene_courte_rejoint_la_voisine():
    images = _images((
        (20, 100, 100, 100, 40, 200),   # 4 s
        (5, 200, 80, 40, 90, 140),      # 1 s, trop court
        (20, 100, 100, 100, 40, 200),   # 4 s
    ))
    trouvees = scenes.segmenter(images, duree=9.0)
    assert trouvees
    assert all(sc.fin - sc.debut >= 2.0 - 1e-6 for sc in trouvees)
    assert not any(abs((sc.fin - sc.debut) - 1.0) < 0.25 for sc in trouvees)


def test_coupure_franche_sans_fondu():
    images = _images((
        (15, 180, 90, 50, 55, 100),     # 3 s, sombre orangé
        (15, 70, 130, 190, 145, 185),   # 3 s, clair bleuté
    ))
    trouvees = scenes.segmenter(images, duree=6.0)
    assert len(trouvees) == 2 and trouvees[1].franche
    s = dataclasses.replace(neutre(), level_black=0.2, level_white=0.8, gain_r=1.1)
    pts = scenes.points_de_commande(trouvees, s)
    assert len(pts) == 2
    assert abs(pts[1][0] - trouvees[1].debut) < 1e-6
    bloc = scenes.filtres(MediaInfo(path=Path("x.mkv"), scenes=trouvees), s, 0.0)
    assert bloc and any(x.startswith("sendcmd=") for x in bloc)
    assert all("enable=" not in x for x in bloc)


def test_passage_doux_sur_une_demi_seconde():
    images = []
    for i in range(40):                      # 8 s, la lumière monte sans à-coup
        images.append(scenes.Image(i * 0.2, 40 + i * 3, 40 + i * 3, 40 + i * 3,
                                   40 + i * 1.5, 70 + i * 1.5))
    trouvees = scenes.segmenter(images, duree=8.0)
    assert len(trouvees) >= 2
    assert any(not sc.franche for sc in trouvees[1:])
    s = dataclasses.replace(neutre(), level_black=0.3, level_white=0.7)
    pts = scenes.points_de_commande(trouvees, s)
    bornes = {round(sc.debut, 3) for sc in trouvees}
    entre = [p for p in pts if round(p[0], 3) not in bornes]
    assert entre, pts
    # le fondu reste dans une fenêtre de 0,5 s autour d'une frontière douce
    douces = [sc.debut for sc in trouvees[1:] if not sc.franche]
    assert douces
    for instant, _valeur in entre:
        assert any(abs(instant - bord) <= 0.25 + 1e-6 for bord in douces)


@pytest.fixture(scope="module")
def film(tmp_path_factory, tools):
    dossier = tmp_path_factory.mktemp("trois-scenes")
    chemins = recette.fabriquer(tools.ffmpeg.path, dossier)
    info = analyze(chemins["film"], tools)
    return chemins, info


def _rgb(ffmpeg, film, t, chaine, n=8):
    vf = f"{chaine},format=rgb24" if chaine else "format=rgb24"
    r = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(film),
         "-an", "-vf", vf, "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    data = r.stdout or b""
    assert r.returncode == 0 and len(data) >= 3, (r.returncode, (r.stderr or b"")[-400:])
    pix = len(data) // 3
    return (sum(data[0::3]) / pix, sum(data[1::3]) / pix, sum(data[2::3]) / pix)


def _span(rgb):
    return max(rgb) - min(rgb)


def _dist(a, b):
    return (abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])) / 3.0


def _chaine(info, s, origine):
    return pipeline.filter_chain(info, s, origine=origine)


def test_trois_scenes_vers_la_cible(film, tools):
    chemins, info = film
    assert len(info.scenes) == 3, [(round(s.debut, 2), round(s.fin, 2), s.franche) for s in info.scenes]
    assert info.scenes[1].franche and info.scenes[2].franche
    assert abs(info.scenes[1].debut - 8.0) <= 0.4
    assert abs(info.scenes[2].debut - 24.0) <= 0.4
    assert 0 < info.scenes_secondes < 60

    conseils = advise(info)
    assert any(a.key == "cast" for a in conseils)
    base = neutre()
    unique_s = apply(base, conseils)
    sans = dataclasses.replace(info, scenes=())
    ffmpeg = tools.ffmpeg.path
    lignes = [f"MESURE analyse_s={info.scenes_secondes:.3f} par_minute={info.scenes_secondes / 32 * 60:.2f}"]
    # milieu de chaque scène, loin des coupures
    moments = (3.0, 16.0, 28.0)
    for moment, nom in zip(moments, ("1", "2", "3")):
        src = _rgb(ffmpeg, chemins["film"], moment, "")
        uni = _rgb(ffmpeg, chemins["film"], moment, _chaine(sans, unique_s, moment))
        par = _rgb(ffmpeg, chemins["film"], moment, _chaine(info, unique_s, moment))
        isolee = analyze(chemins[f"scene-{nom}"], tools)
        oracle_s = apply(base, advise(isolee))
        # Mêmes images que la correction unique : la cible est la correction de
        # cette scène, appliquée aux images du film entier à cet instant.
        oracle_info = dataclasses.replace(info, scenes=())
        ora = _rgb(ffmpeg, chemins["film"], moment, _chaine(oracle_info, oracle_s, moment))
        d_uni, d_par = _dist(uni, ora), _dist(par, ora)
        lignes.append(
            f"scene{nom} span_source={_span(src):.2f} span_unique={_span(uni):.2f} "
            f"span_scenes={_span(par):.2f} span_oracle={_span(ora):.2f} "
            f"ecart_unique={d_uni:.2f} ecart_scenes={d_par:.2f} "
            f"rvb_unique={[round(v, 1) for v in uni]} "
            f"rvb_scenes={[round(v, 1) for v in par]} "
            f"rvb_oracle={[round(v, 1) for v in ora]}")
        # la scène 1 : la correction unique est déjà l'oracle (l'échantillon du
        # moteur est pris au début). On ne doit pas s'en éloigner.
        if nom == "1":
            assert d_par <= d_uni + 2.0, lignes[-1]
        else:
            assert d_par < d_uni - 1.0, lignes[-1]
    print("\n".join(lignes))


def test_pas_de_variation_dans_une_scene(film, tools):
    """La correction est la même à deux instants d'une scène : pas de pompage."""
    chemins, info = film
    base = neutre()
    unique_s = apply(base, advise(info))
    ffmpeg = tools.ffmpeg.path
    sans = dataclasses.replace(info, scenes=())
    for moment in (12.0, 18.0):                 # scène 2, contenu qui bouge (testsrc2)
        par = _rgb(ffmpeg, chemins["film"], moment, _chaine(info, unique_s, moment))
        fixe = _rgb(ffmpeg, chemins["film"], moment, _chaine(sans, base, moment))
        assert _dist(par, fixe) < 2.0, (moment, par, fixe)
    sc3 = info.scenes[2]
    statique = dataclasses.replace(base, level_black=sc3.noir, level_white=sc3.blanc,
                                   gain_r=sc3.gains[0], gain_g=sc3.gains[1], gain_b=sc3.gains[2])
    for moment in (26.0, 30.0):
        par = _rgb(ffmpeg, chemins["film"], moment, _chaine(info, unique_s, moment))
        fixe = _rgb(ffmpeg, chemins["film"], moment, _chaine(sans, statique, moment))
        assert _dist(par, fixe) < 2.5, (moment, par, fixe, _dist(par, fixe))


def test_apercu_a_20s_est_la_scene_2(film, tools):
    """`-ss` avant l'entrée : l'aperçu de 20 s (scène 2), pas la correction de la scène 1."""
    chemins, info = film
    base = neutre()
    unique_s = apply(base, advise(info))
    ffmpeg = tools.ffmpeg.path
    sans = dataclasses.replace(info, scenes=())
    apercu = _rgb(ffmpeg, chemins["film"], 20.0, _chaine(info, unique_s, 20.0))
    scene2 = _rgb(ffmpeg, chemins["film"], 20.0, _chaine(sans, base, 20.0))
    scene1 = _rgb(ffmpeg, chemins["film"], 20.0, _chaine(sans, unique_s, 20.0))
    assert _dist(apercu, scene2) < 2.0, (apercu, scene2)
    assert _dist(apercu, scene2) < _dist(apercu, scene1) - 1.0

    # Le même chemin que « Lumière et couleurs » et les images du rendu :
    # _seek puis dvd_input, puis la chaîne, sans qu'on lui redonne l'instant.
    pipeline._seek(20.0, None)
    pipeline.dvd_input(info)
    chaine = pipeline.filter_chain(info, unique_s)
    assert "setpts=PTS+20" in chaine
    via_seek = _rgb(ffmpeg, chemins["film"], 20.0, chaine)
    assert _dist(via_seek, scene2) < 2.0
    # un second appel (boucle des rendus) garde le même instant
    encore = pipeline.filter_chain(info, unique_s)
    assert encore == chaine


def test_passage_enleve_garde_la_scene_suivante(film, tools, tmp_path):
    """Le trou est sauté (-ss de chaque morceau). La scène 3 garde sa correction."""
    chemins, info = film
    base = neutre()
    s = apply(base, advise(info))
    out = pipeline.export(info, s, tmp_path / "sans-trou.mp4", tools,
                          passages=[(0.0, 4.0), (26.0, 32.0)])
    ffmpeg = tools.ffmpeg.path
    # sortie : 4 s de scène 1, puis la scène 3. t=5 s de la sortie = source ~27 s.
    rendu = _rgb(ffmpeg, out, 5.0, "")
    sans = dataclasses.replace(info, scenes=())
    sc3 = info.scenes[2]
    statique = dataclasses.replace(base, level_black=sc3.noir, level_white=sc3.blanc,
                                   gain_r=sc3.gains[0], gain_g=sc3.gains[1], gain_b=sc3.gains[2])
    cible = _rgb(ffmpeg, chemins["film"], 27.0, _chaine(sans, statique, 27.0))
    autre = _rgb(ffmpeg, chemins["film"], 27.0, _chaine(sans, s, 27.0))
    assert _dist(rendu, cible) < _dist(rendu, autre) - 2.0, (
        _dist(rendu, cible), _dist(rendu, autre), _span(rendu), _span(cible), _span(autre))


def test_montage_trim_concat(film, tools, tmp_path):
    """trim + concat après la chaîne : le temps source a déjà choisi la correction."""
    chemins, info = film
    base = neutre()
    s = apply(base, advise(info))
    chaine = pipeline.filter_chain(info, s, origine=0.0)
    graphe = pipeline.filtres_passages(chaine, [(0.0, 4.0), (26.0, 32.0)], audio=False)
    sortie = tmp_path / "montage.mkv"
    ff("-i", str(chemins["film"]), "-filter_complex", graphe, "-c:v", "ffv1", str(sortie))
    ffmpeg = tools.ffmpeg.path
    rendu = _rgb(ffmpeg, sortie, 5.0, "")
    sans = dataclasses.replace(info, scenes=())
    sc3 = info.scenes[2]
    statique = dataclasses.replace(base, level_black=sc3.noir, level_white=sc3.blanc,
                                   gain_r=sc3.gains[0], gain_g=sc3.gains[1], gain_b=sc3.gains[2])
    cible = _rgb(ffmpeg, chemins["film"], 27.0, _chaine(sans, statique, 27.0))
    autre = _rgb(ffmpeg, chemins["film"], 27.0, _chaine(sans, s, 27.0))
    assert _dist(rendu, cible) < 3.0, (_dist(rendu, cible), _span(rendu), _span(cible))
    assert _dist(rendu, cible) < _dist(rendu, autre) - 2.0


def test_dvd_en_plusieurs_morceaux(film, tools, tmp_path):
    chemins, info = film
    dossier = tmp_path / "VIDEO_TS"
    dossier.mkdir()
    v1, v2 = dossier / "VTS_01_1.VOB", dossier / "VTS_01_2.VOB"
    # Un vrai VOB est un flux MPEG : l'extension force ce démultiplexeur.
    ff("-i", str(chemins["film"]), "-t", "16", "-c:v", "mpeg2video", "-b:v", "8M",
       "-f", "vob", str(v1))
    ff("-ss", "16", "-i", str(chemins["film"]), "-c:v", "mpeg2video", "-b:v", "8M",
       "-f", "vob", str(v2))
    from vhs_restore.dvd import open_media
    dvd = open_media(v1, tools)
    assert len(dvd.parts) == 2
    assert len(dvd.scenes) >= 2, [(round(s.debut, 2), round(s.fin, 2)) for s in dvd.scenes]
    assert any(s.debut < 24 <= s.fin or (s.debut >= 23 and s.fin > 28) for s in dvd.scenes)
    base = neutre()
    s = apply(base, advise(dvd))
    # -ss dans le second morceau : la scène 3 (à partir de 24 s), pas la scène 2.
    out = pipeline.export(dvd, s, tmp_path / "morceau.mp4", tools, start=26, duration=2)
    ffmpeg = tools.ffmpeg.path
    rendu = _rgb(ffmpeg, out, 0.4, "")
    # La scène 3 d'origine a un écart RVB d'environ 22 ; la correction unique
    # l'aggrave (vers 60). Le morceau DVD doit rester près de la cible.
    assert _span(rendu) < 12, (_span(rendu), rendu)


def test_reglages_utilisateur_par_dessus(film, tools):
    chemins, info = film
    base = neutre()
    s0 = apply(base, advise(info))
    avec = dataclasses.replace(s0, lumiere=2, teinte=2)
    chaine = pipeline.filter_chain(info, avec, origine=0.0)
    assert "sendcmd=" in chaine and "gamma=1.2" in chaine
    assert "enable=" not in chaine
    ffmpeg = tools.ffmpeg.path
    sans_teinte = _rgb(ffmpeg, chemins["film"], 16.0, pipeline.filter_chain(info, s0, origine=16.0))
    teinte = _rgb(ffmpeg, chemins["film"], 16.0, pipeline.filter_chain(info, avec, origine=16.0))
    # plus chaud : plus de rouge que de bleu, par-dessus la correction de scène
    assert (teinte[0] - teinte[2]) > (sans_teinte[0] - sans_teinte[2]) + 1.0


def test_analyse_impossible_ou_trop_longue(tools, tmp_path, monkeypatch):
    info = MediaInfo(path=tmp_path / "absent.mkv", width=320, height=180,
                     fps=Fraction(25), duration=10)
    scenes.attacher(info, tools.ffmpeg.path)
    assert info.scenes == ()
    assert info.scenes_secondes >= 0
    s = dataclasses.replace(neutre(), level_black=0.2, level_white=0.7, gain_r=1.1, gain_g=0.95, gain_b=0.95)
    chaine = pipeline.filter_chain(info, s)
    assert "sendcmd=" not in chaine and "colorlevels=" in chaine and "colorchannelmixer=" in chaine

    petit = tmp_path / "court.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=160x120:rate=25", "-t", "1", "-c:v", "ffv1", str(petit))
    monkeypatch.setattr(scenes, "_budget", lambda duree, n: 0.0)
    lu = analyze(petit, tools)
    assert lu.scenes == ()
    assert any("une seule fois" in w for w in lu.warnings)
    assert "sendcmd=" not in pipeline.filter_chain(lu, s)
