# Mémoire de travail (VHS Restore AI)

Logiciel gratuit pour restaurer les cassettes VHS et les photos de famille, utilisé par le père
de l'utilisateur (76 ans). Code dans `vhs-restore-ai/`, décisions dans
`vhs-restore-ai/DECISIONS.md`.

## Ce que l'utilisateur apprécie (à garder)

- Réactivité et anticipation : prévoir l'étape suivante, signaler les pièges avant qu'ils
  arrivent, proposer la suite sans attendre qu'on la demande.
- Des recommandations claires et tranchées (un choix conseillé, dans l'ordre), avec le pourquoi.
  « Tout fonctionne quand tu donnes tes recommandations. »
- Mesurer avant d'affirmer : captures et tests à 100, 125 et 150 % de texte, sur l'écran du père
  (1920 × 1080 à 150 % = 1280 × 641 utiles) et les écrans standard (`tests/test_ecrans.py`).
- Vérifier soi-même le travail des bots (tests, mesures, captures), dire honnêtement ce qui ne va
  pas, et le corriger.
- Réponses en français, phrases simples, au vouvoiement.

## Règles de travail

- L'exe : seulement quand l'utilisateur le demande. Ne pas le relancer, ne pas surveiller sa
  fabrication, ne pas programmer de rappel dessus, ne pas en reparler de soi-même (chaque
  fabrication coûte une heure de GitHub). Se concentrer sur ce qui est demandé, avec conseils.

- Branche `ccr-5856e8d6-8xt8uh` seulement. Jamais de pull request.
- Fusionner une branche des bots seulement quand l'utilisateur écrit « fusionner ».
- « Ne lance pas l'exe » : pousser avec `[skip ci]` ; plus tard, lancer la fabrication par
  `workflow_dispatch`. Exe : artefact de la fabrication Windows, SHA-256 vérifié, envoyé.
  `livraison-*/` reste hors dépôt (exclu localement).
- Aucune nouvelle dépendance Python (onnxruntime et onnx sont déjà là). Aucun test affaibli.
- Suite complète : environ une heure ; la lancer en arrière-plan avec un délai d'au moins 5000 s.

## Les bots (Grok et son chef des bots)

- Claude ne peut pas leur écrire directement : écrire la demande dans
  `vhs-restore-ai/partage-grok/DEMANDE-GROK-BUILD-<n>.md`, la pousser, et donner à l'utilisateur
  un court message à transmettre.
- Une demande précise : agents, branches, fichiers de chacun, choix déjà tranchés, pièges connus,
  tests attendus. Rappels : chaque commit poussé tout de suite, pas la suite complète (seulement
  les fichiers cités), ni fusion ni pull request.
- Leur bac à sable manque souvent : ils ne peuvent pas mesurer. Claude mesure à la livraison.
