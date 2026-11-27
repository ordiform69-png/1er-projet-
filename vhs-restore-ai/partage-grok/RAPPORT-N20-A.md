# Rapport n°20 — agent A : films longs, raccords, son et image

Branche `grok/bugs-a-temps`. Aucune modification dans `vhs_restore/`.

FFmpeg utilisés pour les mesures :

- `6.1.1-3ubuntu5` (`/usr/bin/ffmpeg`)
- `n7.1.5-1-g7d0e842004-20260630` (binaire statique GPL, 7.1.5 plus un commit)

Film de la recette : 60 min, 320×240, 25 i/s, image blanche une image sur 250 (toutes les 10 s, y compris 0) et bip de 1 kHz pendant 20 ms au même instant. Profil Nettoyage léger, préréglage ultrafast. Restauration en une fois et par parties de 10 min.

## Ce qui tient

- **En une fois et par parties, même nombre d'images.** 90 000 images, durée 3600,000 s, son décodé de 172 800 000 échantillons (exactement 3600 s). FFmpeg 6.1.
- **Le raccord de 10 min ne décale pas l'image.** Image n° 14 999, 15 000 et 15 001 : écart moyen 0 entre la passe unique et les parties. FFmpeg 6.1.
- **Le décalage du son ne grandit pas avec les parties de 10 min.** Le bip de 10 s et celui de 3590 s sont au même écart (+24 ms) dans les deux exports. FFmpeg 6.1. Une partie de 600 s avec chauffe, sous FFmpeg 7.1.5 : 15 000 images, 600,000 s d'image et de son (le trou d'une image de `-frames:v` seul ne se reproduit plus quand la cadence constante est demandée).

## Constats

### 1. Bloquant — les passages enlevés font prendre du retard au son

- **Où :** `pipeline.py:1410` (`_export_morceaux` appelle `_concat_sans_recompression`, qui copie l'AAC).
- **Scénario :** huit à douze coupes d'une seconde sur un film de 12 s, avec un bip à chaque seconde. Profil Nettoyage léger.
- **Preuve : PROUVÉ.** Bips lus après restauration, les deux FFmpeg :
  - 6.1.1 : 0,024 s, 1,028 s, 2,030 s, …, 11,054 s au lieu de 0, 1, 2, …, 11.
  - 7.1.5 : la même suite, dernier bip à 11,054 s.
  - Le premier bip a déjà 24 ms de retard (filtre, constat 2). Le dernier en a 54 ms. Le surplus dû aux raccords est de 30 ms après 12 coupes, soit environ 3 ms par raccord. Les deux versions.
- **Correction proposée :** assembler le son des passages comme `_assembler_parties` (le couper à la durée de l'image, puis un seul AAC), au lieu de copier les AAC les uns derrière les autres.

### 2. Gênant — le nettoyage du son retarde l'image de 24 ms, du début à la fin de l'heure

- **Où :** `pipeline.py:284` (`afftdn` dans `audio_filters`, profil Nettoyage léger).
- **Scénario :** le film d'une heure de la recette, restauré en une fois, puis par parties de 10 min.
- **Preuve : PROUVÉ.**
  - FFmpeg 6.1, 60 min : images blanches à 0,000 s, 10,000 s, …, 3590,000 s. Bips à 10,024 s, 20,024 s, …, 3590,024 s. Écart 24 ms au début comme à la fin, en une fois et par parties. Le nombre d'échantillons décodés est exact (le son est décalé, les 24 dernières millisecondes du film sont donc coupées).
  - FFmpeg 7.1.5, film de 20 s, même profil : bips à 0,024 s et 10,024 s.
  - Sans « Restaurer le son », les bips restent à 0,000 s et 10,000 s : ce n'est pas le délai de l'AAC.
- **Correction proposée :** compenser la latence mesurée d'afftdn (24 ms) en avançant le son, et prolonger la fin d'autant pour ne pas la couper.

### 3. Bloquant — une dérive inférieure à 6 ms par minute n'est pas corrigée

- **Où :** `pipeline.py:199` (`_atempo_chain` abandonne un facteur à moins de 0,0001 de 1). Le seuil de `pipeline.py:193` écarte déjà tout ce qui est sous 0,5 ms/min.
- **Scénario :** le son prend 5 ms de retard par minute. On demande cette correction. Film de 3 h.
- **Preuve : PROUVÉ.** `_atempo_filters` renvoie une liste vide pour 0,4, 0,5, 1, 5 et 5,9 ms/min. À 6 ms/min, `atempo=1.000100` apparaît. Sans filtre, le retard reste entier : 5 ms/min × 180 min = 900 ms à la fin d'un film de 3 h. À 0,4 ms/min, le premier seuil laisse 72 ms.
- **Correction proposée :** appliquer atempo dès que le retard accumulé sur la durée du film dépasse quelques millisecondes, au lieu d'un écart relatif fixe de 0,0001.

### 4. Gênant — le profil Bien nettoyé efface le son du premier instant

- **Où :** `pipeline.py:272` puis `283` et `285` (adeclick, afftdn et dynaudnorm enchaînés).
- **Scénario :** film de 12 s, bip à 0 s et à 10 s, profil Bien nettoyé.
- **Preuve : PROUVÉ.** FFmpeg 6.1, bips après restauration : seulement 10,024 s. Le bip à 0 s n'est plus là. Chacun des trois filtres seul le garde (afftdn le décale à 0,026 s, adeclick à 0,014 s, la normalisation le laisse à 0,000 s). FFmpeg 7.1.5 : le test du même film de 12 s échoue de la même façon (aucun bip dans les 20 premières millisecondes).
- **Correction proposée :** ne pas laisser adeclick traiter l'attaque du film avant afftdn, ou retarder l'image de la même latence que cette chaîne.

## Non retenu

Le trou d'une image avec `-frames:v` seul (FFmpeg 7.1, 499 images et 19,960 s) ne se reproduit pas sur une partie quand `-fps_mode cfr` et `-r` sont posés : 15 000 images et 600,000 s mesurés avec FFmpeg 7.1.5. Ce n'est pas un constat ouvert.
