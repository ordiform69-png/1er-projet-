# Rapport n°20 — agent C, écran (zoom Windows 125 % et 150 %, petits écrans)

Demande lue en entier : `vhs-restore-ai/partage-grok/DEMANDE-GROK-BUILD-20.md` au commit `1abf947`.
Branche `grok/bugs-c-ecran`, partie de ce commit. Aucune modification dans `vhs_restore/`.
Aucun test existant modifié. Aucune nouvelle dépendance. Aucune image commitée.

Mesures : Linux, Python 3.12.3, PySide6 6.12.0, hors écran (`QT_QPA_PLATFORM=offscreen`).
Le zoom est celui d'un programme à part lancé avec `QT_SCALE_FACTOR` (1, 1,25 et 1,5),
comme `test_petite_image_du_rendu_entiere_et_centree`. Les tailles d'écran sont celles
de `tests/test_ecrans.py`, plus 1280 × 641. Le point par pouce logique reste 96 :
les textes en points ne grandissent pas dans les coordonnées de la fenêtre. Ce qui
change, c'est le `devicePixelRatio` (1,25 ou 1,5).

Cinq constats, du plus gênant pour l'usage au moins gênant. Tous sont **PROUVÉ**.

## 1. L'aide du premier lancement dépasse l'écran

- **Gravité** : gênant
- **Où** : `vhs_restore/gui.py:2150` (`show_welcome`, le `exec` est à la ligne 2152)
- **Scénario** : au premier lancement, ou en cliquant sur « Aide », la boîte « Bienvenue dans VHS Restore AI » s'ouvre en modal. Elle mesure 709 × 1169 px (hauteur minimale 801). « C'est parti » est le seul bouton, et il n'y a pas de bouton Échap (`escapeButton()` vaut rien). Sur l'écran du père (1280 × 641), le bouton est sous le bord : on ne peut pas le cliquer sans tirer la fenêtre vers le haut.
- **Preuve** : **PROUVÉ**. À `QT_SCALE_FACTOR=1`, écran hors champ 800 × 800, la boîte affichée fait 709 × 1169, minimum 801 × 709. La même hauteur (1169, minimum 801) à 1,25 et à 1,5. 1169 dépasse 641, 535, 689, 785 et 1001. Seul l'écran 2560 × 1361 de la liste contient la boîte. Le texte, à 620 px de large, demande 1081 px de haut.
- **Correction proposée** : limiter la hauteur de cette boîte à la zone utile de l'écran et faire défiler le texte ; accepter aussi Échap.

## 2. La fenêtre remise à sa taille dépasse les petits écrans

- **Gravité** : gênant
- **Où** : `vhs_restore/gui.py:1384` (`MainWindow.resize(1100, 760)`)
- **Scénario** : le logiciel s'ouvre agrandi (`showMaximized` dans `main`). Un double-clic sur la barre de titre le remet à sa taille de repos, 1100 × 760. Cette hauteur dépasse 641 (le père), 689 et 535 : « Lancer la restauration », en bas, sort de l'écran. La largeur 1100 dépasse aussi 1024 et 1093.
- **Preuve** : **PROUVÉ**. Après `showMaximized` puis `showNormal`, la fenêtre fait 1100 × 760 à 1,25 et à 1,5 (et à 1). Les tailles minimales mesurées (environ 685 × 426) tiennent, elles, sur tous les écrans de la liste : c'est bien la taille de repos qui dépasse, pas le minimum.
- **Correction proposée** : avant d'agrandir, borner cette taille de repos à la zone utile (au plus la largeur et la hauteur de l'écran).

## 3. L'image du moniteur est floue à 125 % et à 150 %

- **Gravité** : gênant
- **Où** : `vhs_restore/gui.py:253` (`CompareView.paintEvent` ; le même dessin avant / après est aux lignes 275-280)
- **Scénario** : une image du film (barres verticales d'un pixel, 320 × 240) est posée dans le cadre par `poser_moment`. À 100 %, le contraste moyen des bords vaut 126. À 125 % il tombe à 116, à 150 % à 105. L'image occupe bien son cadre : elle n'est pas trop petite, elle est adoucie. On juge la restauration sur cette image.
- **Preuve** : **PROUVÉ**. Trois mesures identiques à chaque zoom. Le rapport au contraste à 100 % est 0,92 à 125 % et 0,83 à 150 %. Un dessin direct dans les pixels réels, lui, devient plus net quand le zoom augmente. Ici `QPixmap.size().scaled` vise la taille logique, puis `drawPixmap` avec `SmoothPixmapTransform` : Qt agrandit ensuite selon le `devicePixelRatio`.
- **Correction proposée** : préparer l'image en pixels réels (`largeur × devicePixelRatio`), puis `setDevicePixelRatio`, comme pour les tuiles de l'étape 1.

## 4. Les petites images de la barre sont floues à 125 % et à 150 %

- **Gravité** : gênant
- **Où** : `vhs_restore/gui.py:1224` (`_Ruban._dessiner_images`)
- **Scénario** : quatre vignettes en barres d'un pixel (90 × 72, la hauteur des vraies vignettes) sur une barre de 640 × 56. À 100 %, le contraste des bords vaut 105. À 125 % il tombe à 84, à 150 % à 70. On s'en sert pour choisir où couper : le flou gêne le repérage.
- **Preuve** : **PROUVÉ**. Trois mesures identiques. Rapports 0,80 (125 %) et 0,67 (150 %). `pix.scaled(dest.size())` fabrique une image à la taille logique et lui laisse un `devicePixelRatio` de 1 ; le dessin l'étire ensuite. Ce n'est pas le motif `QIcon.pixmap()` (les vignettes viennent d'un fichier, ratio 1), c'est le même oubli de pixels réels.
- **Correction proposée** : mettre à l'échelle vers `dest × devicePixelRatio`, puis `setDevicePixelRatio`, avant `drawPixmap`.

## 5. « Détails du fichier » dépasse l'écran de 535 px de haut

- **Gravité** : mineur
- **Où** : `vhs_restore/ecran.py:231` (`dialog.resize(850, 580)`)
- **Scénario** : sur 1093 × 535 (1366 × 768 à 125 %, ou 1920 × 1080 à 175 %), « Détails du fichier » s'ouvre à 850 × 580. Les 45 px du bas, dont « Fermer », sortent de l'écran. Sur 1280 × 641 la hauteur 580 tient. La hauteur naturelle (`sizeHint`) est 703 : elle dépasserait aussi l'écran du père si le `resize` était retiré.
- **Preuve** : **PROUVÉ**. Après un clic sur « Détails du fichier », la boîte fait 850 × 580 à 1,25 et à 1,5, `sizeHint` en hauteur 703.
- **Correction proposée** : prendre le minimum entre 850 × 580 et la zone utile de l'écran.

## Zones vérifiées sans bug

- **Étape 1, petites images des rendus** (`assistant.py`, `TuileRendu.paintEvent` vers la ligne 297). À 125 %, une image rouge de 480 × 360 sort à 86,4 × 64,8 pour 86 × 65 attendus, dans une ligne de 76 px. Le correctif `2dc2f2a` tient aussi à 125 %. Non resignalé.
- **Motif `QIcon.pixmap()` puis `scaled()` ailleurs.** Une seule occurrence, celle des tuiles, et elle rappelle `setDevicePixelRatio`. Les icônes de `icons.py` portent un ratio d'au moins 2 : un bouton « Aide » avec une icône pleine les dessine à 20 × 20 logiques à 100, 125 et 150 %. Une pastille de carte de 26 px dans un cadre de 30 × 30 tient aussi.
- **Interrupteurs** (feuille de style, 40 × 22). À 150 % le rectangle physique est 60 × 33, le bord reste net (deux ou trois pixels de transition, comme à 100 %).
- **Fenêtre principale forcée** à 1280 × 641, 1024 × 689, 1093 × 535, 1366 × 689, 1536 × 785, 1920 × 1001 et 2560 × 1361, à 150 %, accueil puis réglages libres (les cinq sections). La taille demandée est gardée, aucun défilement horizontal, aucun bouton hors de la fenêtre, aucun texte de bouton ou de libellé coupé par la mesure des métriques.
- **Repères de l'assistant** (« Rendu », « Lumière », « Coupes », « Lancer ») à 1280 × 641, texte à 100 % et à 150 % (A+) : pas d'élision dans la colonne de 140 px.
- **Tuiles de qualité** (« Bien nettoyé, naturel », « Nettoyage au plus fort ») à leur largeur réelle (~209 px, hauteur 108). Le rectangle du nom est un peu juste pour la boîte théorique (50 px demandés, 46 px offerts), mais l'encre s'arrête vers 42 px : rien n'est coupé.
- **Listes déroulantes** : la largeur de liste mesurée reste 144 px.
- **« Séparer en plusieurs films »** (six films) : hauteur affichée 408, souhaitée 456. Tient sur 535.
- **« Comment enlever une scène »** : hauteur affichée 355, souhaitée 417. Tient sur 535.

## Tests

`tests/test_bugs_n20_c.py` : un test par constat, `pytest.mark.xfail(strict=True)`, zoom par sous-processus.

Lancement demandé, et celui-ci seulement :

`timeout 900 python3 -m pytest tests/test_bugs_n20_c.py -q --tb=no`

Résultat : **10 xfailed, 0 xpass, 0 échec**, en **5,02 s**, code de sortie 0.
(Deux zooms, 1,25 et 1,5, pour chacun des cinq constats.)
