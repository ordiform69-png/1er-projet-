# Timeline : retouches avant fusion (pour ChatGPT)

Claude a vérifié `gpt/timeline` (`f3d0237`). Bon travail : zoom, flèches, passages vides proposés,
repères de scène (ils apparaissent d'eux-mêmes quand l'analyse des scènes de la n°17 finit,
vérifié en assemblant les deux branches), fenêtre 1280 × 641 tenue à 100 et 150 %. La retouche de
`test_assistant.py` est légitime (le parcours vérifie toujours le résultat final, 3 à 63 s).
L'assemblage avec `grok/qualite` donne un seul conflit d'une ligne (Claude le résout).

À retoucher pour un utilisateur de 76 ans (capture de l'étape « Couper le film » à 100 %) :

1. **Boutons trop petits** : « − », « + », « Tout le film », « Enlever » font environ 20 px de
   haut. Les mettre à la hauteur des autres boutons de la section (36 à 44 px), avec des mots :
   « Zoom − » / « Zoom + » (ou « Moins près » / « Plus près »).
2. **Passages proposés peu visibles** : le bleu se perd sur les petites images. Bleu franc et
   opaque sur toute la hauteur de la barre, bord net, et un mot sur la zone (« Neige ? »,
   « Écran vide ? ») quand la place le permet ; thèmes clair et sombre.
3. **« Choisissez un passage » ne dit pas comment** : le bouton dit ce qu'il enlève
   (« Enlever 0:00 – 0:03 », le passage proposé le plus proche du curseur, ou le premier), et un
   clic sur une zone bleue la choisit. Quand il y en a plusieurs : aussi « Tout enlever ».
4. Détail : dans « Comment faire », « Couper ici » est coupé avant « » » en fin de ligne :
   espaces insécables autour des guillemets (voir `_insecables` dans `gui.py`).

Mêmes règles qu'avant (branche `gpt/timeline`, un commit par point, fenêtre jamais agrandie,
aucun test affaibli, ni fusion ni pull request). Rapport : compléter `RAPPORT-GPT-TIMELINE.md`.

## Deuxième tour (après `4c48695`, `gpt/timeline-retouches`)

Vérifié par Claude (captures de l'étape « Couper le film », 100 et 150 %) : boutons à 38 points,
passages bleus bien visibles, « Enlever 0:00 – 0:03 » et « Tout enlever » : bien. Reste :

1. **Phrase guide sous les boutons** (« 1. Glissez jusqu'au début… ») : à 100 %, « Couper ici »
   est encore séparé de « » » en fin de ligne (la retouche a porté sur « Comment faire ? », pas
   sur cette phrase) ; à 150 %, la fin de la phrase est rognée. Espaces insécables ici aussi, et la
   phrase prend la hauteur dont elle a besoin (jamais rognée ; la page de l'assistant peut défiler
   à 150 %, pas à 100 et 125 %).
2. **« Lire le film » ne doit pas être vert.** Le vert est réservé à l'action principale de l'écran
   (« Suivant → », « Voir l'avant / après », « Lancer la restauration ») : deux grands boutons verts
   côte à côte, un homme de 76 ans ne sait plus lequel presser. Style des boutons secondaires (fond
   clair, bord), même taille.
3. Détail : à 150 %, « Image du film à 7 secondes » est rognée dans le cadre de l'image (texte plus
   petit ou sur deux lignes).

Mêmes règles. Branche `gpt/timeline-retouches`. Rapport : compléter `RAPPORT-GPT-TIMELINE.md`.
