# Décisions techniques — VHS Restore AI (audit de la phase 1)

Ce document est court et sert de référence unique. Date : novembre 2026.

## Stack retenue

| Rôle | Choix | Licence | Statut |
|---|---|---|---|
| Interface | PySide6 ≥ 6.5 (pip) | LGPLv3 | obligatoire |
| Analyse | FFprobe + filtre `idet` de FFmpeg | GPL (build gyan.dev) | obligatoire |
| Désentrelacement | `bwdif` (FFmpeg), une image par trame | idem | obligatoire |
| Bruit / parasites | `hqdn3d` + `removegrain` mode 1 (FFmpeg) | idem | obligatoire |
| Débruitage haute qualité | `fftdnoiz` + `hqdn3d` en renfort chroma (FFmpeg) | idem | option |
| Couleurs / netteté | `eq`, `cas` (FFmpeg ≥ 5.0) | idem | obligatoire |
| Mise à l'échelle classique | `scale` lanczos, matrice BT.601 → BT.709 | idem | obligatoire |
| Encodage | libx264 CRF 18 + AAC 192k, MP4 `faststart` | idem | obligatoire |
| Désentrelacement HQ (facultatif) | QTGMC = `QTempGaussMC` de vs-jetpack 3.0, VapourSynth R82 (pip) | VapourSynth LGPL-2.1+, vs-jetpack MIT, plugins MIT/LGPL/GPL-2.0 (mvutensils, znedi3) | optionnel |
| Stabilisation (facultatif) | vid.stab : `vidstabdetect` + `vidstabtransform` (FFmpeg) | GPL-2.0 (libvidstab) | optionnel |
| IA (facultatif) | Real-ESRGAN ncnn-vulkan v0.2.5.0, modèle `realesrgan-x4plus` | BSD-3 | optionnel |

**Une seule dépendance Python : PySide6.** Tout le reste est invoqué comme exécutable externe
(listes d'arguments, jamais de shell), donc chaque moteur peut être remplacé seul.

## Pourquoi pas les autres (pour l'instant)

- **QTGMC de havsfunc** : abandonné par ses mainteneurs au profit de vs-jetpack. Nous utilisons
  `QTempGaussMC`, sa réécriture maintenue.
- **Video2X 6.x** : orchestre Real-ESRGAN/Real-CUGAN/RIFE, mais licence AGPLv3, installateur Qt
  et chaîne d'encodage propre à lui. Nous n'utilisons qu'un seul modèle : appeler directement
  Real-ESRGAN est plus simple et laisse l'encodage (synchro son, 4:3, couleurs) sous notre contrôle.
- **Encodage GPU (NVENC/QSV/AMF)** : non retenu dans le MVP. libx264 donne une qualité stable
  partout ; l'accélération GPU est utilisée là où elle compte (Real-ESRGAN, via Vulkan).

## Règles de traitement

- **Entrelacement** : on mesure le contenu avec `idet` (600 images, au tiers du film). La mesure
  prime sur les métadonnées seulement si elle est nette (rapport ≥ 3 et ≥ 30 % d'images décidées).
  Sinon on se replie sur les métadonnées. Sans aucune preuve : « indéterminé », pas de
  désentrelacement, et l'interface demande un choix manuel. On ne suppose jamais l'entrelacement.
- **Cadence** : `bwdif mode=send_field` → 25i devient 50p (29,97i → 59,94p). On garde ainsi les
  50 mouvements par seconde du caméscope ; ni images inventées, ni images perdues.
- **Format d'affichage** : on respecte le rapport de pixel du fichier. Une capture SD (720×576,
  720×480…) sans cette information est supposée 4:3, avec un avertissement et un choix manuel.
  En résolution d'origine, on garde les pixels non carrés (`setsar`). En HD, on passe en pixels
  carrés, 1440×1080 (2880×2160 en 4K) : jamais de déformation de l'image.
- **Couleurs** : BT.601 en entrée (SD), BT.709 en HD, avec des métadonnées de couleur explicites.
- **Pertes** : une seule compression avec perte (H.264 final). Le mode IA passe par un
  intermédiaire sans perte (FFV1 + FLAC), puis par des images PNG, traitées par paquets
  de 60 images pour limiter l'espace disque. Un encodeur unique les reçoit par un tube.
- **Sécurité des fichiers** : l'original n'est jamais ouvert en écriture. La sortie est écrite dans
  `*.partiel.mp4` puis renommée à la fin ; elle est supprimée en cas d'erreur ou d'annulation. Un nom
  existant n'est jamais écrasé.

## QTGMC (phase 3)

- **Installation** : depuis VapourSynth R74, tout passe par pip, plugins compris
  (`vapoursynth-mvutensils`, `-znedi3`, `-bestsource`, `-resize2`). On n'a plus besoin de vsrepo
  ni de l'installateur Windows. Versions figées dans `requirements-qtgmc.txt`, dans le `.venv` de
  l'application, avec Python 3.12 ou plus. L'extra pip `vsjetpack[deinterlace]` n'a pas été retenu :
  il exige `vapoursynth-ffms2>=5.3`, introuvable sur PyPI pour Linux, et il installe beaucoup plus
  que nécessaire.
- **Intégration** : un script fixe, `vhs_restore/qtgmc.vpy`, reçoit uniquement des arguments
  (`vspipe -a`) ; aucun code n'est généré. vspipe envoie du y4m à FFmpeg par un tube, sans shell.
  FFmpeg lit le son dans la source et applique le reste de la chaîne. Une annulation arrête les deux
  processus.
- **Détection** : au démarrage, un essai à blanc sur une image vide (environ 1 s) vérifie vspipe,
  vs-jetpack et les plugins. Un plugin manquant est nommé dans le message d'erreur.
- **Choix par défaut** : QTGMC pour Équilibré et Maximum s'il est installé, bwdif pour Fidèle.
  Les réglages QTGMC par défaut lissent un peu le bruit et le scintillement, ce qui s'éloigne du
  rendu d'origine. Le choix reste modifiable dans l'interface.
- **Source** : BestSource lit la vidéo à l'image près, mais doit d'abord indexer tout le fichier
  (cache réutilisé ensuite). Sur un long film, cette première étape peut prendre plusieurs minutes
  sans progression visible.
- **Mesuré ici** (Linux, 4 cœurs, 720×576) : environ 31 images/s pour QTGMC seul. Rien n'a été
  mesuré sous Windows.

## Stabilisation (phase 4)

- **Choix** : vid.stab, déjà présent dans FFmpeg (le build gyan.dev « essentials » contient
  libvidstab). Aucune nouvelle dépendance. `deshake` a été écarté : il est plus simple mais moins
  précis. Si le FFmpeg utilisé n'a pas libvidstab, la case est grisée et le motif est indiqué.
- **Deux passes** : la passe 1 mesure les mouvements (`transforms.trf`), la passe 2 corrige. Les
  deux passes reçoivent exactement les mêmes images (mêmes entrées, même désentrelacement), sinon
  les corrections ne tomberaient pas sur les bonnes images. Avec QTGMC, il est donc exécuté deux
  fois. Le fichier est nommé relativement au dossier de travail, ce qui évite d'échapper un chemin
  Windows dans le graphe de filtres.
- **Place dans la chaîne** : juste après le désentrelacement, avant le débruitage temporel
  (hqdn3d est plus efficace sur des images alignées) et avant l'agrandissement. Le travail porte
  ainsi sur moins de pixels.
- **Réglages** (`pipeline.py`) : shakiness 5, accuracy 15. Le lissage vaut ±0,3 s (15 images
  en 50p). La correction est bornée à 4 % de la largeur et à 2° de rotation, ce qui limite le
  zoom. Le zoom statique optimal masque les bords ; s'il reste un bord, il est noir plutôt que
  rempli avec une image passée.
- **Fidélité** : la stabilisation agrandit légèrement l'image, donc le cadrage change un peu.
  Elle est désactivée par défaut dans tous les profils et se juge sur l'aperçu.
- **Mesuré** (vidéo de synthèse tremblée, scène fixe) : la différence moyenne entre images
  successives baisse de 59 % (30,9 → 12,7). Aucune mesure sur de vraies cassettes.

## Débruitage haute qualité (phase 5)

Banc d'essai : fractale animée détaillée (720×576), bruit ajouté fort sur la chroma et variable
dans le temps. Mesure : PSNR et SSIM par rapport à l'image propre, vitesse sur 4 cœurs.

| Filtre | PSNR Y | PSNR moyen | SSIM Y | images/s |
|---|---|---|---|---|
| aucun (bruité) | 33,4 | 29,7 | 0,74 | – |
| hqdn3d 3:5:4.5:7 (Équilibré) | 34,1 | 30,1 | 0,78 | 61 |
| nlmeans s=4 | 41,1 | 30,9 | 0,99 | 2,2 |
| fftdnoiz σ9 | 39,4 | 33,0 | 0,97 | 20 |
| **fftdnoiz σ8 + hqdn3d=0:6:0:9** | 39,8 | **33,7** | 0,98 | 21 |
| bm3d (réglages testés) | sortie identique à l'entrée | | | 2,9 |
| MDegrain (vs-jetpack) | sortie identique à l'entrée | | | – |

- **Retenu** : `fftdnoiz` (FFT 3D sur l'image et ses deux voisines), suivi d'un `hqdn3d` réglé pour
  la chroma. Le passage par l'export complet le confirme : +2,9 / +3,9 / +4,8 dB par rapport à
  hqdn3d (Fidèle / Équilibré / Maximum). Il est environ 3 fois plus lent. C'est une case à cocher,
  désactivée par défaut, qui remplace hqdn3d.
- **Écartés** : `nlmeans`, excellent sur la luminance mais faible sur la chroma (pourtant la
  composante dominante sur VHS) et 10 fois plus lent. `bm3d` et MDegrain n'ont rien modifié avec
  les réglages essayés (MDegrain est probablement bloqué par sa détection de changement de plan
  sous un bruit aussi fort) ; les mettre au point coûterait plus que le gain attendu.
- **Limite** : un bruit artificiel n'est pas un bruit VHS réel (traînées horizontales, bruit
  basse fréquence). Les réglages sont à confirmer sur de vraies cassettes.

## IA : limites assumées

Real-ESRGAN est entraîné sur des dégradations synthétiques (flou, bruit, JPEG), pas sur des
défauts VHS/Video8 (traînées de chroma, dropouts, jitter). Sur des visages en basse résolution, il
peut produire une peau « cireuse » ou des détails inventés. L'IA est donc facultative et désactivée
par défaut, sauf dans le profil Maximum. L'aperçu sert justement à juger ce risque. Aucune qualité
n'a été vérifiée sur une vraie cassette.

## Risques principaux

1. Le build FFmpeg « release essentials » suit la dernière version : l'application vérifie au
   démarrage la présence des filtres nécessaires.
2. Real-ESRGAN ncnn n'a plus de nouvelle version depuis 2022. Il demande un GPU compatible Vulkan ;
   sans GPU, le processeur est trop lent pour un film entier.
3. La gestion des chemins avec accents par realesrgan-ncnn-vulkan sous Windows n'a pas été vérifiée.
   Si elle pose problème, définir `VHSRA_TMP=C:\vhs_tmp` pour un dossier de travail ASCII.
4. QTGMC sous Windows : le paquet pip de VapourSynth fournit `vspipe.exe` dans `.venv\Scripts`
   (supposé, non vérifié ici). Une installation « portable » (vspipe.bat) n'est pas prise en charge :
   les .bat sont exclus volontairement, car l'échappement des arguments par cmd n'est pas sûr.
5. Les captures à timestamps irréguliers (VFR, images perdues) sont ramenées à une cadence constante
   par FFmpeg. C'est en général correct, mais ce n'est pas vérifié sur de vraies captures.

## Sources consultées

- FFmpeg filters : https://ffmpeg.org/ffmpeg-filters.html (bwdif, idet, hqdn3d, removegrain, cas)
- Builds Windows : https://www.gyan.dev/ffmpeg/builds/
- Real-ESRGAN : https://github.com/xinntao/Real-ESRGAN (releases v0.2.5.0, exécutables ncnn-vulkan)
- Video2X : https://github.com/k4yt3x/video2x (6.x, AGPLv3)
- VapourSynth R74 (pip) : https://www.vapoursynth.com/2026/03/26/new-packaging-and-install-methods-in-r74/
- QTempGaussMC : https://forum.doom9.org/showthread.php?p=2050828 ; havsfunc :
  https://github.com/HomeOfVapourSynthEvolution/havsfunc/releases
