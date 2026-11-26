# Recette des images de synthèse — agent B (calcul en haute précision)

Branche `grok/qualite-precision`. Aucun binaire : les commandes régénèrent les images.
Comparaison avec la méthode de l'agent E : `mesurer.py` et `METHODE.md` sur `grok/qualite`
(dossier `partage-grok/mesures-n17/`). Les deux recettes ne sont pas les mêmes.

## Ce qui est commun

- Taille PAL 720 × 576, 25 images par seconde, chroma 4:2:0 ou 4:4:4 selon la source.
- FFmpeg 6.1.1 (cette machine) et les filtres aussi présents dans FFmpeg 9.1.
- Le fichier livré reste H.264, `yuv420p`, 8 bits.
- Le film à trois scènes de l'agent E a été rejoué tel quel (`mesurer.py --phase avant`
  puis `--phase apres`, 1 run) pour comparer les marches et le temps sur SA recette.

## 1. Rampe du test `tests/test_precision.py` (la mesure qui tranche)

Ce n'est pas la rampe grise 16 bits de l'agent E. Une rampe déjà en 10 bits, pour que
les niveaux (`colorlevels`) voient plus de 8 bits. En 16 bits gris, la chaîne doit
d'abord passer en YUV : sur la recette E, ce passage mange presque tout le gain.

| Paramètre | Valeur |
|---|---|
| Taille | 720 × 576, une image (la rampe ne bouge pas) |
| Format | `yuv420p10le`, little-endian |
| Luma | colonne `x` : `180 + arrondi(x × 520 / 719)`, codes 10 bits |
| Chroma | U = V = 512 (neutre), plans 360 × 288 |
| Réglages | profil Fidèle, `denoise=None`, `despeckle=False`, `sharpen=0`, progressif, lumière +2 (gamma 1,2), noirs 0,2, blancs 0,75 |

Référence 8 bits, mêmes niveaux, gamma par `eq` :

```text
format=yuv420p,<colorlevels de la chaîne>,eq=contrast=1:saturation=1:gamma=1.2,format=yuv420p
```

Lecture : ligne 288 (centre), `format=gray`. Indicateurs : niveaux distincts, saut max
entre voisins, moyenne des sauts non nuls, moyenne de la ligne.

Mesuré ici : 117 niveaux, saut max 5, saut moyen 1,581, moyenne 125,18
→ 159 niveaux, saut max 2, saut moyen 1,152, moyenne 126,34.

## 2. Image ordinaire (moyennes à 1/255 près)

`testsrc2`, 320 × 240, 1 image, `format=yuv420p`, profil Équilibré, progressif,
résolution d'origine. Ancienne chaîne (`eq=contrast=1.04:saturation=1.08`) contre
`pipeline.filter_chain`. Moyennes R, V, B après `format=rgb24`.

Mesuré : écarts +0,022 / +0,011 / +0,031 (bien sous 1/255).

Même image avec niveaux 0,2–0,75 et lumière +2 (niveaux en `gbrp16le`) :
écarts +0,67 / +0,39 / +0,78, encore sous 1. Sur `mandelbrot` 320 × 240 très saturé,
le canal vert bouge de +2,1 : la moyenne d'une image ordinaire tient, pas celle
d'une fractale.

## 3. Temps

Clip `testsrc2=s=720x576:r=25:d=4,format=yuv420p`, libx264, preset `medium`, crf 18,
profil Équilibré progressif. Ancienne chaîne contre la nouvelle.

Mesuré : 0,84 s → 0,96 s, soit +14 % (plafond +25 %). Le fichier écrit est
`h264` / `yuv420p`.

## 4. Recette de l'agent E, rejouée telle quelle

Script `mesurer.py` sur `grok/qualite` (non recopié ici). Films régénérés dans `/tmp`.

Rampe : 720 × 576, 4 s, 25 im/s, `gray16le` dans du FFV1, Y linéaire de 48/255 à 176/255
(`ymin = arrondi(48 × 65535 / 255)`, pas `x / 719`). Profil Fidèle nu, lumière +2.
L'analyse ne pose pas de `colorlevels` sur cette rampe : la chaîne d'avant était
`eq=contrast=1:saturation=1:gamma=1.2`. Après : `format=yuv420p10le` puis `lutyuv` gamma.

| Lecture | Avant | Après |
|---|---|---|
| Niveaux distincts, avant x264 | 107 | 108 |
| Saut max | 2 | 2 |
| Saut moyen non nul | 1,162 | 1,150 |
| Y | 66–191 | 66–191 |
| MP4 livré, niveaux / saut max / saut moyen | 107 / 2 / 1,152 | 107 / 2 / 1,117 |

Film 32 s (8 + 16 + 8), trois `testsrc2` 720 × 576 concaténés en FFV1, Équilibré,
`medium`, crf 18, progressif, sans son. Temps d'horloge : 9,770 s → 9,834 s
(+0,7 %, 18,32 → 18,44 s de calcul par minute de film). Les moyennes RVB des scènes
bougent de moins de 1 niveau. Le FFV1 de synthèse est en 4:4:4 : la chaîne monte
donc en `yuv444p10le`, pas en `yuv420p10le`.

## En quoi les recettes diffèrent

| | Agent E | Agent B (test) |
|---|---|---|
| Rampe | gris 16 bits, 4 s, Y 48–176/255, pas d'analyse de niveaux utile | YUV 10 bits, 1 image, Y 180–700, niveaux forcés 0,2 / 0,75 |
| But | comparer avant / après sur un fichier fixe | prouver le gain quand les niveaux restent au-dessus de 8 bits |
| Image « ordinaire » | le film à 3 scènes (dominantes) | `testsrc2` 320 × 240, écart de moyennes |
| Temps | 32 s, 3 runs prévus (1 run rejoué ici) | 4 s, une paire avant / après |

Le gain net (159 niveaux au lieu de 117, saut max 2 au lieu de 5) n'apparaît que
sur la rampe 10 bits avec niveaux. Sur la rampe 16 bits de l'agent E, le gamma seul
ne gagne qu'un niveau : `eq` avait déjà quantifié presque toute la courbe.
