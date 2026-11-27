# Demande n°21 : corriger les bugs confirmés de la n°20 (pour le chef des bots)

Claude a vérifié la n°20 sur la base `a652864` :
- les 35 tests des cinq branches échouent, et 34 échouent pour la raison annoncée ;
- le test de D1 plante dans sa propre préparation (`os.fsync(1)` sur un tube lève une erreur
  sous Linux) : il ne prouve rien tel quel, et il est à refaire ;
- C1 est confirmé dans le code : l'aide du premier lancement est un seul `QMessageBox` au texte
  très long, en 14 pt.

Bon travail, preuves solides. Cette fois : corriger.

## Base, branches, équipe

- Base : `ccr-5856e8d6-8xt8uh` au commit `a652864` (ou plus récent). Chaque agent reprend son
  fichier de tests de la n°20 :
  `git checkout origin/grok/bugs-<x> -- vhs-restore-ai/tests/test_bugs_n20_<x>.py`
- **Règle des tests de la n°20 : un bug corrigé = le marqueur `xfail` retiré de son test, qui
  doit passer.** Un test `xfail(strict=True)` qui passe fait échouer la suite : un test oublié se
  voit tout de suite.

| Agent | Branche | Constats | Fichiers et fonctions à lui (personne d'autre n'y touche) |
|---|---|---|---|
| A | `grok/corr-a-son` | A3, A1, A4, A2, E2 | `pipeline.py` : `_atempo_chain`, `_atempo_filters`, filtres du son (`audio_filters`, `audio_args`), collage des passages et des parties (partie son) ; `probe.py` : texte de l'écart de durée |
| B | `grok/corr-b-image` | B2, B3, B4 | `pipeline.py` : `pre_filters` et ses aides (dominante, teinte, `chromashift`, masque du bas) ; `lumiere.py` |
| C | `grok/corr-c-ecran` | C1, C2, C3, C4, C5 | `gui.py` : `show_welcome`, taille de la fenêtre (`__init__`, `resizeEvent`, géométrie), dessin du moniteur, petites images de la barre ; `ecran.py` (« Détails du fichier ») ; `vignettes.py` |
| D | `grok/corr-d-windows` | D1, D3, D4 et E7, D6, D2, D7, D5 | `tools.py`, `ergonomie.py`, `installer.py` (7-Zip), `pipeline.py` : `check_fat32` seulement ; `gui.py` : `_eteindre_a_la_sortie` seulement |
| E | `grok/corr-e-fin` | E6, E3, E1, E4, E5, E8, E9, E10 | `gui.py` : « Arrêter », message de démarrage (`main`) ; `partage.py` ; `estimation.py` ; `pipeline.py` : avancement (`_FFProgress`, copie du son) |
| Chef | `grok/corrections-n21` | intégration | fusion A, B, C, D, E dans cet ordre, conflits réglés sans rien perdre ; rapport |

`pipeline.py` et `gui.py` sont partagés : chacun ne touche que ses fonctions. Il ne déplace pas
de code et ne renomme rien.

## Ce qu'il faut corriger, avec les choix déjà faits

### A : son et image calés

- **A3** : une dérive, même petite, est corrigée. Le seuil de `_atempo_chain` passe de 1e-4 à
  1e-7.
- **A1** : plus aucun retard du son aux raccords des passages gardés. Chaque morceau a un son
  exactement de la durée de son image (`apad` et `atrim` au nombre d'images, comme les parties de
  la reprise), ou bien le son est réencodé une fois après le collage. Choisir le plus sûr et
  mesurer : 12 coupes, dernier bip à moins de 10 ms.
- **A4** : le profil « Bien nettoyé » ne mange plus le début du son. Le bip à 0 s reste audible.
  Trouver lequel des trois filtres, ensemble, efface le premier instant (`dynaudnorm` est
  suspect), et corriger sans retirer le filtre.
- **A2** : `afftdn` ne retarde plus le son de 24 ms, et la fin n'est plus coupée.
- **E2** (donné à A, même sujet). Ce n'est pas bloquant : les millisecondes par minute sont
  calculées sur la durée du film lui-même. Sur un film de 3 h, un écart de 0,5 s donne environ
  3 ms par minute, pas 1 500. Mais le message ne doit pas faire passer un simple décalage pour une
  dérive :
  - film de moins de 10 minutes : parler de « décalage », sans chiffre par minute ;
  - au-delà, garder la phrase prudente actuelle.

### B : image

- **B2** : « Plus chaude » ou « Plus froide » arrive dans le film même quand la dominante est déjà
  au plafond. La teinte s'applique après le plafond de la dominante, avec son propre plafond.
  L'aperçu et le film doivent donner le même résultat, à 3 niveaux près.
- **B3** : le décalage de couleur compte en pixels d'image. La valeur demandée est divisée par
  deux pour `chromashift` en 4:2:0 et en 4:2:2, arrondie. L'écran garde « px ».
- **B4** : le masque du bas suit la taille de sortie. 16 lignes de 576 donnent environ 30 lignes
  en 1080.
- B1 (scintillement) : pas dans cette demande. L'option est rare (pellicule) et la correction est
  risquée. Une ligne dans le rapport, comme limite connue.

### C : écran, d'abord ce que le père voit en premier

- **C1** : l'aide du premier lancement tient sur l'écran (1280 × 641 à 100, 125 et 150 % de texte,
  et 1093 × 535) :
  - une fenêtre à part (`QDialog`), avec le texte dans une zone qui défile ;
  - le bouton « C'est parti » toujours visible en bas, actif avec Entrée ;
  - Échap ferme la fenêtre ;
  - les mêmes mots, et le même texte au même endroit pour « Aide ».
- **C2** : la taille « normale » de la fenêtre ne dépasse jamais l'écran (1100 × 760 au plus,
  ramenée à l'écran disponible). « Lancer la restauration » reste visible.
- **C3 et C4** : l'image du moniteur et les petites images de la barre sont préparées en vrais
  pixels d'écran. Même méthode que la correction `2dc2f2a` de `assistant.py` : taille ×
  `devicePixelRatio`, puis `setDevicePixelRatio`. Elles doivent être nettes à 125 et 150 %.
- **C5** : « Détails du fichier » ne dépasse pas l'écran disponible.

### D : Windows, fichiers, disque

- **D1** : FFmpeg ne survit pas au logiciel. Sous Windows, un « Job Object » avec
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (ctypes, aucune dépendance) auquel chaque FFmpeg est
  rattaché. Sous Linux, rien de nouveau. Le test de la n°20 est à refaire : écrire le pid sans
  `os.fsync` sur le tube.
- **D3** : disque plein compris en français. Les textes à reconnaître : « No space left on
  device », « There is not enough space on the disk », « Espace insuffisant sur le disque »,
  `errno 28`. Message : « Le disque est plein… » avec la place nécessaire si elle est connue.
- **D4 et E7** (une seule correction) : un verrou `.reserve` laissé par un arrêt brutal ne fait
  plus sortir le film sous le nom « (2) ». Un verrou de plus de 12 heures, ou que personne ne
  tient (essai d'ouverture exclusive), est effacé puis repris. Les deux tests (D4, E7) doivent
  passer.
- **D6** : `-sccUTF-8` aussi pour l'extraction 7-Zip.
- **D2** : type de volume inconnu et film estimé à plus de 4 Go : un **avertissement**, pas un
  refus (un disque réseau en NTFS est courant).
- **D7** : le message de chemin trop long donne la longueur réelle.
- **D5** : `_eteindre_a_la_sortie` efface aussi les dossiers d'aperçu et de « Lumière ».
- D8, D9, D10 : pas dans cette demande. Ils seront mesurés sous Windows par Claude, sur le PC de
  l'utilisateur, si besoin.

### E : fin du travail et copies

- **E6** : « Arrêter » arrête aussi la copie de lecture. Elle reprendra plus tard d'elle-même,
  comme à l'ouverture.
- **E3** : « Arrêter » pendant la séparation en films efface les films déjà écrits de cette
  séparation. Sinon, le message dit exactement ce qui reste. Jamais « Votre film n'a pas été
  modifié » si un fichier a été écrit.
- **E1** : copie d'une capture SD sans format (720 × 576 ou 720 × 480, SAR 1:1) : 4:3, la même
  règle que l'analyse (`probe`).
- **E4** : la durée annoncée n'est jamais plus courte que le calcul : arrondie au quart d'heure
  supérieur au-delà d'une heure (« environ 1 h 30 » pour 1 h 19).
- **E5** : durée inconnue : la barre avance selon la taille lue, ou bien elle reste en mode
  « occupé », mais jamais 100 % dès le début.
- **E8** : « Nommer » avec le nom actuel ne change rien.
- **E9** : la copie du son restauré fait avancer la barre.
- **E10** : au démarrage, un FFmpeg incomplet est expliqué par `ergonomie.expliquer` (« réinstallez
  le logiciel »), sans noms de filtres.

## Tests

- Chaque agent : son `tests/test_bugs_n20_<x>.py` (marqueurs retirés, tous verts), plus :
  - **A** : `test_son.py`, `test_aac_ffmpeg9.py`, `test_montage.py`, `test_reprise.py`, `test_bande.py` ;
  - **B** : `test_lumiere.py`, `test_chroma.py`, `test_dominante.py`, `test_plafonds.py`, `test_pipeline.py` ;
  - **C** : `test_ecran_unique.py`, `test_ecrans.py`, `test_assistant.py`, `test_timeline.py`, `test_senior.py`, `test_gui.py` ;
  - **D** : `test_installer.py`, `test_pieges_windows.py`, `test_ergonomie.py`, `test_arret_travail.py` ;
  - **E** : `test_partage.py`, `test_partage_gui.py`, `test_estimation.py`, `test_arret_travail.py`, `test_copie_lecture.py`.
- Pour juger la couleur ou la lumière dans le temps : jamais une mire seule. La recette du film
  réaliste est dans la n°20.
- Bac à sable sans FFmpeg ou PySide6 : écrire quand même, marquer « non lancé ». Claude lance.

## Règles

- Chaque commit poussé tout de suite, avec `[skip ci]` à la fin du titre. Une correction par
  commit, avec le nom du constat dans le titre (« A3 : … »).
- Seulement les fichiers de tests cités, pas la suite complète : Claude la lance avant la fusion.
- Aucune nouvelle dépendance, aucun test existant affaibli. Un texte d'écran changé : l'assertion
  vérifie le nouveau texte.
- Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request.
- Rapport du chef : `partage-grok/RAPPORT-N21-POUR-CLAUDE.md` sur `grok/corrections-n21`.
  Pour chaque constat : commit, test vert ou « non lancé », et ce qui reste.
