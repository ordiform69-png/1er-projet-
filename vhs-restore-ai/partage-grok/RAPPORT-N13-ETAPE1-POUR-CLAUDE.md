# Demande n°13 · Écran unique · Étape 1

## Où

Branche `grok/ecran-unique`, issue de `ccr-5856e8d6-8xt8uh` au commit `0633318`. Les commits de l’interface sont `6d392e8` et `6fe7a0e`. L’exécutable à essayer correspond au second.

## Fait

Une fenêtre réunit l’accueil, la comparaison avant/après et les quatre volets de réglages. « Détails du fichier » donne accès aux caractéristiques, aux avertissements et aux outils. Les coupes utilisent la barre à vignettes existante. « Écouter ces 10 secondes » prépare un aperçu avec les réglages actuels et ouvre l’extrait restauré. Pour une photo, seuls les volets « Qualité » et « Régler l’image » sont proposés.

L’état et les commandes de restauration occupent le pied de la fenêtre. « C’est prêt » remplace les réglages après la restauration. Le bilan complet reste consultable lorsque le message dépasse la place disponible. Le premier lancement utilise l’affichage clair et conserve un choix de thème déjà enregistré.

## Interdit respecté

Les cinq fichiers moteur désignés dans la demande sont identiques à la base. Aucune dépendance Python, image, capture ni archive ajoutée au dépôt. Les modifications sont sur la branche de l’étape 1, sans fusion ni pull request.

## Vérifié

La fabrication Windows n°104 a exécuté toute la suite avec Python 3.12. Résultat : **335 tests réussis, 10 sautés, code de sortie 0**, en 40 min 04 s. PyInstaller a fabriqué l’exécutable. Son autotest a réussi et GitHub a publié le paquet et son fichier SHA-256.

Les neuf cas de `tests/test_ecran_unique.py` couvrent les trois tailles de texte à 1280 × 641, les volets pour vidéo et pellicule, le mode photo, le travail en cours et le résultat. Ils vérifient la visibilité des commandes et les limites du défilement.

[Fabrication Windows n°104 et téléchargement](https://github.com/ordiform69-png/1er-projet-/actions/runs/45525512613)

## Non testé

L’essai manuel sur l’écran familial à 150 % de mise à l’échelle Windows reste à faire. Les mesures automatiques utilisent une fenêtre Qt de 1280 × 641 pixels logiques. Le lecteur intégré relève de l’étape 2, soumise à l’accord de l’utilisateur après cet essai.
