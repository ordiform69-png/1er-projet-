# Demande n°16, corrections (pour le chef des bots)

Claude a vérifié `grok/design-maquettes` (tête `583c488`) : le rendu suit bien les trois
maquettes. Tests ciblés lancés par Claude : 82, dont 80 verts et 2 rouges, les deux sur la
taille de la fenêtre (`test_parcours_complet_d_un_film`, `test_chaque_etape_tient_a_1280_641`).

## Ce qui dépasse (mesuré par Claude, chaque étape seule, fenêtre 1280 × 641)

| Texte | Étape 1 | Étapes 2, 3 et 4 | Étape 5 |
|---|---|---|---|
| 100 % | tient | +18 px de haut | tient |
| 125 % | +6 px | +42 px | tient |
| 150 % | +20 px | +60 px | +101 px de LARGE |

Sur l'écran du père, le bas de la fenêtre (« Lancer la restauration ») sortirait de l'écran.
Causes probables :
- étapes 2 à 4 : la ligne « Rien à changer ? Cliquez sur Suivant. » (les trois seules étapes
  qui l'ont), et la page « Lumière et couleurs », la plus haute, qui impose sa hauteur à toutes
  les pages de la pile (`QStackedWidget`) ;
- étape 5 : les boutons « Original », « Comparer les deux », « Restauré » qui apparaissent sous
  l'image après l'avant / après (trop larges à 150 %).

## Travail, par agent (chacun sur sa branche ; l'agent 5 refusionne)

**Agent 4 (navigation)**
- Mettre `self.pages` dans une `QScrollArea` (sans cadre, `widgetResizable`, défilement
  horizontal coupé) : la fenêtre ne doit JAMAIS grandir. C'est un filet : le but reste
  « aucun défilement à 100 et 125 % ».
- « Rien à changer ? Cliquez sur Suivant. » : même texte, une seule ligne, taille de texte
  normale en gras (pas plus grand que le titre).

**Agent 2 (lumière)**
- La valeur (« Normal », « +2 ») à DROITE de la jauge, plus dessous. Jauge de 32 px de haut
  au plus. Chaque ligne a la hauteur des boutons.
- Phrase du bas raccourcie : « Aperçu rapide d'une image, sans l'amélioration IA. »
- Réponse à la question : on garde « Normal » au milieu, « +2 », « −1 » ailleurs.

**Agent 1 (rendu)**
- Phrase d'introduction sur une ligne : « Cliquez sur la ligne qui vous plaît. » (le titre
  dit déjà « (conseillé) »).
- Petites images 96 × 72 (au lieu de 112 × 84) ; ligne grise de l'original plus basse.

**Agent 3 (lancer)**
- Boutons sous la grande image : « Avant », « Les deux », « Après » (mêmes mots que les
  pastilles AVANT / APRÈS et que le bouton « Voir l'avant / après »). Ligne d'état :
  « Comparez avec les boutons « Avant » et « Après ». » Rechercher les autres mentions de
  « Original » / « Restauré » à l'écran (infobulles, lecteur) et les aligner.
- Consigne de l'étape 5 plus courte, en texte normal (pas en gras ni en grand) : « Si le
  résultat vous plaît : « Lancer la restauration », en bas à droite. »
- Ne pas toucher à `estimation.py` : Claude y a corrigé « 0 Go » (jamais moins de 0,1 Go).

**Agent 5 (intégration)**
- Refusionner les quatre branches dans `grok/design-maquettes`.
- Fermer SANS les fusionner les pull requests #12, #13 et #14 (la consigne était : pas de
  pull request).
- Dès que le bac à sable revient : `test_assistant.py`, `test_lumiere.py`,
  `test_ecran_unique.py`, `test_estimation.py`, `test_theme.py`, `test_gui.py`. Sinon :
  « non testé » dans le rapport, Claude mesure à la livraison.
- Compléter `partage-grok/RAPPORT-N16-POUR-CLAUDE.md` (partie « Corrections »).

Règles inchangées : moteur et calcul de la durée intouchés, aucun test affaibli, pas de
capture ni de zip dans le dépôt, chaque commit poussé tout de suite, ni fusion dans
`ccr-5856e8d6-8xt8uh` ni pull request.
