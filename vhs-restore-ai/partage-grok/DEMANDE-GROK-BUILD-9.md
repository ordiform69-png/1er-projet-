# Demande n°9 à Grok Build : deux corrections sur la timeline (`grok/timeline`)

Bonjour Grok,

Claude a relu `grok/timeline` (commit `832439d`), sans la modifier ni la fusionner. La timeline
fonctionne bien : 13 petites images d'un MPEG-2 SD de 10 min en 1 s, écran jamais bloqué, mêmes
coupes sur les deux barres, 4:3 et entrelacement respectés, DVD en morceaux couvert, clic près d'un
bord et colonnes équilibrées conservés. **Deux points empêchent la fusion.** L'utilisateur te les
renvoie. Corrige-les sur `grok/timeline` (ou `grok/timeline-2` partie d'elle), sans rien changer
d'autre.

Les règles de `DEMANDE-GROK-BUILD-8.md` (section 2) et de `DEMANDE-GROK-BUILD-7.md` (sections 1 à 3)
restent valables : pas de nouvelle dépendance, pas de banc de montage, aucun filtre de restauration
modifié, protections Windows gardées.

---

## 1. Bloquant : plantage à la fin du programme (code de sortie 134)

**Constat.** Toute la suite passe (269 tests verts), puis le processus se termine par :

```
QThread: Destroyed while thread '' is still running
```

et le **code de sortie 134** (abandon). Reproduction en une minute :

```
cd vhs-restore-ai
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_timeline.py tests/test_passages_gui.py
echo $?        # 134 au lieu de 0
```

**Cause.** `_FilMoment` tourne dans une boucle sans fin (`while not self._stop`) jusqu'à `arreter()` ;
`_FilImages` peut aussi être en cours. Seul `closeEvent` les arrête (et n'attend que 2 s chacun).
Une fenêtre qui n'est pas fermée par `closeEvent` (c'est le cas de beaucoup de tests) laisse ces
fils tourner ; à la sortie de Python, PySide détruit les objets `QThread` encore actifs, et Qt
arrête tout le processus (`qFatal`).

**Pourquoi c'est bloquant.**
- La fabrication Windows lance toute la suite : le code de sortie non nul fait échouer l'étape,
  **aucun exe n'est produit**.
- Chez l'utilisateur : si un fil met plus de 2 s à s'arrêter à la fermeture (gros DVD, clé USB
  lente), Windows peut afficher « VHSRestoreAI a cessé de fonctionner ».

**Attendu.** Plus aucun fil d'images ne peut survivre à sa fenêtre ni à Python. À toi de choisir la
façon, par exemple :
- des fils Python courts `threading.Thread(daemon=True)` (un par lot de vignettes, un par demande
  d'image du moment, « la dernière demande gagne »), qui rendent leurs résultats par un signal d'un
  `QObject` vivant dans le fil de l'interface ; ou bien
- garder les `QThread`, mais sans boucle sans fin, arrêtés et attendus aussi à la destruction de la
  fenêtre et à `QApplication.aboutToQuit`, avec un filet `atexit`.
Dans tous les cas : le FFmpeg en cours est tué à l'annulation (pas de processus orphelin), et
l'écran n'est jamais bloqué en attendant un fil.

**Tests d'acceptation.**
- `python -m pytest -q` (toute la suite) : **code de sortie 0**, et aucune ligne
  « QThread: Destroyed » dans la sortie. Écris le code de sortie dans le rapport.
- Un test qui lance, dans un sous-processus Python, une fenêtre qui ouvre un film (vignettes en
  cours) puis se termine **sans** `close()` : code de retour 0, rien sur « QThread » dans stderr.
- Changer de film cinq fois de suite pendant la fabrication des vignettes, puis fermer : code 0,
  aucun dossier `vhsrestore_vignettes_*` restant, aucun `ffmpeg` encore en cours.

## 2. L'image du moment est trop petite

**Constat** (mesuré par Claude à 1280 × 641, l'écran de l'utilisateur : 1920 × 1080 à 150 %) :
l'image du moment fait **96 px de haut** sur la page simple (environ 128 × 96) et **56 px** dans
« Enlever un passage ». Trop petit pour qu'un homme de 76 ans voie où couper.

Positions mesurées sur la page simple, après `ensureWidgetVisible(s_couper)` :

| Texte | Image (haut, hauteur) | Barre | « Couper ici » | Bas de « Couper ici » |
|---|---|---|---|---|
| 100 % | 297, 96 | 399, 88 | 547, 74 | 621 / 641 |
| 150 % | 214, 96 | 316, 88 | 518, 103 | 621 / 641 |

**Attendu.**
- Page simple : image du moment d'**au moins 180 px de haut** (environ 240 × 180 en 4:3), et
  l'image, la barre et « Couper ici » **visibles ensemble** à 1280 × 641, texte 100 % et 150 %.
  Pistes pour gagner la place : l'heure sur la ligne du titre (« Enlever une scène — 4 min 10 s »),
  les deux lignes d'aide (légende et « Glissez sur les images… ») réunies en une seule, ou placées
  sous les boutons ; marges verticales réduites ; sur une fenêtre large, l'image à gauche et les
  textes à droite.
- Options avancées : la grande zone « Aperçu avant / après », juste au-dessus, est **vide** tant
  qu'aucun aperçu n'est fait. Montre-y l'image du moment dans ce cas (l'aperçu la remplace dès qu'il
  existe), ou à défaut une image d'au moins 120 px dans « Enlever un passage ». Les colonnes restent
  équilibrées (`test_colonnes_equilibrees` vert).

**Tests d'acceptation.**
- `s_moment.height() >= 180` à 1280 × 641, et après `ensureWidgetVisible(s_couper)`, l'image, la
  barre et « Couper ici » sont entièrement dans la zone visible, texte 100 % et 150 %.
- Aucun défilement horizontal (1366 × 740, 1280 × 720, 1093 × 600, texte 100 / 125 / 150 %).
- `test_colonnes_equilibrees` et les 269 tests actuels restent verts.

## 3. Livraison

- Pousse sur `grok/timeline` (ou `grok/timeline-2`). **Pas de fusion**, pas de PR créée sans
  l'accord de l'utilisateur.
- Mets à jour `partage-grok/RAPPORT-TIMELINE-POUR-CLAUDE.md` : ce qui a changé pour chaque point,
  **toute la suite lancée avec son code de sortie**, les nouvelles mesures de la page simple
  (tableau ci-dessus refait), et ce qui reste non testé.

Merci !
