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

## Retouches après intégration du lecteur

### Où

Branche `gpt/timeline-retouches`, créée sur `grok/lecteur` au commit `be6fe19`.

| Commit publié | Retouche |
|---|---|
| `61a547e` | Boutons agrandis et zoom nommé |
| `4a4098c` | Zones bleues opaques sur toute la piste |
| `fe02f83` | Bornes du passage choisi et retrait groupé |
| `9ca1f9a` | Libellés entre guillemets sur une ligne dans « Comment faire ? » |

### Fait

- « Zoom − », « Zoom + », « Tout le film » et les commandes de retrait mesurent
  38 points logiques de haut.
- Le bleu opaque couvre la hauteur de la piste. La bordure indique le passage choisi.
  « Neige ? » ou « Écran vide ? » apparaît quand le passage est assez large. Une zone
  de trois pixels reste cliquable sur une longue cassette.
- « Enlever 0:00 – 0:03 » indique directement la plage choisie. Le passage bleu le
  plus proche du curseur est proposé. Cliquez sur une autre zone bleue pour la choisir.
  « Tout enlever » apparaît dès qu’au moins deux passages sont proposés. La commande
  refuse la demande si elle laisserait moins d’un passage gardé ou plus de huit coupes.
  « Annuler la dernière coupe » remet le dernier passage retiré.
- Dans « Comment faire ? », les noms des commandes restent entiers avec leurs guillemets.
  Le moteur de restauration et le lecteur conservent leur code. Aucune dépendance
  ajoutée au projet, aucune fusion et aucune pull request.

### Vérifié

Linux, Python 3.12.14, PySide6 6.12.0 et FFmpeg 7.1.5, avec
`QT_QPA_PLATFORM=offscreen`.

| Groupe | Fichiers | Réussis | Code |
|---|---|---:|---:|
| 1 | `test_timeline.py`, `test_barre_montage.py`, `test_coupe_un_clic.py`, `test_passages_gui.py` | 28 | 0 |
| 2 | `test_guide_coupes.py`, `test_vides_montage.py`, `test_lecteur.py` | 13 | 0 |
| 3 | `test_ecran_unique.py`, `test_ecrans.py`, `test_assistant.py` | 32 | 0 |

**73 tests réussis, aucun échec ni saut.**

Les mesures sur un film simulé de 3 h, avec une coupe et deux propositions, couvrent
20 configurations. À 1280 × 641, les deux thèmes et les tailles de texte 100, 125 et
150 % gardent les commandes de retrait, la barre et le bouton de restauration dans la
fenêtre. L’assistant tient sans défilement vertical à 100 et 125 % avec ces propositions.
À 1024 × 689 et 1093 × 535, le contrôle après adaptation confirme les dimensions
de la fenêtre et l’absence de défilement horizontal. Sur le plus petit écran, le premier
redimensionnement depuis une fenêtre haute peut s’arrêter à 560 points avant une seconde
demande de taille. Le même comportement est présent à `be6fe19`.

Le guide sous la barre peut rogner une ligne à 150 % dans une configuration dense.
La comparaison avec `be6fe19` montre le même rognage. « Comment faire ? » ouvre la
version complète.

### Non testé

- Windows et lecture d’une cassette réelle sur l’écran de l’utilisateur.
- Suite complète, réservée à la vérification avant fusion.
