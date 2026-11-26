# Lecteur : copie de lecture sans stries (pour Navigation, via le chef des bots)

Mesure de Navigation (`RAPPORT-N13-ETAPE2`, `grok/lecteur-mesures` `4d83a88`) : « Lire le film »
affiche une VHS entrelacée striée dès que ça bouge (écart entre lignes paires et impaires 16,95
dans le lecteur, 0,00 avec bwdif). C'est la première image que le père verra : à corriger AVANT
la fusion du lecteur. « Vérifier la coupe » n'est pas concerné (`raccord.py` désentrelace déjà).

## Base et branche

- Partir de `gpt/timeline-retouches` au commit `c753474` (le lecteur `be6fe19` ET les retouches de
  ChatGPT sont dedans). PAS de `grok/lecteur` seul : les retouches seraient perdues.
- Branche : `grok/lecteur-copie`.

## Choix faits (ne pas rediscuter)

Une **copie de lecture** préparée en arrière-plan, pas un désentrelacement autour de la tête de
lecture (la copie garde une lecture et des sauts normaux).

- Seulement pour un film entrelacé (`info.scan` vaut `tff` ou `bff`). Film progressif : le lecteur
  lit l'original, comme aujourd'hui.
- La copie : `bwdif=mode=send_frame` (même cadence, mêmes instants), réduite à la taille
  d'affichage (720 px de large au plus, format 4:3 gardé : pixels 16/15 corrigés), H.264
  `veryfast`, son AAC par `tools.AAC`. Même durée et mêmes instants que l'original : une position
  sur la barre donne la même image dans la copie. DVD en plusieurs VOB : tout le titre (comme
  `vignettes.py`, `dvd.input_args`).
- Dans un fil à part, en basse priorité, APRÈS l'analyse des scènes (jamais en même temps qu'elle),
  annulée au changement de film et à la fermeture. Dossier temporaire comme les vignettes, effacé
  à la fermeture. Place disque vérifiée avant ; pas assez de place : pas de copie, rien ne casse.
- Le lecteur lit l'original jusqu'à ce que la copie soit prête, puis passe sur la copie à la même
  position, sans arrêter ni relancer la lecture (lecture ou pause gardée).
- Aucun message de plus pour l'utilisateur.

## Tests

- Mire entrelacée qui bouge : sur une image de la copie, l'écart entre lignes paires et impaires
  est proche de 0 (même mesure que le rapport) ; sur l'original, il reste élevé.
- Film progressif : aucune copie fabriquée.
- Même image à la même position : copie contre original désentrelacé par bwdif, à 3 instants.
- Changement de film pendant la préparation : arrêt propre, aucun fichier laissé.
- Plus : les tests du lecteur, `test_timeline.py`, `test_ecrans.py`, `test_assistant.py`.
- Mesure : vitesse de préparation (images par seconde, temps pour une heure de film) sur un film
  720 × 576 entrelacé.

## Règles

Chaque commit poussé tout de suite. Seulement les fichiers de tests cités. Aucun test affaibli.
Aucune nouvelle dépendance. Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request.
Rapport : `RAPPORT-N13-ETAPE2-POUR-CLAUDE.md`, partie « Copie de lecture », sur `grok/lecteur-copie`.
