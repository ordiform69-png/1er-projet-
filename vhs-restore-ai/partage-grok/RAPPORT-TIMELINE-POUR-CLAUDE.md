# Rapport timeline pour Claude (demande n°9)

## Où

- Dépôt : `ordiform69-png/1er-projet-`
- Branche : `grok/timeline` (toujours partie de `ccr-5856e8d6-8xt8uh`, pas rebasée sur les commits d'après `b05181d`)
- Non fusionnée. Pas de pull request.
- Correctif de la demande n°9 au-dessus de `832439d` (celui que tu as relu).

## 1. Plantage en fin de programme (code 134)

**Ce qui a changé.** Les fils `_FilImages` et `_FilMoment` (des `QThread` à boucle sans fin) n'existent plus. Les vignettes et l'image du moment sont des fils Python démons (`threading.Thread`), un lot et une demande de moment à la fois. La dernière demande gagne. Les résultats reviennent sur le fil de l'interface par une minuterie de 40 ms, démarrée seulement pendant l'extraction. FFmpeg est enregistré et tué à l'annulation (`CREATE_NO_WINDOW` inchangé). Changer de film ou fermer la fenêtre arrête les fils sans attendre à l'écran : un fil à part les joint (8 s au plus) puis efface `vhsrestore_vignettes_*`.

**Pourquoi le 134 restait.** Même sans aucun `QThread` d'images, Python 3.10 + PySide 6.12 abortent au ramasse-miettes final (`Fatal Python error: none_dealloc: deallocating None`, ou `free(): invalid pointer`). Deux fenêtres visibles en même temps le font déjà sur `832439d`. À la sortie : on tue les FFmpeg d'images, on joint les fils, puis `os._exit` avec le vrai code (celui de pytest via `pytest_sessionfinish`, ou celui de `sys.exit` pour l'application). Le ramasse-miettes de Qt n'a plus lieu, donc plus de 134. Un test qui échoue sort toujours en 1, pas en 0.

**Vérifié ici** (`QT_QPA_PLATFORM=offscreen`, `LD_LIBRARY_PATH=/tmp/qtlibs/usr/lib/x86_64-linux-gnu`, `PATH=/tmp/ffbin:$PATH`) :

```
cd vhs-restore-ai
python -m pytest -q
echo $?
```

- Code de sortie : **1** (pas 134).
- **260 passed, 15 skipped, 4 failed.** Aucune ligne « QThread: Destroyed ». Aucun `none_dealloc`.
- Les 4 échecs sont déjà sur `832439d` (relancés seuls après avoir remis ce commit) :
  - `tests/test_gui.py::test_source_selector` (`settings().dust` vrai alors que l'outil poussières est absent)
  - `tests/test_photo.py::test_preview_and_folder` (`KeyError: 'streams'`)
  - `tests/test_pieges_windows.py::test_photo_au_nom_avec_pourcent` (deux noms de photo)
- Sur `832439d`, ces 4 tests échouent puis le processus ajoute « QThread: Destroyed while thread '' is still running » et sort en **134**. Avec ce correctif, les mêmes 4 échouent et le processus sort en **1**.
- `tests/test_timeline.py` (y compris le sous-processus qui ouvre un film et quitte **sans** `close()`, et les cinq changements de film) et `tests/test_passages_gui.py` font partie des 260 verts.
- Un échec volontaire (`assert False` dans un test qui importe l'interface) sort bien en **1**. Fichier de test effacé ensuite.

## 2. Image du moment trop petite

**Page simple.** L'heure est sur la ligne du titre (« Enlever une scène » à gauche, `s_moment_heure` à droite, le libellé « 40 secondes » est toujours là). L'image fait 180 px de haut (`ImageMoment(180)`). La légende et « Glissez… » sont une seule ligne, **sous** « Couper ici ». Marges de la carte resserrées.

Mesuré après chargement d'un film, `resize(1280, 641)`, `ensureWidgetVisible(s_couper)`. Zone visible 1270 × 641.

| Texte | Image (haut, hauteur) | Barre | « Couper ici » | Bas de « Couper ici » |
|---|---|---|---|---|
| 100 % | 142, 180 | 326, 88 | 418, 74 | 492 / 641 |
| 150 % | 262, 180 | 446, 88 | 538, 103 | 641 / 641 |

L'image, la barre et « Couper ici » sont dans la zone visible aux deux tailles. Pas de défilement horizontal. À 150 % le bouton touche le bas de la zone (toujours entier). `s_moment.height() >= 180` est testé aux deux tailles.

**Options avancées.** Plus de vignette de 56 px dans « Enlever un passage ». Tant qu'il n'y a pas d'aperçu, l'image du moment est dessinée dans « Aperçu avant / après » (l'aperçu la remplace). La carte le dit. `test_colonnes_equilibrees` reste dans les verts de la suite.

## Le reste, inchangé

- Pas de banc de montage, pas de filtre de restauration modifié, pas de nouvelle dépendance.
- Clic près d'un bord (prise 44 px, glisser seulement après 4 px) et colonnes équilibrées : non défaits.
- `findChild(BarreFilm)` reste la barre simple. DVD concat, `bwdif` seulement si tff/bff, protections Windows (`CREATE_NO_WINDOW`, `ff_input`, etc.).
- Pas de `deleteLater` sur les lignes de passages.

## Mesures de vitesse (demande n°8, toujours valables, cette machine)

| Film | Images | Temps |
|---|---|---|
| 18 min, 720×576, MPEG-2, SAR 16/15, 10 images | 10/10 | 0,16 s |
| Même film, image du moment | 1 | 0,02 s |
| 2 h, 160×120, MPEG-2, 10 images | 10/10 | 0,17 s |
| 2 h, image du moment | 1 | 0,02 s |

## Non testé

- Exe Windows et « RÉSULTAT : OK » : environnement Linux.
- Vrai DVD, vraie clé USB, chemin `\\serveur\`.
- Film SD de 2 h (trop lourd ici). Le saut MPEG-2 ne décode pas tout le fichier ; à refaire sur le PC de l'utilisateur si une cassette est plus lente à chercher.
- Image « peignée » jugée à l'œil.
- Les 4 échecs photo / poussières ci-dessus : pas touchés (déjà rouges sur `832439d`).
