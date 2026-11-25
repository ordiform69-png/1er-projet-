# Rapport n°15 pour Claude

Branche `grok/estimation`, partie de `ccr-5856e8d6-8xt8uh` au commit `c25f265`.
Ni fusion, ni pull request. Un commit par chantier ; le point 1 a d'abord été poussé incomplet (`065513f`), puis complété par-dessus, sans réécrire l'historique.

## Où

| Commit | Chantier |
|---|---|
| `78d2e33` | 2. Harmoniques du ronflement |
| `4d6472a` | 3. Aide « Ce que le logiciel ne peut pas faire » |
| `065513f` | 1. Première version : durée et place (résumé et ligne d'état seulement) |
| `7b418aa` | 1. Complété : phrase à côté de « Lancer », place, outils manquants |
| `249cedc` | 3. Le profil « Maximum » s'affiche « Au plus fort » |
| ce fichier | Rapport |

## Fait

1. **Durée avant de lancer.** L'aperçu (10 s, les mêmes réglages, preset `veryfast`) chronomètre seulement l'export restauré, pas la comparaison (`PreviewResult.restauration_s`). Ce temps est rapporté à la durée gardée : début, fin, et passages enlevés. Phrase : « Environ 2 heures sur cet ordinateur. Vous pouvez faire autre chose pendant ce temps. » Elle est à l'étape « Vérifier et lancer », et en réglages libres à côté de « Lancer la restauration ».

   Place : `pipeline.disk_needs`, fichier final et temporaires s'ils sont sur le même disque, marge 1,1 comme le contrôle déjà en place. « Il faut environ 6 Go ; il en reste 120 Go dans le dossier choisi. » S'il manque de la place : « Il manque de la place… », avant de lancer.

   Outils : si le profil voulait QTGMC sur une vidéo entrelacée et qu'il n'est pas installé : « Le désentrelacement le plus fin n'est pas installé : un autre, un peu moins fin, sera utilisé. » Si le profil voulait l'IA et qu'elle n'est pas installée : « L'amélioration par intelligence artificielle n'est pas installée : elle ne sera pas utilisée. »

   La veille était déjà empêchée (`SetThreadExecutionState` dans `Worker.run`). La phrase de patience le dit : « Vous pouvez faire autre chose pendant ce temps. L'ordinateur ne se mettra pas en veille. » La même phrase est au point 3 de « Aide ».

2. **Ronflement.** Les deux encoches (fondamentale et double) deviennent quatre, seulement si 50 ou 60 Hz est choisi : 50/100/150/200 ou 60/120/180/240, toujours `bandreject` `t=q:w=30`. Rien par défaut. La voix à 300 Hz n'est pas dans ces encoches.

3. **Mots.** La clé reste `maximum`. Les fichiers gardent `_restaure_maximum`. À l'écran le nom est « Au plus fort », avec « Nettoyage fort, plus long » sous les images du rendu et sur la carte. Police des images figée à 11 pt pour que la ligne tienne à 150 %. Les cartes réduisent la police si la tuile est basse.

   « Aide » contient « Ce que le logiciel ne peut pas faire » : détail absent, tracking et bande abîmée, numérisation, couleurs estimées, textures inventées par l'IA.

## Interdit respecté

- Moteur de restauration inchangé, sauf les deux harmoniques (3× et 4×) du point 2. `pipeline.py` n'a reçu qu'un commentaire sur `restauration_s`.
- Aucune nouvelle dépendance Python.
- Aucun test affaibli : les textes attendus ont été mis à jour quand l'écran a changé (« Maximum » → « Au plus fort », phrase de patience).
- Pas de fusion, pas de pull request, pas d'étiquette de version.
- Vouvoiement. Les options sont nommées comme à l'écran.
- 1280 × 641, sans défilement horizontal, sans défilement vertical à 100 % et 125 % (vérifié sur l'assistant et l'écran libre).

## Vérifié

Python 3.12.15, PySide6 6.12, FFmpeg 7.0.2, `QT_QPA_PLATFORM=offscreen`.

Suite complète : **353 passed, 15 skipped, code 0**, en 2763,70 s (46 min 04 s).

Une passe précédente s'était arrêtée à 352 passed, 1 failed : `test_publication_apres_les_controles` ne trouvait pas `.github/workflows/vhs-restore-windows.yml` dans un clone partiel. Le fichier rétabli, ce test passe. Ce n'était pas une régression du code.

Avant cela, zone touchée : **42 passed, code 0** (5 min 10 s) — `test_estimation`, `test_son` (encoches et énergie), `test_assistant` (parcours, 1280 × 641 à 100/125/150 %, texte des tuiles à 150 %), `test_ecran_unique`, `test_guide_coupes`, `test_ergonomie`, `test_senior`.

Énergie (son de synthèse 50 + 150 + 200 + 300 Hz, encoches Q=30) : à 150 Hz et 200 Hz, baisse de plus de 12 dB ; à 300 Hz, écart inférieur à 1 dB (`78d2e33`).

## Mesures

Film de synthèse 720×576, 25 i/s, profil Équilibré, sans IA. L'aperçu restaure 10 s. L'export complet est en preset `medium` (l'aperçu est en `veryfast`). Pas de coefficient ajouté : l'estimation est donc un peu courte.

| Durée du film | Restauration des 10 s | Estimation | Export réel | Réel / estimation |
|---|---|---|---|---|
| 16 s | 2,97 s | 4,76 s | 5,68 s | 1,19 |
| 40 s | 3,17 s | 12,69 s | 13,73 s | 1,08 |

Sur ces courts métrages, l'écart vient surtout du preset, pas de la règle de trois. Sur une cassette de 2 h le même écart de preset reste ; le chiffre dit « environ ».

## Non testé

- Un vrai PC Windows, et la mise en veille réelle (`SetThreadExecutionState` n'est appelé que si `sys.platform == "win32"`).
- Une cassette de 2 ou 3 heures : les mesures ci-dessus sont des films de synthèse de 16 s et 40 s.
- QTGMC et Real-ESRGAN installés : les phrases « pas installé » sont couvertes par le test unitaire, pas par un outil vraiment présent.
- SmartScreen, et un vrai boîtier de numérisation.
