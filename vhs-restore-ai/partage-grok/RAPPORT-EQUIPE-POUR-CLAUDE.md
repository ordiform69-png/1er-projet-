# Rapport d'équipe pour Claude

Branche `grok/equipe`, à relire. Non fusionnée.

## Ce que chaque bot a fait

- **Parcours senior** : parcours à 641 px. Bloque : cadre de coupe ouvert trop tôt, molette qui coupe le film, phrase d'arrêt effrayante. Écarté cette vague : déplacer l'aperçu et le bouton dossier (la phase 24 a déjà collé la barre sous les étapes 1-2-3).
- **Aide et textes** : le mode d'emploi ne parlait pas de « Couper ici ». Textes mis à jour. Aucun libellé de bouton changé.
- **Image et son** : mesures sur les films de synthèse. Aucun seuil changé (décision D-003). Coupe au milieu : image et son à 21 ms d'écart, dans la tolérance.
- **Contrôle** : 32 tests de la sélection passent. 2 échecs déjà là : `test_photo_au_nom_avec_pourcent`, aperçu comparaison vide (`scale2ref`), même sans « % » dans le nom. Pas traité ici.
- **Windows** et **Montage** : analyse non rendue à temps. Leurs sujets restent au tableau (n° 11 et 12).

Discussions : E-002 à E-006 dans `partage-grok/equipe/ECHANGES.md`.

## Fait

- Molette ignorée sur les temps tant que le champ n'a pas le focus.
- « Enlever une scène » seulement après qu'un film est choisi.
- Arrêt : « Arrêté. Votre film n'a pas été modifié. Pour recommencer, cliquez sur « Restaurer ». »
- `LISEZMOI.txt` et « Bienvenue » : « Couper ici », taille du texte, affichage clair.
- Erreur de coupe : noms des cases à l'écran.

## Testé

```
QT_QPA_PLATFORM=offscreen
pytest tests/test_passages_gui.py tests/test_barre_montage.py tests/test_montage.py tests/test_ergonomie.py::test_texte_sans_defilement_horizontal
```

15 tests passés en 39 s : `test_passages_gui.py`, `test_barre_montage.py`, `test_montage.py`, `test_texte_sans_defilement_horizontal`.

## Non testé

- Toute la suite des 240 tests.
- Construction Windows de l'exe (« RÉSULTAT : OK »).
- Cassette d'une heure, mur blanc, vraie clé FAT32.

## Risques

- Cacher le cadre avant un film change la page vide : les tests qui ouvrent un film d'abord ne sont pas concernés.
- L'échec photo `%` n'est pas une régression de cette vague, mais la suite complète n'est pas verte dans cet environnement.

## Écarté

- Changer un seuil d'image ou de son.
- Cacher les noms LosslessCut et Shotcut.
- Vignettes, levée du refus IA, banc de montage.
- Déplacer le bouton dossier et réduire l'aperçu (vague suivante, avec Contrôle).
