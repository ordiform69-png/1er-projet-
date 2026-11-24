# Demande n°11 à Grok Build : installateur, enregistrement depuis le magnétoscope, rapport pour le fils, photos redressées

Bonjour Grok,

Merci pour `grok/integration` (`1090e99`) : Claude l'a relue, toute la suite passe chez lui
(293 réussis, code 0, FFmpeg 6.1) et la timeline marche de bout en bout (couper 20 → 35 s sur un
film d'une minute donne un film de 45,02 s, image et son). L'utilisateur l'a approuvée.

**Base** : partez de **`grok/integration`** (`1090e99`) — ou de `ccr-5856e8d6-8xt8uh` si elle a été
fusionnée entre-temps. En parallèle, **Claude** ajoute trois fonctions (copie à partager, séparer une
cassette en plusieurs films, nommer un film) dans `vhs_restore/partage.py` (nouveau), `vides.py` et
l'écran « C'est prêt » de `gui.py` : **n'y touchez pas** ; si un de vos chantiers doit modifier
l'écran « C'est prêt », faites-le dans un commit à part, Claude rapprochera.

Les règles de `DEMANDE-GROK-BUILD-7.md` (sections 1 à 3) restent valables : fidélité, vouvoiement,
options nommées comme à l'écran, aucune nouvelle dépendance **Python**, protections Windows
(`tools.finaliser` / `effacer` / `verifier_chemin` / `ff_input` / `partiel_unique` /
`reserver_sorties`, `CREATE_NO_WINDOW`), toute la suite à **code 0** avec **Python 3.12 ou plus**,
pas de fusion ni de pull request. Travaillez avec vos bots comme pour la demande n°7
(`partage-grok/equipe/`), une branche par chantier.

---

## Chantier 1 : un vrai installateur et une page de téléchargement fixe — `grok/installateur`

Aujourd'hui : un zip de 340 Mo à décompresser, puis `VHSRestoreAI.exe` à trouver parmi des
centaines de fichiers ; l'artefact de GitHub Actions expire après 90 jours et demande un compte.

- **Installateur Windows** fabriqué dans `.github/workflows/vhs-restore-windows.yml` (Inno Setup ou
  NSIS, installés **dans la fabrication seulement** : ce n'est pas une dépendance du logiciel).
  Installation **sans droits administrateur** (`%LOCALAPPDATA%\Programs\VHS Restore AI`), icône sur
  le bureau et dans le menu Démarrer (« VHS Restore AI »), désinstallation propre qui **garde** les
  outils installés à part (`%LOCALAPPDATA%\VHSRestoreAI\tools`), les réglages et les films. Textes de
  l'installateur en français. Une mise à jour s'installe par-dessus l'ancienne version.
- **Page de téléchargement** : sur une étiquette `v*` (ex. `v1.0.0`), une **GitHub Release** publie
  l'installateur, le zip et leurs empreintes SHA-256 (permission `contents: write` limitée à ce
  travail), **seulement si** les tests et l'essai automatique de l'exe sont verts. Ne créez aucune
  étiquette vous-même : l'utilisateur décidera de la première version.
- **SmartScreen** : l'exe n'est pas signé ; ajoutez dans `LISEZMOI.txt` et la page de version, en
  mots simples, quoi faire devant « Windows a protégé votre ordinateur » (« Informations
  complémentaires » puis « Exécuter quand même »).
- Acceptation : le workflow produit `VHSRestoreAI-Setup-<version>.exe` ; installé puis lancé par
  l'essai automatique (`--autotest`) dans la fabrication : « RÉSULTAT : OK » ; désinstallé : plus de
  fichier dans `Programs`, mais `tools` et les réglages restent.

## Chantier 5 : enregistrer une cassette depuis le magnétoscope — `grok/enregistrement`

L'utilisateur numérise aujourd'hui avec un autre logiciel. Objectif : brancher le magnétoscope sur
un boîtier USB de numérisation et cliquer sur **« Enregistrer une cassette »**.

- FFmpeg seulement (`-f dshow` sous Windows ; liste des appareils avec
  `-list_devices true -f dshow -i dummy`). Choix de l'appareil vidéo et du son en mots simples (le
  boîtier est souvent « USB2.0 Video Capture » / « Digital Audio Interface ») ; entrée
  « Composite » ou « S-Vidéo » (`crossbar`) si le boîtier le propose ; norme PAL / SECAM (720 × 576,
  25 i/s, entrelacé) par défaut, NTSC possible.
- Enregistrement **sans perte de qualité utile** : FFV1 + PCM en MKV (environ 20 à 30 Go par heure :
  le dire **avant**, et vérifier la place libre avec `pipeline.check_disk_space` / `check_fat32`), ou
  x264 très haute qualité (CRF 10, environ 8 Go par heure) au choix ; tampons suffisants
  (`-rtbufsize`, `-thread_queue_size`) pour ne perdre aucune image ; son et image synchrones.
- Pendant l'enregistrement : petite image en direct, temps écoulé, place restante, gros bouton
  « Arrêter l'enregistrement ». **Arrêt automatique** proposé après N minutes d'écran bleu / neige /
  noir continus (fin de bande), en réutilisant `vides.py`.
- À la fin : le fichier est ouvert dans le logiciel, prêt pour les étapes 2 et 3 (et la timeline).
- Rien d'enregistré n'est jamais écrasé ; un enregistrement interrompu (câble, plantage) reste
  lisible (MKV) et le logiciel le dit.
- Tests : appareil **simulé** (entrée `lavfi` à la place de `dshow`, la commande étant construite par
  une fonction testable) ; **dites clairement que rien n'a été essayé sur un vrai boîtier** : l'utilisateur
  le fera avec le sien.

## Chantier 6 : « Envoyer le rapport à mon fils » — `grok/rapport`

- Un bouton dans la fenêtre « Aide » (et dans les options avancées) : **« Préparer un rapport pour
  mon fils »**. Il crée sur le Bureau un fichier `Rapport VHS Restore AI - <date>.zip` contenant : les
  journaux (`vhs_restore.log`, `poussieres.log`), la version et le commit du logiciel, la version de
  Windows, la carte graphique si on la connaît, l'état des outils (voyants), la dernière erreur, et
  une capture de la fenêtre. Puis il dit : « Le rapport est sur le Bureau. Envoyez-le à votre fils
  (par e-mail ou WhatsApp). »
- Aucune donnée envoyée sur Internet par le logiciel ; aucun film ni photo dans le rapport ; taille
  raisonnable (journaux tronqués aux derniers Mo).
- Bureau introuvable ou protégé (OneDrive) : dossier « Documents », sinon le dossier du logiciel ;
  le message dit où.
- Tests : contenu du zip, absence de médias, Bureau absent.

## Chantier 7 : photos redressées et recadrées — `grok/photos`

- Mode Photo : case **« Redresser et enlever le bord du scanner »**, cochée d'office **seulement**
  si l'analyse trouve un bord uniforme ou une inclinaison nette ; aperçu avant / après comme aujourd'hui.
- Bord blanc ou noir du scanner : détecté et enlevé (FFmpeg `cropdetect`, image inversée pour un bord
  blanc, ou équivalent maison). Inclinaison de moins de 10° : mesurée sans nouvelle dépendance (par
  exemple profils de projection sur une image réduite) et corrigée par `rotate` ; au-delà, ou en cas
  de doute, ne rien faire.
- Deux boutons simples dans le mode Photo : « Tourner à gauche » / « Tourner à droite » (90°), pour
  une photo scannée à l'envers.
- La photo d'origine n'est jamais modifiée ; jamais de recadrage dans l'image elle-même (au moindre
  doute, garder le bord).
- Tests : photo de synthèse avec bord blanc et inclinaison de 4° : bord enlevé, inclinaison ramenée
  à moins de 0,5° ; photo droite sans bord : inchangée.

## Livraison

- Quatre branches poussées : `grok/installateur`, `grok/enregistrement`, `grok/rapport`,
  `grok/photos`, chacune partie de `grok/integration` (ou de `ccr-5856e8d6-8xt8uh` si fusionnée).
  Aucune fusion, aucune pull request, aucune étiquette de version.
- `partage-grok/RAPPORT-N11-POUR-CLAUDE.md` : **Où** (branches, commits) · **Fait, ne pas refaire** ·
  **Interdit respecté** · **Vérifié** (toute la suite : Python, PySide, FFmpeg, nombre de tests,
  **code de sortie**) · **Mesures** · **Non testé** (vrai boîtier de numérisation, vrai Windows,
  SmartScreen…).

Merci !
