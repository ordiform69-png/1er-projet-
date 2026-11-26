# Rapport n°18 pour Claude — essai d'IA légères (synthèse F4)

Mesures faites **hors bac à sable**, sur les machines des agents, le 26 novembre 2026.
La recommandation en fin de note est **provisoire** : elle ne tranche pas ce qui entrera dans le logiciel.

Sources, lues sans fusion :

| Agent | Branche | Commit | Notes et CSV |
|---|---|---|---|
| F4 | `grok/ia-essai` | `d9d88e4`, puis ce rapport | `essais/n18/resultats-reference.csv`, `banc.py` |
| F1 | `grok/ia-lumiere` | `5091c59` | `essais/n18/NOTE-F1-IA-LUMIERE.md`, `resultats-f1-ia-lumiere.csv` |
| F2 | `grok/ia-juge` | `ec827b6` | `essais/n18/RAPPORT-F2-JUGE.md`, `resultats-juge-*.csv` |
| F3 | `grok/ia-vhs` | `fdf1027` | `essais/n18/F3-MODELES-VHS.md`, `f3_resultats/*.csv` |

Le point de comparaison du logiciel est `pipeline.filter_chain`, profil « Bien nettoyé, naturel » (`banc.chaine_naturelle()`). Chaîne lue, non modifiée :

`removegrain=m0=1:m1=1:m2=1,hqdn3d=3:5:4.5:7,eq=contrast=1.04:saturation=1.08,cas=strength=0.3,setsar=16/15,format=yuv420p`

Aucun extrait de vraie cassette n'a été fourni : les trois agents écrivent « non mesuré » pour `--extraits`.

## 1. L'écart signalé par F3 : le banc est déterministe, FFmpeg 6 et FFmpeg 7 ne rééchantillonnent pas pareil

F3 signale que relancer `reference.py` ne redonne pas le `resultats-reference.csv` poussé par F4 (intérieur dégradé : 19,27 dB contre 19,02 dB).

**Deux relances** de `python essais/n18/reference.py` sur la machine de F4 (FFmpeg 6.1.1, 4 cœurs), sorties comparées hors temps d'horloge : **aucun écart** de PSNR, SSIM ni ΔE2000, ni avec le CSV déjà poussé. L'intérieur dégradé reste 19,272477 dB. Seules les secondes par image bougent (temps mur).

Contrôles séparés, même image préparée, FFmpeg 6.1.1 du système et FFmpeg 7.0.2 statique :

- Deux passes et 1, 4 ou 8 fils : pixels identiques, dans chaque version. La graine du filtre `noise` (`c0_seed=1`, `c1_seed=2`, `c2_seed=3`, drapeaux `t+u`) ne rend pas le banc aléatoire.
- Le bruit seul, les filtres de couleur (`eq`, `colorchannelmixer`, `lutrgb`) et la chaîne du logiciel appliquée à l'image d'origine : **identiques** entre 6.1.1 et 7.0.2.
- L'écart apparaît au `scale` bilinéaire des plans Y et UV (définition réduite et couleur étalée). Le rééchantillonnage de ces plans a changé entre FFmpeg 6.1 et 7.0. Ce n'est pas un défaut de graine : c'est une différence de version, stable.

FFmpeg 7.0.2 reproduit **à six décimales** les colonnes « dégradée » et « sans IA » du CSV de F3 (FFmpeg 7.1.5) sur les cinq images. L'exemple de F3 est celui-ci : intérieur dégradé, 19,272477 dB (6.1.1, CSV F4) et 19,022313 dB (7.0.2 = CSV F3). Écart : **0,250 dB**.

Écart de PSNR, FFmpeg 6.1.1 moins FFmpeg 7.0.2, mesuré ici sur les cinq références :

| Image | Dégradée | Chaîne « Bien nettoyé, naturel » |
|---|---:|---:|
| intérieur | +0,250 dB | +0,113 dB |
| extérieur | +0,216 dB | −0,166 dB |
| visages | +1,445 dB | +1,841 dB |
| peau | +0,429 dB | +0,445 dB |
| ciel | +0,145 dB | +0,084 dB |

Le banc n'a pas été modifié : le changer produirait une troisième série, comparable ni au CSV F4 ni aux CSV de F1, F2 et F3.

**Les chiffres de F1, F2 et F3 restent comparables entre eux**, et comparables à la chaîne du logiciel **telle que F3 l'a mesurée** (`sans_ia`, même dégradation, FFmpeg 7.1.5). Les moyennes « entrée » de F1 et « dégradée » de F3 coïncident (PSNR 19,99 dB). Ils ne sont pas comparables chiffre à chiffre au `resultats-reference.csv` de F4 (FFmpeg 6.1.1) : l'écart va de 0,08 dB à 1,8 dB selon l'image. Dans chaque essai, le classement interne (méthode contre méthode, sur les mêmes images) reste valable.

## 2. Référence : la chaîne du logiciel

### CSV F4, FFmpeg 6.1.1, 4 cœurs (`resultats-reference.csv`)

Temps : mur du processus FFmpeg divisé par 9 images, démarrage inclus. Pas de juge.

| Image | PSNR dégradé | SSIM dégradé | ΔE dégradé | PSNR chaîne | SSIM chaîne | ΔE chaîne | s/image |
|---|---:|---:|---:|---:|---:|---:|---:|
| intérieur | 19,272 | 0,5375 | 14,498 | 18,565 | 0,6155 | 13,531 | 0,0122 |
| extérieur | 19,086 | 0,3733 | 15,124 | 18,524 | 0,4964 | 13,329 | 0,0107 |
| visages | 24,077 | 0,6261 | 9,191 | 23,823 | 0,8644 | 9,303 | 0,0135 |
| peau | 20,577 | 0,4276 | 13,665 | 19,476 | 0,6943 | 13,625 | 0,0140 |
| ciel | 19,440 | 0,4948 | 14,081 | 18,598 | 0,6751 | 13,278 | 0,0147 |

### Même chaîne sur la dégradation de F1 et F3 (FFmpeg 7.1.5, 8 cœurs)

Moyenne des 5 images, `f3_resultats.csv`, variante `sans_ia`, zone « image entière » (la note F3 arrondit pareil) :

| | PSNR | SSIM | ΔE2000 | hf_rapport | s/image | Film 2 h |
|---|---:|---:|---:|---:|---:|---:|
| dégradée | 19,99 | 0,447 | 13,82 | 1,13 | — | — |
| chaîne, sans IA | 19,33 | 0,683 | 14,03 | 0,98 | 0,014 (médiane, `f3_chrono.csv` : 0,014293) | 0,7 h |

Formule de F3, citée telle quelle : heures = secondes/image × 180 000 / 3 600 (25 images/s × 2 h). Le 0,7 h vient du chronométrage `--chrono 3`, machine plus calme que l'essai complet. La chaîne améliore le SSIM (0,447 → 0,683) et laisse le PSNR et le ΔE du même ordre.

## 3. F1 — lumière et couleurs (IAT)

Note `NOTE-F1-IA-LUMIERE.md`, moyennes des 5 scènes recalculées sur `resultats-f1-ia-lumiere.csv` (elles coïncident). Machine : 8 cœurs, FFmpeg 7.1.5, onnxruntime 1.32.0. Les temps FFmpeg sont bruités (F1 : 11 à 35 ms pour un même filtre). « Actuelle » = niveaux et dominante du logiciel (`safe_levels`, `safe_gains`, `_levels_filter`, `_cast_filter`), **pas** la chaîne complète du profil : F1 le dit. Le film de 2 h est l'estimation de F1 (une scène toutes les 5 s pour IAT global).

| Méthode | Plafond | Poids | PSNR | SSIM | ΔE | Écart PSNR à l'entrée | ms/image | Film 2 h | Taille | Licence |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| entrée dégradée | — | — | 19,99 | 0,45 | 13,82 | 0 | — | — | — | — |
| actuelle | oui | — | 20,21 | 0,45 | 13,95 | +0,22 | 27,8 | 83 min | — | code du logiciel |
| actuelle | non | — | 19,25 | 0,44 | 14,55 | −0,74 | 21,1 | 63 min | — | — |
| actuelle, par scène | oui | — | 19,99 | 0,42 | 15,27 | 0,00 | 17,7 | 53 min | — | — |
| IAT global | oui | LOL v1 | 15,08 | 0,46 | 20,14 | −4,91 | 34,1 | 112 min | fichier non publié | Apache-2.0 pour le code et les poids ; données LOL : licence non trouvée |
| IAT global | non | LOL v1 | 15,06 | 0,46 | 21,01 | −4,93 | 46,8 | 150 min | idem | idem |
| IAT complet | oui (global) | LOL v1 | 7,93 | 0,46 | 30,57 | −12,06 | 3 516 | 10 548 min | idem | idem |
| IAT complet | non | LOL v1 | 7,76 | 0,45 | 31,82 | −12,23 | 3 516 | 10 548 min | idem | idem |
| IAT global | oui | LOL v2 | 11,68 | 0,27 | 22,76 | −8,31 | 45,8 | 143 min | idem | idem |
| IAT global | non | LOL v2 | 8,27 | 0,23 | 32,67 | −11,72 | 51,1 | 159 min | idem | idem |
| IAT complet | oui (global) | LOL v2 | 11,78 | 0,45 | 27,93 | −8,21 | 6 682 | 20 046 min | idem | idem |
| IAT complet | non | LOL v2 | 10,98 | 0,42 | 24,67 | −9,01 | 6 682 | 20 046 min | idem | idem |

Licences (F1, vérifiées à la source) : dépôt IAT commit `c764722`, Apache-2.0. Poids « Exposure » **exclus** (MIT-Adobe FiveK, « research purposes only »). LOL v1 et LOL v2 **retenus sous réserve** : aucune licence sur les pages des auteurs. La partie globale est bien une matrice 3×3 et un gamma (`global_net.py`) ; F1 note qu'ils ont été appris pour s'appliquer après la partie locale.

Verdict provisoire : sur ce banc, IAT s'éloigne de l'origine (PSNR et ΔE) par rapport à l'entrée et à la correction actuelle. Le modèle complet se compte en heures de film pour deux heures de cassette. Rien à intégrer tant que les données LOL n'ont pas de licence et que de vrais extraits n'ont pas été vus.

## 4. F2 — un juge choisit débruitage et netteté

Note `RAPPORT-F2-JUGE.md`. 15 cas : 5 images × 3 bruits, 9 réglages sûrs pris dans `profiles.py`. Le réglage `equilibre+n030` **est** la chaîne actuelle. Machine : 8 cœurs, FFmpeg 7.1.5, charge 11 à 15. Les taux viennent de `resultats-juge-resume.csv`, les temps de `resultats-juge-chrono.csv` (la note arrondit ces temps ; le résumé donne des médianes un peu différentes, par exemple 303,9 ms au lieu de 313,1 ms pour CLIP-IQA+ en tuiles : deux passages, charge différente).

| Juge | Bon choix | Top 3 | ρ PSNR | ρ SSIM | ρ ΔE | Perte PSNR | Trop net | Trop coloré | ms/image (8 fils) | Taille | Licence des poids |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| CLIP-IQA+ tuiles | 53,3 % (8/15) | 80 % | 0,71 | 0,73 | 0,49 | 0,064 dB | 0 % | 6,7 % | 313 | 153,2 Mo | CC-BY-NC-SA-4.0 |
| CLIP-IQA+ image réduite | 20 % | 33 % | −0,04 | 0,18 | −0,10 | 0,248 dB | 73 % | 47 % | 247 | 153,2 Mo | idem |
| MUSIQ tuiles | 20 % | 53 % | 0,17 | 0,22 | 0,05 | 0,320 dB | 67 % | 20 % | 397 | 109,7 Mo | idem |
| MUSIQ image réduite | 6,7 % | 13 % | −0,35 | −0,31 | −0,27 | 0,461 dB | 80 % | 53 % | 196 | 109,7 Mo | idem |
| LIQE (mix, natif) | 13,3 % | 13 % | −0,21 | −0,11 | −0,19 | 0,398 dB | 100 % | 73 % | 767 | 353,9 Mo | idem |
| DOVER-Mobile | non mesuré | — | — | — | — | — | — | — | non mesuré | non mesuré | MIT pour le code ; poids non séparés |
| témoin fixe `maximum+n0` | 60 % (9/15) | 93 % | — | — | — | 0,0035 dB | — | — | — | — | — |
| témoin `equilibre+n030` (chaîne) | 0 % | 0 % | — | — | — | 0,361 dB | — | — | 22 ms pour appliquer un réglage (médiane, 180 passages) | — | — |

Film de 2 h, **estimation de F2** (720 scènes, une toutes les 10 s, un point par scène, 9 réglages) : environ 56 min de plus avec CLIP-IQA+ en tuiles. Avec 3 points par scène, F2 dit environ trois fois plus.

Autres faits mesurés par F2 : sur ce banc le meilleur consensus est toujours `cas` à 0 ; le bon débruitage suit le niveau de bruit (`maximum+n0` dès le bruit par défaut). CLIP-IQA+ en tuiles fait 5/5 au bruit fort, 3/5 au défaut, 0/5 au bruit léger. LIQE note l'image brute au-dessus de toute la grille.

Licences (F2) : exports ONNX `86Cao/IQA-ONNX-Models`, révision `2e32ab1`. La fiche dit Apache-2.0, mais les poids d'origine sont en CC-BY-NC-SA-4.0 et le code IQA-PyTorch en PolyForm Noncommercial. KonIQ-10k est offert « à la communauté de recherche » sans licence commerciale écrite : zone grise, signalée par F2. CLIP-IQA+ a été recalé sur `pyiqa` (écart < 1e-4). LIQE de l'ONNX est `liqe_mix`, pas KonIQ seul. MUSIQ de l'ONNX n'est qu'une échelle de 224 : écart à `pyiqa` multi-échelle de 0,1 à 18,3 points. DOVER-Mobile : pas d'ONNX publié, non mesuré.

Verdict provisoire : aucun juge ne bat le réglage fixe `maximum+n0` (60 % contre 53 % pour le meilleur juge, perte 0,0035 dB contre 0,064 dB). MUSIQ et LIQE préfèrent l'image trop nette. Piste citée par F2, non décidée ici : CLIP-IQA+ en tuiles comme garde-fou contre l'excès de netteté, pas comme sélecteur, et seulement après de vrais extraits.

## 5. F3 — modèles VHS d'OpenModelDB

Note `F3-MODELES-VHS.md`. Moyennes des 5 images du banc, zone « image entière », recalculées sur `f3_resultats.csv` (elles coïncident avec la note). Temps : médiane de `f3_chrono.csv` (8 fils ONNX, charge encore 5 à 8). Les temps de `f3_temps.csv` (jusqu'à 84 s/image) sont ceux de la machine chargée : F3 ne les retient pas.

| Variante | PSNR | SSIM | ΔE | hf_rapport | Écart PSNR à la chaîne | s/image | Film 2 h | Taille ONNX | Licence |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| dégradée | 19,99 | 0,447 | 13,82 | 1,13 | +0,66 | — | — | — | — |
| sans IA (la chaîne) | 19,33 | 0,683 | 14,03 | 0,98 | 0 | 0,014 | 0,7 h | — | — |
| 1x VHS Sharpen | 12,88 | 0,569 | 19,58 | 0,79 | −6,45 | 16,96 | 848 h | ~67 Mo | CC-BY-NC-SA-4.0 ; données non trouvées |
| 1x BaldrickVHSFix | 19,46 | 0,620 | 14,48 | 0,55 | +0,13 | 16,63 | 831 h | ~67 Mo | idem |
| 2x VHS upscale and denoise Film | 17,99 | 0,535 | 15,24 | 1,47 | −1,34 | 17,99 | 900 h | ~67 Mo | idem |
| Real-ESRGAN x4plus seul (ONNX) | 20,68 | 0,723 | 11,65 | 0,35 | +1,35 | 18,84 | 942 h | ~67 Mo | BSD-3-Clause ; DIV2K « academic research purpose only » |
| rendu « au plus fort » (pré-filtres + Real-ESRGAN) | 19,49 | 0,722 | 13,90 | 0,42 | +0,16 | 17,17 | 858 h | idem | idem |

Les trois modèles VHS sont des ESRGAN 64nf 23nb, environ 16,6 millions de paramètres, la même taille que Real-ESRGAN. F3 ramène les sorties x2 et x4 en 720×576 par moyenne de blocs et signale que ce lissage avantage le PSNR des modèles qui agrandissent.

Visages (2 zones) et texte (mire FFmpeg, hors références du banc), moyennes de F3 : « 2x VHS Film » est le seul dont le hf_rapport visage (3,93) dépasse l'image déjà bruitée (2,47). Real-ESRGAN monte le PSNR visage à 23,03 et le SSIM à 0,915, avec un hf_rapport de 0,36 (détails fins en moins). VHS Sharpen tombe à 13,21 dB sur le visage et 11,31 dB sur le texte.

Verdict provisoire : les trois modèles VHS ne se rapprochent pas de l'origine mieux que la chaîne, pour un temps CPU d'environ 850 à 900 h par film de 2 h, sous CC-BY-NC-SA, avec des films du commerce dont la licence d'entraînement n'a pas été trouvée. Real-ESRGAN seul est le plus proche en PSNR, SSIM et ΔE sur ce banc, et le plus lisse ; ses données DIV2K sont limitées à la recherche académique, cas que la demande demande d'écarter pour un nouveau modèle.

## 6. Recommandation provisoire

Ces trois essais ne suffisent pas à décider : cinq images, une dégradation synthétique, des machines partagées, aucun extrait de cassette, et un écart de 0,1 à 1,8 dB selon que FFmpeg est en 6.1 ou en 7.

En l'état des chiffres publiés : ne rien faire entrer dans `vhs_restore`. IAT s'éloigne de l'origine. Aucun juge ne choisit mieux qu'un débruitage fixe sans netteté `cas`. Les modèles VHS d'OpenModelDB coûtent le même temps CPU que Real-ESRGAN sans le même rapprochement, avec une licence non commerciale et des données d'entraînement non établies.

À revoir seulement si de vrais extraits sont fournis, sur une machine au repos, avec un seul FFmpeg (7.1, celui de F1, F2 et F3). D'ici là, la chaîne « Bien nettoyé, naturel » reste le point de comparaison le moins coûteux (environ 0,01 s/image, film de 2 h en moins d'une heure de calcul d'après le chronométrage de F3).
