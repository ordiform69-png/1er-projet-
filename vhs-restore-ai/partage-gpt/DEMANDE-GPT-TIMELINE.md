# Pour ChatGPT : améliorer la timeline (barre du film) — état du projet et consignes

Rédigé par Claude le 26 novembre 2026. Dépôt `ordiform69-png/1er-projet-`, code dans
`vhs-restore-ai/`, décisions dans `vhs-restore-ai/DECISIONS.md`, mémoire de travail dans
`CLAUDE.md` (racine).

## 1. Le projet en bref

VHS Restore AI : logiciel gratuit (Python, PySide6, FFmpeg) qui restaure les cassettes VHS et les
photos de famille. Il est utilisé par un homme de 76 ans. Son écran : 1920 × 1080 à 150 %, soit
**1280 × 641 points utiles** ; le logiciel doit aussi tenir sur les écrans standard (1024 × 689 à
2560 × 1361, `tests/test_ecrans.py`). L'original n'est jamais modifié ; vouvoiement et mots
simples partout ; les options sont nommées partout comme à l'écran.

## 2. État au 26 novembre (mises à jour récentes)

- **Assistant en 5 étapes**, selon des maquettes choisies par l'utilisateur : Rendu, Lumière et
  couleurs, **Couper le film**, Son, Vérifier et lancer (photo : 3 étapes). Repères d'étapes à
  gauche, boutons verts, « Rien à changer ? Cliquez sur Suivant. ». « Réglages libres » donne
  l'écran complet (sections Qualité, Lumière et couleurs, Couper le film, Régler l'image, Régler
  le son).
- Rendus : « Nettoyage léger », « Bien nettoyé, naturel (conseillé) », « Nettoyage au plus fort »
  (clés internes `fidele`, `equilibre`, `maximum`).
- Lumière et couleurs : 4 réglages de −3 à +3, image avant / après tout de suite.
- Durée et place annoncées avant de lancer (calibrées sur la vraie restauration).
- Écrans standard ; texte plus grand d'office sur grand écran ; « A » / « A+ » grisés si l'écran
  est trop petit.
- En validation (demande n°17, branche `grok/qualite`) : lumière et couleurs **scène par scène**
  (analyse des scènes en arrière-plan, `scenes.py`, `info.scenes`), calcul en 10 bits, contrôle de
  la numérisation.
- Demande n°18 (essai d'IA) : conclusion, aucune IA ajoutée ; Real-ESRGAN gardé.
- En cours chez Grok (demande n°19, branches `grok/reprise*`) : reprendre une restauration
  interrompue. Ces branches ne touchent pas la timeline.

## 3. La timeline aujourd'hui

- Code : `vhs_restore/gui.py`, classes `_Ruban`, `BarreFilm`, `BarreCompacte`, `SchemaCoupe`
  (lignes ~798 à 1076) ; petites images : `vhs_restore/vignettes.py` ; mise en place dans la section
  « Couper le film » : `vhs_restore/ecran.py` (fonction `installer`, partie `contenu("Couper le
  film")`) ; l'assistant emprunte cette section (`assistant.py`, `_emprunter_coupe`).
- Ce qu'elle fait : petites images du film (environ une tous les 90 pixels, extraites par FFmpeg
  dans un fil à part), image du moment au-dessus avec l'heure ; début et fin du film (bords
  dorés, « Ici ») ; passages enlevés au milieu (« Couper ici » puis « Le film reprend ici »,
  « Annuler la dernière coupe », liste des passages avec « Remettre ») ; « Chercher la neige… »
  (neige, écran bleu ou noir trouvés par `vides.py`).
- Histoire et règles : `DECISIONS.md`, parties « Timeline (phase 29) », « Découpage du début et de
  la fin », « Passages enlevés au milieu ».
- Tests : `test_timeline.py`, `test_barre_montage.py`, `test_coupe_un_clic.py`,
  `test_passages_gui.py`, `test_guide_coupes.py`, `test_vides_montage.py`, et pour la taille
  `test_ecran_unique.py`, `test_ecrans.py`, `test_assistant.py`.

## 4. Pistes, dans l'ordre conseillé par Claude

Envoyez d'abord une **proposition courte** (une page : ce que vous changez, où, comment vous le
testez). Puis le code, une piste par commit.

1. **Précision sur une longue cassette.** Sur 2 à 3 heures, un pixel de la barre vaut 10 à 15
   secondes : couper au bon endroit est difficile. Loupe ou zoom autour du curseur ; flèches du
   clavier (1 s, 10 s avec Maj) ; image précédente / suivante.
2. **Montrer ce que le logiciel a trouvé.** Passages vides (neige, écran bleu ou noir) en zones
   bien visibles, avec « Enlever » en un clic ; changements de scène (`info.scenes`, disponible
   quand l'analyse de fond est finie) en petits repères ; les coupes « s'aimantent » à ces repères.
3. **Lisible pour 76 ans.** Poignées plus grandes, heure au survol, passages enlevés hachurés,
   contraste suffisant (thèmes clair et sombre, `theme.py`).
4. **Petites images plus rapides.** Les garder par film (pas de nouvelle extraction à chaque
   ouverture de la section), nombre adapté à la largeur de la barre.

## 5. Règles

- Branche `gpt/timeline`, partie de `ccr-5856e8d6-8xt8uh` au commit `f484b40` (ou plus récent).
  Chaque commit poussé tout de suite. **Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request.**
- Fichiers : les 4 classes de la timeline dans `gui.py`, `vignettes.py`, la partie « Couper le
  film » d'`ecran.py`, un nouveau `timeline.py` si utile. **Ne pas déplacer** le code existant
  (d'autres chantiers modifient `gui.py` ailleurs : un déplacement créerait des conflits). Ne pas
  toucher au moteur (`pipeline.py`, `scenes.py`, `estimation.py`).
- La fenêtre ne grandit jamais : 1280 × 641 à 100, 125 et 150 % de texte, aucun défilement de
  côté, aucun défilement à 100 et 125 % dans l'assistant ; écrans standard de `test_ecrans.py`.
- Aucune nouvelle dépendance Python ; FFmpeg seulement ; rien de lent dans le fil de l'écran.
- Aucun test affaibli (un texte renommé : l'assertion vérifie le nouveau texte).
- Tests : seulement les fichiers cités au point 3 (la suite complète dure une heure ; Claude la
  lance avant toute fusion). Aucune capture, aucun zip dans le dépôt.
- Rapport : `vhs-restore-ai/partage-gpt/RAPPORT-GPT-TIMELINE.md` : Où (branche, hash de chaque
  commit) · Fait · Vérifié (fichiers lancés, nombres, codes de sortie) · Non testé.
  Claude vérifie, mesure, et fusionne quand l'utilisateur écrit « fusionner ».
