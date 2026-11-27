"""Pièges propres à Windows et aux vrais dossiers de l'utilisateur, relevés par un audit.

Chaque cas a été reproduit avant correction (sous Linux, ou en imitant le comportement de Windows).
"""
import dataclasses
import os
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import ff
from vhs_restore import ergonomie, photo, pipeline, tools as tools_mod
from vhs_restore.probe import MediaInfo
from vhs_restore.profiles import profile_for


def _image(path: Path, gris: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ff("-f", "lavfi", "-i", "mandelbrot=size=320x240" if gris else "testsrc2=size=320x240", "-frames:v", "1",
       *(["-vf", "format=gray"] if gris else []), "-update", "1", str(path))
    return path


@pytest.mark.parametrize("nom", ["Photo%20dimanche.jpg", "Couleur%03d.png"])
def test_photo_au_nom_avec_pourcent(tools, tmp_path, nom):
    """« Photo%20dimanche.jpg » (nom venu d'Internet) était lu comme une suite d'images numérotées."""
    d = tmp_path / "Photos%20dimanche"
    src = _image(d / nom, gris=nom.endswith(".jpg"))
    info = photo.analyze_photo(src, tools)
    assert (info.width, info.height) == (320, 240)
    s = pipeline.Settings(profile_for("equilibre"))
    out = photo.restore_photo(info, s, photo.output_path(info, s, d), tools)
    assert out.is_file() and out.parent == d and "%" in out.name
    prev = photo.make_photo_preview(info, s, tools, tmp_path / "apercu")
    assert prev.stills[0].is_file()
    assert sorted(x.name for x in d.iterdir()) == sorted([nom, out.name])      # rien d'autre d'écrit


def test_resultat_ouvert_dans_un_lecteur(tmp_path, monkeypatch):
    """Windows : un lecteur vidéo garde le fichier ouvert. On réessaie, puis on explique sans tout perdre."""
    part, final = tmp_path / "noel.partiel.mp4", tmp_path / "noel.mp4"
    part.write_bytes(b"film")
    essais = []

    def refuse(a, b):
        essais.append(1)
        raise PermissionError(32, "Le processus ne peut pas accéder au fichier")
    monkeypatch.setattr(tools_mod, "_publier", refuse)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    with pytest.raises(tools_mod.FichierOccupe) as e:
        tools_mod.finaliser(part, final, essais=3)
    assert len(essais) == 3 and part.is_file()                 # le travail fini n'est pas effacé
    clair, _ = ergonomie.expliquer(str(e.value))
    assert "renommez ce fichier" in clair and "noel.mp4" in clair


def test_fichier_verrouille_explique():
    clair, _ = ergonomie.expliquer("[WinError 32] Le processus ne peut pas accéder au fichier car ce fichier "
                                   "est utilisé par un autre processus. Permission denied")
    assert "autre programme" in clair and "n'est plus là" not in clair


def test_cle_fat32_prevenue(monkeypatch):
    info = MediaInfo(path=Path("a.mpg"), has_audio=True, duration=2 * 3600, fps=Fraction(25),
                     width=720, height=576)
    s = pipeline.Settings(profile_for("equilibre"))
    monkeypatch.setattr(pipeline, "systeme_de_fichiers", lambda p: "FAT32")
    with pytest.raises(tools_mod.ToolError, match="FAT32"):
        pipeline.check_fat32(info, s, Path("."))
    pipeline.check_fat32(dataclasses.replace(info, duration=1800), s, Path("."))   # 30 min : ça tient
    monkeypatch.setattr(pipeline, "systeme_de_fichiers", lambda p: "NTFS")
    pipeline.check_fat32(info, s, Path("."))


def test_deux_dvd_dans_le_dossier_de_secours(tools, tmp_path, monkeypatch):
    """Deux disques protégés aux noms identiques (VTS_01) : le second était dit « déjà fait »."""
    secours = tmp_path / "Vidéos" / "Films restaurés"
    monkeypatch.setenv("VHSRA_SORTIE", str(secours))
    monkeypatch.setattr(pipeline, "is_writable", lambda d: False)
    for disque in ("disque 1", "disque 2"):
        d = tmp_path / disque
        d.mkdir()
        ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-t", "1", "-c:v", "mpeg2video",
           str(d / "film.mpg"))
        reglages = lambda info: pipeline.Settings(profile_for("fidele", "video"))   # noqa: E731
        res = pipeline.restore_folder(d, tools, reglages)
        assert len(res.done) == 1 and not res.skipped, (disque, res)
    assert len(list(secours.glob("film_restaure_*.mp4"))) == 2


def test_un_fichier_bloque_n_arrete_pas_le_dossier(tools, tmp_path, monkeypatch):
    d = tmp_path / "films"
    d.mkdir()
    for n in ("a", "b"):
        ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-t", "1", "-c:v", "mpeg2video",
           str(d / f"{n}.mpg"))
    vrai = pipeline.export

    def export(info, s, out, t, **k):
        if info.path.name == "a.mpg":
            raise PermissionError(13, "Permission denied")
        return vrai(info, s, out, t, **k)
    monkeypatch.setattr(pipeline, "export", export)
    res = pipeline.restore_folder(d, tools, lambda info: pipeline.Settings(profile_for("fidele", "video")))
    assert len(res.done) == 1 and res.errors and res.errors[0][0] == "a.mpg"


@pytest.mark.skipif(os.name == "nt", reason="un « % » dans le dossier temporaire : imité sous Linux")
def test_mode_ia_avec_pourcent_dans_le_dossier_temporaire(tools, tmp_path, monkeypatch):
    """Extraction des images pour l'IA : le motif « %08d.png » est relatif au dossier de travail."""
    travail = tmp_path / "temp 50% ok"
    travail.mkdir()
    monkeypatch.setenv("VHSRA_TMP", str(travail))
    film = tmp_path / "film.mkv"
    ff("-f", "lavfi", "-i", "testsrc2=size=160x120:rate=25", "-f", "lavfi", "-i", "sine=d=1",
       "-t", "1", "-c:v", "ffv1", "-c:a", "flac", str(film))

    class FauxAgrandisseur:            # pas de carte graphique ici : copie des images, agrandies x4
        scale = 4

        def __init__(self, tool):
            pass

        def upscale_dir(self, src, dst, cancel=None, on_count=None):
            import subprocess
            dst.mkdir(parents=True, exist_ok=True)
            subprocess.run([tools.ffmpeg.path, "-v", "error", "-start_number", "0", "-i", "%08d.png",
                            "-vf", "scale=iw*4:ih*4", "-start_number", "0", os.path.join("..", dst.name, "%08d.png")],
                           cwd=src, check=True)
    monkeypatch.setattr(pipeline, "RealEsrganUpscaler", FauxAgrandisseur)
    from vhs_restore.probe import analyze
    info = analyze(film, tools)
    s = dataclasses.replace(pipeline.Settings(profile_for("equilibre", "video")), use_ai=True, resolution="1080")
    out = pipeline.export(info, s, tmp_path / "film_ia.mp4", tools)
    assert out.is_file() and not list(travail.iterdir())


def test_morceaux_reservent_le_disque_temporaire(monkeypatch, tmp_path):
    """Le résultat seul tiendrait ; les morceaux, en plus, non. On refuse avant d'encoder."""
    info = MediaInfo(path=tmp_path / "a.mpg", has_audio=True, duration=3600, fps=Fraction(25),
                     width=720, height=576)
    s = pipeline.Settings(profile_for("equilibre"))
    final, _ = pipeline.disk_needs(info, s, None, 3600)

    class _Stat:
        st_dev = 1

    class _Usage:
        def __init__(self, free):
            self.free = free

    monkeypatch.setattr(pipeline.os, "stat", lambda _p: _Stat())
    monkeypatch.setattr(pipeline.shutil, "disk_usage", lambda _p: _Usage(final * 1.2))
    pipeline.check_disk_space(info, s, tmp_path, None, 3600)
    with pytest.raises(tools_mod.ToolError, match="Espace disque"):
        pipeline.check_disk_space(info, s, tmp_path, None, 3600, extra_temp=final)


def test_copie_sans_vides_refuse_la_cle_fat32(monkeypatch, tmp_path):
    from vhs_restore import vides
    monkeypatch.setattr(pipeline, "systeme_de_fichiers", lambda _p: "FAT32")
    with pytest.raises(tools_mod.ToolError, match="FAT32"):
        vides.verifier_place(tmp_path / "copie.mp4", 90 * 60)
    vides.verifier_place(tmp_path / "copie.mp4", 20 * 60)
    clair, _ = ergonomie.expliquer(
        "La copie serait enregistrée sur une clé USB ou une carte au format FAT32.")
    assert "FAT32" in clair


def test_film_origine_trop_long_dit_de_le_deplacer(monkeypatch, tmp_path):
    long = tmp_path
    while len(str(long)) < 260:
        long = long / ("dossier" * 8)
    monkeypatch.setattr(tools_mod, "IS_WIN", True)
    with pytest.raises(tools_mod.ToolError, match="film d'origine") as origine:
        tools_mod.verifier_chemin(long / "film.mpg", origine=True)
    with pytest.raises(tools_mod.ToolError, match="fichier à créer"):
        tools_mod.verifier_chemin(long / "sortie.mp4")
    clair, _ = ergonomie.expliquer(str(origine.value))
    assert "Déplacez le film" in clair


def test_outil_ouvert_n_est_pas_desinstalle(tmp_path, monkeypatch):
    from vhs_restore import installer
    final = tmp_path / "LosslessCut"
    final.mkdir()
    (final / "LosslessCut.exe").write_text("ancien", encoding="utf-8")
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "LosslessCut.exe").write_text("nouveau", encoding="utf-8")
    vrai = Path.rename

    def bloque(self, dest):
        if self == final:
            raise PermissionError(5, "access")
        return vrai(self, dest)

    monkeypatch.setattr(Path, "rename", bloque)
    # message juste (n°21) : l'antivirus d'abord (ordinateur tout juste allumé chez l'utilisateur),
    # puis le programme ouvert
    with pytest.raises(tools_mod.ToolError, match="refuse de remplacer") as e:
        installer._poser_installation(staged, final, "LosslessCut")
    assert "Historique de protection" in str(e.value) and "fermez-le" in str(e.value)
    assert (final / "LosslessCut.exe").read_text(encoding="utf-8") == "ancien"
    clair, _ = ergonomie.expliquer(str(tools_mod.ToolError(
        "LosslessCut est ouvert dans un autre programme. Fermez-le, puis recommencez l'installation.")))
    assert "Fermez-le" in clair


def test_lancement_depuis_un_chemin_reseau():
    racine = Path(__file__).resolve().parent.parent
    lancer = (racine / "lancer.bat").read_text(encoding="utf-8")
    installer = (racine / "installer.bat").read_text(encoding="utf-8")
    assert "cd /d" not in lancer
    assert "/D" in lancer and "%~dp0" in lancer
    assert "pushd" in installer and "popd" in installer
    assert "cd /d" not in installer

