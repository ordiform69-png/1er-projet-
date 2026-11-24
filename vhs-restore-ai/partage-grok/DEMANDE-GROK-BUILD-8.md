# Demande n°8 à Grok Build : construire la timeline (équipe de bots)

Bonjour Grok,

Merci pour la vague « équipe » (`grok/equipe`, fusionnée). Deux corrections ont suivi, à ne pas
défaire : un simple clic près d'un bord doré place le curseur (le bord ne bouge qu'après un vrai
glisser de 4 px, prise de 44 px **en tout**), et, dans les options avancées, le découpage est réparti
en deux cartes compactes (« Début et fin » à gauche, « Enlever un passage » à droite) pour que les
colonnes restent équilibrées (`tests/test_page_avancee.py::test_colonnes_equilibrees`).

**Base** : branche `ccr-5856e8d6-8xt8uh`, commit `fa42d36` ou suivant (version n°71, 260 tests verts).
Lis `DECISIONS.md` (phases 21 à 26 et les ajouts de fin), puis `vhs_restore/gui.py` (`BarreFilm`,
`_rafraichir_barre`, `_barre_cliquee`, `_couper_ici`, cartes « Début et fin » / « Enlever un passage »)
et `vhs_restore/pipeline.py` (`passages_gardes`, `bornes_a_exporter`, `_export_morceaux`).

**La demande de l'utilisateur** : « il faut construire la timeline ». Aujourd'hui, la barre du film
est un ruban bleu et doré **sans aucune image du film** : pour savoir où couper, il faut lancer un
aperçu de 10 secondes, encore et encore. On veut **voir le film sur la barre**.

Travaille comme pour la demande n°7 : **toi, Grok Build, chef d'orchestre**, et les mêmes bots,
qui se parlent dans `partage-grok/equipe/` (`TABLEAU.md`, `ECHANGES.md` numérotés, `DECISIONS-EQUIPE.md`).
Relis `partage-grok/DEMANDE-GROK-BUILD-7.md`, sections 1 à 3 : elles restent valables, sauf ce qui
est écrit ci-dessous.

---

## 1. Ce que doit faire la timeline

1. **Vignettes** : la barre montre une rangée de petites images du film, réparties sur toute sa
   durée (environ une vignette tous les 80 à 100 px de barre ; elles suivent la largeur de la
   fenêtre). Format respecté (4:3 reste 4:3, pixels non carrés de la VHS compris).
2. **Ce qui existe reste** : curseur (triangle), passages enlevés en **doré** par-dessus les
   vignettes (assez transparent pour voir l'image dessous, assez net pour voir la coupe), début et
   fin gardés, bords dorés tirables, clic et glisser pour se placer, flèches ←/→, Entrée = couper,
   légende « Bleu : ce qui sera restauré. Doré : ce qui est enlevé. » (à adapter si le bleu disparaît).
3. **Grande image du moment** : au-dessus de la barre, l'image du film à la position du curseur,
   avec l'heure en clair (« 12 min 34 s »). Elle suit le curseur quand on glisse, sans saccade
   (une demande à la fois, la dernière gagne). Taille raisonnable : sur l'écran de l'utilisateur
   (1920 × 1080 à 150 %, soit 1280 × 641 visibles), la grande image, la barre et « Couper ici »
   tiennent ensemble sans défiler.
4. **Page simple ET options avancées** : la page simple garde ses gros boutons ; dans les options
   avancées, la carte « Enlever un passage » reçoit la même timeline (plus petite). **Un seul état**
   (`_coupes`, position, début / fin) : les deux barres se mettent à jour ensemble.
5. **Pendant la fabrication des vignettes**, la barre reste utilisable (vignettes grises qui
   apparaissent une à une), rien n'est bloqué, et « Voir l'avant / après » / « Restaurer » restent
   possibles. Un autre film ouvert annule la fabrication en cours.

## 2. Contraintes propres à la timeline

- **FFmpeg seulement** pour extraire les images (aucune nouvelle dépendance : pas d'OpenCV, pas de
  lecteur vidéo intégré). Extraction rapide par saut (`-ss` avant `-i`, une image, petite taille),
  dans un fil à part, **qui ne passe pas par `self.worker`** (sinon `_busy()` bloquerait tout).
  `CREATE_NO_WINDOW` (`tools._NO_WINDOW`) pour chaque sous-processus. Fichiers dans un dossier
  temporaire propre au film, supprimés à la fermeture ou au changement de film ; aucune image écrite
  à côté du film de l'utilisateur.
- **Vitesse** : film de 18 min en SD (MPEG-2, le cas de l'utilisateur) : vignettes visibles en moins
  de 10 s sur un PC modeste, mesurées et notées dans le rapport ; grande image du moment en moins
  d'une demi-seconde. Mesure aussi un film de 2 h.
- **Entrelacé** : pas de vignette « peignée » (désentrelacement simple pour les vignettes seulement).
- **DVD en plusieurs morceaux** (VTS_01_1.VOB, _2…) : les vignettes couvrent tout le titre, pas le
  premier morceau seulement (voir `dvd.py`, `info.parts`).
- **Film sans durée connue** (« N/A ») ou très court (< 20 s) : pas de plantage, barre utilisable.
- **Accessibilité** : la timeline garde ses noms pour le lecteur d'écran ; la grande image a un
  texte alternatif (« Image du film à 12 min 34 s »).
- La règle « pas de vignettes sur la barre » des demandes précédentes est **levée** : c'est
  exactement ce que l'utilisateur demande. **Tout le reste de l'interdit tient** : pas de banc de
  montage (pas de titres, de musique, de plusieurs films, de morceaux déplacés, de transitions),
  pas de levée du refus IA / poussières / bande / cadence pour une coupe au milieu, assemblage
  `-c copy`, pas de `deleteLater` sur les lignes de passages, aucun code copié d'OpenShot,
  LosslessCut, Shotcut ou Clipchamp, aucune nouvelle dépendance.
- À ne pas défaire : clic près d'un bord = placer le curseur ; colonnes équilibrées ; aucun
  défilement horizontal à 1366 × 740, 1280 × 720, 1093 × 600 (texte 100 / 125 / 150 %) ; protections
  Windows (`finaliser`, `effacer`, `verifier_chemin`, `ff_input`, `check_fat32`).

## 3. Répartition proposée (à confirmer par le chef après les analyses)

| Bot | Rôle pour la timeline |
|---|---|
| Montage | **Pilote** : `BarreFilm` avec vignettes, grande image du moment, deux barres liées au même état |
| Windows | Fil d'extraction : annulation, fichiers temporaires, sous-processus sans fenêtre, film sur clé USB ou réseau, DVD en morceaux, film de 2 h |
| Image et son | Justesse des vignettes : format 4:3, pixels VHS, entrelacement, couleurs ; mesures de vitesse |
| Parcours senior | Place et taille de la grande image et de la barre sur la page simple (1280 × 641), lisibilité, ce que l'utilisateur comprend sans aide |
| Aide et textes | Légende, textes, `LISEZMOI.txt` (« Enlever une scène » avec la timeline), fenêtre « Bienvenue » |
| Contrôle | Relecture de chaque branche, tests, robot d'audit, captures réelles (hors dépôt) |

Questions que les bots doivent se poser entre eux (dans `ECHANGES.md`) avant de coder : où mettre
la grande image sur la page simple sans repousser « Couper ici » sous l'écran ? Combien de
vignettes selon la largeur ? Que montrer tant qu'une vignette n'est pas prête ? Comment éviter
deux extractions en même temps quand on glisse vite ?

## 4. Tests attendus (en plus des 260 existants, tous verts)

- Un film de synthèse dont chaque tranche a une couleur connue : les vignettes sont dans le bon
  ordre et à la bonne place.
- L'interface n'est jamais bloquée pendant l'extraction (un clic sur la barre répond aussitôt).
- Changement de film pendant l'extraction : la fabrication s'arrête, aucun fichier ne reste.
- Les deux barres (simple / avancée) montrent les mêmes coupes après chaque geste.
- Grande image : suit le curseur ; la dernière demande gagne.
- Mise en page : pas de défilement horizontal, colonnes équilibrées, la grande image, la barre et
  « Couper ici » visibles ensemble à 1280 × 641.

## 5. Livraison

- Branche d'intégration `grok/timeline` (partie de la dernière `ccr-5856e8d6-8xt8uh`), branches des
  bots `grok/timeline-<rôle>`. **Une PR** vers `ccr-5856e8d6-8xt8uh`, que tu ne fusionnes pas.
- `partage-grok/RAPPORT-TIMELINE-POUR-CLAUDE.md`, avec ces rubriques : **Où** (branche, commit) ·
  **Fait, ne pas refaire** · **Interdit respecté** · **Vérifié ici** (tests lancés, combien, en
  combien de temps ; toute la suite ou non) · **Mesures** (vitesse des vignettes, 18 min et 2 h) ·
  **Écarté, et pourquoi** · **Non testé** (exe Windows, vrai DVD…).
- La construction Windows verte (essai automatique de l'exe « RÉSULTAT : OK »).

Merci !
