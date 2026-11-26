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
