# Note de livraison — Petit guide de survie

**Version** : **1.0 — 9 novembre 2026**, version finalisée après relecture éditoriale, rapports d'agents et arbitrages.  
**Statut** : **version 1.0 finalisée**. Deux contenus restent volontairement signalés « à valider » dans le livret, faute de source spécialisée (voir plus bas). Relecture par un formateur PSC recommandée avant diffusion large.  
**Source** : dépôt `ordiform69-png/1er-projet-`, branche `ccr-3a2da90d-9th5tm`.

## Contenu du livrable

| Fichier | Rôle |
|---|---|
| `guide-survie.pdf` | Livret complet, A5, 143 pages, illustré (dessins et 28 photos libres), lisible hors ligne et imprimable |
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

## Arbitrages de finalisation (règle du brief : la version la plus sûre)

- **Point 022, eau naturelle** : « à traiter avant consommation » partout, l'exception de dernier recours renvoyant au chapitre 21.
- **Point 019, brancard** : jamais de personne pour tester ; contrôle avec une charge inerte.
- **Point 003, apports massifs d'eau** : maux de tête ou nausées → arrêt de l'effort et avis médical rapide ; vomissements, malaise ou confusion → secours.
- **Nœud de cabestan** : 5 étapes numérotées + photo ; nœud de chaise et tendeur illustrés en étapes.
- **Illustrations** : 28 photos sous licence libre (crédits en fin de livret) ; coches ✓/✗ supprimées ; légendes alignées sur le texte.

## Restent « à valider » (signalés dans le livret)

- Procédure **enfant** de l'arrêt cardiaque (ne pas extrapoler la procédure adulte).
- **If, myrtilles, lianes** : abstention, formulation spécialisée non transmise.

Une demande précise pour les agents est prête (`partage-grok/DEMANDE-GROK-V1.1.md`) ; leurs réponses permettront une version 1.1.

**Recommandé** : une relecture finale par un formateur aux premiers secours (PSC) sur les chapitres 8, 16 et 23 avant toute diffusion.

## Empreintes SHA-256

```
7d25a7fffe50c2806b2b79f1e90489af8fe2ca6fea18499aba0632747c0ee7d2  guide-survie.pdf
5ee5787978f9c86818c34a1d90f78df7a15a9b6abac51fca8644fb50c4d435aa  fiches-reflexes.pdf
6b1560aff4012a4f26fbe1d2cf8faaead87616dd5b4d71ed35586937068ce2c7  guide-survie.html
baa01f2fa44614fdfff08b9956d47ad9b3ac3351d942cf24d1c794c4cac2cbb1  guide-survie-corrige.md
f695414a2336ec738f5384b5925cbace04f30f41897d11f689ebfacb9c6d3a50  JOURNAL-CORRECTIONS.md
76eb0a45df55ba4222b74317b3824ebddd1240e2b28954292dde51ea7a7aed51  CONTROLE-PERSISTANCE.md
```
