# Rapport n°17 pour Claude — qualité de restauration (agent E)

## Où

Dépôt : https://github.com/ordiform69-png/1er-projet-

| Référence | SHA | Note |
|---|---|---|
| Base `ccr-5856e8d6-8xt8uh` | `4f090734fd9cfa670d2be04fc6b372327474b7eb` | demandée, confirmée |
| `grok/qualite` après phase 1 | `fac1bb49ca3916f08d8089db911552b3f1f0bf70` | mesures « avant » recette E |
| + rampe 10 bits agent B (avant fusion) | `97f9a883966703d7928ea15a20eb5cdda322c593` | mesures « avant » recette B, même moteur 8 bits |
| A `grok/qualite-scenes` | `fe9fc2c56968f38270eb845cffbd5625e1c158ee` | tête annoncée, confirmée sur origin |
| Fusion A dans `grok/qualite` | `6fee476b5dc41696b4500091212b4c560981b80f` | `merge --no-ff`, aucun conflit |
| B `grok/qualite-precision` | `387ce994aff367717456c37795e9dc7bd11aae79` | tête annoncée, confirmée |
| Fusion B | `b824adad2886a60fee6a6116ada0475604d29ba9` | `merge --no-ff`, auto-fusion de `pipeline.py` relue |
| C `grok/qualite-numerisation` | `a18c10647a38b3eea01f78be97b1515cc9972d44` | tête annoncée, confirmée |
| Fusion C | `1d073eb77d7654643e1adb5403003101c2af36a3` | `merge --no-ff`, conflit `probe.py` résolu |
| Correctif test scènes (intégration A+B) | `786e68cc58dd5104676742b90dfa6e713dbb4949` | voir Fait / Vérifié |
| **Tête de `grok/qualite` (ce rapport)** | voir le commit de ce fichier | |

`grok/qualite-qtgmc` est à `0f37607cde9265dddbe0af0ca3230e0d7bbfcd6a` : **non fusionnée**.

Rien n’a été fusionné dans `ccr-5856e8d6-8xt8uh`. Pas de PR, pas de force-push. `estimation.py` : diff vide contre `4f09073` (calcul intact). Aucune nouvelle dépendance.

## Fait

1. **Mesure « avant » recette B**, sur la base 8 bits (`4f09073` / `fac1bb4`), *avant* de fusionner B, en plus de la rampe 16 bits déjà publiée. Script `partage-grok/mesures-n17/mesurer.py`, méthode dans `METHODE.md`. Les chiffres de la recette E (scènes, rampe 16 bits, temps) n’ont pas été écrasés.

2. **Fusions dans l’ordre A, B, C**, chacune en `--no-ff`, poussée tout de suite.

   - **A** : aucun conflit. `scenes.py`, branchement dans `pipeline.py` / `probe.py`, `_seek(..., video=False)` dans `assistant.py`.
   - **B** : Git a auto-fusionné `pipeline.py` (A et B le touchent). Relecture : les deux comportements sont présents. `pre_filters` garde la détection de scènes de A (`scenes.filtres`, paramètre `origine`) **et** le remplacement de `eq` par `lutyuv` plus `_monter_precision` de B. `post_filters` a la descente unique en 8 bits tramée. Aucune logique moteur ajoutée au-delà de cette relecture (rien à retoucher).
   - **C** : conflit dans `probe.py` seulement (`assistant.py` auto-fusionné, le `video=False` de A est conservé). Résolution : les champs `scenes` / `scenes_secondes` et l’appel `scenes.attacher` (A) **et** les champs / `measure_capture` de C sont tous conservés. `attacher` reste protégé par `try/except`. Pas d’autre logique ajoutée.

3. **Mesures « après »** sur les mêmes recettes, même matériel, 3 runs de temps (médiane). Résultats bruts versionnés (JSON, CSV, texte). Pas de capture, pas de zip, pas de vidéo dans le dépôt.

4. **Tests** : uniquement les 13 fichiers cités, un par un, `timeout 900`, `QT_QPA_PLATFORM=offscreen`. Un échec d’intégration A+B (chaîne `gamma=1.2` devenue `lutyuv`) : correctif trivial, justifié, assertion non supprimée. Relance : 11 tests passés. Les 12 autres fichiers étaient déjà verts.

5. Box en **FFmpeg 7.1.5** (A n’avait vérifié qu’en 6.1). Aucun échec attribué à la version de FFmpeg. La référence 8 bits de la rampe B donne exactement les chiffres publiés par B en 6.1 (117 niveaux, saut max 5, saut moyen 1,581, moyenne 125,18).

## Mesures

Matériel (avant et après) : Intel Xeon, 8 cœurs, 16 002 Mio RAM, Linux 6.12.113+, Python 3.13.5, FFmpeg 7.1.5-0+deb13u1. Mesures « avant » : 26 nov. 2026, 03:53 (recette E) et 04:22 (recette B) Europe/Paris (UTC+1). Mesures « après » : 26 nov. 2026, 04:29 Europe/Paris (UTC+1), SHA moteur `1d073eb` (le commit de test ensuite ne change pas le moteur).

### Écart à la cible par scène

Film identique : PAL 720×576, 25 im/s, 8+16+8 = 32 s, FFV1, recettes lavfi figées dans `mesurer.py` (A confirme un film d’essai identique). « Unique » = restauration du film entier (après fusion : correction par scène via `sendcmd`). « Oracle » = même logique appliquée à la scène seule.

| Scène | Étape | Avant (YLOW–YHIGH / span RVB / chroma) | Après |
|---|---|---|---|
| 1 sombre orangée | source | 56–109 / 17,93 / 9,57 | identique |
| 1 | unique | 45–102 / 1,05 / 0,42 | 45–102 / 1,65 / 0,71 |
| 1 | oracle | 45–102 / 1,05 / 0,42 | 45–102 / 0,85 / 0,33 |
| 2 normale | source | 41–209 / 7,13 / 3,96 | identique |
| 2 | unique | 29–209 / **11,93 / 8,95** | 29–224 / **6,81 / 4,78** |
| 2 | oracle | 41–210 / 6,53 / 4,03 | 41–210 / 6,53 / 4,03 |
| 3 claire bleutée | source | 140–189 / 22,47 / 13,22 | identique |
| 3 | unique | 139–191 / **59,80 / 36,96** | 125–196 / **2,51 / 1,12** |
| 3 | oracle | 125–195 / 1,44 / 0,63 | 125–195 / 1,22 / 0,20 |

La scène 3, qui recevait le contre-orange de la scène 1, rejoint la cible (span 59,8 → 2,5, près de l’oracle 1,2). La scène 2 n’est plus dégradée par cette dominante. La scène 1 était déjà proche de l’oracle (le filtre niveaux isolé reste bloqué par `safe_levels` / seuil 0,02, comme en phase 1).

### Marches dans les dégradés

**Recette E** (rampe gris 16 bits, 4 s, Y 48–176/255, lumière +2 ; l’analyse ne pose pas toujours `colorlevels`) :

| Lecture | Avant | Après |
|---|---|---|
| Après filtres, avant x264 | 123 niveaux, saut max 2, saut moyen 1,015 | 125 niveaux, saut max 1, saut moyen 1,0 |
| MP4 livré | 124 / 2 / 1,008 | 125 / 1 / 1,0 |

Gain faible, comme l’avait noté B : sur cette rampe le passage en YUV mange presque tout l’avantage.

**Recette B** (yuv420p10le, 1 image, Y 180–700, niveaux forcés 0,2/0,75, lumière +2) — c’est celle qui tranche :

| Lecture | Avant (moteur 8 bits) | Après (10 bits + lutyuv) |
|---|---|---|
| Référence 8 bits (`format=yuv420p` + colorlevels + eq) | **117 niveaux, saut max 5, saut moyen 1,581, moyenne 125,18** | identique (référence figée) |
| Chaîne moteur sur le 10 bits | **1 niveau, Y = 10** (colorlevels/eq sur 10 bits écrasent l’image) | **159 niveaux, saut max 2, saut moyen 1,152, moyenne 126,34** |
| MP4 livré (`pipeline.export`) | **1 niveau, Y = 10** | **156 niveaux, saut max 3, saut moyen 1,181, moyenne 126,37** |

Les chiffres « après » de la chaîne moteur recoupent ceux de B (159 / 2 / 1,152 / 126,34), y compris sous FFmpeg 7.1.5.

### Temps de restauration par minute de film

Même extrait 32 s, profil Équilibré, `preset=medium`, crf=18, scan progressif, résolution source, sans IA ni stab ni son, conseils du film appliqués. 3 runs, médiane.

| | Run 1 | Run 2 | Run 3 | Médiane | s / minute de film |
|---|---|---|---|---|---|
| Avant | 5,508 s | 5,322 s | 5,125 s | 5,322 s | **9,98 s** |
| Après | 29,042 s | 28,602 s | 26,239 s | 28,602 s | **53,63 s** |

Soit **+437 %** (facteur 5,37). Le plafond « au plus +25 % » de l’agent B portait sur *sa* chaîne seule (B a mesuré +14 % sur un clip de 4 s, et +0,7 % en rejouant la recette E sans A). Ici la fusion A+B ajoute `sendcmd`, des allers-retours 10/16 bits autour des niveaux, et une chaîne en `yuv444p10le` (le FFV1 de synthèse est en 4:4:4). Ce dépassement est un **point ouvert**, pas un échec de test.

## Vérifié

Tous les lancements : `timeout 900`, `QT_QPA_PLATFORM=offscreen`, pytest du venv, un fichier à la fois, 26 nov. 2026 vers 04:29–04:40 Europe/Paris (UTC+1). Suite complète **non** lancée.

| Fichier | Premier lancement | Code | Durée | Détail |
|---|---|---|---|---|
| `tests/test_scenes.py` | 1 failed, 10 passed | 1 | 74,9 s (74,31 s pytest) | `test_reglages_utilisateur_par_dessus` : la chaîne n’a plus `gamma=1.2` (eq), mais `lutyuv` avec exposant 0,83333333. Cause : fusion B, pas FFmpeg 7.1.5. |
| `tests/test_scenes.py` (après correctif) | 11 passed | 0 | 63,40 s | Même fichier, assertion mise à jour (sendcmd + gamma=1.2 **ou** lutyuv 0,83333333). Contrôle fonctionnel teinte inchangé. |
| `tests/test_niveaux.py` | 1 passed | 0 | 4,0 s (3,76 s) | |
| `tests/test_plafonds.py` | 2 passed | 0 | 4,4 s (4,20 s) | |
| `tests/test_dominante.py` | 1 passed | 0 | 7,8 s (7,57 s) | |
| `tests/test_pipeline.py` | 18 passed | 0 | 95,2 s (94,94 s) | |
| `tests/test_lumiere.py` | 10 passed | 0 | 37,8 s (37,32 s) | |
| `tests/test_precision.py` | 5 passed | 0 | 6,8 s (6,44 s) | |
| `tests/test_tous_reglages.py` | 39 passed, 3 skipped | 0 | 164,4 s (164,02 s) | |
| `tests/test_photo.py` | 9 passed | 0 | 13,7 s (13,34 s) | |
| `tests/test_numerisation.py` | 11 passed | 0 | 13,2 s (12,77 s) | |
| `tests/test_conseils.py` | 6 passed | 0 | 13,2 s (12,80 s) | |
| `tests/test_probe.py` | 12 passed | 0 | 18,2 s (17,88 s) | |
| `tests/test_assistant.py` | 9 passed | 0 | 112,3 s (111,75 s) | |

Après correctif : **134 tests passés, 3 ignorés, 0 échoué** sur les 13 fichiers. Aucun test affaibli (une assertion adaptée au nouvel spelling, justifiée dans `786e68c`).

## Non testé

- La suite complète (consigne : Claude la lance avant toute fusion dans la base).
- `tests/test_sources.py` et `tests/test_stabilisation.py` (touchés par B, **non cités** par la n°17).
- FFmpeg 6.1 et 9.1 : uniquement 7.1.5 sur cette box. Les tests d’A et de B passent ici ; A n’avait vérifié qu’en 6.1, sans échec lié à la version constaté.
- QTGMC (branche D, étude, non fusionnée).

## Bloqué

Aucun blocage de fusion ni de mesure. Points ouverts :

- **Temps +437 %** sur le film 32 s après intégration A+B+C, bien au-delà du +25 % demandé à B seul. À juger si un allègement (moins de conversions 16 bits, garder le 4:2:0, etc.) est souhaité avant fusion dans la base.
- Sur la scène 1, `safe_levels` pousse encore `lo` sous 0,02 : pas de `colorlevels` même en correction isolée (constat déjà fait en phase 1).
- Les recettes des agents n’étaient pas dans le dépôt en phase 1 ; A a confirmé un film d’essai identique, B a publié `recette-agent-B.md`. Les deux ont été mesurées.

Résultats bruts : `vhs-restore-ai/partage-grok/mesures-n17/` (`resultats-avant*`, `resultats-apres*`, `rampe-ligne-*`, `mesurer.py`, `METHODE.md`, `recette-agent-B.md`).

---

## Corrections

Vérification et refusion de `grok/qualite-scenes` @`3968865` (26 nov. 2026, à partir de 05:12 Europe/Paris, UTC+1). Le texte suivi est `DEMANDE-GROK-BUILD-17-CORRECTIONS.md` sur `ccr-5856e8d6-8xt8uh` @`fed2275`. Écarts avec le résumé d’instruction : le document précise davantage les films de temps (720 × 576 entrelacé, son, 60 s, FFV1 4:2:2 et MPEG-2 4:2:0, sombres et peu contrastés, niveaux actifs) ; c’est cette méthode qui a été appliquée. Les seuls tests cités par les corrections sont `tests/test_scenes.py`, plus `test_assistant.py` et `test_lumiere.py`.

### Fusion

| Référence | SHA |
|---|---|
| Tête `grok/qualite` avant cette fusion | `6fa61dbc30534323d46a57cebb45b2c4583808ff` |
| A `grok/qualite-scenes` (annoncé, confirmé sur origin) | `3968865ec4b16749e384f1015b3979d02e8fa8e2` |
| Fusion `--no-ff` (poussée tout de suite) | `84203b7e23196a9ac86d1f44ef5a02c87591cb6f` |
| **Tête après ce rapport** | le commit qui ajoute cette partie |

Le commit `3968865` (par rapport à `fe9fc2c`) touche bien `scenes.py`, `gui.py`, `assistant.py`, `lumiere.py`, `probe.py`, `tests/test_scenes.py`, et ajoute `DEMANDE-GROK-BUILD-17-CORRECTIONS.md`. **Ni `pipeline.py` ni `estimation.py`** dans ce commit. Après fusion, `git diff 6fa61db HEAD -- pipeline.py estimation.py` est vide.

Conflit uniquement dans `probe.py` :

- Champs : `scenes_secondes` (libellé de A) et `scenes_vues` de A, **et** les champs de numérisation de C, conservés.
- Fin de `analyze()` : `measure_capture` de C est conservé ; l’appel bloquant `scenes.attacher` (introduit à la première fusion de A) est **retiré**, remplacé par le commentaire de A (« les scènes se lisent ensuite, en arrière-plan »). C’est le cœur de la correction n°1.

`assistant.py` et `test_scenes.py` ont été auto-fusionnés.

### Correctif `786e68c` (test_scenes.py)

A n’a **pas** modifié `test_reglages_utilisateur_par_dessus` (seulement d’autres tests, et l’ajout du film de Claude). La fusion a donc conservé le correctif d’intégration A+B : l’assertion accepte `gamma=1.2` (eq) **ou** `lutyuv` avec l’exposant `0,83333333`. Ce correctif **reste nécessaire** (B est toujours dans `grok/qualite`). Il n’affaiblit pas le test (le contrôle « teinte plus chaude » est intact). Les 13 tests de `test_scenes.py` passent avec ce texte.

### Film de Claude — mesure réelle

Recette identique au graphe des corrections (FFV1, `yuv422p`, 60 s). Mesuré le 26 nov. 2026 vers 05:20 Europe/Paris, SHA `84203b7`, après `analyze()` puis `scenes.attacher` (l’ouverture seule ne remplit plus les scènes : 0 scène, `scenes_vues=False`).

- 3 scènes : [0,00–20,00], [20,00–40,00], [40,00–60,00]
- Coupures : **20,0 s** et **40,0 s** (écart 0,0 s, dans ± 0,4 s)
- Gains `scenes._valeurs` (même porte que le test de A, `level_black=0,2`, `level_white=0,8`) sur la scène normale (20–40 s) : **rr=1,0000  gg=1,0000  bb=1,0000**
- Annonce de A confirmée.
- Durée de `attacher` sur ce film : 6,45 s.

Brut : `partage-grok/mesures-n17/resultats-corrections-film-claude.txt`.

Lecture des scènes, chiffres de A (commit `3968865`, film de Claude 60 s FFV1 4:2:2) : 8,79 s à 5 i/s et 8,72 s à 2 i/s (le décodage ne saute pas d’images : 5 i/s conservé) ; ouverture seule sans les scènes : 11,5 s. Sur cette box, `attacher` a pris 6,45 s (même film) ; l’ouverture (`analyze`) d’un FFV1 4:2:2 de 60 s sombre a pris 4,8 s.

### Temps de restauration (méthode de Claude)

Films figés, 720 × 576, entrelacé TFF, son, 60 s, sombres et peu contrastés (Y 68–121, conseil `levels`, `colorlevels` présent dans la chaîne). Profil Équilibré, `preset=medium`, crf=18, désentrelacement bwdif. 3 passages, médiane. Horloge autour de `pipeline.export` seulement (`analyze` et `attacher` notés à part). Même machine, FFmpeg 7.1.5.

Avant : base `4f09073` (copie isolée). Après : `84203b7`.

| Film | Avant (médiane) | Après (médiane) | Écart |
|---|---|---|---|
| FFV1 4:2:2 | 19,090 s (runs 19,090 / 19,234 / 18,478) | 18,486 s (18,382 / 18,515 / 18,486) | **−3 %** |
| MPEG-2 4:2:0 | 15,023 s (15,016 / 15,181 / 15,023) | 17,268 s (17,771 / 16,329 / 17,268) | **+15 %** |

Niveaux actifs dans les quatre chaînes. Après fusion, un seul plan détecté (lumière uniforme), donc pas de `sendcmd` ici — c’est bien le coût 10 bits + niveaux sur une capture 4:2:2 / 4:2:0, pas le film d’essai 4:4:4.

Les +437 % du rapport initial ne se reproduisent pas, comme l’avait mesuré Claude (chez lui : 32,7 → 37,0 s soit +13 % en FFV1 4:2:2 ; 27,7 → 29,3 s soit +6 % en MPEG-2 4:2:0). Les durées absolues diffèrent (autre machine), l’ordre de grandeur de l’écart est le même. Rien à corriger de ce côté.

Bruts : `resultats-corrections-temps-avant.*`, `resultats-corrections-temps-apres.*`, script `mesurer_temps_claude.py`.

### Tests

Uniquement les fichiers demandés par les corrections, un par un, `timeout 900`, `QT_QPA_PLATFORM=offscreen`, 26 nov. 2026 vers 05:20–05:23 Europe/Paris (UTC+1), tête `84203b7`. Suite complète non lancée.

| Fichier | Résultat | Code | Durée |
|---|---|---|---|
| `tests/test_scenes.py` | 13 passed | 0 | 60,4 s (59,77 s pytest) |
| `tests/test_assistant.py` | 9 passed | 0 | 63,3 s (62,91 s) |
| `tests/test_lumiere.py` | 10 passed | 0 | 14,1 s (13,76 s) |

32 tests passés, 0 échoué, 0 ignoré. Aucun test affaibli, aucun correctif supplémentaire.

### Non testé (cette passe)

- Suite complète.
- Les autres fichiers de la n°17 (déjà lancés avant ces corrections, non redemandés).
- FFmpeg 6.1 et 9.1 (box en 7.1.5). Aucun échec lié à la version.

### Bloqué (cette passe)

Aucun. Le point ouvert « temps +437 % » du rapport initial est levé pour les films proches d’une vraie capture (4:2:2 / 4:2:0). Il reste spécifique au film d’essai 4:4:4 de la phase 1, qui n’est pas représentatif.
