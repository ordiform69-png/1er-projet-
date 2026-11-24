# Demande n°12 à Grok Build : finir les quatre chantiers de la n°11

Bonjour Grok,

Merci pour les quatre branches. Claude les a relues, fusionnées **à l'essai** (localement, rien de
poussé) sur `ccr-5856e8d6-8xt8uh` (`c092cdc` : timeline, corrections d'Astra, « Nommer ce film »,
« Faire une copie à partager », « Séparer en plusieurs films ») et lancé vos 12 tests avec
**FFmpeg 6.1** : **12 réussis**. Un seul conflit, simple (`_tourner_photo` et
`_enregistrer_cassette` au même endroit de `gui.py`).

Mais plusieurs points **empêchent l'usage réel**, prouvés ci-dessous. **Base** : partez de
`ccr-5856e8d6-8xt8uh` (`c092cdc` ou suivant) et refaites les quatre branches dessus (rebase ou
nouvelle branche `…-2`), un commit par point, en citant son code (E2, P1…).

**Placement des boutons : ne le changez plus.** L'utilisateur veut que tout tienne sur un écran
de 1280 × 641 sans descendre ; Claude placera lui-même « Enregistrer une cassette »,
« Redresser… », « Tourner… » et « Préparer un rapport… » dans la page réorganisée. Gardez vos noms de
widgets (`s_enregistrer`, `s_redresser`, `s_tourner_gauche`, `s_tourner_droite`) et mettez le
travail dans des méthodes / modules, pas dans la mise en page.

Règles inchangées (demandes n°7 et n°11) : vouvoiement, options nommées comme à l'écran, aucune
nouvelle dépendance Python, `CREATE_NO_WINDOW` (`tools._NO_WINDOW`) pour tout sous-processus,
`tools.finaliser` / `effacer` / `verifier_chemin` / `partiel_unique` / `reserver_sorties`, toute la
suite à **code 0** (Python 3.12+), et **FFmpeg 6.1 et 7.x** si possible. Ni fusion, ni pull request,
ni étiquette.

---

## Enregistrer une cassette (`grok/enregistrement`)

| Code | Constat (prouvé) | À faire |
|---|---|---|
| E1 | Le bouton affiche seulement un message : **rien n'est enregistré**. Manquent : choix de l'appareil, entrée Composite / S-Vidéo, norme, place libre vérifiée avant, image en direct, temps écoulé, place restante, bouton « Arrêter l'enregistrement », arrêt automatique en fin de bande, ouverture du film à la fin, message si l'enregistrement a été interrompu. | Tout ce que la demande n°11 (chantier 5) décrit. Une petite fenêtre « Enregistrer une cassette » suffit, ouverte par `_enregistrer_cassette`. |
| E2 | `-analog_video_standard` **n'existe pas** dans dshow (FFmpeg 7.0.2, `libavdevice/dshow.c`, liste des options lignes 1894-1919) : FFmpeg refuserait de démarrer. | Retirer. PAL / NTSC : `-video_size` et `-framerate` seulement (la norme se règle dans le pilote du boîtier). |
| E3 | `video="USB2.0 Video Capture"` passe **avec les guillemets** à FFmpeg (liste d'arguments, pas de shell) ; `parse_device_name` coupe sur `=` et `:` sans retirer les guillemets : « Could not find video device ». Votre test vérifie la forme fausse. | `video=USB2.0 Video Capture:audio=Digital Audio Interface`, sans guillemets ; corriger le test. |
| E4 | L'aperçu `<film>.mkv.apercu.jpg` est écrit **à côté de l'enregistrement** (fichier visible dans le dossier de l'utilisateur) ; et `-n` vaut pour toutes les sorties : un aperçu resté d'une fois précédente bloque le démarrage. | Aperçu dans un dossier temporaire (`tempfile`), effacé à la fin. |
| E5 | `stderr=PIPE` **jamais lu** : une longue capture qui écrit des avertissements remplit le tube et **bloque FFmpeg** (image figée, images perdues). `-loglevel error` ne donne ni temps ni taille. | Lire la sortie dans un fil (ou `-progress pipe:1`) pour le temps écoulé et la taille ; journaliser les avertissements « buffer too full ». |
| E6 | `Popen` sans `CREATE_NO_WINDOW`. | `creationflags=tools._NO_WINDOW`. |

Tests : appareil simulé (lavfi) **pendant 20 s** au moins, lecture de la sortie, temps écoulé
affiché, arrêt par « q », MKV lisible ; arrêt automatique après N secondes de noir simulé
(`color=black`) ; commande dshow sans guillemets et sans option inconnue. **Dites** que rien n'a été
essayé sur un vrai boîtier.

## Photos redressées (`grok/photos`)

| Code | Constat (prouvé) | À faire |
|---|---|---|
| P1 | **Faux bord** : une photo **sans bord de scanner**, ciel blanc en haut et neige en bas (800 × 600, image de 140 à 500 px) : « Bord blanc du scanner détecté », **case cochée d'office**, et la restauration **coupe 40 % de la photo** (sortie 800 × 360). Contraire à « au moindre doute, garder le bord ». | Un bord de scanner est **uniforme** (écart-type très faible, presque blanc pur ou noir pur) **et** se termine par une **ligne droite nette** (le bord de la photo) ; au doute : case décochée, rien coupé, message « Aucun bord net trouvé ». |
| P2 | **Mode dossier** : `_reglages_dossier` part de `self.settings()`, donc `photo_quarts` et `redresser` de la photo ouverte s'appliquent à **toutes** les photos du dossier : « Tourner à gauche » sur une photo, puis « Restaurer tout un dossier », fait tourner tout le dossier. | Dossier : `photo_quarts = 0` toujours ; `redresser` seulement si l'analyse de **chaque** photo est sûre. |
| P3 | « Tourner » ne vide pas l'aperçu : l'avant / après affiché ne correspond plus. | Effacer l'aperçu comme `_colorize_toggled`, avec la phrase « Réglage changé : cliquez sur « Voir l'avant / après » ». |

Tests à ajouter : la photo « neige » ci-dessus (pas cochée, taille gardée) ; une photo posée **dans
le coin** du scanner (bord blanc à droite et en bas seulement) : bord enlevé ; bord blanc tout autour
+ 4° : comme aujourd'hui ; dossier de 2 photos après « Tourner à gauche » sur la première : la
seconde n'est pas tournée.

## Rapport pour mon fils (`grok/rapport`)

| Code | Constat (prouvé) | À faire |
|---|---|---|
| R1 | **Aucun journal dans le zip** : le logiciel écrit ses journaux dans `__main__.log_dir()` (`%LOCALAPPDATA%\…`), le rapport les cherche dans le dossier personnel et le dossier courant. | Prendre `log_dir()` : `vhs_restore.log`, `poussieres.log` et leurs copies `.1` à `.3`, tronqués. |
| R2 | Contenu incomplet : version écrite « VHS Restore AI » au lieu du numéro (`vhs_restore.__version__`) et du commit ; `self.tools.summary()` n'existe pas (voyants vides) ; ni dernière erreur, ni capture de la fenêtre, ni carte graphique. | Tout ce que liste la demande n°11 (chantier 6) ; capture par `self.grab()` ; carte graphique si on l'obtient sans dépendance, sinon « inconnue ». |
| R3 | **OneDrive** : quand le Bureau est déplacé dans OneDrive, `~/Desktop` n'est pas le vrai Bureau ; et le dernier recours (`Path.cwd()`) est le dossier du programme, introuvable pour l'utilisateur. | Vrai Bureau et vrais Documents par `SHGetKnownFolderPath` (`ctypes`, sans dépendance) ; dernier recours : le dossier personnel ; bouton « Ouvrir le dossier » dans le message. |

Tests : zip contenant les journaux de `log_dir()` (simulé), la version réelle, `fenetre.png` ;
Bureau introuvable → Documents ; ni film ni photo.

## Installateur et page de téléchargement (`grok/installateur`)

| Code | Constat (prouvé) | À faire |
|---|---|---|
| I1 | **L'installateur n'est jamais fabriqué** : Inno Setup est installé mais `iscc` n'est jamais lancé ; le travail « release » télécharge l'artefact (zip + empreinte) alors que `setup.iss` attend `dist\VHSRestoreAI\*`. | Lancer `iscc` dans le travail Windows, après PyInstaller, avec `/DAppVersion=…` ; joindre `VHSRestoreAI-Setup-<version>.exe` et son SHA-256 à l'artefact et à la Release. |
| I2 | `SetupIconFile=vhs_restore\assets\icon.ico` : **ce fichier n'existe pas** dans le dépôt ; `iscc` échouerait. | Fabriquer l'icône pendant la fabrication (par exemple depuis les icônes SVG existantes) ou retirer la ligne. |
| I3 | **Plus aucune fabrication sur les branches** : sous `push`, ajouter `tags:` sans `branches:` fait que GitHub ne lance le travail **que** pour les étiquettes (documentation GitHub : « If you define only tags/tags-ignore or only branches/branches-ignore, the workflow won't run for events affecting the undefined Git ref »). | Ajouter `branches: ["**"]`. |
| I4 | Acceptation de la n°11 non faite : installer, lancer `--autotest`, désinstaller, vérifier `Programs` vide et `tools` / réglages gardés. | L'ajouter au travail Windows (installation silencieuse `/VERYSILENT /SUPPRESSMSGBOXES`). |

---

## Livraison

Quatre branches poussées depuis `ccr-5856e8d6-8xt8uh`, et
`partage-grok/RAPPORT-N12-POUR-CLAUDE.md` : **Où** · **Fait, ne pas refaire** (code par code) ·
**Vérifié** (toute la suite : Python, PySide, FFmpeg, nombre de tests, **code de sortie**) ·
**Mesures** · **Non testé**.

Merci !
