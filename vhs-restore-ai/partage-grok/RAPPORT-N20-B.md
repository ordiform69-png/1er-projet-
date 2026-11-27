# Rapport n°20 — agent B (image, d'une image à l'autre)

Branche `grok/bugs-b-image`, à partir de `1abf947`. Aucune modification dans `vhs_restore/`.
La correction scène par scène reste désactivée (`scenes.ACTIF = False`) : elle n'est pas re-signalée.
`scenes.filtres` renvoie `None`, la chaîne ne contient pas de `sendcmd`.

Film utilisé pour la couleur et la lumière : la recette de la demande (plan mobile, sinus de lumière,
bruit, `interlace`, `yuv422p`, `setsar=16/15`), avec une vraie coupure `concat` vers un second plan
(autre teinte, autre sens). Durée ramenée à 2 s par plan : le graphe de filtres est celui de la
demande. Mesures sur FFmpeg 6.1.1.

Quatre constats, du plus gênant au moins gênant. Les quatre sont prouvés par
`tests/test_bugs_n20_b.py` (`xfail`, strict).

## 1. Le scintillement tire la couleur du plan suivant — gênant — PROUVÉ

**Où.** `vhs_restore/pipeline.py`, lignes 580-581 (`deflicker=size=5:mode=pm` dans `pre_filters`).

**Scénario.** Pellicule transférée sur vidéo, case « Réduire le scintillement lumineux », profil
Bien nettoyé. Deux plans de la recette collés par `concat`. La fenêtre de 5 images est centrée :
les quatre images avant la coupure voient déjà le plan suivant.

**Preuve.** Moyennes RVB des quatre images avant la coupure (25 i/s, une image par image source) :

| | sans scintillement | avec scintillement |
|---|---|---|
| image −4 | 165,3 / 170,1 / 3,6 | 164,5 / 170,0 / 3,6 |
| image −3 | 165,3 / 170,1 / 3,6 | 162,6 / 168,9 / 3,6 |
| image −2 | 164,6 / 170,1 / 4,3 | 159,4 / 165,9 / 4,3 |
| image −1 | 164,7 / 170,1 / 4,3 | 156,3 / 161,6 / 4,3 |

Le vert passe de 170 à 162 avant la coupure (écart max 8,6 niveaux). Le plan d'après commence
ensuite vers 155 / 138 / 47. Même dérive sur un film progressif en profil Nettoyage léger
(bleu 10 → 28 sur les mêmes quatre images).

**Correction proposée.** Ne pas laisser la fenêtre de `deflicker` traverser une coupure (fenêtre
causale, ou couper le lissage quand la moyenne change d'un coup).

## 2. « Plus chaude » n'ajoute pas de rouge quand la dominante est au plafond — gênant — PROUVÉ

**Où.** `vhs_restore/pipeline.py`, lignes 564-572 (`_cast_filter`) et 429-430 (`safe_gains`,
plafond 1,18). L'aperçu, lui, ajoute la teinte après coup : `vhs_restore/lumiere.py`, lignes 44-45.

**Scénario.** Cassette verte. La correction de dominante est déjà au maximum autorisé
(rouge × 1,18, vert × 0,85, bleu × 1,10). L'utilisateur met Teinte sur +3 (« Plus chaude »).
Image jugée : une image de la recette (0,4 s), désentrelacée, avec une dominante verte.

**Preuve.** Moyenne du rouge :

- teinte 0 : 146,6
- teinte +3 dans le film : 146,6 (delta **0,0**) — le filtre reste `rr=1.1800`
- teinte +3 comme l'aperçu (`colorchannelmixer` ajouté sur l'image déjà plafonnée) : delta **+13,1**

Le bleu de cette image est déjà presque à zéro, donc le film ne change presque rien. L'aperçu
montre un visage plus chaud que le film ne le sera.

**Correction proposée.** Appliquer la teinte après le plafond de la dominante, sans la recouper
au même 1,18, pour que le film reçoive le même rouge que l'aperçu.

## 3. Un décalage de couleur de 4 px en déplace 8 — gênant — PROUVÉ

**Où.** `vhs_restore/pipeline.py`, lignes 594-597. Le nombre saisi est passé tel quel à
`chromashift=cbh=…:crh=…`. L'écran dit « px » (`gui.py`, suffixe du réglage).

**Scénario.** DVD 4:2:0, 720 × 576. Frontière verticale rouge | bleu. Réglage +4 px.
Le débruitage est retiré pour mesurer le décalage seul ; le filtre émis est celui de `filter_chain`.

**Preuve.** La frontière passe de la colonne 360 à la colonne 368 : **8 pixels d'image** pour
4 demandés. Même écart en 4:2:2 (capture) : un cran de chroma vaut deux pixels, parce que la
chroma est deux fois moins large. Le test déjà en place (`test_chroma.py`) annule un
`chromashift` du même nombre : il ne voit pas ce facteur deux.

**Correction proposée.** Passer en 4:4:4 avant `chromashift`, pour qu'un cran vaille un pixel d'image.

## 4. La bande du bas reste visible en Full HD — gênant — PROUVÉ

**Où.** `vhs_restore/pipeline.py`, lignes 641-650 (`_bottom_mask`). Le masque des côtés, lui,
est mis à l'échelle (`_edge_mask`, lignes 660-661). Le bas ne l'est pas.

**Scénario.** VHS 720 × 576, 16 lignes de commutation peintes en rouge sur une image de la recette
(0,4 s, désentrelacée). Export Full HD (1440 × 1080), « Masquer la bande du bas » = 16 lignes.

**Preuve.** 16 lignes de 576 font 30 lignes de 1080. La chaîne fait `crop=1440:1064` puis un
`pad` noir : seules les 16 dernières lignes sont noires. Les lignes −30 à −17 restent rouges,
moyenne R = **199,8**.

**Correction proposée.** Multiplier le nombre de lignes par la hauteur de sortie / 576, comme
le masque des côtés le fait déjà avec la largeur.

## Contrôles sans bug retenu

- Ordre des trames de la recette : `idet` donne 84 TFF et 0 BFF. Avec `bwdif` `parity=tff`,
  la moyenne paire et la moyenne impaire diffèrent de moins de 0,1 niveau.
- `lutyuv` contre `eq` sur une image de la recette (lumière +3, contraste et saturation du profil
  Bien nettoyé) : écart moyen inférieur à 0,5 niveau, maximum 4. Le réglage arrive.
- `colorlevels` en 10 bits sur FFmpeg 6.1.1 ne noircit pas l'image (écart d'environ 3 niveaux
  avec le passage en 16 bits). Le plafond décrit dans le commentaire ne se reproduit pas ici.
- `fftdnoiz` (débruitage haute qualité) ne mélange pas la moyenne des deux plans à la coupure.
