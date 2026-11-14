# Décisions techniques — VHS Restore AI (audit de la phase 1)

Ce document est court et sert de référence unique. Date : novembre 2026.

## Stack retenue

| Rôle | Choix | Licence | Statut |
|---|---|---|---|
| Interface | PySide6 ≥ 6.5 (pip) | LGPLv3 | obligatoire |
| Analyse | FFprobe + filtre `idet` de FFmpeg | GPL (build gyan.dev) | obligatoire |
| Désentrelacement | `bwdif` (FFmpeg), une image par trame | idem | obligatoire |
| Bruit / parasites | `hqdn3d` + `removegrain` mode 1 (FFmpeg) | idem | obligatoire |
| Couleurs / netteté | `eq`, `cas` (FFmpeg ≥ 5.0) | idem | obligatoire |
| Mise à l'échelle classique | `scale` lanczos, matrice BT.601 → BT.709 | idem | obligatoire |
| Encodage | libx264 CRF 18 + AAC 192k, MP4 `faststart` | idem | obligatoire |
| IA (facultatif) | Real-ESRGAN ncnn-vulkan v0.2.5.0, modèle `realesrgan-x4plus` | BSD-3 | optionnel |

**Une seule dépendance Python : PySide6.** Tout le reste est invoqué comme exécutable externe
(listes d'arguments, jamais de shell), donc chaque moteur peut être remplacé seul.

## Pourquoi pas les autres (pour l'instant)

- **VapourSynth + QTGMC** : meilleur désentrelaceur connu, mais il faut VapourSynth, havsfunc,
  mvtools, nnedi3, fmtconv… et des versions compatibles entre elles : trop fragile pour une
  installation par des non-techniciens. `bwdif` est intégré à FFmpeg et donne un résultat correct.
  QTGMC reste le premier module à ajouter (adaptateur : remplacer l'étape 2 de `pipeline.py`).
- **Video2X 6.x** : orchestre Real-ESRGAN/Real-CUGAN/RIFE, mais licence AGPLv3, installateur Qt
  et chaîne d'encodage propre à lui. Nous n'utilisons qu'un seul modèle : appeler directement
  Real-ESRGAN est plus simple et laisse l'encodage (synchro son, 4:3, couleurs) sous notre contrôle.
- **nlmeans / bm3d** (FFmpeg) : qualité de débruitage supérieure, mais beaucoup plus lent.
  Candidats pour un futur réglage « qualité lente ».
- **Stabilisation** (`vidstabdetect/transform`, disponibles dans FFmpeg) : demande deux passes
  et recadre l'image. Reportée.
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
4. Les captures à timestamps irréguliers (VFR, images perdues) sont ramenées à une cadence constante
   par FFmpeg. C'est en général correct, mais ce n'est pas vérifié sur de vraies captures.

## Sources consultées

- FFmpeg filters : https://ffmpeg.org/ffmpeg-filters.html (bwdif, idet, hqdn3d, removegrain, cas)
- Builds Windows : https://www.gyan.dev/ffmpeg/builds/
- Real-ESRGAN : https://github.com/xinntao/Real-ESRGAN (releases v0.2.5.0, exécutables ncnn-vulkan)
- Video2X : https://github.com/k4yt3x/video2x (6.x, AGPLv3)
