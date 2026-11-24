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

