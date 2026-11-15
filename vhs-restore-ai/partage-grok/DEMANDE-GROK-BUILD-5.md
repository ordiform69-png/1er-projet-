Bonjour Grok,

Merci pour les PR #3 à #9 : elles sont toutes fusionnées et l'exe Windows fonctionne chez
l'utilisateur. Cette fois, la demande porte uniquement sur **le visuel de l'interface**.

## Ce qui a changé depuis ta dernière demande (à lire avant de commencer)

- **Mode Photo** (`vhs_restore/photo.py`) : on choisit une photo scannée (JPEG/PNG/TIFF),
  l'avant/après s'affiche, et la restauration donne un PNG à la même taille. Le noir et blanc
  est conservé. L'autotest de l'exe (`--autotest`) le vérifie aussi.
- **Trois petites fonctions** : temps restant estimé (`eta.py`), « Garder du début à … jusqu'à
  … » (début/fin du film), bouton « Vérifier l'installation » (lance l'autotest).
- **Nouveau thème** (commit `df299ca`, `vhs_restore/theme.py`) :
  - la page « Options avancées » est enfin dans une `QScrollArea` (l'utilisateur ne pouvait pas
    descendre jusqu'au bouton de restauration) ;
  - une palette claire fixe + une feuille QSS : bandeau bleu en dégradé, cartes blanches
    (`QGroupBox`), gros boutons d'étape, bouton « Restaurer » vert ;
  - la zone avant/après (`CompareView.paintEvent`) est sur fond sombre, avec des pastilles
    « Original » / « Restauré ».
  - Noms d'objets utilisés par le QSS (à garder, ou à renommer partout) : `page`, `bandeau`,
    `marque`, `titre`, `infos`, `etape`, `principal`, `lien`, `note`, `statut`, `action`.
  - Piège déjà rencontré : du QSS sur `QComboBox` / `QDoubleSpinBox` **sans** styler aussi
    `::drop-down`, `::down-arrow`, `::up-button`, `::down-button` casse l'affichage des flèches.
    Si tu les styles, fournis les flèches toi-même (SVG embarqués) et vérifie-les sur capture.

L'utilisateur trouve l'interface encore trop sage. Sa demande, mot pour mot :
**« j'aimerais que l'interface soit visuellement très badass, classe et futuriste »**.

## Ce que je te demande — branche `grok/interface-futuriste`, une seule PR

Une refonte **visuelle** de `theme.py` (et des retouches de mise en page dans `gui.py` si
nécessaire). Direction artistique proposée, à affiner :

1. **Thème sombre « salle de montage »** : fond anthracite profond (pas noir pur), cartes
   légèrement plus claires avec bord fin lumineux, un accent néon (cyan ou ambre « bande
   magnétique ») utilisé avec retenue. Classe plutôt que gadget : peu de couleurs, beaucoup de
   cohérence.
2. **Typographie** : une police d'interface moderne sous licence libre (OFL), par ex. *Inter*
   pour le texte et éventuellement une police plus « tech » (*Orbitron*, *Rajdhani*, *Exo 2*…)
   **uniquement** pour le bandeau et les titres. Polices embarquées dans le dépôt
   (`vhs_restore/assets/fonts/` + licence OFL à côté), chargées avec `QFontDatabase`, et
   ajoutées dans `VHSRestoreAI.spec` (`datas`) pour qu'elles soient dans l'exe. Si une police
   manque, retomber proprement sur la police système.
3. **Bandeau** : logo dessiné (SVG embarqué ou `QPainter`) évoquant une cassette / une bobine,
   titre en lettres espacées, fine ligne lumineuse en dégradé dessous.
4. **Boutons d'étape** : grands, avec numéro dans un cercle, état survol avec léger halo
   (`QGraphicsDropShadowEffect` coloré), état désactivé clairement différent. Le bouton
   « Restaurer » reste le plus visible de l'écran.
5. **Barre de progression** : fine, en dégradé, avec un effet « balayage » animé pendant le
   traitement (un `QPropertyAnimation` ou un minuteur léger, arrêté quand rien ne tourne).
6. **Avant / après** : cadre type moniteur de contrôle, pastilles « Original » / « Restauré »
   style HUD, ligne de séparation fine et lumineuse.
7. **Options avancées** : cartes sombres cohérentes, cases à cocher et boutons radio redessinés
   (indicateurs SVG), listes déroulantes et champs numériques stylés **avec leurs flèches**,
   barre de défilement fine et discrète.
8. **Écran d'accueil / fenêtre « Vérifier l'installation »** et boîtes de dialogue
   (`QMessageBox`) : même thème, rien qui reste en gris Windows au milieu.

## Règles non négociables

- **Lisibilité d'abord** : l'utilisateur final est né en 1950. Texte principal ≥ 12 pt, gros
  boutons ≥ 13 pt, contraste texte/fond **≥ 4,5:1** (WCAG AA) partout, y compris les textes
  secondaires et les boutons désactivés lisibles. Ajoute un test qui calcule ces contrastes à
  partir des constantes de couleur de `theme.py`.
- **Aucun changement de comportement** : mêmes boutons, mêmes textes (ou textes équivalents),
  mêmes noms d'attributs dans `gui.py` (`s_run`, `run_btn`, `pages`, etc.). Les 120 tests
  actuels doivent rester verts.
- **Le défilement de la page avancée doit continuer à fonctionner** à 1366×768 et à 1280×720,
  et la fenêtre doit rester utilisable à 125 % / 150 % de mise à l'échelle Windows.
- **Pas d'effets lourds** : pas de flou plein écran, pas d'animation permanente qui consomme du
  processeur pendant une restauration de plusieurs heures. Pas de nouvelle dépendance Python
  (PySide6 suffit) ; les seuls fichiers ajoutés sont des polices OFL et des SVG.
- **Le thème ne doit pas dépendre du mode clair/sombre de Windows** (palette fixe, comme
  aujourd'hui dans `theme.apply`).

## Preuves attendues dans la PR

- Captures **réelles** (rendues avec `QT_QPA_PLATFORM=offscreen` puis `widget.grab()`) :
  mode simple vide, mode simple avec une vidéo chargée et l'avant/après affiché, mode simple en
  cours de restauration (barre de progression), mode Photo, options avancées en haut et tout en
  bas, une boîte de dialogue. Mets-les dans la PR (pas dans le dépôt).
- Le test de contraste, et un test qui vérifie que la page avancée défile jusqu'au bouton
  `run_btn` à 1280×720.
- La construction Windows (`.github/workflows/vhs-restore-windows.yml`) verte, avec l'autotest
  de l'exe OK, et les polices bien présentes dans l'exe.

Termine la PR par **Fait / Testé (comment) / Non testé / Risques**. Pars de la dernière version
de `ccr-5856e8d6-8xt8uh` et rebase avant d'ouvrir la PR.

Merci !
