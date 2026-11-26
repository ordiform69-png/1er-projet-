# Méthode de mesure — demande n°17 (qualité de restauration)

Script : `mesurer.py`. Aucune dépendance nouvelle, aucun changement du moteur
ni des tests. Les films de synthèse sont régénérés à chaque exécution, avec des
recettes figées dans le script, pour que la mesure « après » (même commande,
`--phase apres`) soit comparable point par point à la mesure « avant ».

```bash
# depuis n'importe quel répertoire, avec le vhs_restore du dépôt dans le PYTHONPATH
# (le script l'ajoute tout seul s'il reste à cet emplacement)
python3 vhs-restore-ai/partage-grok/mesures-n17/mesurer.py --phase avant
python3 vhs-restore-ai/partage-grok/mesures-n17/mesurer.py --phase apres
```

Les fichiers vidéo restent dans `/tmp/mesures-n17/<phase>/` (non versionnés).
Les résultats bruts (JSON, CSV, texte) sont écrits dans ce dossier.

La demande n'a pas fourni d'outil de mesure : cette méthode reprend les films
décrits pour les agents A et B, et les mêmes limites de correction que le
moteur actuel (`safe_levels`, `safe_gains`, niveaux à moitié).

## 1. Écart à la cible par scène (agent A)

Film PAL 720 × 576, 25 im/s, FFV1, sans son, trois scènes (8 s + 16 s + 8 s = 32 s).
L'aperçu à 20 s tombe dans la scène 2 (intervalle 8–24 s). Les trois morceaux sont
assemblés par le filtre FFmpeg `concat` en une seule piste FFV1 continue, comme un
fichier réel. Le démultiplexeur `concat` (copie sans réencodage) a été écarté : sur
ce montage, l'analyse du moteur (`-frames:v 600`) sautait la scène 2 et ne lisait
que 400 images (scènes 1 et 3), ce qui faussait la correction unique.

Les mesures par scène utilisent le filtre `trim` (précis à l'image, que le fichier
soit FFV1 ou H.264). Un `-ss` en option de sortie combiné à `-frames:v` reste coincé
au début du fichier sur ce FFV1.

| Scène | Intervalle | Contenu | Recette lavfi (figée) |
|---|---|---|---|
| 1 | 0–8 s | sombre et orangée | `testsrc2=size=720x576:rate=25,setsar=16/15,colorchannelmixer=rr=1.20:gg=0.92:bb=0.55,colorlevels=romin=0.16:gomin=0.16:bomin=0.16:romax=0.48:gomax=0.48:bomax=0.48` |
| 2 | 8–24 s | normale | `testsrc2=size=720x576:rate=25,setsar=16/15` |
| 3 | 24–32 s | claire et bleutée | `testsrc2=size=720x576:rate=25,setsar=16/15,colorchannelmixer=rr=0.55:gg=0.92:bb=1.20,colorlevels=romin=0.52:gomin=0.52:bomin=0.52:romax=0.90:gomax=0.90:bomax=0.90` |

Vérifié à l'écriture : l'analyse isolée conseille `levels` + `cast` sur les scènes 1 et 3, et rien sur la scène 2.

Pour chaque scène, trois mesures au milieu de la scène (8 images, médiane de `signalstats`, moyenne RVB comme `probe.rgb_mean`) :

1. **source** — le film avant restauration ;
2. **unique** — le film restauré avec *une* correction calculée sur le film entier (`analyze` + `advise` + `apply`), c'est le comportement actuel du moteur ;
3. **oracle** (cible équitable pour l'agent A) — la *même* correction (mêmes `safe_levels`, `safe_gains`, niveaux à moitié), mais mesurée et appliquée à la scène seule.

Réglages de cette mesure (pour isoler lumière et couleurs) : profil Fidèle (`fidele`) sans débruitage ni netteté ni grains, `scan=progressive`, `restore_audio=False`, `preset=ultrafast`, `crf=18`, résolution source, pas d'IA ni de stabilisation. Les réglages utilisateur (lumière, contraste, couleurs, teinte) restent à 0.

Indicateurs : YLOW, YHIGH, ouverture (YHIGH − YLOW), YAVG, moyennes R, G, B et leur étendue (`span_rgb`), écart chroma `|U−128| + |V−128|`.

Deux écarts sont reportés :

- **unique vs oracle** — c'est la cible de l'agent A (« chaque scène corrigée vers la cible mieux qu'avec la correction unique ») ;
- **unique vs idéal** — repère TV ouvert (YLOW = 16, YHIGH = 235, span RVB = 0, chroma = 0). Ce n'est pas ce que le moteur vise aujourd'hui (niveaux à moitié, plafonds `safe_*`).

Note sur l'échantillon du moteur : pour un film de moins de 60 s, `analyze` commence à t = 0 et lit `IDET_FRAMES` (600) images, soit 24 s ici (scènes 1 et 2 pour les niveaux, dont la médiane). La dominante est mesurée sur 8 images au début (scène 1 seulement). C'est le comportement réel du moteur, pas un choix de cette mesure. Conséquence typique sur ce film : la plage médiane 1+2 est déjà « ouverte », donc pas de conseil `levels` pour le film entier, alors que les scènes 1 et 3, isolées, en ont un ; le conseil `cast` suit uniquement la dominante de la scène 1 et s'applique à tout le film.


Sur ce film, à la mesure « avant » (base `4f09073`) :

- l'analyse du film entier conseille seulement `cast` (la médiane des niveaux
  sur 24 s, scènes 1+2, est déjà ouverte : YLOW=41, YHIGH=209) ;
- la scène 1 isolée conseille `levels` + `cast`, mais `safe_levels` élargit la
  plage jusqu'à un `lo` < 0,02, et `_levels_filter` n'émet alors pas de
  `colorlevels` : l'oracle de la scène 1 se confond avec la correction unique ;
- la scène 3 isolée a bien `levels` + `cast` (gains inverses). C'est surtout
  là que la correction unique s'écarte de la cible (dominante orangée de la
  scène 1 appliquée à une scène déjà bleue, niveaux non ouverts).

## 2. Marches dans les dégradés (agent B)

Rampe de gris horizontale, 720 × 576, 25 im/s, 4 s, encodée FFV1 en 16 bits (`gray16le`). Chaque colonne a une luminance distincte, répartie linéairement entre Y = 48/255 et Y = 176/255 (plage qui déclenche le conseil « niveaux »).

Restauration : mêmes réglages « nu » que ci-dessus, plus les conseils de l'analyse de la rampe, plus le cran lumière = 2 (gamma = 1,2) qui passe aujourd'hui par le filtre `eq` en 8 bits — c'est la chaîne « niveaux + gamma » demandée à l'agent B.

Quatre lectures de la ligne centrale (ligne 288, paire, compatible 4:2:0) :

- source 16 bits (valeurs 0–65535) — contrôle : 720 niveaux, saut d'environ (176−48)×257/719 ;
- source simplement divisée en 8 bits (`// 257`, sans tramage) — plancher d'une conversion naïve ;
- après la chaîne de filtres, avant x264 (image `gray` brute) — isole le moteur de l'encodeur ;
- fichier livré (MP4 H.264 8 bits, `crf=18`, `yuv420p`) — ce que reçoit l'utilisateur.

Indicateurs : nombre de niveaux distincts, saut maximal entre voisins, saut moyen des sauts non nuls, min/max. La ligne brute (720 échantillons) est conservée dans `rampe-ligne-<phase>.csv` pour une comparaison point par point.

## 3. Temps de restauration par minute de film

Même film à 3 scènes (32 s). Réglages typiques d'une restauration, pas le profil « nu » :

- profil Équilibré (`equilibre`, débruitage et netteté du profil) ;
- `scan=progressive`, résolution source, `preset=medium`, `crf=18` ;
- pas d'IA, pas de stabilisation, pas de son, `denoise_hq=False` ;
- conseils du film entier appliqués (niveaux et dominante, comme un utilisateur qui coche « Appliquer les conseils »).

Trois runs d'horloge (`time.perf_counter` autour de `pipeline.export`). On retient la **médiane**. Le chiffre reporté est en **secondes de calcul par minute de film** : `durée_horloge / 32 × 60`. Le matériel (processeur, cœurs, RAM, OS, version de FFmpeg et de Python) est enregistré dans les résultats, parce que le plafond « au plus +25 % » de l'agent B n'a de sens que sur la même machine, avec la même commande.

## Fichiers produits

| Fichier | Contenu |
|---|---|
| `resultats-<phase>.json` | Tout, y compris chaînes de filtres et analyses |
| `resultats-<phase>.txt` | Résumé lisible des chiffres |
| `resultats-<phase>-scenes.csv` | YLOW/YHIGH/RVB/chroma par scène et par étape |
| `resultats-<phase>-degrades.csv` | Niveaux distincts et sauts |
| `resultats-<phase>-temps.csv` | Chaque run et la médiane |
| `rampe-ligne-<phase>.csv` | 720 valeurs de la ligne centrale |
