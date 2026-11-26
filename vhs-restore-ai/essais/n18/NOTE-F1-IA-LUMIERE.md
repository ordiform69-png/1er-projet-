# Demande n°18, agent F1 : lumière et couleurs réglées par IAT

Branche `grok/ia-lumiere` (depuis `38554ea`, banc F4 `d9d88e4` récupéré par fusion de
`grok/ia-essai`). Rien dans `vhs_restore/`, rien dans `requirements*.txt`, `VHSRestoreAI.spec`
inchangé : le paquet part de `VHSRestoreAI.py` et liste ses données une par une, `essais/` n'est
ni importé par le logiciel ni listé, donc hors du paquet. Aucun poids, ONNX, image ni vidéo
commité (`essais/n18/.gitignore` de F4 : `cache/`, `sorties/`, `*.onnx`, `*.pth`…).

## Fichiers

| Fichier | Rôle |
|---|---|
| `ia_lumiere.py` | l'essai, une commande ; CSV ; `--extraits <dossier>` ; `--verifier` |
| `f1_banc.py` | seul point de contact avec le banc F4 (`banc.py`) |
| `f1_iat.py` | IAT en ONNX (onnxruntime, CPUExecutionProvider), matrice + gamma → filtres FFmpeg, plafonds |
| `iat_export_onnx.py` | export ONNX, une fois, à part (seul script qui demande torch + timm) |
| `iat_modeles.json` | URL figées, SHA-256, licences, empreintes des ONNX obtenus |
| `resultats-f1-ia-lumiere.csv` | mesures faites sur le box de Grok (conditions ci-dessous) |

## Commandes (depuis `vhs-restore-ai/`)

```
# 1. une fois, dans un environnement À PART (jamais celui du logiciel) :
python -m venv venv-export && venv-export/bin/pip install torch timm onnx onnxruntime numpy
venv-export/bin/python essais/n18/iat_export_onnx.py     # -> essais/n18/cache/iat/*.onnx + export_iat.json
# 2. l'essai (numpy, onnxruntime, FFmpeg seulement) :
python essais/n18/ia_lumiere.py --verifier
python essais/n18/ia_lumiere.py                          # -> essais/n18/resultats-f1-ia-lumiere.csv
python essais/n18/ia_lumiere.py --extraits <dossier>     # + vrais extraits : écarts « non mesuré »
```
Images avant / après : `essais/n18/sorties/f1/<scène>.png` (+ `.txt` = ordre des vignettes).

## Licences, vérifiées à la source

- Code et poids IAT : https://github.com/cuiziteng/Illumination-Adaptive-Transformer, commit
  `c76472265247f47cea57649af28b15018bb64cb1`, fichier `LICENSE` : « Copyright 2022 The
  University of Tokyo » + Apache License 2.0 (API GitHub : `Apache-2.0`). Les poids sont dans
  ce même dépôt (`IAT_enhance/*.pth`).
- **`best_Epoch_exposure.pth` : EXCLU.** Données « Exposure » d'Afifi et al. ;
  https://github.com/mahmoudnafifi/Exposure_Correction : « As the dataset was originally
  rendered using raw images taken from the MIT-Adobe FiveK dataset, our dataset follows the
  original license of the MIT-Adobe FiveK dataset. » et « This software is provided for research
  purposes only and CANNOT be used for commercial purposes. » Jamais téléchargé par les scripts.
- **MIT-Adobe FiveK : EXCLU** (aucun poids FiveK n'est publié dans le dépôt IAT de toute façon).
- **`best_Epoch_lol_v1.pth` (LOL, Wei et al. 2018) : retenu SOUS RÉSERVE.**
  https://daooshee.github.io/BMVC2018website/ ne donne AUCUNE licence (ni permission ni
  restriction ; les catalogues indiquent « licence inconnue »). Pas de « recherche seulement »
  écrit : non exclu par la règle, mais à signaler à l'utilisateur.
- **`best_Epoch_lol.pth` (LOL-v2-real, Yang et al. 2021, utilisé par `evaluation_lol_v2.py`) :
  retenu SOUS RÉSERVE**, même situation : https://github.com/flyywh/SGM-Low-Light et
  https://github.com/flyywh/TIP-2021-Deep-Recursive-Band-Network n'ont ni licence ni mention.
  (Un miroir Hugging Face annonce Apache-2.0, mais ce n'est pas la source : non retenu comme preuve.)

SHA-256 : lol_v1 `6fb32236…3435b`, lol_v2 `9564b7e1…bdc4`, exposure (exclu) `15a94945…a3ee`
(complets dans `iat_modeles.json`, avec ceux des trois fichiers de code téléchargés pour l'export).

## La partie « globale » donne bien une matrice 3 × 3 et un gamma (code vérifié)

Commit `c764722`, dossier `IAT_enhance/model/` :
- `global_net.py` l. 90 : `color_base = nn.Parameter(torch.eye(3))` ; l. 17 : 10 requêtes apprises ;
  l. 113-121 : `gamma = gamma_linear(x[:, 0]) + gamma_base` (1 valeur),
  `color = color_linear(x[:, 1:]).view(-1, 3, 3) + color_base` (9 requêtes → matrice 3 × 3).
- `IAT_main.py` l. 104-109 : `apply_color` = `tensordot(image, ccm, dims=[[-1], [-1]])` puis
  `clamp(1e-8, 1)` ; l. 113-114 : partie locale `img * mul + add` ; l. 120 : la partie globale
  regarde l'image d'ENTRÉE ; l. 123 : sortie = `apply_color(img_high, color) ** gamma`.
- Donc sortie_R = M[0,0]·R + M[0,1]·G + M[0,2]·B (etc.), écrêtée, puis puissance gamma par canal.
- Réserve tirée du code (pas d'une mesure) : matrice et gamma ont été appris pour s'appliquer
  APRÈS la partie locale. « Global seul » les applique à l'image brute, ce pour quoi ils n'ont
  pas été entraînés. Exemple relevé : avec lol_v2 la matrice brute a des sommes de lignes
  d'environ 0,3 (elle assombrit, la partie locale ayant éclairci avant).

## Méthode

- Banc F4 sans changement (`banc.charger_references()`, `banc.degrader()` par défaut, `images`
  et `graine` inchangés ; `banc.mesurer` sur l'image du milieu ; `banc.appliquer_filtre`).
- (1) **actuelle** : ce que fait le logiciel, appelé sans le modifier. Niveaux = médiane de
  YLOW / YHIGH de signalstats (`probe.parse_signals`), dominante = moyennes RGB sur 8 images 32 × 32
  → `probe.cast_gains`, seuils de `advice.py` (l. 44-59), filtres de `pipeline._cast_filter` puis
  `pipeline._levels_filter` (ordre de `pre_filters`). Mesuré UNE fois sur le « film » = les
  5 extraits à la suite. `actuelle_par_scene` = même mesure sur la scène seule (en plus).
  Ne contient que niveaux + dominante (pas débruitage ni `eq` du profil : c'est `chaine_naturelle`
  de F4).
- (2) **iat_global** : 4 images par scène (`--images-par-scene`, 3 à 5), médiane élément par
  élément de la matrice et du gamma, puis `format=rgb48le,colorchannelmixer=…,lutrgb=…,format=rgb24`
  sur tout l'extrait. `colorchannelmixer` = la matrice telle quelle (lignes = sorties) et
  écrête comme le `clamp` d'IAT ; `lutrgb` = puissance exacte `val^gamma` par canal comme IAT
  (pas `eq=gamma`, qui agit sur la luminance en YUV ; pas `curves`, qui interpole entre des points) ;
  16 bits entre les deux pour ne pas arrondir deux fois. Contrôle `--verifier` : FFmpeg contre
  numpy, écart max 1/255.
- (3) **iat_complet** : modèle complet sur l'image du milieu (ONNX, puis recomposition numpy
  identique à `IAT.forward`, écart à PyTorch ≤ 5e-7 vérifié à l'export).
- **Plafonds** : méthode actuelle « sans plafond » = `safe_levels` / `safe_gains` remplacés par
  l'identité le temps de l'appel (fichier non modifié, rétabli après, vérifié). Pour IAT, le
  logiciel n'a ni matrice ni gamma : transposition F1 **à valider par Claude** (`f1_iat.plafonner`) :
  gains relatifs (sommes des lignes / moyenne) → `safe_gains` ; gain moyen borné à ×/÷ `MAX_CONTRAST`
  (1,6, la borne de `safe_levels`) ; gamma borné pour que le gain sur le gris moyen reste dans ×/÷ 1,6.
  Limite : les proportions entre canaux d'une ligne sont gardées, donc la saturation / le mélange
  des canaux n'est pas borné. La partie locale d'IAT complet n'a aucun plafond équivalent.
- **ONNX** : export legacy (`dynamo=False`), opset 17, hauteur / largeur libres ; torch 2.15.0+cpu.
  Deux exports successifs donnent les mêmes octets :
  `iat_lol_v1_global.onnx` a161618a…e328, `iat_lol_v1_complet.onnx` 43f1d97a…c390,
  `iat_lol_v2_global.onnx` f24b9aa0…eb1f, `iat_lol_v2_complet.onnx` 134fc6a5…207b
  (complets dans `iat_modeles.json`). Le script d'essai refuse un ONNX dont l'empreinte ne
  correspond pas à son manifeste d'export.

## État des mesures

Mesures RÉELLES faites sur le box de Grok, le 26/11/2026 : banc F4 (5 références CC0),
8 cœurs Intel Xeon partagés avec d'autres tâches, FFmpeg 7.1.5, onnxruntime 1.32.0, Python 3.13.
Ce n'est PAS le bac à sable de référence. **Aucune conclusion : Claude relance
`python essais/n18/ia_lumiere.py`.** Les temps FFmpeg (9 images, démarrage compris) sont bruités
(de 11 à 35 ms par image pour un même filtre). L'écart de temps lol_v1 / lol_v2 en IAT complet
(même architecture) n'est pas expliqué. Estimation 2 h pour IAT global : une scène toutes les 5 s
(`--scene-s`), hypothèse.

Moyennes des 5 scènes (détail par scène, matrices, gammas et chaînes dans le CSV) :

| méthode | plafond | poids | PSNR | SSIM | ΔE2000 | ms / image (application) | film 2 h (min) |
|---|---|---|---|---|---|---|---|
| entrée dégradée | - | - | 19,99 | 0,45 | 13,82 | - | - |
| actuelle | oui | - | 20,21 | 0,45 | 13,95 | 27,8 | 83 |
| actuelle | non | - | 19,25 | 0,44 | 14,55 | 21,1 | 63 |
| actuelle par scène | oui | - | 19,99 | 0,42 | 15,27 | 17,7 | 53 |
| actuelle par scène | non | - | 19,10 | 0,40 | 16,06 | 19,7 | 59 |
| iat_global | oui | lol_v1 | 15,08 | 0,46 | 20,14 | 34,1 | 112 |
| iat_global | non | lol_v1 | 15,06 | 0,46 | 21,01 | 46,8 | 150 |
| iat_complet | oui (global) | lol_v1 | 7,93 | 0,46 | 30,57 | 3 516 | 10 548 |
| iat_complet | non | lol_v1 | 7,76 | 0,45 | 31,82 | 3 516 | 10 548 |
| iat_global | oui | lol_v2 | 11,68 | 0,27 | 22,76 | 45,8 | 143 |
| iat_global | non | lol_v2 | 8,27 | 0,23 | 32,67 | 51,1 | 159 |
| iat_complet | oui (global) | lol_v2 | 11,78 | 0,45 | 27,93 | 6 682 | 20 046 |
| iat_complet | non | lol_v2 | 10,98 | 0,42 | 24,67 | 6 682 | 20 046 |

Extraits réels : non mesuré (aucun extrait fourni).
