# Demande n°2 à GPT Astra : corriger les constats de votre rapport

Bonjour,

Merci pour `RAPPORT-GPT-ASTRA.md`. Claude a vérifié vos 15 constats : **tous sont exacts**
(`partage-gpt/VERIFICATION-CLAUDE.md` : 6 reproduits aux mêmes chiffres, les autres relus dans le
code). L'utilisateur vous confie maintenant **les corrections**.

## 1. Où travailler, et comment livrer

- Dépôt `ordiform69-png/1er-projet-`, partez de la branche **`ccr-5856e8d6-8xt8uh`** (commit `948f068`
  ou suivant ; le code est identique à celui que vous avez audité, seuls des documents ont changé).
- Travaillez sur une branche **`astra/corrections`**, **un commit par constat** (message en français,
  qui cite le n°). **Ne fusionnez pas, ne créez pas de pull request, ne poussez sur aucune autre branche.**
- Si vous ne pouvez pas pousser sur GitHub : livrez un fichier de correctifs par lot
  (`git format-patch`), que l'utilisateur transmettra à Claude.
- Livrez lot par lot (1, puis 2, puis 3) ; un lot peut être relu et fusionné avant le suivant.
- **Tests** : `pip install -r requirements.txt -r requirements-dev.txt`, FFmpeg dans le PATH, puis
  `QT_QPA_PLATFORM=offscreen python -m pytest -q` (260 tests, environ 15 min). Si votre environnement
  ne peut pas les lancer (vous n'aviez ni pytest ni PySide6), **dites-le clairement** dans le rapport :
  Claude lancera toute la suite avant toute fusion. Chaque correction a **son propre test**, qui échoue
  sans elle.

## 2. Règles non négociables

- L'original n'est **jamais** modifié ; 4:3 et son gardés ; aucun traitement plus fort. **Ne changez
  pas les filtres de restauration ni les réglages par défaut** (débruitage, netteté, profils, IA).
- Utilisateur de 76 ans : textes en français, **vouvoiement**, phrases courtes, options nommées
  **comme à l'écran** ; aucune décision prise à sa place (proposer, ne pas décocher en silence).
- **Aucune nouvelle dépendance.** Pas d'exe, de zip, de capture ni de média de test dans le dépôt.
- Gardez les protections Windows existantes et utilisez-les pour tout fichier écrit :
  `tools.finaliser` / `effacer` / `verifier_chemin` / `ff_input`, `pipeline.check_fat32`,
  `CREATE_NO_WINDOW` (`tools._NO_WINDOW`).
- **Ne touchez pas à la timeline** (`BarreFilm`, `BarreCompacte`, `vignettes.py`, fils d'images) :
  Grok la corrige sur `grok/timeline` (`partage-grok/DEMANDE-GROK-BUILD-9.md`). Pour le n°4, changez
  `closeEvent` le moins possible et dans un commit à part : Claude rapprochera les deux branches.
- Gardez les noms utilisés par les tests (`s_status`, `s_fini`, `run_btn`, `pages`, `segments`…)
  ou renommez-les partout. Pas d'identifiant de modèle d'IA dans les commits ni le code.

## 3. Lot 1 : sûr et rapide

| N° | À faire | Test d'acceptation |
|---|---|---|
| 1 | **Ne jamais écraser un fichier.** Réserver ensemble toutes les sorties d'un travail (MP4, WAV / FLAC, PNG, copie colorisée) ; si l'une existe, prendre un autre nom pour **toutes** (« (2) »). Partiel au nom propre au travail (pas un nom prévisible que la relance écrase) ; à la publication, ne jamais remplacer un fichier arrivé entre-temps. Le message « renommez ce fichier » de `FichierOccupe` donne le vrai nom du partiel. | Un WAV témoin et un `.partiel.mp4` témoin préexistants gardent leur contenu ; deux exports simultanés du même film donnent deux jeux de fichiers complets. |
| 2 | **Reconnaître un travail déjà fait sans confusion.** `Noel.jpg` et `Noel.png` dans un même dossier : deux résultats. « Déjà fait » seulement si la même source (chemin, taille, date) a été restaurée avec les **mêmes réglages effectifs** (décalage son compris) et que ses sorties existent ; sinon un nom libre. | Les deux photos restaurées ; relance identique : les deux sautées ; relance avec un autre décalage son : refaites. |
| 4 | **Fermeture propre.** Rendre l'analyse annulable (`probe.py`, `photo.py`, `dvd.py` : plus d'attente de 300 s sans annulation) ; au clic sur Quitter pendant un travail, demander l'arrêt, garder la fenêtre réactive, fermer quand le travail est **vraiment** fini (ne plus ignorer le résultat de `wait`). | Sous-processus Python : fenêtre, analyse volontairement lente, demande de fermeture → code de sortie 0, aucune ligne « QThread: Destroyed », dossiers temporaires effacés. |
| 12 | Un délai dépassé (`subprocess.TimeoutExpired`) devient une erreur **du fichier concerné** ; le dossier continue. | Délai simulé sur le 2e élément d'un lot de 3 : le 3e aboutit, le 2e est listé en échec avec une phrase claire. |
| 10 | **Fabrication Windows** (`.github/workflows/vhs-restore-windows.yml`) : l'artefact n'est déposé que si les tests **et** l'essai automatique réussissent ; nom du zip avec numéro de fabrication et commit ; empreinte SHA-256 publiée avec. | Relecture du workflow ; un test rouge empêche le dépôt. |
| — | `pipeline.bornes_a_exporter(0, 5, 0, [])` renvoie une durée de **−5 s** : fin inconnue = fin ouverte (`None`) jusqu'à la commande FFmpeg. | Ce cas renvoie une durée `None` ou positive, jamais négative. |

## 4. Lot 2 : plus délicat (mesurer avant / après)

| N° | À faire | Test d'acceptation |
|---|---|---|
| 3 | **Son au raccord des coupes.** Calculer la fenêtre son de chaque morceau depuis le temps de la source, **décalage et dérive compris**, bornée à la durée image du morceau ; du silence seulement au bord réellement manquant. L'assemblage reste `-c copy`, sans seconde compression. Remplacez le test trop large de `tests/test_montage.py` (n°15). | Votre essai : [0,2] et [4,6] à +400 ms → durée ≈ 4,02 s, aucun écart d'image > 40 ms ; idem à −400 ms et avec une dérive ; un « clap » (flash + bip) reste synchrone à ± 40 ms après chaque raccord. |
| 5 | **Couleurs.** En résolution d'origine, garder matrice, primaires, transfert et plage de la source quand ils sont connus ; en conversion HD, des étiquettes qui correspondent à la conversion réellement faite (`in_color_matrix` d'après la source). Rien ne change pour une VHS PAL / SECAM ou NTSC SD sans étiquette. | Source BT.709 → sortie BT.709 ; source PAL SD → inchangée (`bt470bg`) ; conversion HD vérifiée sur une mire colorée décodée en RGB. |
| 6 | **Son jugé muet trop vite.** Mesurer plusieurs extraits (début, milieu, fin) au lieu des seules 300 premières secondes ; phrase « Aucun son entendu dans les extraits analysés » ; ne pas couper le nettoyage du son sur un seul extrait silencieux. | Cassette de 303 s : silence jusqu'à 301 s puis voix → pas déclarée muette. |
| 7 | **Échec partiel dit honnêtement.** Le résultat principal et l'état de chaque copie (WAV / FLAC, couleurs) sont rendus séparément : « Votre photo restaurée est prête. La copie en couleur a été interrompue. », avec « Ouvrir le dossier » ; la relance d'un dossier refait seulement la copie manquante. | Colorisation annulée après l'écriture du PNG : écran « prêt » avec la phrase ; relance : seule la copie couleur est refaite. |
| 8 | **Mode IA : place disque.** Vérifier le MP4 sur le disque de destination **et** l'intermédiaire (FFV1, PNG, WAV) sur le disque de travail, additionnés s'ils sont sur le même disque, **avant** le prétraitement. | Deux disques simulés, destination trop petite : refus immédiat avec un message clair. |
| 9 | **Essai de vitesse de l'IA.** Avant un aperçu ou une restauration avec « Amélioration IA », chronométrer 2 ou 3 images (démarrage du modèle à part), extrapoler à la cadence de sortie ; si c'est très long (par exemple plus de 3 fois la durée du film, ou plus de 2 h), demander : « Continuer sans l'IA » / « Continuer avec l'IA » / « Annuler », en donnant la durée estimée en mots. Rien n'est décoché sans réponse. Remplacer le comptage des images à délai fixe (60 s) par une opération annulable. | Agrandisseur factice à 30 s / image : la question apparaît avant tout long travail, avec une estimation juste à ± 20 % ; « Continuer sans l'IA » lance sans IA. |

## 5. Lot 3

| N° | À faire | Test d'acceptation |
|---|---|---|
| 11 | `scripts/installer_outils.ps1` : mêmes versions et empreintes que `installer.py` (un seul manifeste lu par les deux), téléchargement dans un temporaire, vérification, puis mise en place. | Empreinte fausse ou téléchargement interrompu : rien d'installé, relance propre. |
| 13 | Archives : appartenance au dossier par composants de chemin (pas un préfixe de texte), membres examinés **avant** écriture, liens refusés. | L'entrée `../installe-voisin/hors.txt` est refusée. |
| 14 | DVD : liste `concat` temporaire effacée après usage ; un morceau manquant (`VTS_01_1`, `VTS_01_3`) est signalé avant d'annoncer un film réuni. | Plus de dossier `vhsrestore_dvd_*` après l'export ; avertissement pour le trou. |
| 15 | La liste des travaux terminés (`self._fils`) ne grossit plus pendant une longue session. | 50 ouvertures / aperçus puis fermeture : mémoire stable, code 0. |
| — | **Proposition seulement, sans coder :** une fois un film ouvert, la page simple compte 19 boutons, 1 case, 2 champs et fait 2 561 px de haut pour 641 visibles (environ 4 écrans). Proposez dans le rapport une page plus courte pour un homme de 76 ans (par exemple « Enlever une scène » replié derrière un bouton), avec un croquis ; l'utilisateur décidera. | — |

## 6. Rapport attendu

`partage-gpt/RAPPORT-CORRECTIONS-ASTRA.md`, mis à jour à chaque lot :
**Où** (branche, commits) · **Fait, ne pas refaire** · **Interdit respecté** · **Vérifié** (tests lancés,
combien, **code de sortie de toute la suite** ou la raison de ne pas l'avoir lancée) · **Mesures**
(raccord son / image, estimation IA) · **Écarté, et pourquoi** · **Non testé** (Windows réel, GPU…).

Merci !
