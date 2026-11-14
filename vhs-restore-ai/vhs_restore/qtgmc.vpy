# Script VapourSynth fixe, piloté par VHS Restore AI via « vspipe -a nom=valeur ».
# Aucun code n'est généré : seuls des arguments sont transmis.
#   src   : chemin de la vidéo source
#   tff   : "1" trame haute en premier, "0" trame basse en premier
#   first : première image SOURCE à traiter (aperçu), count : nombre d'images source (0 = jusqu'à la fin)
#   check : "1" = test d'installation sur une image vide (aucun fichier lu)
# QTGMC = QTempGaussMC de vs-jetpack (réécriture maintenue de QTGMC), réglages par défaut.
# Sortie : une image par trame (double cadence), même format de pixels que la source.
import vapoursynth as vs
from vapoursynth import core
from vsdeinterlace import QTempGaussMC

_args = globals()
tff = _args.get("tff", "1") == "1"
if _args.get("check") == "1":
    src = core.std.BlankClip(format=vs.YUV420P8, width=720, height=576, length=12, fpsnum=25, fpsden=1)
else:
    src = core.bs.VideoSource(source=_args["src"])
src = core.std.SetFieldBased(src, 2 if tff else 1)

clip = QTempGaussMC().deinterlace(src, tff=tff)

first = int(_args.get("first", "0"))
count = int(_args.get("count", "0"))
if count:
    clip = clip[2 * first: min(clip.num_frames, 2 * (first + count))]
elif first:
    clip = clip[2 * first:]
clip.set_output()
