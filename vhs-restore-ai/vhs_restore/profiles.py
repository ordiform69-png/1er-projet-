"""Les trois profils de restauration.

Chaque valeur correspond directement à un paramètre de filtre FFmpeg. Ce sont
des points de départ raisonnables pour des captures VHS/Video8, pas des
réglages universels : l'aperçu sert à juger sur VOTRE vidéo.

- denoise : hqdn3d = (luma spatial, chroma spatial, luma temporel, chroma temporel).
  Défauts FFmpeg : 4:3:6:4.5. Le bruit chroma (taches colorées) étant dominant
  sur VHS/Video8, la chroma est filtrée plus fort que la luminance, qui porte
  le détail des visages.
- denoise_hq : débruitage « haute qualité » (option, ~3x plus lent), qui remplace hqdn3d :
  fftdnoiz (débruitage par FFT 3D sur l'image et ses deux voisines) avec ce sigma,
  puis hqdn3d=0:c:0:ct en renfort sur la chroma. Mesuré sur une vidéo détaillée
  bruitée artificiellement : +3,6 dB de PSNR moyen par rapport à hqdn3d pour
  Équilibré (voir DECISIONS.md).
- despeckle : removegrain mode 1 = ramène un pixel isolé dans l'intervalle de ses
  8 voisins ; enlève points et petits parasites sans flouter.
- contrast / saturation : filtre eq (1.0 = inchangé).
- deinterlacer : désentrelaceur préféré. « qtgmc » (QTGMC, VapourSynth) est utilisé
  s'il est installé, sinon « bwdif » (FFmpeg). Fidèle garde bwdif : QTGMC lisse
  aussi un peu le bruit et le scintillement, ce qui s'éloigne du rendu d'origine.
- sharpen : filtre cas (Contrast Adaptive Sharpening, 0 = désactivé), appliqué
  après l'agrandissement. Désactivé quand l'IA est utilisée (elle renforce déjà
  les contours ; un double renforcement crée des halos).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    description: str
    denoise: tuple[float, float, float, float] | None
    despeckle: bool
    contrast: float
    saturation: float
    sharpen: float
    default_resolution: str       # "source" | "1080" | "2160"
    ai_default: bool
    deinterlacer: str = "qtgmc"   # "qtgmc" | "bwdif"
    denoise_hq: tuple[float, float, float] = (8.0, 6.0, 9.0)   # sigma fftdnoiz, chroma spatial, chroma temporel


PROFILES: dict[str, Profile] = {p.key: p for p in (
    Profile("fidele", "Fidèle",
            "Nettoyage léger du bruit, couleurs et cadrage d'origine, pas d'agrandissement.",
            denoise=(1.5, 3.0, 2.0, 4.0), despeckle=False,
            contrast=1.0, saturation=1.0, sharpen=0.0,
            default_resolution="source", ai_default=False, deinterlacer="bwdif",
            denoise_hq=(5.0, 4.0, 6.0)),
    Profile("equilibre", "Équilibré",
            "Réduction du bruit et des parasites, couleurs ravivées modérément, "
            "netteté prudente. Export Full HD possible.",
            denoise=(3.0, 5.0, 4.5, 7.0), despeckle=True,
            contrast=1.04, saturation=1.08, sharpen=0.3,
            default_resolution="source", ai_default=False),
    Profile("maximum", "Maximum",
            "Nettoyage plus fort et Full HD par défaut ; amélioration IA (Real-ESRGAN) "
            "si elle est installée. À vérifier sur l'aperçu : visages et peau.",
            denoise=(4.0, 7.0, 6.0, 10.0), despeckle=True,
            contrast=1.06, saturation=1.12, sharpen=0.45,
            default_resolution="1080", ai_default=True, denoise_hq=(11.0, 8.0, 12.0)),
)}

RESOLUTIONS = {
    "source": "Résolution d'origine",
    "1080": "Full HD (1080 lignes)",
    "2160": "4K (2160 lignes, IA requise)",
}
