# Note de livraison — Petit guide de survie

**Version** : 9 novembre 2026, version corrigée après relecture éditoriale et rapports d'agents.
**Statut** : **version de travail corrigée, non validée pour diffusion publique**. Trois arbitrages éditoriaux et quelques compléments restent ouverts (voir plus bas).
**Source** : dépôt `ordiform69-png/1er-projet-`, branche `ccr-3a2da90d-9th5tm`.

## Contenu du livrable

| Fichier | Rôle |
|---|---|
| `guide-survie.pdf` | Livret complet, A5, 125 pages, illustré, lisible hors ligne et imprimable |
| `fiches-reflexes.pdf` | Les 10 fiches réflexes seules (A5, 4 pages), à imprimer et glisser dans le kit |
| `guide-survie.html` | Version web autonome (un seul fichier, hors ligne, mode sombre) ; source des deux PDF |
| `guide-survie-corrige.md` | Texte intégral en Markdown, autonome : toutes les consignes vitales y sont en texte |
| `JOURNAL-CORRECTIONS.md` | Chaque correction : chapitre, avant, après, source ; arbitrages ; illustrations à revoir |
| `CONTROLE-PERSISTANCE.md` | Vérification des points 001 à 102 sur la version corrigée : 102 / 102 conformes |
| `NOTE-DE-LIVRAISON.md` | Ce document |

Les trois versions (PDF, HTML, Markdown) disent la même chose sur les points vitaux.

## Contenu du livret

Avant-propos puis 25 chapitres : priorités, kit, abri, feu et techniques d'allumage, eau, orientation, signaux, premiers secours, nourriture, plantes, techniques issues de l'armée, nœuds, fabrications, météo, montagne, mer, désert, grand froid, jungle, ville et catastrophes, avec rien sur soi, avec un outil, fiches réflexes, programme d'entraînement, check-lists. Un avertissement en tête rappelle que ce n'est pas une formation de secourisme (urgence : 112 ou 15).

## Corrections intégrées

- **Lot 1** : les 11 corrections du brief éditeur (arrêt cardiaque, garrot, monoxyde de carbone, encordement, ail des ours, eau, coup de chaleur, jour blanc, avalanche, glace, orage).
- **Lot 2** : environ 120 points des rapports d'agents (Médecin, Botaniste, Eau, Abri et feu, Militaire, Navigateur, Psychologue, Bushcraft). Doublons fusionnés ; fiches réflexes alignées.
- **Contrôle de persistance** : 10 reprises secondaires alignées ; résultat 102 / 102.
- Le numéro de rappel des secours **0 800 112 112** a été vérifié sur des sources officielles avant intégration.

## Points ouverts avant diffusion

**À trancher par l'éditeur** (le texte en place est indiqué dans `CONTROLE-PERSISTANCE.md`) :
1. **Point 022, eau naturelle** : le chapitre 5 dit « à traiter avant consommation », le chapitre 19 « lorsque possible ». C'est une incohérence interne.
2. **Point 019, brancard** : essai avec une charge inerte (en place) ou essai prudent au ras du sol.
3. **Point 003, symptômes après de grands apports d'eau** : appel aux secours (en place) ou avis médical rapide.

**À compléter** :
- Procédure **enfant** de l'arrêt cardiaque (« à valider », ne pas extrapoler la procédure adulte).
- **If, myrtilles, lianes** : abstention seulement, formulation spécialisée non transmise.
- **Schémas pas à pas** du cabestan et du nœud tendeur (chapitre 12).
- **Trois illustrations encore en tension** avec le texte : coches ✓/✗ sur les plantes (ch. 10), « Est » et « Sud » dans le dessin du bâton et de la montre (ch. 6), « …à faire bouillir ! » sous le filtre (ch. 13).

**Recommandé** : une relecture finale par un formateur aux premiers secours (PSC) sur les chapitres 8, 16 et 23 avant toute diffusion.

## Empreintes SHA-256

```
6854e47b424f8b27aeb67e3fa82fc4aa44e7e86850600cca475de3ba66bb6f58  guide-survie.pdf
24a0824f9d14e872f4f549ab9a3b0c3117f0e25d59ed80396ed1c5a4a1e9fd42  fiches-reflexes.pdf
57464829feaf1af73d9cced5b658cea4a58909edd2b0991abb44bcc95f57af7c  guide-survie.html
d6bafe90ff2bfe09df5019ee8d634b833a5debfc2a302be6380cea84771a7796  guide-survie-corrige.md
5fa8d0bc2e75c06d3a26924a38788eb1d512622a2972e63f1a45e424d60bd5a8  JOURNAL-CORRECTIONS.md
e646ce6166871d65245cdcba2721cdc29c0f34cd1c4c7bb7812bda057bc7dd2c  CONTROLE-PERSISTANCE.md
```
