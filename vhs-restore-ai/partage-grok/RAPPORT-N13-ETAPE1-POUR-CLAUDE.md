# Rapport n°13 — étape 1, écran unique

## Où

- Dépôt : `ordiform69-png/1er-projet-`
- Branche : `grok/ecran-unique`, au-dessus de `6fe7a0e` (celui que vous avez relu)
- Pas de fusion. Pas de pull request.
- Fichiers : `vhs_restore/theme.py`, `vhs_restore/gui.py`, `vhs_restore/ecran.py`
- Le moteur (pipeline, coupes, FFmpeg) n'est pas touché.

Commits, un par point, plus un correctif de hauteur de barre :

| Commit | Sujet |
|---|---|
| `3c28396` | Affichage clair par défaut |
| `458969b` | Gros boutons pour les quatre sections |
| `57eaa4b` | « Lancer la restauration » en 400 × 64 |
| `6d841c8` | Accueil : grand bouton et trois étapes |
| `aa37fb5` | Commandes plus grandes dans Qualité et le son |
| `0000c16` | La barre de coupe reste redimensionnable |

## Fait

1. **Affichage clair par défaut.** Les couleurs du module partent de la palette claire. Au premier lancement, sans préférence enregistrée, l'écran est clair. Le bouton dit « Affichage sombre ». Si le réglage enregistré est exactement `affichage = sombre`, l'écran reste sombre.

2. **Titres de section.** « Qualité », « Couper le film », « Régler l'image », « Régler le son » sont des boutons d'au moins 44 px (mesurés à 46 px), texte gras 14 pt, flèche à droite (chevron). La section ouverte est surlignée (fond actif, bordure accentuée, flèche vers le haut). Une seule section est ouverte à la fois.

3. **« Lancer la restauration ».** 400 × 64 px, à 100 %, 125 % et 150 %, y compris dans une fenêtre de 1093 × 600. Il reste dans l'écran. « Regarder le film » / « Voir la photo » ne sont pas forcés à 400 px.

4. **Accueil, aucun film ouvert.** « Choisir un film ou une photo » est un bouton d'environ 493 × 148 px, au centre de la zone image. À droite : « 1. Choisir le film », « 2. Voir l'avant / après », « 3. Lancer la restauration ». « Détails du fichier » est caché tant qu'aucun fichier n'est ouvert. Un `click()` sur ce bouton caché ouvre toujours la fenêtre (les tests d'installation le font sans film). « Restaurer tout un dossier » reste dans l'écran à 100 %, 125 % et 150 %.

5. **Sections courtes.** Dans « Qualité », les tuiles de profil font 108 px de haut (112 en photo), les cases et « Dossier de sortie… » sont plus hauts. Si le conseil d'analyse est affiché, les tuiles redescendent à 80 px pour que la ligne tienne sans défilement à 125 %. Dans « Régler le son », tant que « Plus de réglages… » est fermé : « Écouter ces 10 secondes » fait 64 px, « Nettoyer le son » 48 px, « Plus de réglages… » 56 px. Dès que le détail s'ouvre, ces commandes redeviennent compactes : le test qui ouvre « Plus de réglages » ne défile pas.

6. **Barre de coupe.** Elle est compacte (64 px dans l'écran, au lieu de 88). Elle n'est pas figée : `test_barre_comme_un_montage` la remet à 400 × 56. À 60 px figés, ce test échouait.

Tout tient à 1280 × 641 sans défilement vertical à 100 % et 125 % (vidéo et pellicule, « Plus de réglages » ouvert). Pas de défilement horizontal à 100 %, 125 % ni 150 %. À 150 %, un défilement vertical dans une section est encore permis.

## Interdit respecté

- Aucune nouvelle dépendance.
- Moteur non modifié (pipeline, filtres, coupes, FFmpeg).
- Aucun test affaibli, aucun test supprimé.
- Pas de fusion, pas de pull request.
- Les captures ne sont pas dans le dépôt.

## Vérifié

Commande, Linux, hors écran :

```
cd vhs-restore-ai
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

- **330 passed, 15 skipped, 0 failed.**
- **Code de sortie : 0.**
- Durée : 1978 s (32 min 58 s).
- Python 3.12.7, PySide6 6.12.0, FFmpeg 7.0.2-static.
- `LD_LIBRARY_PATH=/tmp/qtlibs/usr/lib/x86_64-linux-gnu`, `PATH` avec cet FFmpeg.

La même suite, avant le correctif de barre, avait **1 échec** : `tests/test_barre_montage.py::test_barre_comme_un_montage` (hauteur 60 au lieu de 56). Après `0000c16`, ce test et `tests/test_coupes_bords.py` / `tests/test_passages_gui.py` passent, et la suite complète ci-dessus est verte.

Contrôles mesurés à 1280 × 641, captures locales non commitées :

| Écran | 100 % | 150 % |
|---|---|---|
| Accueil | bouton choisir et dossier dans l'écran, 3 étapes à droite, détails cachés, lancer 400 × 64 | fenêtre toujours 1280 × 641, choisir et dossier dans l'écran |
| « C'est prêt » (film) | titre, « Regarder le film », « Ouvrir le dossier », « Lire le bilan complet », lancer : dans l'écran | les mêmes, dans l'écran |
| Photo | seulement « Qualité » et « Régler l'image », aperçu et lancer dans l'écran, pas de défilement | « C'est prêt » photo : « Voir la photo », nommer, bilan, lancer dans l'écran |

Thème des captures : clair. « Affichage sombre » est bien le libellé du bouton.

## Non testé

- Exe Windows, installateur, vraie cassette, vrai DVD, clé USB, chemin réseau.
- Lecture à l'œil d'une restauration (le moteur n'a pas changé).
- Le texte d'attente dans le cadre noir (« choisissez un film… ») est coupé sur la gauche à cette largeur : il est dessiné centré, sans retour à la ligne. Ce n'est pas un défilement de la fenêtre. Les boutons de « C'est prêt » et du mode photo, eux, sont entiers.
- Écran « C'est prêt » après une vraie exportation (les captures appellent l'écran directement, comme le test).
