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

## Origines des films : vidéo, pellicule, transfert (phase 6)

Une seule chaîne FFmpeg. L'origine (`Settings.source`) ne change que des paramètres, jamais de moteur.

| | VIDÉO (VHS, Video8, Betamax…) | FILM (Super 8, 8, 16, 9,5 mm scannés) | TRANSFERT (film copié sur vidéo) |
|---|---|---|---|
| Désentrelacement | si mesuré : bwdif/QTGMC, 50p | **jamais automatique** (choix manuel seulement) | si mesuré : `fieldmatch` puis `bwdif` sur les seules images encore mélangées, 25p |
| Cadence exportée | 50p (une image par trame) | celle du fichier, ou la **cadence de tournage choisie** | celle du support (25p) |
| Images répétées | – | – | conservées : aucune suppression (`decimate`), cadence d'origine non supposée |
| Débruitage | profils existants (inchangés) | nettement plus léger, Fidèle sans débruitage : le grain est préservé | luminance plus douce, chroma comme en vidéo |
| Scintillement | – | option `deflicker` | option `deflicker` |

- **Origine suggérée, jamais imposée** : l'analyse existante (`idet` + `signalstats`, même passe)
  fournit la cadence, les champs ou images répétés et la saturation. Si la vidéo est entrelacée,
  une seconde passe courte compare les trames hautes successives : une image de film répartie sur
  plusieurs trames donne des trames identiques au bruit près. `idet` seul ne voit plus ces
  répétitions dès qu'il y a du bruit de bande (0 % mesuré sur l'échantillon de test), alors que
  cette mesure en trouve 26 à 28 %, comme le veut la théorie (18 → 25 : 7/25). Sur les trois
  vidéos de caméscope de test, elle trouve 0 %. Le codec n'est jamais utilisé comme indice. Choix
  « Je ne sais pas » = suivre la suggestion, affichée avec sa raison ; elle reste modifiable.
- **Cadence de tournage** (16, 18 ou 24 i/s, pellicule seulement) : `setpts` re-date les images
  sans en créer ni en supprimer (pas d'interpolation, pas de conversion forcée en 25 i/s). Le son
  éventuel suit avec `atempo`, ce qui garde sa hauteur et la synchronisation. Les pages de la NARA
  consultées ne donnent aucune cadence : les valeurs proposées sont les cadences d'usage, jamais
  appliquées automatiquement.
- **Noir et blanc** : détecté pour information (saturation moyenne < 15). Aucune colorisation
  n'existe dans le logiciel.
- **Films muets** : la piste son est facultative (`0:a:0?`). Aucune piste n'est créée (vérifié par
  test, en export comme en aperçu).
- **Fidélité mesurée, pas seulement le débruitage** : sur une pellicule de synthèse avec grain,
  la proximité avec le scan d'origine (PSNR Y, image par image) vaut 34,7 dB avec les réglages
  vidéo, 36,7 dB avec Équilibré pellicule et 48,9 dB avec Fidèle pellicule. Ici, une PSNR élevée
  signifie « texture d'origine conservée ».
- **Reporté (P2)** : rayures et poussières image par image. FFmpeg n'a pas de filtre adapté
  (`removegrain` ne traite que les points isolés). Les solutions connues sont des plugins
  VapourSynth issus d'AviSynth (famille DeSpot/DeScratch) ; je n'ai pas vérifié leur maintenance
  ni leur disponibilité par pip : pas d'intégration. Restent aussi en P2 la correction automatique
  des couleurs décolorées (trop risquée pour la fidélité), la suppression des images répétées
  d'un transfert (cadence d'origine rarement certaine) et l'IA spécialisée pellicule.

## Test sur de vraies archives libres de droits (phase 7)

Extraits de 30 s téléchargés sur archive.org, non versionnés :
- « Home Movie: González Family, circa 1970s » (Amateur Library Collection Fund, CC BY-NC-SA) :
  scan image par image 2048×1556 à 18 i/s, couleur très décolorée (dominante bleu-cyan), grain
  fort, poussières, rayures, piste son vide ajoutée.
- « DEX No. 56 Exercising (June 1988) (Vintage VHS Camcorder Footage) » (CC0) : VOB d'origine,
  MPEG-2 NTSC 352×240 (mode longue durée d'un graveur DVD), 4:3, son AC3.

Constats et corrections :
1. **Aperçu décalé de 0,5 s sur le VOB réel** : au point de saut, l'image reprend 0,4 s après le
   son. L'export gère ce cas correctement (synchronisation avec le son), mais la moitié
   « original » de l'aperçu était assemblée d'après ses horodatages et se décalait (15 images de
   décalage mesurées). Correction : l'original de l'aperçu suit le même chemin que l'export.
   Décalage mesuré ensuite : 0 image. Un test de non-régression échoue avec l'ancien code.
2. **Couleur décolorée prise pour du noir et blanc** (saturation moyenne 8) : le critère est
   désormais la saturation des pixels les plus colorés (noir et blanc ≈ 4, film décoloré ≈ 15),
   avec un état « couleurs très pâles ». Aucune correction automatique des couleurs n'est faite.
3. **Piste son vide** (-91 dB) annoncée comme « silencieuse ». Elle est conservée telle quelle.
4. Ce qui était correct d'emblée : NTSC, 4:3 avec pixels non carrés, balayage progressif et
   origine « vidéo, à confirmer » pour la VHS ; origine « pellicule », 18 i/s et aucun
   désentrelacement pour le film.

Rendu (comparaison à 100 %, même image) : en profil Fidèle, la pellicule reste quasi identique
au scan ; Équilibré pellicule atténue légèrement le grain sans lisser ; les réglages vidéo
appliqués au même film lissent davantage, ce qui confirme l'intérêt des profils par origine.
Le débruitage haute qualité avec anti-scintillement réduit la variation de luminosité d'une
image à l'autre de 11 % (0,95 → 0,84) sans aplatir la texture. Les poussières et rayures
restent : ce n'est pas traité (P2). Sur la VHS, la dominante verte reste, faute de correction
automatique des couleurs (choix de fidélité, à reconsidérer avec de vraies cassettes).

## Paquet Windows et poussières/rayures (phase 8)

- **Fabrication Windows** (`.github/workflows/vhs-restore-windows.yml`, `VHSRestoreAI.spec`) :
  PyInstaller (dossier autonome) + FFmpeg gyan.dev « essentials » copié dans `tools\ffmpeg`.
  Sur la machine Windows de GitHub, la suite de tests passe, puis l'application fabriquée est lancée
  avec `--autotest` sans Python ni FFmpeg du système, depuis un dossier accentué : analyse et
  restauration Full HD 50p, 4:3, son conservé. L'artefact pèse environ 130 Mo.
- Problème rencontré : FFmpeg 9 a supprimé l'option `-top`, qui ne servait qu'à générer les
  vidéos d'essai ; l'application elle-même n'était pas concernée. La version de FFmpeg n'est pas
  figée (dernière version « release » de gyan.dev) : à reconsidérer si une mise à jour casse
  quelque chose. La question est posée à Grok Build (`partage-grok/DEMANDE-GROK-BUILD-1.md`).
- **DeScratch** (rayures verticales, VapourSynth) : installable par pip (`vapoursynth-descratch`
  4.0, GPL-2.0). Essai sur l'extrait González avec les réglages par défaut : une rayure sur deux
  est détectée et effacée (13 i/s en 2048×1556), et aucune verticale réelle de l'architecture n'est
  touchée. C'est prudent mais incomplet : **pas encore intégré**. Il faut d'autres films rayés
  pour régler `mindif`/`maxwidth`, et l'avis de Grok.
- **SpotLess** (poussières) : ce n'est pas un paquet pip, et vs-jetpack n'a pas d'équivalent.
  Reporté.
- **Analog Repair** (https://github.com/Bratwurstexe/ANALOG_REPAIR, lien fourni par Grok) : le
  dépôt existe. Licence MIT, 5 commits, 0 étoile, dernier commit le 26/10/2026. Moteur Python de
  3 600 lignes (NumPy + OpenCV + FFmpeg, aucun modèle d'IA), interface .NET. Code lu avant
  exécution : pas d'accès réseau, FFmpeg appelé sans shell, seuls ses fichiers temporaires sont
  supprimés. Testé dans un environnement séparé, sur les deux extraits réels, avec les valeurs
  exactes de ses préréglages :

  | Mesure (même instant, ciel du film González) | Grain conservé |
  |---|---|
  | VHS Restore AI Fidèle / Équilibré / Équilibré HQ | 99 % / 107 % / 75 % |
  | Analog Repair, préréglage « 8 mm / Super 8 » | 51 % |
  | Analog Repair, **poussières et rayures seules** (60/100) | **97 %** |

  - Poussières et rayures : c'est **nettement mieux que nous** (nous ne faisons rien) : point noir
    supprimé, rayure verticale fortement atténuée. Avec ce seul réglage, la texture du film reste
    intacte. 49 s pour 6 s de film 2K sur 4 cœurs.
  - Le préréglage complet Super 8 lisse la moitié du grain et la stabilisation déplace le cadrage.
  - **Défaut de proportions sur la VHS** : la sortie 352×240 perd le rapport de pixel (10:11) et
    s'affiche en 1,47:1 au lieu de 4:3. Elle a aussi une cadence irrégulière (179 images au lieu
    de 180).
  - Piste d'intégration (non faite, décision à prendre) : appeler uniquement son étape
    « poussières et rayures » comme moteur externe facultatif pour les pellicules, avec un
    intermédiaire ProRes pour éviter une double compression, et une version du projet figée.
    Coût : NumPy + OpenCV dans le paquet (environ 60 à 80 Mo, non mesuré). Risque : projet très
    jeune, interface interne non documentée (paramètres en allemand). Fausses détections sur des
    objets réels en mouvement : non évaluées (l'extrait est presque fixe).

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
- NARA, formats film et vidéo : https://www.archives.gov/preservation/formats/motion-picture-film-identify-formats.html
  et https://www.archives.gov/preservation/formats/video-identify-formats.html (VHS et Betamax :
  « late 1970s to 1990s » ; Super 8 : « common home movie format » ; aucune cadence indiquée)
- FFmpeg : fieldmatch, deflicker, signalstats, setpts, atempo (https://ffmpeg.org/ffmpeg-filters.html)
- VapourSynth R74 (pip) : https://www.vapoursynth.com/2026/03/26/new-packaging-and-install-methods-in-r74/
- QTempGaussMC : https://forum.doom9.org/showthread.php?p=2050828 ; havsfunc :
  https://github.com/HomeOfVapourSynthEvolution/havsfunc/releases
