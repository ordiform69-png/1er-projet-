# Rapport n°20-D pour Claude — Windows, fichiers, disque

Vous trouverez ci-dessous dix constats, les plus graves d'abord. Agent D, branche `grok/bugs-d-windows`, créée depuis `1abf947` (base `ccr-5856e8d6-8xt8uh`). Aucune modification dans `vhs_restore/`. Les 3 échecs déjà corrigés dans `193a716` (mise en page à 1024 px, JSON du test de reprise, `test_copie_lecture` et `/tmp`) ne sont pas signalés à nouveau.

Les tests sont dans `tests/test_bugs_n20_d.py`. Lancés seuls, `QT_QPA_PLATFORM=offscreen`, `timeout 900`, venv `/workspace/ctrl-vhs/venv-tests` : **7 xfailed**, 0 passé, 0 échec inattendu (strict tient).

## Ce qui a été vérifié et n'est pas un constat

- Chemins avec accents, espaces et apostrophes : la liste concat (`dvd._ecrire_liste`, échappement `'\''`) et `_ff_filter_path` (graphe de filtres, ex. `movie=`, `arnndn=m=`) ont été exercés sur un fichier `Noel l'été 1989/film 'noël'.mkv` avec FFmpeg 7.1.5 : lecture et filtre **réussissent**.
- Le manifeste de reprise et les réglages poussières sont écrits par `json.dumps` (les « \ » de Windows y sont déjà échappés). Le JSON écrit à la main qui cassait un test a été corrigé dans `193a716`.
- Aucun décodage littéral `cp1252` ne reste dans `vhs_restore/`. Le risque éventuel est l'inverse (voir constat 9).

## Constats

### 1. Bloquant — FFmpeg continue après la fin du processus père

- **Où** : `vhs_restore/tools.py`, lancement vers les lignes 462–464 ; `terminate` aux lignes 517–524. Même schéma dans `pipeline.py` (encodeur IA, vers 1732), `vignettes.py` (121), `copie_lecture.py` (146). Aucun objet Job Windows, pas de `PDEATHSIG`.
- **Scénario** : le père restaure un film de 2 heures. Il quitte par « Fin de tâche » dans le Gestionnaire des tâches, ou l'interface se ferme sans passer par `closeEvent`. FFmpeg, lancé comme dans `tools.run()`, reste en vie, continue d'écrire le fichier `.partiel`, et peut verrouiller le dossier de sortie.
- **Preuve** : **PROUVÉ** ici (`test_ffmpeg_meurt_avec_le_processus_qui_l_a_lance`). Un processus Python lance FFmpeg avec les mêmes drapeaux que `tools.run()`, puis fait `os._exit(0)` sans `terminate()`. Le FFmpeg est encore vivant un instant plus tard. `_eteindre_a_la_sortie` (gui.py, vers 50) tue les FFmpeg des vignettes et de la copie de lecture, **pas** celui de l'export.
- **Correction proposée** : rattacher chaque processus fils à un Job Object Windows (`KILL_ON_JOB_CLOSE`) et, dans `atexit`, appeler `terminate()` sur les FFmpeg encore suivis.

### 2. Bloquant — Contrôle FAT32 inopérant si le format du volume est inconnu

- **Où** : `vhs_restore/pipeline.py`, `systeme_de_fichiers` lignes 902–914 (tout échec, y compris lecteur réseau, renvoie `""`) et `check_fat32` ligne 922 (`if … startswith("FAT")`).
- **Scénario** : le père enregistre sur un disque réseau ou une clé partagée dont Windows ne renvoie pas le type. Un film de 3 heures dépasse 4 Go. Le logiciel ne prévient pas ; l'écriture échoue après des heures, souvent avec un fichier incomplet.
- **Preuve** : **PROUVÉ** pour le trou de logique (`test_fat32_reseau_inconnu_est_traite_comme_un_risque`) : `systeme_de_fichiers` forcé à `""`, `check_fat32` sur un film de 3 h laisse passer. Le cas réel « partage Windows FAT32 » est **non lancé** (pas de volume FAT32 ici).
- **Correction proposée** : si le film estimé dépasse ~3,6 Go et que le type de volume est vide, avertir (ou refuser) comme pour FAT32, plutôt que de se taire.

### 3. Gênant — Disque plein en cours de route : le message ne parle pas du disque

- **Où** : `vhs_restore/ergonomie.py`, `expliquer`, lignes 91–97.
- **Scénario** : la place a été contrôlée au départ, puis un autre programme remplit le disque. FFmpeg s'arrête avec `No space left on device`. La phrase montrée est la formule générale (« Cette étape n'a pas abouti »), pas « il n'y a plus assez de place ». Le père ne sait pas qu'il doit libérer le disque.
- **Preuve** : **PROUVÉ** (`test_disque_plein_ffmpeg_explique_la_place`). `expliquer` sur ce texte FFmpeg ne contient ni « place » ni « disque », et ne prend pas le branchement de la ligne 91 (qui cherche « espace disque » ou « insuffisant », absents du texte anglais).
- **Correction proposée** : reconnaître aussi « no space left », « pas assez d'espace », « disk full », « ENOSPC » dans `expliquer`.

### 4. Gênant — Un verrou `.reserve` orphelin fait sauter le nom du film

- **Où** : `vhs_restore/tools.py`, `reserver_sorties`, lignes 199–205 (`touch(..., exist_ok=False)` puis `except FileExistsError: numero += 1`).
- **Scénario** : une restauration s'interrompt brutalement après la création de `.noel.mp4.reserve`, sans laisser `noel.mp4`. Au lancement suivant, ce verrou est pris pour « nom déjà pris » : le logiciel écrit `noel (2).mp4` et laisse le fichier caché.
- **Preuve** : **PROUVÉ** (`test_verrou_reserve_orphelin_ne_bloque_pas_le_nom`).
- **Correction proposée** : si le verrou existe mais que le fichier de sortie n'existe pas, et qu'aucun autre processus ne le tient, l'effacer et réutiliser le nom.

### 5. Gênant — Dossiers temporaires d'aperçu et de « Lumière » laissés si `closeEvent` ne passe pas

- **Où** : `vhs_restore/gui.py` ligne 1395 (`preview_dir`), nettoyage seulement dans `closeEvent` ligne 4766 ; `vhs_restore/lumiere.py` ligne 125, `fermer()` lignes 295–297. `_eteindre_a_la_sortie` (gui.py, vers 50) ne les efface pas.
- **Scénario** : interruption (Ctrl+C sur une console, plantage après `atexit`, fermeture qui n'envoie pas `closeEvent`). Il reste des dossiers `vhsrestore_apercu_*` et `vhsrestore_lumiere_*` dans le répertoire temporaire, qui s'accumulent au fil des essais.
- **Preuve** : **PROUVÉ** (`test_atexit_efface_les_dossiers_temporaires_de_la_fenetre`). Après un appel à `_eteindre_a_la_sortie` sans `closeEvent`, les deux dossiers sont encore là.
- **Correction proposée** : dans `_eteindre_a_la_sortie`, appeler `lumiere.fermer()` et supprimer `preview_dir` pour chaque fenêtre encore connue.

### 6. Gênant — Extraction 7-Zip sans `-sccUTF-8`

- **Où** : `vhs_restore/installer.py`, `_extraire_7z` : la liste a `-sccUTF-8` (ligne 138), l'extraction `7z x … -o{dest}` (ligne 141) ne l'a pas.
- **Scénario** : installation des outils dans un profil Windows dont le chemin a un accent (`C:\Users\Gérard\…`). 7-Zip, sous Windows, peut interpréter `-o` selon la page de code et extraire au mauvais endroit, ou échouer.
- **Preuve** : **PROUVÉ** que le drapeau manque sur `x` (`test_extraction_7z_demande_l_utf8_comme_la_liste`). L'échec réel d'une extraction dans un profil accentué est **non lancé** (pas de 7zr.exe Windows ici).
- **Correction proposée** : ajouter `-sccUTF-8` à la commande `x`, comme déjà fait pour `l`.

### 7. Gênant — Chemin trop long : le nombre affiché peut être faux

- **Où** : `vhs_restore/tools.py`, `verifier_chemin`, lignes 259–267. Le test se fait sur `Path(path).resolve()`, le message utilise `len(str(Path(path)))`.
- **Scénario** : le père choisit un dossier profond (OneDrive, plusieurs sous-dossiers) et un nom court `sortie.mp4`. Le logiciel refuse, mais le message peut parler de « 11 caractères » alors que le chemin résolu dépasse 250. Le conseil reste juste, le chiffre est trompeur.
- **Preuve** : **PROUVÉ** (`test_verifier_chemin_annonce_la_longueur_reelle`), en simulant Windows (`IS_WIN`).
- **Correction proposée** : afficher la longueur du chemin déjà résolu, celle qui a déclenché le refus.

### 8. Gênant — Liste concat et chemins UNC / disque réseau

- **Où** : `vhs_restore/dvd.py`, `_ecrire_liste`, lignes 83–87 ; même motif dans `pipeline.py`, `_concat_sans_recompression`, vers 1303–1305 (`as_posix()` puis `file '…'`).
- **Scénario** : un DVD ou des parties restaurées sont lus depuis `\\NAS\films\…`. La liste devient `file '//NAS/films/…'`. Certains FFmpeg sous Windows traitent `//` comme un protocole et refusent la liste, alors que le même fichier ouvert en `-i` direct irait.
- **Preuve** : **PLAUSIBLE**, **non lancé** (pas de partage UNC ici ; sous Linux, `//tmp/…` est accepté, ce qui ne prouve rien pour Windows).
- **Correction proposée** : pour un chemin UNC, écrire une forme que le démultiplexeur concat reconnaît (`file:////serveur/partage/…` ou le chemin natif `\\serveur\partage\…`).

### 9. Gênant — Sorties FFmpeg toujours décodées en UTF-8

- **Où** : `vhs_restore/tools.py`, `run_capture` ligne 323 et `run` ligne 464 (`encoding="utf-8", errors="replace"`).
- **Scénario** : sur un Windows français, un FFmpeg officiel écrit souvent un chemin accentué dans stderr selon la page de code ANSI (cp1252). « Fichier introuvable : C:\Users\Gérard\Noël.avi » arrive alors avec des `�` dans « Détails pour l'aide ». Ce n'est pas un décodage *en* cp1252 dans le code actuel (plus aucune occurrence) : c'est un décodage UTF-8 d'un texte qui, sous Windows, peut être en cp1252.
- **Preuve** : **PLAUSIBLE**, **non lancé** (FFmpeg 7.1.5 de cette machine Debian émet de l'UTF-8).
- **Correction proposée** : sous Windows, tenter UTF-8 puis, en cas d'échec, `mbcs` / cp1252, avant `errors="replace"`.

### 10. Gênant — Fichier OneDrive « uniquement en ligne »

- **Où** : ouverture du film (`probe` / `open_media` / `-i` FFmpeg), pas de prise en charge particulière d'un attribut « recall on data access ».
- **Scénario** : le film est dans OneDrive, coche « Fichiers à la demande », et n'est pas encore téléchargé. L'ouverture échoue ou reste bloquée, avec un message peu clair (fichier introuvable, erreur d'E/S), alors que l'Explorateur Windows lancerait le téléchargement.
- **Preuve** : **PLAUSIBLE**, **non lancé** (pas de compte OneDrive sur cette machine).
- **Correction proposée** : si le chemin contient « OneDrive » ou si l'ouverture échoue avec une erreur de fichier cloud, expliquer qu'il faut d'abord rendre le fichier disponible hors connexion, puis réessayer.

## Tests

Fichier : `tests/test_bugs_n20_d.py`. Uniquement ce fichier, `QT_QPA_PLATFORM=offscreen`, `timeout 900`.

Résultat : **7 xfailed**, 0 passed, 0 failed (pytest-9, strict=True). Les 7 tests correspondent aux constats 1 à 7 (les constats 8 à 10 n'ont pas de test lancé ici).
