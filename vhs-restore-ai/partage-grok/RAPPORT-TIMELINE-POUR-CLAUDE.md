# Rapport timeline pour Claude

## Où

- Dépôt : `ordiform69-png/1er-projet-`
- Branche : `grok/timeline` (partie de `ccr-5856e8d6-8xt8uh`, commit de départ `b05181d`)
- Non fusionnée.
- Fichiers : `vhs_restore/vignettes.py` (nouveau), `vhs_restore/gui.py`, `tests/test_timeline.py`, `LISEZMOI.txt`, `DECISIONS.md`, `partage-grok/equipe/`.

## Fait, ne pas refaire

- La barre de la page simple montre des petites images du film (une tous les 90 px), gris tant qu'elles ne sont pas prêtes, puis l'image.
- Au-dessus : l'image du moment et l'heure (« 12 min 34 s »). Texte alternatif : « Image du film à … ».
- La carte « Enlever un passage » a la même barre, plus petite (`BarreCompacte`), et la même image. Un seul état (`_coupes`, curseur, début, fin).
- Le doré des coupes est par-dessus les images (transparent). Clic près d'un bord = se placer. Glisser de 4 px = tirer le bord. Prise 44 px en tout. Entrée = couper. Flèches inchangées.
- `findChild(BarreFilm)` reste la barre du mode simple.
- Extraction FFmpeg : `-ss` avant `-i`, une image, `-an`, `CREATE_NO_WINDOW`, fil à part (pas `self.worker`). Dossier `vhsrestore_vignettes_`, jamais à côté du film. DVD : tous les VOB. Changer de film annule et efface. La dernière demande d'image du moment gagne.
- `bwdif` seulement si le balayage est tff ou bff. 720×576 en pixels 16/15 reste du 4:3.
- Légende : « Les petites images montrent le film. Doré : ce qui est enlevé. »
- LISEZMOI et « Bienvenue » le disent, sans le mot « timeline ».

## Interdit respecté

- Pas de banc de montage (pas de titres, musique, plans déplacés, transitions).
- Pas de levée du refus IA / poussières / bande / cadence. Assemblage `-c copy` inchangé.
- Aucun code d'OpenShot, LosslessCut, Shotcut ou Clipchamp. Aucune nouvelle dépendance.
- Pas de `deleteLater` sur les lignes de passages.
- Clic près d'un bord et colonnes équilibrées : non défaits (tests verts).
- Aucun filtre de restauration modifié.

## Vérifié ici

```
QT_QPA_PLATFORM=offscreen
LD_LIBRARY_PATH=/tmp/qtlibs/usr/lib/x86_64-linux-gnu
PATH=/tmp/ffbin:$PATH
pytest tests/test_timeline.py tests/test_barre_montage.py tests/test_coupes_bords.py \
  tests/test_page_avancee.py tests/test_passages_gui.py tests/test_coupe_un_clic.py \
  tests/test_ergonomie.py::test_texte_sans_defilement_horizontal
```

9 tests timeline, puis barre, coupes, page avancée (colonnes), passages, coupe un clic : verts.
Défilement horizontal (1366×740, 1280×720, 1093×600, texte 100/125/150 %) : vert, 7 s.
Toute la suite (environ 260) n'a pas été relancée.

## Mesures

Machine de l'environnement (Linux, FFmpeg du banc), pas le PC de l'utilisateur.

| Film | Images | Temps |
|---|---|---|
| 18 min, 720×576, MPEG-2, SAR 16/15, 10 images (barre de 900 px) | 10/10 | 0,16 s |
| Même film, image du moment (y compris près de la fin) | 1 | 0,02 s |
| 2 h, 160×120, MPEG-2, 10 images | 10/10 | 0,17 s |
| 2 h, image du moment | 1 | 0,02 s |

Le nombre d'images dépend de la largeur, pas de la durée. Un film SD de 2 h n'a pas été fabriqué ici (fichier trop lourd) : le saut MPEG-2 ne décode pas tout le film, le temps reste celui du nombre de sauts. Sous 10 s et sous 0,5 s, ici. À refaire sur le PC de l'utilisateur si un vrai MPEG-2 de cassette est plus lent à chercher.

## Écarté, et pourquoi

- Bots séparés : le lanceur a fermé le flux trois fois. Le chef a fait les six rôles (D-014).
- Exe Windows et « RÉSULTAT : OK » : cet environnement est Linux, l'exe n'a pas été construit.
- Vignettes calculées sur la durée (une par minute) : trop lent sur une cassette de 2 h, et illisible. Le pas de 90 px tient la demande.
- Désentrelacer les films progressifs : inutile, et ce n'est pas le filtre de restauration.

## Non testé

- Toute la suite.
- Construction Windows de l'exe. Pas de « RÉSULTAT : OK ».
- Vrai DVD, vraie clé USB, vrai chemin `\\serveur\`, cassette d'une heure sur le PC de l'utilisateur.
- Image « peignée » jugée à l'œil sur une vraie cassette entrelacée (le filtre `bwdif` est bien mis seulement dans ce cas, testé sur la chaîne).
