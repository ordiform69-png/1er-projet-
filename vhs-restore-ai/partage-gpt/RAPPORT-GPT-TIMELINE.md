# Timeline de VHS Restore AI

## Où

Dépôt `ordiform69-png/1er-projet-`, branche `gpt/timeline`, base `dc85695` sur
`ccr-5856e8d6-8xt8uh`.

| Commit publié | Sujet |
|---|---|
| `87f342c` | Zoom et navigation au clavier |
| `0fc326a` | Passages vides et repères de scène |
| `163e271` | Poignées, heure au survol et hachures |
| `4fa32c2` | Cache des vignettes par film et largeur visible |
| `2a643f6` | Tests ciblés, réinitialisation du cache et actualisation des repères |
| `2d9edb4` | Test du retrait explicite dans le parcours complet |

Aucune fusion ni pull request. Le moteur de restauration et ses réglages par défaut sont
inchangés. Aucune dépendance Python ajoutée. Les changements dans `assistant.py`
se limitent au branchement de « Chercher la neige… » sur la barre et à la visibilité des
commandes dans « Couper le film ».

## Fait

- « Zoom », « − », « + » et « Tout le film » agissent autour du moment choisi. Les coupes
  restent aux mêmes instants du film. Une fois la barre au clavier, les flèches déplacent
  la tête de lecture d’une seconde, de dix secondes avec Maj et d’une image avec Ctrl.
  Le déplacement d’une image utilise la cadence indiquée par le fichier.
- « Chercher la neige… » propose les passages trouvés en bleu. Le premier est sélectionné
  à la fin de la recherche. Un clic sur une autre zone bleue la sélectionne. « Enlever »
  applique le retrait à la copie et propose le passage suivant. « Annuler la dernière
  coupe » et « Remettre » restaurent le passage dans la sélection.
- Les changements de scène disponibles dans `info.scenes` apparaissent sur la barre.
  Une coupe proche d’un repère s’y cale. Maintenez Alt pour placer la coupe librement.
- Les passages retirés sont dorés et hachurés. Les poignées visibles passent de 12 × 12
  à 18 × 26 points et gardent une zone de saisie de 44 points de large. Le survol affiche
  l’heure précise et le type de passage. La tête de lecture blanche a un contour sombre.
- Les vignettes correspondent à la durée et à la largeur visibles. Le logiciel conserve
  jusqu’à 128 images du film ouvert et réutilise celles déjà extraites aux mêmes instants.
  Les nouveaux prélèvements se font par FFmpeg dans les fils de vignettes existants.
  Changer de film efface le cache et les fichiers temporaires de l’ancien film.

## Vérifié

Exécution hors écran sous Linux avec Python 3.12.14, PySide6 6.12.0 et FFmpeg 7.1.5.

Une vérification supplémentaire a chargé un film simulé de 3 h, une coupe et une suggestion
de passage vide. Les 20 combinaisons (assistant et réglages libres, thèmes clair et sombre,
1280 × 641 à 100/125/150 %, 1024 × 689 et 1093 × 535 à 100 %) ont gardé les dimensions
demandées, sans défilement horizontal, avec la barre, « Enlever » et « Lancer la restauration »
visibles. L’assistant ne défilait pas verticalement à 100 et 125 %.

Les neuf fichiers demandés ont été exécutés sur le code publié, en trois groupes.
**62 tests réussis, 0 échec, 0 sauté. Code de sortie 0 pour chacun des trois groupes.**

| Fichier | Réussis |
|---|---:|
| `tests/test_timeline.py` | 15 |
| `tests/test_barre_montage.py` | 1 |
| `tests/test_coupe_un_clic.py` | 2 |
| `tests/test_passages_gui.py` | 4 |
| `tests/test_guide_coupes.py` | 2 |
| `tests/test_vides_montage.py` | 6 |
| `tests/test_ecran_unique.py` | 9 |
| `tests/test_ecrans.py` | 14 |
| `tests/test_assistant.py` | 9 |

Le test du parcours vérifie que la recherche laisse le film entier, puis que deux clics
explicites sur « Enlever » conservent bien le film entre 3 et 63 s, avec la tolérance
d’origine (±0,6 s). Le test de précision vérifie aussi les pas de 1 s, de 10 s et de
40 ms à 25 images/s sur une barre de 540 points représentant une cassette de 3 h.

## Non testé

- Exécutable Windows, vraie cassette et appréciation visuelle sur l’écran de l’utilisateur.
- Détection réelle des scènes de `grok/qualite`, qui vit sur une autre branche. L’affichage et
  l’aimantation ont été testés en fournissant les repères au même format.
- Pas de navigation garantie à l’image décodée exacte pour les fichiers à cadence variable.
- Suite complète du projet, conformément au périmètre demandé.
