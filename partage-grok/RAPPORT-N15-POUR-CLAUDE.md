# Rapport n°15 pour Claude

Branche `grok/estimation`, partie de `ccr-5856e8d6-8xt8uh` au commit `c25f265`.
Ni fusion, ni pull request. La suite complète n'a pas été lancée (demandé : trop longue).

## Où

| Chantier | Commit |
|---|---|
| Branche vide, identique à `c25f265` | `c25f265` |
| 2. Harmoniques du ronflement | `78d2e33` |
| 3. Aide « Ce que le logiciel ne peut pas faire » | `4d6472a` |
| 1. Durée estimée, place disque, phrase de veille | ce commit (voir `git log -1`) |

## Fait

2. `audio_filters` : quand `audio_mains_hz` vaut 50 ou 60, encoches `bandreject` à 1×, 2×, 3× et 4× (150/200 Hz ou 180/240 Hz), `t=q:w=30`. Le reste de la chaîne n'a pas changé.

3. Fin de « Aide » (`show_welcome`) : cinq phrases, vouvoiement. « Maximum » n'a pas été renommé (l'assistant dit déjà « Le plus beau, plus long »).

1. L'aperçu chronomètre seulement `export` des 10 s (`PreviewResult.restauration_s`), pas la comparaison. L'estimation étend ce temps à la durée gardée (`passages_gardes` : début, fin, passages enlevés). Affichage :
- assistant : dans `self.resume` de « Vérifier et lancer », seulement après l'avant / après ;
- réglages libres : à la fin de la ligne `s_status`, qui commence toujours par « Aperçu prêt » ;
- rien à côté de « Lancer » (`note_lancer` non touché).
Place : `pipeline.disk_needs` (final + temporaire si le dossier temporaire est le même disque) et `shutil.disk_usage` du dossier de sortie. S'il manque de la place (marge 1,1, comme `check_disk_space`), la phrase commence par « Il manque de la place ».
La veille était déjà empêchée (`gui._keep_awake` dans `Worker.run`). Seule la phrase d'attente a changé : « L'ordinateur ne se mettra pas en veille. »
Outils manquants (QTGMC, IA) : non faits (facultatif).

## Vérifié

Python 3.12, `QT_QPA_PLATFORM=offscreen`, timeout 900 s par fichier. Code de sortie 0 partout.

| Fichier | Résultat |
|---|---|
| `tests/test_son.py` | 7 passed |
| `tests/test_tous_reglages.py` | 39 passed, 3 skipped |
| `tests/test_conseils.py` | 6 passed |
| `tests/test_bande.py` | 4 passed |
| `tests/test_senior.py` | 5 passed |
| `tests/test_guide_coupes.py` | 2 passed |
| `tests/test_estimation.py` | 3 passed |
| `tests/test_assistant.py` | 9 passed |
| `tests/test_ecran_unique.py` | 9 passed |
| `tests/test_etats_interface.py` | 4 passed |

`test_parcours_complet_d_un_film` vérifie la phrase dans le résumé et dans la ligne d'état, et que la fenêtre reste 1280 × 641. `test_chaque_etape_tient_a_1280_641` et `test_ecran_unique` (100, 125 et 150 %) restent verts. Aucun test assoupli.

## Mesures

Film de synthèse 60,0 s, 720×576, 25 ips, progressif, son 300 Hz, profil Équilibré, sans coupe. FFmpeg 7.0.2.

| | Secondes |
|---|---|
| Restauration seule de l'aperçu (10 s, preset `veryfast`) | 3,26 |
| Estimation (× 6) | 19,6 — phrase « moins d'une minute » |
| Export réel du film entier (preset `medium`) | 28,6 |
| Réel / estimation | 1,46 |

L'estimation est trop courte d'environ un tiers : l'aperçu est en `veryfast`, l'export en `medium`. Les mots (« moins d'une minute ») restent justes sur ce film court. Aucun coefficient n'a été ajouté pour compenser. Place calculée : environ 0,06 Go pour le fichier, 0 Go de temporaire (pas d'IA ni d'Analog Repair).

## Non testé

- Suite complète.
- Vrai Windows, et la mise en veille réelle (`SetThreadExecutionState` n'a pas été rejoué).
- Cassette de 2 ou 3 heures.
- Message si QTGMC ou l'IA manquent.
- Vrai boîtier de numérisation.

## Bloqué

Rien. Les copies locales ont disparu une fois en cours de route ; chaque chantier a été poussé dès qu'il tenait, pour ne pas rester seulement en local.
