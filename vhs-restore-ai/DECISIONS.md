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
  - **Intégré (phase 9)** comme option facultative « Enlever les poussières et rayures »,
    réservée aux pellicules et désactivée par défaut (`vhs_restore/dust.py`). Seule son étape
    « poussières et rayures » est utilisée (60/100, toutes les autres à 0), dans la version figée
    `561ba5a` (`requirements-poussieres.txt`, archive zip : pip n'a pas besoin de Git). Il est
    lancé dans un sous-processus annulable de notre propre exécutable (`--poussieres`), ce qui
    fonctionne aussi dans le paquet Windows. Son PATH commence par notre FFmpeg. L'intermédiaire
    est en ProRes 422 10 bits, et le reste de la chaîne en part : une seule compression finale.
    Le rapport de pixel, la cadence et le son d'origine sont rétablis par notre chaîne (son défaut
    de proportions ne nous touche pas : test dédié).
  - **Test en mouvement** (`tests/test_poussieres.py`, film de synthèse avec grain) : écart avec
    le film propre sur les poussières d'une seule image 140 → 5 ; balle claire rapide (30 px par
    image), balle sombre rapide (35 px par image) et grand objet lent intacts (écart ≈ 4, le niveau
    du grain). Ce sont les cas qui ressemblent le plus à une poussière. Ce n'est pas un vrai film
    avec des visages : à confirmer sur les films réels.
  - Coût : NumPy + OpenCV embarqués (taille du paquet Windows à mesurer). Licence MIT : son texte
    est copié dans `licences/` du paquet.

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

## Son (phase 9, obligatoire)

Le son d'origine est une archive, pas un bruit à jeter. Aucune piste n'est inventée :
un film muet le reste, une piste silencieuse est conservée, le mono d'origine n'est pas
converti en stéréo.

| Profil | Souffle `afftdn` | Clics `adeclick` | Volume `dynaudnorm` (gain max 8 dB) | Voix IA |
|---|---|---|---|---|
| Fidèle | 4 dB | non | non | non |
| Équilibré | 10 dB | oui | oui | non |
| Maximum | 14 dB (seulement si DeepFilterNet est absent) | oui | oui | DeepFilterNet si le binaire est là |

- **Moteurs** : uniquement FFmpeg, déjà dans le paquet, et en option le binaire libre
  [`deep-filter` 0.5.6](https://github.com/Rikorose/DeepFilterNet) (`-D` compense la latence du modèle,
  `-a 12` limite l'atténuation à 12 dB pour ne pas effacer la pièce, WAV 48 kHz, canaux d'origine).
  `installer.bat -AvecSon` le place dans `tools/deepfilter/deep-filter.exe`. Variable `VHSRA_DEEPFILTER`
  acceptée. S'il échoue, repli sur `afftdn` : l'export ne s'arrête pas.
- **Pas de séparation voix / ambiance.** DeepFilterNet atténue le bruit qui masque la parole ;
  il ne remplace pas les voix et n'ajoute aucun son. Audacity n'est pas piloté : les mêmes
  nettoyages (souffle, clics, volume, encoche) sont déjà des filtres FFmpeg, sans deuxième logiciel.
  RNNoise (modèle `std` de Xiph, licence BSD, fichier `vhs_restore/models/rnnoise_std.rnnn`)
  est inclus mais **désactivé par défaut** : les profils restent ceux du tableau.
  Case « Souffle de la voix » : il remplace `afftdn` en Équilibré (35 % du signal nettoyé)
  et en Maximum (55 %) quand DeepFilterNet n'a pas tourné. Le filtre est `arnndn`.
  S'il manque, on revient à `afftdn`. Fidèle reste sur `afftdn` à 4 dB, même si la case
  est cochée. Les séparateurs (Demucs) ne sont pas branchés.
- **Synchronisation** : décalage constant manuel, −500 à +500 ms (`adelay` ou `atrim`).
  Dérive manuelle en ms par minute (`atempo`, hauteur conservée, bornée à ±4 %). L'analyse
  signale un écart de durée ou d'horodatage déjà présent dans le fichier, sans le corriger
  toute seule et sans prétendre lire les lèvres.
- **Ronflement** : encoche `bandreject` 50 ou 60 Hz plus l'harmonique, seulement si l'utilisateur
  l'active. Q = 30, donc très étroite.
- **Copie** : WAV (PCM) ou FLAC facultatifs, extraits du film restauré. L'original n'est pas écrasé.
- **Comparaison** : l'extrait restauré porte le son traité ; `apercu_original.mp4` garde le son
  d'origine, sans le décalage ni la dérive, pour l'écoute comparative (boutons « Écouter »).
- **Bande du bas** : option VHS, 0 à 32 lignes passées au noir, taille d'image inchangée. Défaut : rien.
- **Veille** : pendant un traitement, Windows est prié de ne pas s'endormir (`SetThreadExecutionState`).
- **Réglages** : profil, son et dossier de sortie sont mémorisés (`QSettings`).
- **Analog Repair et VapourBox** recopient le son. Ils ne couvrent pas ce besoin.

## Bande et décrochages (Analog Repair, phase 10)

Le même moteur MIT déjà utilisé pour les poussières (`561ba5a`) expose d'autres étapes.
On n'en active que trois, chacune en case à cocher, jamais par défaut, jamais toutes
les corrections de son préréglage « VHS » (celui-ci lisse le grain : 51 % conservés) :

| Case | Réglage Analog Repair | Force | Ce qui ne change pas |
|---|---|---|---|
| Bruit de bande | `bandstoerung` | 60 | le reste de l'image, si les lignes voisines sont saines |
| Couleur des décrochages | `farbberuhigung` | 40 | la luminance ; un noir et blanc passe tel quel |
| Taches d'une image | `staubentfernung` | 30 | un objet qui bouge (même essai que les poussières) |

Refusé, exprès : effacement du tampon date (il invente le fond et enlève un souvenir),
agrandissement, « look » (étalonnage), fusion temporelle (`rauschminderung`),
stabilisation (déjà `vid.stab`). DeScratch (GPL-2.0) n'est pas copié : sur l'extrait
González il ratait une rayure sur deux, et l'étape poussières d'Analog Repair fait
déjà ce travail.

Une cassette vidéo entrelacée est d'abord passée en images progressives par `bwdif`
(une image par trame, `setfield=prog`). Une pellicule copiée sur bande passe par
`fieldmatch` puis `bwdif` sur les images encore mélangées, à la cadence d'origine.
Analog Repair ne désentrelace donc pas une seconde fois. QTGMC n'est pas relancé après.
Les pellicules numérisées directement ne voient pas ces cases.

## DVD en plusieurs VOB (phase 11)

Un film gravé sur DVD est souvent coupé en `VTS_01_1.VOB`, `VTS_01_2.VOB`… (1 Go).
Choisir un morceau, le dossier `VIDEO_TS`, ou le disque qui le contient, restaure
**un film par titre**. Les menus (`VTS_xx_0.VOB`, `VIDEO_TS.VOB`) sont ignorés.
FFmpeg les enchaîne avec son démultiplexeur `concat` (liste dans un dossier temporaire,
rien n'est écrit sur le DVD). Pas de nouvelle dépendance. QTGMC et les poussières
ne lisent pas cette liste : le message le dit, bwdif reste disponible.
Aucune copie du code d'un autre logiciel : c'est un usage de FFmpeg, déjà dans le paquet.

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

## Conseils de l'analyse et réparations du son (phase 11)

- `audio_check.py` mesure (FFmpeg seul, 2 premières minutes) : un canal muet (RMS < −70 dB
  d'un côté, > −50 dB de l'autre), l'opposition de phase (somme des canaux plus de 10 dB sous
  leur différence), la saturation (part d'échantillons au plafond, pic > −0,1 dB, seuil 0,05 %)
  et le ronflement (bande de 4 Hz à 50/60 Hz plus de 12 dB au-dessus de 75/90 Hz).
- `advice.py` en tire une phrase simple et la correction : `pan` (canal recopié, ou un côté
  inversé pour la phase), `adeclip`, encoche 50/60 Hz existante. **Rien n'est appliqué sans
  accord** : case « Appliquer ces conseils » du mode simple, décochée, visible seulement s'il y
  a un conseil, ou réglages équivalents dans les options avancées. Ces corrections réparent un
  défaut : elles s'appliquent même si « Restaurer le son » est décoché. Le ronflement suit
  désormais la même règle.
- Vérifié : 5 cas de synthèse détectés, aucun conseil sur un son propre ni sur les deux archives
  réelles. Chaque correction est mesurée dans le fichier exporté : son des deux côtés, plus
  d'opposition de phase, saturation divisée par plus de 2, ronflement plus détecté.
  `aeval` a été écarté pour la phase (format refusé par l'encodeur AAC) au profit de `pan`.
- Coût : les mesures du son (canal, phase, saturation, ronflement, vent) sont une seule
  commande FFmpeg (`asplit` + `astats`), plus une deuxième seulement si les canaux sont en
  opposition de phase. Avant : jusqu'à 8 lectures des deux premières minutes. Mesuré sur un
  VOB de 10 minutes (598 Mo, son entrelacé) : 2,26 s à froid et 2,16 s à chaud avant, 1,40 s
  et 1,34 s après. Même conclusion (ronflement 50 Hz, pas de vent). Sur un MKV indexé au son
  PCM léger, le temps reste autour de 1,5 s : ce sont les filtres qui comptent, pas la lecture.
  Les niveaux des bandes restent à 0,2 dB près.
- **Vent et grondements** : une lecture de plus, passe-bas 80 Hz. Conseil seulement si ces graves
  sont forts (RMS > −36 dB), irréguliers (crête au moins 8 dB au-dessus du RMS : un ronflement
  sinusoïdal reste un ronflement) et comparables au reste du signal. Correction, jamais par défaut :
  `highpass=f=80:poles=1` (6 dB/octave). Case avancée « Réduire le vent et les grondements »,
  ou le conseil `wind`. Mesuré sur synthèse : graves −29,5 → −35,5 dB (−6,0 dB) ; voix 300 Hz–3 kHz
  −42,2 → −42,3 dB. Un son rose léger et un ronflement ne déclenchent pas le conseil.
- **Voix étouffée** : case « Rendre les voix plus claires », jamais par défaut.
  `equalizer=f=3000:t=q:w=1:g=3` (+3 dB, pas plus). Mesuré : bande 2–4 kHz en hausse d'environ
  3 dB, crête toujours loin de 0 dB (pas d'écrêtage créé).
- **Niveaux** : YLOW et YHIGH (déjà dans la passe `signalstats` de l'analyse), médiane sur
  l'échantillon. Conseil `levels` seulement si l'écart est sous 140 et que les noirs dépassent 35
  et les blancs restent sous 190. Correction fixe `colorlevels` pour tout le film, jamais image
  par image, jamais sans accord. Un `testsrc2` déjà ouvert ne déclenche pas le conseil.
- **Décalage de couleur** : réglage avancé −8 à +8 pixels, 0 par défaut (`chromashift` horizontal,
  le glissement typique d'une VHS). Mesuré : un carré rouge décalé de 4 px (PSNR du plan U ≈ 31 dB
  contre l'original) revient à l'identique (PSNR infini) après correction de −4 px. Taille inchangée.
- **Dominante de couleur** : `grayworld` écarté (il fait exploser `signalstats`, y compris sur un
  noir et blanc). Correction choisie : moyennes R, G, B sur 8 images réduites à 32×32, une seule
  fois, puis `colorchannelmixer` avec trois gains fixes (moyenne / canal, bornés 0,5–1,5). Conseil
  `cast` seulement si l'écart entre les moyennes dépasse 15. Case avancée « Corriger la dominante
  de couleur », décochée. Le filtre est placé avant l'étirement des niveaux : le même étirement
  sur les trois canaux ne recrée pas la teinte. Mesuré : vert ajouté, écart des moyennes 36,3 → 1,4,
  UAVG 118,7 → 127,9 et VAVG 113,7 → 127,6 (neutre = 128). Noir et blanc : gains 1, saturation 0.
  Couleur pâle (saturation 0,25) : pas de conseil, saturation 27,2 → 26,9 (pas ravivée). Un
  `testsrc2` déjà neutre (écart 4,8) n'a pas de conseil.
- **Bords abîmés** : réglage avancé en pixels, 0 par défaut. Vidéo : gauche et droite noirs.
  Pellicule : cadre des quatre côtés. `crop` puis `pad` noir, donc la taille et le 4:3 ne changent
  pas (comme la bande du bas). Mesuré sur un gris uniforme (YAVG 126) : après 16 px, les bords
  masqués sont à YAVG 16 et le centre reste à 126. Cassette 720×576, pixels 16:15, format 4:3.
  Pellicule 720×540 : les quatre côtés du cadre à 16, centre à 126, format 4:3.

## Interface (phase 14)

Thème sombre fixe (« salle de montage »), indépendant du mode clair ou sombre de Windows.
Inter (texte, OFL) et Rajdhani (bandeau et titres, OFL) sont dans `vhs_restore/assets/fonts/`
et dans l'exécutable (`VHSRestoreAI.spec`). Si un fichier manque, la police du système est
utilisée. Accent cyan en filet seulement ; le bouton Restaurer est ambre, le plus visible.
Le balayage de la barre de progression est un minuteur à 120 ms, actif seulement pendant le
traitement. Contrastes listés dans `theme.CONTRASTES`, tous ≥ 4,5:1 (`tests/test_theme.py`).
Aucun réglage de restauration n'a changé.

Correctifs après relecture sur un écran de portable : la page des options demandait 1 609 px de
large (défilement horizontal, colonne de droite coupée à 1366 px). Les listes aux libellés longs
sont désormais compactes (texte complet à l'ouverture), la ligne d'aperçu est sur deux lignes, et
sous 1 240 px (portable à 125 % ou 150 %) les deux colonnes passent l'une sous l'autre. Test :
aucun défilement horizontal à 1366×740, 1280×720 et 1093×600. Sur une photo en hauteur, l'étiquette
« Restauré » passe en bas pour ne plus chevaucher « Original ».




## Plafonds de fidélité des conseils d'image (phase 12)

Après fusion des PR #3 à #9, les conseils d'image (niveaux, dominante) ont été essayés sur les
deux archives réelles. Sur la pellicule González, le résultat est bon. Sur la VHS de 1988 (très
verte, niveaux 84-163), la correction sans limite (rouge x1,56, contraste x2,8) faisait **virer
l'image au magenta** avec des noirs bouchés : pire que l'original. Les corrections sont désormais
plafonnées (`pipeline.MAX_CONTRAST` = 1,6 ; gains de dominante entre 0,85 et 1,18), dans le
conseil comme dans la chaîne. Le défaut est atténué, il n'est plus forcément annulé. Vérifié à
l'œil sur les deux archives, et par `tests/test_plafonds.py` (dominante jamais inversée).

## Mode Photo (phase 13)

- `vhs_restore/photo.py` : photo ou carte postale numérisée -> PNG sans perte. Filtres FFmpeg
  seuls : `spp` (blocs de compression JPEG), `nlmeans` léger (grain), `cas` (netteté), x2 en
  Maximum. Niveaux et dominante : mêmes mesures, mêmes conseils et mêmes plafonds que les films.
  Une photo noir et blanc sort en niveaux de gris : aucune couleur n'est ajoutée.
- Réglages choisis sur une vraie carte postale ancienne (730×1156, noir et blanc, blocs JPEG) : un
  débruitage `nlmeans` s=2,5 donnait aux pierres d'un mur un aspect d'aquarelle ; les profils
  restent donc à s=1,2 (Équilibré) et 1,6 (Maximum).
- Vérifié (`tests/test_photo.py`) : la photo Fidèle est plus proche de l'image non compressée que
  le JPEG de départ (PSNR), le noir et blanc reste gris, l'original n'est pas modifié, aucun
  écrasement, aperçu avant/après à la même taille, dossier mixte films et photos avec relance.
- Real-ESRGAN (facultatif) peut agrandir une photo ; décochée par défaut, car l'IA invente des
  traits sur des visages de quelques pixels. Pas de colorisation ni de retouche des visages.

## Colorisation facultative des photos noir et blanc (phase 15)

Demandée par l'utilisateur, alors que la règle de départ était « pas de colorisation ». Elle reste
donc encadrée : photo noir et blanc seulement, case décochée à chaque photo, copie **en plus**
(`…_colorisee_ia.png`), la photo restaurée en noir et blanc toujours écrite, aucun fichier existant
écrasé, étiquette « COULEURS IA (inventées) » sur l'avant / après. Pas pour les films (couleurs
qui clignotent d'une image à l'autre, calcul très long).

- Modèle : DDColor-tiny (ICCV 2023, Apache-2.0), export ONNX 512×512 de edgetools/ddcolor,
  révision `4755ae9f…` et SHA-256 `2653da00…` figés (vérifiés au téléchargement et au premier
  usage). Licence dans `vhs_restore/models/DDCOLOR-LICENSE.txt`, copiée dans le zip.
- L'IA ne fournit que la couleur (canaux a et b de Lab, à 512×512, agrandis en bilinéaire) ; la
  luminance vient de la photo restaurée, pixel pour pixel. Mesuré : écart de L < 1,5 au 99e
  centile (`tests/test_colorize.py`) ; le test échoue si l'on altère la luminance de 5 %.
- Le fichier publié stocke ses poids en fp16 : onnxruntime sur processeur mettait plus de
  3 minutes par photo (arrêté). Converti en fp32 en mémoire au chargement (paquet `onnx`) :
  environ 1 seconde par photo sur 4 cœurs. Le fichier sur disque reste celui publié.
- Essais réels : sur une vue de ville en couleur passée en noir et blanc, ciel bleu, tour dorée et
  toits rouges retrouvés, mais plus saturés que l'original (couleurs plausibles, pas exactes). Sur
  la carte postale de l'église (pierre, ciel blanc), le résultat reste presque gris : l'IA n'invente
  pas de couleur là où elle n'en devine pas.
- Livraison : modèle inclus dans le zip Windows (`tools/ddcolor/`, +130 Mo) pour que l'exe marche
  sans installation ; depuis les sources, `installer.bat -AvecCouleurs`. L'autotest de l'exe
  colorise la carte postale de synthèse quand le modèle est là (taille, luminance, noir et blanc
  gardé, original intact), sinon il écrit « non installée (facultatif) ».
- Non testé : photos de famille réelles avec visages (teintes de peau), très grandes numérisations
  (> 6000 px, traitées par bandes de 512 lignes pour limiter la mémoire).

## Interface plus futuriste, icônes pour chaque réglage (phase 16)

Demande de l'utilisateur : une interface « plus futuriste et fun, avec des icônes pour les
différents réglages ». Rien ne change dans les traitements.

- `vhs_restore/icons.py` : 48 icônes au trait néon dessinées dans le code (SVG 24×24), une par
  réglage (poussières, bande, arcs-en-ciel, stabilisation, vent, voix, ronflement…), rendues à la
  densité de l'écran. Si QtSvg manque, l'icône est vide et rien d'autre ne change.
- Page des options réorganisée en cartes « console » (en-tête à icône, titre néon, numéro
  d'étape 01 à 04, coins façon HUD) : Vidéo, Caractéristiques, Profil, Image, Son, Aperçu,
  Restauration complète. Les réglages d'image et de son ne sont plus mélangés.
- Profils en trois tuiles (bouclier, balance, fusée) avec voyant allumé ; la description complète
  du profil choisi s'affiche dessous.
- Cases à cocher remplacées par des interrupteurs (SVG), fond de page avec halo cyan, flèches
  des champs numériques recalées dans le champ (elles débordaient).
- Barre d'état compacte : ● installé / ○ facultatif, détail dans l'infobulle.
- Largeur : la page des options tient en 1 208 px (deux colonnes jusqu'à 1 240 px, une colonne
  en dessous) ; les tests de défilement horizontal (1366, 1280, 1093 px) passent. Contrastes des
  nouveaux couples (tuiles, titres, numéros) ≥ 6,3:1, listés dans `theme.CONTRASTES`.

## Analyse de bugs de l'ensemble du logiciel (phase 17)

Méthode : vérification statique (ruff : noms indéfinis, imports inutiles), robot d'interface qui
fait passer la fenêtre par six états (vide, film chargé, aperçu, traitement en cours, photo noir
et blanc, photo couleur) et relève pour chaque bouton et réglage s'il est actif, visible et
branché, puis clique chaque bouton actif et vérifie qu'il se passe quelque chose ; relecture des
parcours d'annulation et de fermeture. Aucun bouton actif sans effet. Défauts trouvés et corrigés :

1. **Dossier de sortie « collant »** : après le premier fichier ouvert, tous les suivants (et les
   séances suivantes, via les préférences) étaient enregistrés dans le dossier de ce premier
   fichier, contrairement au mode d'emploi. Désormais : à côté de chaque original, sauf dossier
   choisi exprès (« Dossier de sortie… » ou saisie) ; l'ancien réglage automatique mémorisé est
   ignoré (clé `out_dir_manual`).
2. **Réglages modifiables pendant un traitement** : profils, cases, listes, champs, « Choisir… »,
   dossier de sortie restaient actifs alors qu'ils n'avaient plus d'effet (lus au lancement) ; un
   fichier glissé pendant un traitement était ignoré sans message. Ils sont grisés ; un message
   explique pourquoi un fichier glissé n'est pas pris.
3. **Mode Photo** : le son, le désentrelaceur, la bande, la stabilisation, les masques, l'extrait,
   le découpage… restaient affichés sans aucun effet sur une photo. Ils sont cachés (profil,
   dominante, IA et colorisation restent).
4. **« Écouter » actif pour un film sans son** (ou piste silencieuse) : grisé, avec une infobulle.
5. **« Annuler » pendant « Vérifier l'installation »** n'arrêtait rien : la vérification
   s'arrête maintenant en environ 1 s, sans rapport d'échec.
6. **« Vérifier l'installation » semblait ne rien faire** (état figé à 10 %) : étapes affichées.
7. Textes : « Choisir un film ou une photo », zone de dépôt et titre de la carte idem.
   En mode Photo, l'encadré d'avertissements affichait des messages de film (« Film noir et blanc
   probable : aucune colorisation », « Aucune piste son ») : remplacés par des messages de photo.
8. Code : deux imports inutiles retirés.

Tests ajoutés : `tests/test_etats_interface.py` (4 tests), qui échouent tous sur l'ancien code.
Non testé : clics réels sous Windows (le robot tourne hors écran sous Linux).

## Outils facultatifs installables depuis l'application (phase 18)

Demande : cliquer sur « QTGMC », « Real-ESRGAN » ou « DeepFilterNet » ne faisait rien (simples
voyants), et l'installation par PowerShell dans le dossier de l'exe était perdue à chaque nouvelle
version. Désormais :

- Les voyants de la barre du bas sont des boutons : une fiche explique l'outil, son état
  (installé, inutilisable avec la raison, pas installé) et propose « Installer (taille) » ou
  « Réinstaller ». QTGMC (Python + VapourSynth) et FFmpeg (livré) ne s'installent pas ainsi.
- `vhs_restore/installer.py` : publications officielles à version figée (Real-ESRGAN v0.2.5.0,
  DeepFilterNet v0.5.6, DDColor révision 4755ae9f), empreinte SHA-256 vérifiée, 3 essais,
  progression en Mo, annulation, archive refusée si un chemin sort du dossier, rien d'installé à
  moitié (dossier temporaire puis mise en place d'un coup). Réel vérifié ici : les trois outils
  téléchargés, vérifiés et rangés, aucun reste temporaire.
- Rangement : `%LOCALAPPDATA%\VHSRestoreAI\tools` (`tools.user_tools_dir()`), cherché après le
  dossier `tools` de l'application : un outil installé sert encore après une mise à jour.
- Tests : `tests/test_installer.py` (serveur HTTP local : mise en place, mauvaise empreinte,
  annulation, archive piégée, outil du profil détecté, fiche avec « Installer »).
- Non testé : l'installation réelle de Real-ESRGAN et DeepFilterNet SOUS Windows (vérifiée ici
  en simulant Windows) et le fonctionnement de Real-ESRGAN sans carte graphique Vulkan.

## Boutons désactivés bien visibles (phase 19)

Sur la capture Windows de l'utilisateur, « Arrêter » et « Écouter… » (désactivés, rien de chargé)
ressemblaient à des boutons actifs : texte #d5dde6 contre #f3f6fa. Un clic sans effet passait pour
une panne. Texte désactivé #8e9bab (6,5:1 sur son fond, toujours lisible), bordure plus discrète ;
« Restaurer » indisponible : ambre éteint #3d3324 / #c9b893 (6,3:1) au lieu d'un ambre presque allumé.

## Pensé pour une personne âgée (phase 20)

Revue « l'utilisateur a 76 ans » des captures, puis corrections :

- **Mots simples** : le cadre d'information dit « Film de caméscope ou de magnétoscope,
  31 secondes. Prêt : cliquez sur le bouton 2 » et « Défauts repérés : image un peu terne,
  couleurs un peu tirées » ; le détail technique (niveaux, Hz, %) passe en infobulle. Case
  « Corriger aussi ces défauts, avec prudence », toujours décochée d'avance (règle de fidélité).
- **Étape suivante désignée** : le bouton à utiliser (1, puis 2, puis 3) a un cadre épais.
- **Comparer sans geste précis** : sous l'aperçu, « Original », « Comparer les deux »,
  « Restauré » (l'écran montre une seule image en entier, ou les deux avec la souris).
- **Écran simple épuré** : plus de noms d'outils (barre du bas visible seulement dans les
  options avancées), « Arrêter » seulement pendant un traitement, « Écouter » seulement quand il
  y a un aperçu avec du son, « Options avancées » discret, note rassurante (« votre fichier
  d'origine n'est jamais modifié… »).
- **Lisibilité** : grands boutons en Inter 16 pt gras (au lieu de la police étroite Rajdhani,
  gardée pour le bandeau et les titres de cartes), cadre d'information 15 pt, état 14,5 pt.
- **Affichage clair** (bouton dans le bandeau) : deuxième palette, fond blanc, toutes les couleurs
  nommées (`theme.SOMBRE` / `theme.CLAIR`), contrastes ≥ 4,5:1 testés pour les deux. Le choix est
  mémorisé ; le logiciel redémarre pour l'appliquer.
- **Aide** : fenêtre « Bienvenue » en trois étapes au premier lancement, rouvrable par « Aide ».
- La case « Coloriser » reste cliquable même si la colorisation manque : elle ouvre la fiche
  « Installer » (les voyants du bas n'étant plus visibles en mode simple).

Tests : `tests/test_senior.py` ; contrastes des deux palettes dans `tests/test_theme.py`.
Non testé : un vrai essai avec l'utilisateur final (le seul juge) et le redémarrage pour
changer d'affichage sous Windows.

## Ergonomie pour l'utilisateur de 76 ans (phase 21)

Aucun traitement n'a changé (mêmes filtres, mêmes profils, case de conseils toujours décochée).

- **Fin de travail** : écran « C'est prêt » dans le mode simple (plus une petite boîte), avec
  « Regarder le film » ou « Voir la photo », « Ouvrir le dossier », « Restaurer un autre… ».
  Son bref et clignotement de la barre des tâches.
- **Pendant le travail** : temps restant en mots (« environ 25 minutes »), phrase
  « Vous pouvez utiliser l'ordinateur ou le laisser travailler ». « Arrêter » demande
  confirmation si le travail dure déjà (le robot d'audit, lui, annule sans boîte).
- **Dossier** : « Film 3 sur 12 : nom… » et un résumé (réussis, déjà faits, échecs en mots simples).
- **Erreurs** : ce qui s'est passé et quoi faire ; le détail technique est derrière
  « Détails pour l'aide », avec « Copier ».
- **Choisir un fichier** : la fenêtre s'ouvre dans Vidéos ou Images, puis dans le dernier
  dossier ; glisser-déposer sur toute la page simple ; cinq derniers fichiers.
- **Texte** : A− / A / A+ (100 / 125 / 150 %), mémorisé. À 125 % et 150 % les étapes passent
  l'une sous l'autre, pour qu'il n'y ait pas de défilement horizontal.
- **Clavier** : Entrée active l'étape encadrée, ordre de tabulation, noms pour le lecteur d'écran,
  focus visible. Un bouton « ? » à côté des cases dont le détail était seulement en infobulle.

## Premier vrai film de l'utilisateur : corrections d'office, bords repérés (phase 21)

L'utilisateur a restauré un vrai film de famille (VHS) : « le résultat n'est pas dingue ». Sur ses
enregistrements d'écran (avant / après), l'analyse trouve des niveaux de 39 à 172 (image terne), une
dominante jaune-verte et des traits colorés sur les bords. Avec le réglage par défaut d'alors (case des
corrections décochée), le profil Équilibré ne changeait presque rien : c'est ce qu'il a constaté.
Simulation sur son film dans le vrai logiciel : avec la case cochée et les bords masqués, noirs
profonds, voile jaune retiré, plus de relief. Décision de l'utilisateur :

- **La case « Corriger aussi ces défauts » est cochée d'office** quand des défauts sont repérés (et
  appliquée aussi aux films d'un dossier, sauf si la case a été décochée). Les plafonds de fidélité
  (phase 12) restent : contraste ≤ 1,6, gains 0,85–1,18, rien pour une image déjà correcte.
- **Bords abîmés repérés tout seuls** (`probe.edge_damage`) : 6 images réparties, 48 colonnes de chaque
  côté comparées à l'intérieur ; une colonne compte si sa couleur est anormale (traits colorés, liseré)
  ou si elle est claire et très différente (neige). Une bande noire régulière ne compte pas. Résultat
  arrondi au pair, de 4 à 24 px, sinon rien. Conseil « bords abîmés » → `mask_sides`. Mesuré : image
  propre 0, bande noire 0, traits colorés de 10 px → 12, VHS 1988 → 0, film de l'utilisateur → 8.
- « Masquer les bords » compte désormais en **pixels du film d'origine** (multiplié en sortie Full HD).
- Après la PR #11 (Grok, fusionnée) : erreurs « pas de piste vidéo », « caractéristiques illisibles »,
  « FFprobe ne répond pas » → « fichier abîmé » ; FFmpeg absent → « réinstallez le logiciel » ; écran
  « C'est prêt » : boutons avant le texte (visibles sur un portable à 125 %) et cadre du haut « Terminé » ;
  bandeau sur deux lignes ; captures retirées du dépôt.

Tests : `tests/test_bords_auto.py`. Non testé : d'autres vrais films (un seul film réel examiné, et
seulement à travers un enregistrement d'écran recompressé).

## Montage : passages vides, LosslessCut et Shotcut (phase 22)

Demande : « un menu pour faire du montage vidéo » ; décision de l'utilisateur après discussion :
intégrer des logiciels libres existants plutôt que tout créer, et garder dans le logiciel ce qui est
propre aux cassettes.

- **Passages vides** (`vhs_restore/vides.py`) : 4 images/s réduites à 48×36, écart YHIGH − YLOW ;
  ≤ 20 pendant au moins 2 s = passage vide (neige, écran bleu ou coloré, noir). Mesuré : neige 5 à 11
  (capture 320 ou 720 de large), bleu et noir 0, vrais films 74 (VHS 1988) à 123 (film de
  l'utilisateur) ; aucune fausse alerte sur ces films ni sur une image noir et blanc en mouvement.
  La liste (heures, genre, durée) est montrée avant toute action ; une **copie** sans ces passages est
  créée (`…_sans_vides.mp4`, x264 CRF 16, son gardé), jamais l'original. Rien n'est proposé si tout le
  film semble vide (erreur probable).
- **LosslessCut 3.70.2** (GPL-2.0, couper / assembler sans perte) et **Shotcut 26.8.1** (GPL-3.0,
  montage complet) : installés d'un clic comme les autres outils (`installer.py`, version figée,
  SHA-256 relevé sur les fichiers publiés), rangés dans le profil, lancés comme programmes séparés
  avec le film (`QProcess.startDetached`). LosslessCut n'existe pour Windows qu'en 7z : l'extracteur
  officiel `7zr.exe` (7-Zip, LGPL, 0,6 Mo) est installé d'abord. Contenu vérifié ici : `LosslessCut.exe`
  à la racine de l'archive, `Shotcut/shotcut.exe` dans le zip.
- Écran « C'est prêt » (film) : « Retirer les passages vides » et « Faire un montage » ; mêmes
  boutons dans les options avancées (dernier film restauré, sinon le film ouvert). Choisir un montage
  non installé ouvre la fiche « Installer », puis le logiciel s'ouvre tout seul une fois installé.
- Au passage : le redémarrage pour changer d'affichage lisait mal la réponse de Qt (`startDetached`
  renvoie un couple) ; fonction commune `_demarrer`.

Tests : `tests/test_vides_montage.py`. Non testé : l'installation réelle de LosslessCut, de Shotcut et
de 7zr.exe SOUS Windows (empreintes et contenus vérifiés ici) et l'ouverture du film dans ces
logiciels ; la détection sur de vraies cassettes avec neige (seulement de la neige de synthèse).

## Options avancées remises d'aplomb (phase 23)

Captures de l'utilisateur (écran 1920 × 1080 à 150 %), reproduites ici à la même échelle :

- L'aperçu s'étirait sur toute la hauteur de la colonne de gauche : un rectangle noir de 1 300 px.
  Sa hauteur suit maintenant sa largeur (image 4:3, entre 240 et 900 px) et la carte **Son** passe à
  droite, sous les boutons « Écouter » : les deux colonnes ont la même hauteur (page de 2 025 à 1 627 px).
- La liste des images de l'aperçu (vide avant le premier aperçu) est cachée tant qu'elle est vide.
- Libellés coupés : « Je ne sais pas — suggestion : v… » devient « Automatique : vidéo » (la suggestion
  détaillée est sur la ligne du dessus) ; les listes du son sont une par ligne, textes entiers.
- Le bouton « Générer l'aperçu » s'appelle comme en mode simple, « Voir l'avant / après » ; les messages
  ne parlent plus du « bouton 2 » ou du « bouton 3 » dans les options avancées (message propre à chaque page).
- Défauts repérés : la case « Corriger aussi ces défauts » est aussi dans les options avancées (la même,
  synchronisée) ; les lignes disent « Corrigé d'office » ou « Repéré, pas corrigé (case décochée) » au
  lieu de renvoyer au mode simple « ou réglages du son ci-dessous » ; « Masquer les bords » affiche
  « auto (12 px) » au lieu de « 0 px » quand les bords abîmés seront masqués.

Tests : `tests/test_page_avancee.py`.

## Panne « Souffle de la voix » sous Windows (phase 23, suite)

Constat de l'utilisateur (n°61) : avec « Souffle de la voix (RNNoise) » coché, la restauration
s'arrêtait : `No option name near '/Users/…/rnnoise_std.rnnn:mix=0.35'`. Le chemin du modèle
(`C:\…`) n'était échappé qu'une fois ; FFmpeg lit un graphe de filtres en deux temps (le graphe,
puis les options du filtre) et chaque lecture retire un niveau de « \ ». `_ff_filter_path` échappe
maintenant les deux niveaux (`C\\:/…`), apostrophes, virgules, crochets et points-virgules compris.
Essai réel avec FFmpeg (-af et -filter_complex) dans un dossier « C:Mes films, l'été [1988]; essai ».
Pourquoi les essais ne l'avaient pas vu : sous Linux un chemin n'a pas de « C: », et l'essai
automatique de l'exe Windows ne cochait pas RNNoise ; il le coche désormais (avec le filtre 50 Hz).

## Vérification complète par trois relecteurs automatiques (phase 24)

À la demande de l'utilisateur, trois assistants ont vérifié tout le logiciel en parallèle, sans rien
modifier : relecture du code récent, pièges de Windows, parcours de l'interface écran par écran
(environ 330 captures, 1280 × 720 à 150 %, 1366 × 768, 1920 × 1040, thèmes sombre et clair, texte
100 et 150 %). Chaque problème retenu a été reproduit ; les corrections ont chacune un test.

Passages vides et montage :
- Durée annoncée absente (« N/A ») ou fausse (VOB aux horodatages qui repartent à zéro) : la durée
  est mesurée en lisant le film ; le dernier morceau gardé va « jusqu'au bout » ; une copie plus
  courte que prévu est refusée (rien n'est retiré) au lieu de perdre des minutes en silence.
- DVD en plusieurs morceaux : refusé tant qu'il n'est pas restauré (seul le premier morceau était pris).
- L'écran « C'est prêt » ne disparaît plus quand la recherche ne trouve rien, est refusée, annulée,
  ou quand une installation échoue ; un autre film ouvert n'hérite plus du film restauré précédent ;
  le nom du film est dans la question ; copie dans le dossier de secours si le dossier est protégé.
- Montage en attente oublié si la fiche d'installation est fermée sans installer.
Autres : téléchargement coupé en route réessayé (au lieu de « fichier pas bon ») ; bande noire au
bord flou (capture analogique) plus prise pour un bord abîmé ; « Arrêter » pendant que le travail
finit ; temps « encore environ … » ; dossier déposé sur la fenêtre = restaurer le dossier (après
question) ; réglages d'un dossier lus dans le fil de l'interface, plus dans le fil de travail.

Windows :
- Plus de fenêtre noire qui clignote (trois appels de FFmpeg sans CREATE_NO_WINDOW).
- Photo au nom avec « %20d » (nom venu d'Internet) : lue comme une suite numérotée ; corrigé
  (`-pattern_type none`, `-update 1`).
- Fichier ouvert dans un lecteur vidéo : nouvel essai, puis message clair, et le résultat terminé
  est gardé (« renommez … ») ; aperçu dans un dossier neuf à chaque fois ; « permission denied » dit
  « utilisé par un autre programme ou dossier protégé » (plus « la clé USB n'est plus là »).
- Clé USB ou carte en FAT32 : prévenu AVANT si le film dépasserait 4 Go.
- Deux DVD protégés (VTS_01 tous les deux) : le second n'est plus dit « déjà fait ».
- Un fichier bloqué n'arrête plus tout le dossier ; chemin de plus de 250 caractères dit avant ;
  « % » dans le dossier temporaire (mode IA) ; « & » dans un nom de fichier récent ; journal à part
  pour le sous-processus « poussières » ; vrai dossier « Vidéos » (déplacé par OneDrive).

Interface :
- Pendant une restauration, la barre, l'état et « Arrêter » étaient sous le bas de l'écran (150 %) :
  ils sont juste sous les boutons 1-2-3 et la page y défile toute seule ; après l'aperçu, l'image
  (à la taille de la fenêtre, plus 260 px de large) et ses boutons sont amenés à l'écran.
- « Derniers fichiers » sous les étapes (ils les poussaient hors de l'écran).
- Entrée sur « C'est prêt » relançait la même restauration : elle ouvre maintenant le film.
- Questions en français (« Oui, arrêter » / « Non, continuer ») au lieu de « Yes / No » ; Qt traduit.
- Libellés coupés (« Pellicule cinéma numéris… », « 25 images/ ») raccourcis ; case « Coloriser
  aussi (IA) » courte, l'explication en dessous (plus de défilement horizontal).
- Boutons qui suivent la taille du texte ; A− / A / A+ montrent la taille choisie ; boutons
  Original / Comparer / Restauré côte à côte tant qu'ils tiennent.
- Texte du haut toujours juste (aperçu prêt, travail en cours, arrêté, échec) ; les boutons du mode
  simple ne figent plus l'aperçu des options avancées ; « Arrêter » sur les deux pages.
- Options avancées : réglages corrigés d'office marqués (« · corrigé d'office », « Automatique :
  ronflement 50 Hz filtré ») ; boutons de montage grisés pendant un travail et cachés pour une photo ;
  photo : plus de lignes « — » ni « extrait de 10 s ».
- Dossier où tout a échoué : plus d'écran « C'est prêt ».

Tests : `tests/test_pieges_windows.py`, ajouts dans `test_installer.py`, `test_bords_auto.py`,
`test_vides_montage.py`.

## Découpage du début et de la fin, en langage clair (phase 25, branche grok/montage)

Le réglage existait déjà (secondes brutes, options avancées seulement, libellé
« Garder du début à … jusqu'à »). Rien ne change dans `trim_window` ni dans les filtres.

- Les durées s'affichent « 1 min 05 s » ou « 1 h 04 min ». La valeur interne reste des secondes.
  On peut aussi taper `1:05` ou `90`.
- Le même réglage est sur la page simple : « Le film commence à » / « Le film s'arrête à »,
  une phrase qui dit combien de temps la copie gardera, « Tout garder », et
  « Montrer ce début dans l'aperçu ».
- Dans les options avancées, « Commencer à cet extrait » et « Arrêter après cet extrait »
  recopient le moment de l'aperçu (10 secondes). 0 reste « dès le début » / « à la fin ».
- Une photo n'affiche pas ce bloc. L'original n'est jamais coupé.

## Passages enlevés au milieu (phase 26, branche grok/montage)

On peut enlever plusieurs passages au milieu d'un film, pas seulement le début et la fin.
Chaque morceau gardé est restauré seul : les scènes enlevées ne sont pas traitées, ce qui
raccourcit le travail. Les morceaux sont ensuite assemblés sans seconde compression.
Ce n'est pas compatible avec l'amélioration IA, les poussières, la réparation de bande,
ni le re-cadencement de la pellicule.

La barre du film est dessinée dans l'application (aucun code de Clipchamp, OpenShot ou
LosslessCut). Un clic place l'extrait. En doré : ce qui ne sera pas restauré.
Les flèches gauche et droite déplacent d'une seconde.
On fait glisser le curseur pour se placer. « Couper ici » une fois pour le
début du passage, une seconde fois pour la fin. Les bords dorés, avec un
petit carré blanc, se tirent pour ajuster. Rien n'est fusionné tant que
le bouton de la souris reste enfoncé.

Rapprochement de grok/montage avec la n°64 : les morceaux d'une coupe au milieu profitent des
protections de la n°64 (fichier ouvert dans un lecteur : réessai et résultat gardé ; chemin trop long
dit avant ; clé FAT32 vérifiée sur la durée gardée, pas sur le film entier ; liste d'assemblage
effacée sans masquer une erreur).
- Page simple : « Couper ici » deux fois suffit ; « Ce passage inutile commence ici », « Le film reprend ici » et « Autre façon, en deux temps » y sont cachés (pas détruits), toujours visibles dans les options avancées.
- Avant « Restaurer » : la note des passages prévient si une option cochée empêchera la coupe au milieu, avec les mots de l'écran (« Amélioration IA », « Enlever les poussières et rayures », « Bruit de bande », « Couleur des décrochages », « Taches d'une seule image », « Cadence de tournage ») ; rien n'est décoché ; le refus de pipeline.export et ergonomie.expliquer citent aussi la cadence de tournage.
- Un dossier ignore les coupes du film ouvert : la phrase est écrite en haut de la page et répétée dans « C'est prêt » (la ligne d'état est remplacée aussitôt par « Film 1 sur … »), sans fenêtre ; restore_folder ne reçoit aucun passage.

## Équipe, vague 1 (phase 27)

Demande n°7 : six rôles, le chef tranche. Rien n'a été changé dans les filtres.

- La molette sur « Le film commence à » et « Le film s'arrête à » ne change plus le temps
  tant que le champ n'a pas été cliqué : défiler la page ne coupe plus le film par accident.
- Le cadre « Enlever une scène » n'apparaît qu'une fois un film choisi (toujours caché pour une photo).
- Après « Arrêter », la ligne d'état dit : « Arrêté. Votre film n'a pas été modifié.
  Pour recommencer, cliquez sur « Restaurer ». »
- Le mode d'emploi et la fenêtre « Bienvenue » expliquent « Couper ici ». L'erreur de coupe
  nomme les cases telles qu'à l'écran, plus « réparations de bande ».

## Équipe, vague 2 (phase 28)

Toujours aucun filtre modifié.

- Une coupe qui ne laisse qu'un seul morceau (début ou fin enlevé) est vraiment envoyée
  à l'export : avant, l'écran annonçait un film plus court et le film entier partait.
- Le curseur de la barre va de 0 jusqu'à la fin du film, y compris sur un film de moins
  de 10 secondes. L'aperçu, lui, reste calé pour tenir dans le film.
- Entrée sur la barre pose la coupe. Elle ne lance plus « Voir l'avant / après » ni « Restaurer ».
- La zone pour tirer un bord doré fait 44 px (le carré dessiné reste petit). La barre
  ne descend pas sous 56 px.
- Au-delà de huit passages, ou avec « Annuler la dernière coupe » pendant un geste commencé,
  le bouton revient à « Couper ici » sans retirer une coupe déjà posée.
- Les morceaux d'une coupe au milieu réservent leur place sur le disque temporaire.
  La copie sans passages vides refuse une clé FAT32 si elle dépasserait 4 Go.
  Un film dont le chemin dépasse 250 caractères est signalé (il faut le déplacer).
  `lancer.bat` ne fait plus `cd` (un dossier `\\serveur\` échouait).
  Réinstaller LosslessCut ou Shotcut pendant qu'il est ouvert ne l'efface plus.
- Le décalage son / image n'est pas retiré des morceaux : chaque morceau repart à zéro.


Relecture de grok/equipe (f4cba42, 252 tests verts) puis fusion, avec deux corrections :
- Barre du film : un simple clic près d'un bord doré rallongeait la coupe jusqu'au clic (prise de 44 px de chaque côté, bord déplacé dès l'appui) ; désormais la prise fait 44 px en tout (22 de chaque côté), le bord ne bouge qu'après un vrai glisser (4 px), et un simple clic place le curseur.
- Après « Arrêter », « Pour recommencer, cliquez sur Restaurer » seulement après une restauration ; aperçu, recherche de passages vides, installation et dossier ont chacun leur phrase.

Capture de l'utilisateur (n°69, options avancées) : les commandes de découpage de la branche
grok/montage occupaient « Restauration complète » (onze boutons pleine largeur, deux champs de temps
sur toute la largeur) : « Lancer la restauration » était loin en bas et un grand vide restait à
gauche. Une seule carte de découpage déséquilibrait les colonnes de 500 px, de quelque côté qu'elle
soit (mesuré). Deux cartes : « Début et fin » (réglage du film entier) à gauche sous « Image »,
« Enlever un passage » à droite sous l'aperçu, dont il utilise le moment « Début de l'extrait ».
Champs de temps côte à côte, boutons compacts deux ou trois par ligne (libellés courts ; noms complets
pour le lecteur d'écran et en infobulle). Aperçu plafonné à 620 px de haut sur grand écran. Écart entre
le bas des deux colonnes : 107 px (1280 × 720 à 150 %), 40 px (1366 × 768), 65 px (1920 × 1040), au lieu
de 533. Le mode simple garde ses gros boutons. Tests : `test_page_avancee.py`
(`test_decoupage_hors_de_restauration_complete`, `test_colonnes_equilibrees`).

## Timeline (phase 29)

La barre montrait un ruban bleu et doré, sans image : pour savoir où couper, il fallait
relancer un aperçu de 10 secondes. Elle montre maintenant de petites images du film
(environ une tous les 90 pixels), et l'image du moment au-dessus, avec l'heure en clair.

- FFmpeg seulement, `-ss` avant `-i`, une image, fil à part (pas le fil de restauration).
  Dossier temporaire `vhsrestore_vignettes_`, jamais à côté du film, effacé au changement
  de film et à la fermeture. DVD en plusieurs VOB : tout le titre (`dvd.input_args`).
- Désentrelacement `bwdif` seulement si le balayage est tff ou bff. Le 4:3 VHS (pixels 16/15) est gardé.
- Les deux barres (page simple et carte « Enlever un passage ») partagent les coupes,
  le curseur et les images. Un clic près d'un bord doré place toujours le curseur.
- Aucun filtre de restauration n'a été modifié. L'interdiction du banc de montage tient
  (pas de titres, de musique, de plans déplacés). La règle « pas de vignettes » est levée :
  c'est la demande.


## Après la restauration : nommer, copie à partager, séparer en films (phase 30)

Demande de l'utilisateur (points 2, 3 et 4 de « ce qu'il manque ») : un film restauré s'appelait
« DVD_041544_0_restaure_equilibre.mp4 », pesait plusieurs Go (impossible à envoyer) et une cassette
de 3 heures mélangeait Noël, des vacances et un anniversaire dans un seul fichier. Nouveau module
`vhs_restore/partage.py` ; trois boutons sur l'écran « C'est prêt » et dans « Restauration complète ».

- **Nommer ce film / cette photo** : seulement un **résultat du logiciel** (`_fini_fichier`), jamais
  l'original (refus vérifié dans `partage.nommer`). Le film est recopié sans recompression
  (`-c copy`), avec le titre et la date (`1988`, `12/1988`, `25/12/1988` → forme ISO) écrits dans
  le fichier ; l'ancien nom n'est effacé qu'après. Nom libre (jamais d'écrasement : « (2) »),
  caractères interdits par Windows retirés, noms réservés (CON…) protégés. Les copies du son
  (WAV, FLAC) et la copie colorisée d'une photo suivent le nouveau nom. Une photo change seulement
  de nom (pas de métadonnées).
- **Faire une copie à partager** : nouveau fichier à côté du film, le film restauré reste le
  résultat. « Copie légère » : 640 × 480 (4:3, pixels carrés), 25 i/s au plus, H.264 Main 3.0,
  CRF 28 plafonné à 2 Mbit/s, AAC 96k stéréo : mesuré 5,2 Mo par minute sur une image bruitée
  (15 Mo au plus). « Pour la télévision » : 960 × 720 au plus, jamais agrandi (une VHS SD donne
  768 × 576), cadence gardée (50 i/s au plus), H.264 High 3.2, CRF 20 plafonné à 8 Mbit/s, AAC 192k :
  mesuré 63 Mo par minute ; le débit baisse pour qu'un film de plusieurs heures reste sous 3,6 Go
  (clé FAT32). Place libre vérifiée avant. Au-delà de 25 Mo, la phrase dit qu'un e-mail peut refuser.
- **Séparer en plusieurs films** : les frontières sont les passages vides que `vides.py` repère déjà
  (neige, écran bleu ou noir) ; un morceau de moins de 20 secondes n'est pas un film ; moins de deux
  films : rien n'est proposé (« Aucune coupure nette… »). Une fenêtre demande un nom par film (de/à,
  durée), facultatif (« <cassette> - film 2 »). Chaque film : x264 CRF 16 + AAC 192k comme la copie
  sans passages vides, titre dans le fichier ; la cassette entière reste. Clé FAT32 vérifiée sur le
  plus long film, place libre sur l'ensemble. La question « Passages vides » propose aussi
  « Séparer en N films » quand c'est possible.
- Jamais d'écrasement, partiel caché puis publication (`reserver_sorties`, `partiel_unique`,
  `finaliser`) ; DVD ou clé protégée : dossier de secours (`pipeline.output_dir_for`).
- Pendant « Nommer » et la copie, l'écran « C'est prêt » reste ; arrêt ou erreur : il revient.
  Séparation et copie sont des travaux longs (phrase de patience, confirmation avant d'arrêter).
- Page avancée : deux boutons par ligne (« Retirer les passages vides… » / « Séparer en films… »,
  « Nommer le résultat… » / « Copie à partager… », « Faire un montage… » / « Vérifier
  l'installation ») : pas de défilement horizontal à 1280 px, texte 100 à 150 %.
- Tests : `tests/test_partage.py` (moteur : tailles, cadences, niveaux, FAT32, noms Windows, dates,
  séparation d'une cassette de synthèse, nommer avec WAV et nom déjà pris) et
  `tests/test_partage_gui.py` (fenêtre réelle : nommer depuis « C'est prêt », refus sans résultat,
  vérification du nom et de la date, copie légère, séparation par les deux chemins, photo).
- Non testé : lecture des copies sur un vrai téléviseur et sur un téléphone ; envoi réel par
  e-mail ou WhatsApp.

## Son AAC avec FFmpeg 9.1 (Windows)

Les fabrications Windows ne finissaient plus depuis la fenêtre de son des morceaux (lot 2
d'Astra) : FFmpeg 9.1, celui que le logiciel installe, tournait sans fin. Quatre diagnostics sur
le Windows de la fabrication l'ont isolé : l'encodeur AAC, méthode par défaut (« twoloop »), sur un
son bref suivi d'un silence parfait (mono 192 kbit/s) ; silence pur, son continu, stéréo, débit
plus bas ou méthode « fast » finissent. Un raccord de coupe ou une cassette presque muette crée ce
cas chez l'utilisateur. Tous les encodages AAC passent par `tools.AAC` (« -aac_coder fast »).
Le silence ajouté au bout d'un morceau est aussi borné (`apad=whole_dur`). Test :
`tests/test_aac_ffmpeg9.py` (échoue en 60 s au lieu de bloquer).

Chez l'utilisateur (journal du 24 et du 25 novembre), deux restaurations avec « Souffle de la voix »
(RNNoise) ont échoué à la toute fin du film : « [aac] Input contains (near) NaN/+-Inf ». Les seules
restaurations du journal qui ont échoué sont celles avec arnndn. Une garde `aeval` (`GARDE_NAN`)
suit désormais arnndn : toute valeur invalide devient du silence. Reproduit avec une source
contenant des NaN : sans garde, même erreur ; avec garde, fichier complet (`tests/test_aac_ffmpeg9.py`).

## Lumière et couleurs avant de lancer

Chez l'utilisateur, l'image restaurée paraissait sombre et terne, et la restauration est trop
longue pour essayer au hasard. Deux changements :

- Niveaux à moitié : l'étirement des noirs et des blancs mesuré sur le film (`_levels_filter`)
  n'est plus appliqué qu'à moitié. Complet, il bouchait les ombres des scènes d'intérieur.
  `tests/test_plafonds.py` : la balance des couleurs ramène les trois moyennes au même niveau ;
  l'écart vert − rouge passait de +0,03 à −0,4 sur 255 (image grise). Le test accepte désormais
  1/255 d'écart ; un vrai virage au magenta se mesure en dizaines.
- Quatre réglages de −3 à +3, « Normal » au départ : Lumière (gamma des tons moyens, 10 % par
  cran), Contraste (6 %), Couleurs (saturation, 12 %), Teinte (3 % de rouge en plus et de bleu en
  moins vers le chaud). Ils s'ajoutent au profil dans la chaîne (`pipeline.reglages_image`, la
  teinte dans la balance) ; à zéro, la chaîne est identique à avant. Photos : même chose.
- Où : étape 2 de l'assistant (« Lumière et couleurs », film et photo), et une section du même
  nom dans « Réglages libres ». Une seule source de valeurs (`lumiere.Lumiere`) ; propres à chaque
  film, comme le son. Le résumé de « Vérifier et lancer » les cite ; les changer oblige à revoir
  l'avant / après.
- Aperçu instantané : une image du film est restaurée une fois (sans IA, 1 à 2 s), puis chaque
  clic n'applique que les réglages à cette image (0,5 s environ) ; la grande image montre avant
  et après côte à côte. « Autre moment du film » prend une autre image de la partie gardée (jamais
  un passage enlevé). Mesuré : l'image rapide et la même image passée dans la chaîne complète
  diffèrent de 3/255 au plus en moyenne (`tests/test_lumiere.py`).
- Cinq titres de section à 35 px au lieu de quatre à 44 px : la section ouverte garde sa hauteur,
  rien ne défile à 100 et 125 % (`tests/test_ecran_unique.py`).
- Non testé : sur le PC de l'utilisateur, le temps de l'image de base avec « Maximum ».


## Durée annoncée avant de lancer (demande n°15, corrigée)

La durée de Grok étendait le temps de l'aperçu de 10 s à la durée gardée. Mais l'aperçu encode
en « veryfast » et la restauration en « medium » ; « Fidèle » garde en plus 50 demi-images par
seconde. Mesuré sur un film SD de synthèse avec son (durée réelle / estimation) :

| Rendu | 60 s | 180 s | Facteur retenu |
|---|---|---|---|
| Fidèle | 2,34 | 2,11 | 2,2 |
| Équilibré | 1,82 | 1,66 | 1,75 |
| Maximum | 1,65 | 1,57 | 1,65 |

Le facteur multiplie l'estimation (`estimation.FACTEUR`), arrondi vers le haut : mieux vaut
finir avant l'heure annoncée. Encoder l'aperçu en « medium » aurait évité le facteur, mais
doublé l'attente de chaque avant / après. `estimation.lignes` donne la durée et la place sur
deux lignes (maquette « Vérifier et lancer »). Tests : `tests/test_estimation.py` (facteur par
rendu ; film de 60 s : estimation entre 0,7 et 2,5 fois la durée réelle). Non mesuré : le PC
de l'utilisateur, l'IA, une cassette de 2 à 3 heures.

## L'assistant selon les maquettes (demande n°16)

Fait par cinq agents de Grok (rendu, lumière, lancer, navigation, intégration) d'après les trois
maquettes choisies par l'utilisateur, avec les adaptations décidées avant : vraies petites
images (pas d'icônes), vrais noms d'étapes, grande image partagée en deux plutôt que deux
portraits, boutons en mots autour des jauges (pas de glisser). Noms des rendus : « Nettoyage
léger », « Bien nettoyé, naturel », « Nettoyage au plus fort » (clés inchangées).

Corrigé à la fusion (mesuré à 100, 125 et 150 % de texte, fenêtre 1280 × 641) :
- après « Voir l'avant / après », la fenêtre s'élargissait (1342 px à 125 %, 1404 à 150 %) : la
  pile des étapes prenait la largeur et la hauteur de sa plus grande page (« Lumière et
  couleurs »), y compris pour le texte qui revient à la ligne (`heightForWidth`). `_Pile` ne
  mesure plus que l'étape affichée. La liste « Image 2/3 » est cachée dans l'assistant
  (« Avant », « Les deux », « Après » suffisent ; l'écran complet la garde) ;
- défilement de 9 à 30 px à 125 % : « Rien à changer ? Cliquez sur Suivant. » passe sur la ligne
  des boutons, à côté de « Suivant → » ;
- titre coupé à 125 % (« …passages à enleve ») : l'étape s'appelle « Couper le film », comme la
  section de l'écran complet, et le titre revient à la ligne s'il le faut ;
- réglages libres : la durée et la place avaient disparu de la ligne d'état (le test vérifiait
  une phrase sans elles) ; elles y sont revenues, l'assistant ne les répète pas.

Résultat : aucun défilement à 100 et 125 %, à chaque étape, après l'avant / après et en revenant
à « Lumière et couleurs » ; 3 px à l'étape 1 à 150 %. `test_chaque_etape_tient_a_1280_641`
clique désormais « Voir l'avant / après » et vérifie l'absence de défilement à 100 et 125 %.

## Écrans standard

Demande de l'utilisateur : le logiciel doit tenir sur les tailles d'écran courantes, pas seulement
sur celui de son père. La fenêtre s'ouvre agrandie ; sa taille utile = largeur / zoom de Windows,
hauteur / zoom − 79 (barre des tâches et titre ; 1920 × 1080 à 150 % donne 1280 × 641, mesuré).

Mesuré avant : à 1024 px de large, la fenêtre débordait (1028 px, boutons « ← Revenir » 160 px et
« Suivant → » 220 px au minimum) et « Régler l'image » défilait de côté après un aperçu ; à
1093 × 535 (1366 × 768 à 125 %, 1920 × 1080 à 175 %), l'assistant défilait (jusqu'à 67 px à
l'étape 1) ; sur grand écran, « Suivant → » s'étirait sur toute la largeur.

- Largeurs minimales réduites (Revenir 120, Suivant 170, champ « Début de l'extrait » 140, liste
  « Image 2/3 » 6 caractères), « Décalage entre la voix et les lèvres » sur deux lignes.
- Écran bas (moins de 600 px utiles) : boutons verts et petites images de l'étape 1 resserrés
  (`ecran.adapter`, propriété `serre`, la feuille de style imposait 58 px).
- Texte agrandi : sur un écran de moins de 1280 px de large ou de 600 px de haut, « A » et « A+ »
  sont grisés et le texte reste à 100 % (à 125 et 150 %, les sections défilaient de côté). Le
  choix est gardé et revient sur un écran plus grand.
- Grand écran : la place libre va avant « Suivant → », qui garde sa taille.

Résultat, texte à 100 %, assistant complet (avec l'avant / après) et réglages libres : aucune
fenêtre qui déborde, aucun défilement de côté, « Lancer » et « Suivant » visibles, assistant sans
défilement sur 1024 × 689, 1093 × 535, 1366 × 689, 1536 × 785, 1920 × 1001 et 2560 × 1361
(`tests/test_ecrans.py`). Sous 641 px de haut, les sections des réglages libres défilent (40 à
72 px à 1093 × 535). Limite de temps de la fabrication Windows : 120 min (tests : 68 min).
Non vérifié : un vrai écran autre que celui du père ; texte plus grand automatique sur grand écran.
- Premier lancement (aucun choix enregistré) : texte selon l'écran (`ecran.texte_selon_ecran`) :
  125 % sur 1920 × 1080 sans zoom (zone utile 1920 × 1032), 150 % sur 2560 × 1440 ou 4K à 150 %,
  100 % ailleurs (dont l'écran du père). Un choix enregistré l'emporte toujours.
- Défaut trouvé par ce test et corrigé : la fenêtre naît à 1100 × 760 (texte plafonné à 100 %),
  et la ligne qui réappliquait la taille après le chargement des réglages enregistrait ce 100 % :
  le 125 % du père aurait été perdu à chaque lancement. Elle reprend désormais le choix voulu.

## Qualité de restauration (demandes n°17 et n°18)

Fait par les agents de Grok, vérifié et mesuré par Claude avant fusion.

- **Lumière et couleurs scène par scène** (`scenes.py`) : les niveaux et la dominante sont mesurés
  par scène (images réduites, 5 par seconde) et appliqués par commandes (`sendcmd`), avec les mêmes
  plafonds qu'avant et un passage progressif hors coupure franche. L'analyse tourne en
  arrière-plan après l'ouverture ; tant qu'elle n'est pas finie, correction unique ; un avant /
  après vu avant la fin est à revoir ; la restauration attend la fin si besoin. Détection des
  coupures vérifiée sur 8 films d'essai (changement de lumière seul, vraie coupure, sans bruit,
  sans entrelacement, écrans noir et bleu, lumière qui monte doucement, scintillement VHS, fondu).
- **Calcul en 10 bits** jusqu'à l'encodage (le fichier livré reste en 8 bits) : `eq` (8 bits
  seulement) remplacé par `lutyuv`, même rendu à 1/255 près ; dégradés de 1 à 159 niveaux.
- **Contrôle de la numérisation** (`probe.py`, `advice.py`) : copie déjà compressée, déjà réduite
  ou désentrelacée, noirs ou blancs écrasés ; aucune fausse alerte sur une capture sans
  compression.
- Temps de restauration mesuré par Claude sur des films proches de vraies captures (720 × 576
  entrelacé, son, niveaux appliqués) : +13 % en FFV1 4:2:2, +6 % en MPEG-2 4:2:0.
- **QTGMC non embarqué** (étude de l'agent D) : +111 Mo au paquet et environ 14 images par seconde
  sur un PC modeste (3 h 30 de désentrelacement pour une cassette de 2 h).
- **Pas d'IA d'analyse ajoutée** (essai n°18) : un juge de qualité (CLIP-IQA+, DBCNN) choisissant
  lumière et couleurs abîme les photos intactes (24 sur 24, mesuré par Claude) ; IAT éloigne
  l'image de l'original ; les modèles VHS d'OpenModelDB demandent des centaines d'heures pour une
  cassette sans faire mieux. Essais sur dégradations simulées seulement : à refaire sur de vrais
  extraits si l'utilisateur en fournit (`essais/n18/`).
- **Real-ESRGAN gardé** (choix de l'utilisateur) : code BSD-3 ; ses poids sont appris sur DIV2K,
  réservé à la recherche académique. Accepté pour un usage familial gratuit.

## Timeline, lecteur, copie de lecture et reprise (n°13 étape 2, n°19, ChatGPT)

- **Timeline** (ChatGPT, `gpt/timeline` puis `gpt/timeline-retouches`) : zoom autour du curseur,
  « Tout le film », flèches (1 s, 10 s, une image) ; « Chercher la neige… » propose les passages
  vides en bleu, à enlever un par un (« Enlever 0:00 – 0:03 ») ou ensemble (« Tout enlever ») :
  plus rien n'est enlevé d'office ; repères de scène (analyse de la n°17) ; boutons de 38 points.
- **Lecteur intégré** (Grok) : une barre sous l'image, « Lire le film » (bouton clair : le vert
  reste à l'action principale), « Vérifier la coupe » (3 s de chaque côté du raccord, avec le son,
  désentrelacé). Qt Multimedia : +10 Mo au paquet compressé.
- **Copie de lecture** : un film entrelacé s'affichait strié pendant la lecture (écart entre
  lignes 17 dans le lecteur, 0 avec bwdif). Une copie désentrelacée, réduite à 720 px, CRF 27
  (environ 0,55 Go par heure), est préparée en arrière-plan, en priorité basse, APRÈS l'analyse
  des scènes (mesuré : analyse finie à 11,1 s, copie lancée à 11,2 s) ; le lecteur passe dessus à
  la même position. Film progressif : l'original. Place réservée : 4 Mbit/s, doublée (le fichier
  est réécrit à la fin).
- **Reprise** (n°19) : un film gardé de 20 minutes ou plus est restauré par parties de
  10 minutes, chaque partie lue 8 s plus tôt puis la chauffe retirée ; parties gardées dans le
  profil local, vérifiées, reprise automatique ; à l'ouverture, « Une restauration de ce film
  s'était arrêtée à … % ». Pas de reprise avec l'IA, les poussières, la réparation de bande, un
  changement de cadence ou la stabilisation (travail sur tout le film). Surcoût mesuré avec de
  vraies parties : +3 % (FFV1) à +9 % (MPEG-2).
- Fabrication Windows : un seul test échouait depuis la n°155 (1 px de défilement de côté à
  1024 px dans « Lumière et couleurs », polices Windows) ; corrigé, marge de 82 px.

## Fabrication sur le PC de l'utilisateur et petites images de l'étape 1

- `fabriquer_exe.bat` (double-clic) fabrique l'exe sur un PC Windows : mise à jour (`git pull`),
  Python et modules, FFmpeg, une courte sélection de tests, PyInstaller, essai de l'exe, zip et
  SHA-256 dans `livraison\`. Il a trouvé 3 défauts propres à Windows, corrigés : chemin JSON écrit
  à la main (les « \ » cassaient le JSON), fichier écrit dans `/tmp`, et « Régler l'image » qui
  dépassait de 9 px à 1024 px (cases longues à gauche, courtes à droite : marge 50 à 78 px).
- Capture de l'utilisateur (Windows à 150 %, comme l'écran du père) : les petites images de
  l'étape 1 sortaient aux 2/3, collées en haut à gauche, et leur cadre dépassait de la ligne. Le
  dessin tient compte du zoom de l'écran ; l'image se loge dans sa ligne, à 4 px du bord
  (`taille_image`). Test avec un vrai zoom de 150 % (programme à part) : il échoue avec l'ancien
  dessin.
- Lignes de l'étape 1 séparées de 6 px (avant : 1 px avec la ligne « Des détails sont déjà
  perdus », 4 px sans ; 4 px sur un écran bas). Pour que la fenêtre ne grandisse pas, lignes un
  peu moins hautes (rendus 76 px, original 52 px ; images 86 × 65 au lieu de 96 × 72). Une ligne
  n'est jamais plus basse que son texte (le sous-titre était coupé sur un écran bas avec
  l'avertissement). Mesuré : à 1280 × 641, 4 px de moins qu'avant à 100 et 125 % ; à 150 % avec
  l'avertissement, l'étape 1 défile de 42 px (31 avant), le texte n'y est plus coupé.

## Correction scène par scène désactivée (27 novembre 2026)

- Constat (film de l'utilisateur, copie pour la télévision) : à 7,8 s, toute l'image passe d'un
  coup du blanc au jaune entre deux images, l'enfant immobile. Le son est normal.
- Trois défauts, prouvés :
  1. Une « coupure » est un écart de couleur moyenne nettement plus fort qu'autour (rapport
     1,6), **sans minimum**. Sur 15 s d'un vrai plan continu (lu à l'endroit puis à l'envers),
     une coupure est inventée à 10,2 s pour un écart de 1,7 niveau sur 255, invisible : le plan
     y est immobile, la moindre variation paraît « nette ».
  2. Toute coupure trouvée est marquée franche : le fondu de 0,5 s n'est jamais utilisé.
  3. Chaque morceau reçoit la correction de sa propre moyenne, en tout ou rien (dominante si
     l'écart RVB dépasse 15, niveaux selon un seuil) : deux morceaux d'un même plan peuvent
     recevoir des corrections très différentes.
- Pourquoi les essais ne l'ont pas vu : films de mire (testsrc2) dont la couleur moyenne ne
  bouge pas, coupures exactes ; le cas « lampe qu'on allume » (demandé par Claude) a rendu la
  règle plus sensible ; le second tour, jugé sûr, n'a été vérifié que sur 4 variantes de mire.
  Aucun essai sur un vrai film de famille avant la fusion. Erreur de méthode de Claude.
- Décision : `scenes.ACTIF = False`. Correction unique pour tout le film (celle d'avant la
  n°17, la même du début à la fin : aucun saut possible) ; plus de lecture de tout le film à
  l'ouverture. Le mécanisme reste dans le code et ses essais tournent (ils le rallument).
  `test_plan_continu_reel_reste_une_seule_scene` (moyennes du vrai plan, rien de l'image)
  échoue exprès tant que la découpe invente des coupures.
- Pour la rallumer, les quatre ensemble : coupure = vrai changement d'image (contenu) avec un
  seuil minimum ; fondu partout sauf vraie coupure ; correction de chaque scène proche de celle
  du film (écart plafonné, sans tout ou rien) ; validée sur de vrais films de l'utilisateur, sur
  son PC (les films ne quittent pas le PC) : aucune coupure inventée, aucun saut visible.

## Installation des modules : certificat refusé par Python sous Windows (27 novembre 2026)

- Chez l'utilisateur (PC principal, connexion qui marche) : « Téléchargement impossible de
  Real-ESRGAN : [SSL: CERTIFICATE_VERIFY_FAILED] … unable to get issuer certificate ».
  Real-ESRGAN, DeepFilterNet, LosslessCut et Shotcut (tous sur GitHub). Les adresses et les
  empreintes sont bonnes (vérifiées le 27 novembre). Cause : Python lit les certificats de Windows
  mais ne va pas chercher un certificat racine manquant, ce que Windows fait pour le navigateur.
- Correction : certificat refusé (ou réseau en échec après 3 essais), le même fichier est repris
  par `curl.exe` de Windows (System32, Windows 10 et 11), qui vérifie comme le navigateur ;
  empreinte SHA-256 vérifiée de la même façon. Pas de nouvelle dépendance. Message juste si tout
  échoue : le certificat, pas « Vérifiez la connexion Internet ».
- Puis, au démarrage : « PermissionError: [WinError 5] Accès refusé » sur
  `realesrgan-ncnn-vulkan.exe` (dans le profil), probablement gardé par un antivirus : le logiciel
  s'arrêtait avant sa fenêtre. Toute recherche d'outil passe par `tools.est_fichier`, qui ne
  plante pas ; un outil présent mais refusé est marqué inutilisable, avec la raison et quoi faire
  (Historique de protection de la Sécurité Windows, redémarrer, réinstaller).

## Programme d'installation (27 novembre 2026)

- Demande de l'utilisateur, après une journée de difficultés sur son PC principal : que son père
  ne soit pas perdu. Plus de zip à extraire : `Installer-VHS-Restore-AI-….exe` (Inno Setup
  6.7.4, gratuit), un double-clic puis « Installer » ; icône « VHS Restore AI » (une cassette)
  sur le bureau et dans le menu Démarrer ; sans droits d'administrateur
  (`%LOCALAPPDATA%\Programs\VHS Restore AI`) ; une nouvelle version s'installe par-dessus
  (même `AppId`), outils et réglages du profil gardés ; désinstallation dans Paramètres.
- Fabriqué par `scripts/installateur.ps1`, appelé par `fabriquer_exe.ps1` (après le zip : un
  échec n'empêche pas le zip) et par la fabrication GitHub. Inno Setup est installé au besoin,
  version figée, empreinte SHA-256 vérifiée, dans le profil. Ce n'est pas une dépendance Python.
- Icône de l'exe et de la fenêtre : `vhs_restore/assets/VHSRestoreAI.ico` (16 à 256 px).
- Non essayé par Claude (Inno Setup ne tourne que sous Windows) : premier essai sur le PC de
  l'utilisateur. Vérifié ici : encodage des scripts pour PowerShell 5.1, empreinte, icône, appels
  (`tests/test_installateur.py`).

## Chasse aux bugs (n°20, bots) et corrections (n°21, Claude) — 27 novembre 2026

- n°20 : 33 constats des bots, avec preuves ; Claude a relancé les 35 tests sur la base : 34
  échouent pour la raison annoncée ; le test de D1 plantait dans sa propre préparation.
  Tests et rapports repris dans la branche (`tests/test_bugs_n20_*.py`, `partage-grok/RAPPORT-N20-*`).
- n°21 faite par Claude (crédits des bots épuisés). Corrigés, test sans marqueur, vert :
  C1 (aide du premier lancement : fenêtre qui défile, « C'est parti » visible, Échap), C2
  (taille de la fenêtre ramenée à l'écran), C3 et C4 (image du film extraite à 576 lignes,
  petites images de la barre à 72 × zoom, dessinées en vrais pixels), C5 (« Détails du
  fichier »), A3 (petite dérive), A2 et A4 (retard de 25 ms d'afftdn compensé, 0,1 s de silence
  devant le nettoyage du son), E2 (message d'écart de durée), B2 (teinte après le plafond de la
  dominante), B4 (masque du bas en lignes du film), D3 (disque plein), D4/E7 (verrou tenu par le
  système, repris après un arrêt brutal), D5, D6, D7, E1 (copie 4:3 d'une capture SD sans
  format), E4 (durée au quart d'heure supérieur), E5, E6, E8, E9, E10.
- Tests de netteté C3/C4 de la n°20 : ils mesuraient une image fixe que le zoom étale forcément ;
  réécrits avec la taille que le logiciel extrait vraiment (échouent avec l'ancien code).
- Gardés, avec leur test toujours marqué : B3 (la détection automatique compte le décalage de
  couleur en pixels de couleur ; changer l'unité casserait la correction), D2 (refuser un disque
  de type inconnu bloquerait les disques réseau ; à faire en avertissement), B1 (scintillement,
  option rare).
- Restent à faire : A1 (3 ms de son par raccord des passages enlevés : refaire le son en une
  fois après le collage), E3 (« Arrêter » pendant la séparation), D1 (FFmpeg survit à un
  plantage : « Job Object » Windows, à essayer sur le PC de l'utilisateur), D8 à D10 (Windows).

## Avant / après en Full HD : couleurs justes — 28 novembre 2026

- Constat de l'utilisateur : en « Nettoyage au plus fort », l'aperçu tirait au vert, couleurs
  ternes, lumière trop jaune. Mesuré sur une mire : moitié « après » +46 niveaux de vert, rouge
  −10. Le film restauré, lui, était juste (écart de 0 à 9 niveaux, comme en « Bien nettoyé »).
- Cause : le film en Full HD est codé en BT.709, l'original en BT.601 ; la comparaison collait
  les deux moitiés sans convertir, dans un fichier sans étiquette de couleurs.
- Choix : les deux moitiés sont converties en BT.601 (taille de définition standard, 540
  lignes) et le fichier de comparaison est étiqueté BT.601. Écart retombé à 8 niveaux au plus.
  Ni Real-ESRGAN ni DeepFilterNet n'étaient en cause (DeepFilterNet ne traite que le son).
  Test : `test_apercu_full_hd_garde_les_couleurs` (échoue avec l'ancien code).

## Réglages libres : l'avant / après ancien est signalé — 28 novembre 2026

- Constat de l'utilisateur : après avoir coché des réglages (voix, contraste…), l'ancienne image
  restait affichée sans rien dire ; on croyait le réglage sans effet. Tous les réglages, image et
  son, sont pourtant pris en compte quand on refait l'avant / après.
- Choix : on garde l'image (un écran vide déroute), mais elle dit « APRÈS (ancien réglage) »,
  le bas de la fenêtre dit « Réglage changé : cliquez sur « Voir l'avant / après » pour voir son
  effet », et ce bouton redevient l'étape conseillée. Revenir au réglage vu efface
  l'avertissement. Comparaison faite sur les réglages eux-mêmes (comme l'assistant, qui avait
  déjà la sienne) : changer d'image fixe ou d'extrait ne déclenche rien.
- Vérifié à 1280 × 641 et 150 % : l'étiquette passe sous l'image, sans cacher « AVANT ».
  Tests : `tests/test_apercu_perime.py` (échouent avec l'ancien code).

## Couleurs : dominante mesurée sur tout le film — 28 novembre 2026

- Demande de l'utilisateur : un rendu moderne pour des cassettes de caméscope (le Super 8 est
  mis de côté), en retrouvant de bonnes couleurs ; une analyse en amont qui choisit les bons
  réglages.
- Constat : la dominante de tout le film venait de 8 images à un seul moment (au tiers du film),
  par la moyenne des trois couleurs (« monde gris »). Un plan de pelouse à cet endroit faisait
  virer tout le film au magenta ; de la neige et du ciel, au jaune ; une lampe orangée à
  l'intérieur bleuissait toutes les scènes du dehors.
- Choix (films de plus d'une minute) : 24 moments répartis (de 3 % à 97 % du film), une image
  réduite chacun ; par image, la moyenne géométrique de deux méthodes classiques (« monde gris »
  sans les pixels très colorés, et « blanc de référence » : les 8 % de pixels les plus clairs,
  non brûlés) ; puis la médiane des moments. Si l'orangé/bleuté varie beaucoup d'un moment à
  l'autre (écart entre le 20e et le 80e centile > 0,25 en log), le conseil le dit : la
  correction est un juste milieu. Film d'une minute ou moins : la mesure d'avant (ses essais sur
  mire restent valables ; la méthode combinée voit la mire testsrc2 comme magenta).
- Mesuré sur des scènes d'essai réalistes (pièce, jardin, neige, grain et mollesse de VHS ;
  écart entre couleurs, 15 = seuil du conseil) : pelouse au tiers 42 → 6 ; neige au tiers
  48 → 6 ; jardin tout du long 42 → 13 ; pièce neutre 11 → 6 ; lampe orangée 80 → 68 (toujours
  corrigée) ; intérieur puis dehors : repéré comme variable. Coût : 24 lectures courtes, moins
  de 2 s ici. Tests : `tests/test_couleur_film.py` (échouent avec l'ancien code).
- Limite : scènes d'essai synthétiques ; à confirmer sur les cassettes de l'utilisateur.
  Étape suivante : une correction par ambiance (intérieur / dehors), quand la mesure par moments
  aura été vérifiée sur ses cassettes.

## Lumière : noirs et blancs mesurés sur tout le film — 28 novembre 2026

- Même défaut que la dominante : les niveaux (YLOW / YHIGH) venaient d'un seul moment, au tiers
  du film. Une pièce terne à cet endroit faisait éclaircir tout le film, et les blancs des
  scènes bien exposées (dehors) brûlaient.
- Choix (films de plus d'une minute) : les mêmes 24 moments, lus en une seule passe avec la
  couleur (signalstats sur l'image entière, puis l'image réduite). Noirs : le quart le plus
  sombre des moments ; blancs : le quart le plus clair. Seul un film terne presque partout est
  corrigé ; l'étirement reste à moitié et une seule fois pour tout le film.
- Mesuré : pièce terne au tiers entre deux scènes de jardin : avant, noirs 88 / blancs 130,
  conseil « éclaircir » pour tout le film ; maintenant, blancs 193, aucun étirement. Film terne
  partout : toujours corrigé. Film d'une minute ou moins : la mesure d'avant.
  Tests : `tests/test_couleur_film.py`.

## Bulles d'aide lisibles — 28 novembre 2026

- Constat de l'utilisateur : « les couleurs des descriptions de chaque bouton sont illisibles ».
  Les bulles d'aide gardaient le fond foncé du bandeau dans les deux affichages, avec la couleur
  de texte du thème : en affichage clair, texte presque noir sur fond foncé, contraste 1,18.
- Choix : fond propre aux bulles (blanc en affichage clair, foncé en sombre), texte du thème,
  13 pt au lieu de 12. Contraste 17,3 (clair) et 13,6 (sombre). Le couple est ajouté à la liste
  des contrastes vérifiés, et `test_bulle_d_aide_lisible` lit le style réellement appliqué.

## Caler la voix sur les lèvres : l'écran l'explique — 28 novembre 2026

- Constat de l'utilisateur : « Il faut l'indiquer, sinon l'utilisateur ne comprend pas. »
  Réglages libres : légende coupée à 150 % (« Décalage entre la voix et »), « − » et « + »
  sans explication, et le calage au début et à la fin (qui calcule la dérive) n'existait que
  dans l'assistant, sans chemin pour y aller. Assistant : « Le son est en retard ? » trompait
  (la voix peut être en avance) ; on ne savait ni où s'ouvrent les 10 secondes, ni ce qui était
  déjà corrigé.
- Choix. Réglages libres : « Voix et lèvres », une ligne qui explique « − » et « + », et
  « Caler au début et à la fin… », qui ouvre l'étape du son de l'assistant, réglage ouvert.
  Assistant : « La voix ne colle pas aux lèvres ? », la phrase dit que l'extrait s'ouvre dans le
  lecteur vidéo de Windows et qu'un clic décale la voix d'une image ; une ligne dit ce qui est
  réglé, en images (« Au début : voix avancée de 2 images. »), jamais en millisecondes.
- Vérifié à 1280 × 641 et 150 % (captures). Tests : `tests/test_calage_son.py` (échouent avec
  l'ancien code) ; l'assertion du texte du bouton dans `test_assistant.py` vérifie le nouveau.
