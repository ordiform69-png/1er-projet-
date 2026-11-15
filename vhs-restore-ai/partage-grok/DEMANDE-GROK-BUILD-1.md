Bonjour Grok,

**VHS Restore AI** est un petit logiciel Windows, gratuit et local, qui restaure des films de
famille numérisés des années 1970 à 1995 (cassettes VHS/Video8, pellicules Super 8 scannées,
pellicules copiées sur cassette). Il est destiné à une personne née en 1950 : la simplicité et la
fidélité aux souvenirs passent avant tout effet spectaculaire.

- Dépôt : `ordiform69-png/1er-projet-`, branche `ccr-5856e8d6-8xt8uh`, dossier `vhs-restore-ai/`
  (le reste du dépôt est un autre projet : n'y touche pas).
- À lire d'abord : `vhs-restore-ai/README.md` puis `vhs-restore-ai/DECISIONS.md` (choix techniques,
  mesures, limites).
- Principe : l'application orchestre FFmpeg (et en option VapourSynth/QTGMC, Real-ESRGAN). Interface
  PySide6, une seule dépendance Python. 67 tests automatiques (pytest), qui passent sous Linux.
- Fabrication Windows : `.github/workflows/vhs-restore-windows.yml` + `vhs-restore-ai/VHSRestoreAI.spec`
  (PyInstaller). L'application fabriquée démarre sous Windows ; la suite de tests sous Windows est
  en cours de stabilisation.

**Règle de travail** : ne pousse rien sur la branche ci-dessus. Propose tes modifications sous forme
de correctifs (diff) dans ta réponse, ou sur une branche séparée nommée `grok/...`. N'invente ni
résultat de test, ni projet, ni licence : si tu n'as pas pu vérifier, écris « non vérifié ».

Merci de répondre au format habituel, un bloc par point :
**POINT / Fichier / Ligne / Problème / Correction proposée / Source ou preuve**.

---

## 1. Relecture indépendante du code (priorité)

Fichiers : `vhs_restore/pipeline.py`, `probe.py`, `tools.py`, `gui.py`, `__main__.py`.

Cherche en priorité :
- les cas où le **fichier source pourrait être modifié ou écrasé**, ou une sortie existante écrasée ;
- les risques de **désynchronisation image/son** (saut au début d'un extrait, re-cadencement d'une
  pellicule avec `setpts` + `atempo`, chemin IA par paquets, chemin QTGMC avec `-itsoffset`) ;
- les **pièges Windows** : chemins avec accents, espaces ou apostrophes, processus non arrêtés lors
  d'une annulation, fichiers temporaires non supprimés, encodage de la sortie de FFmpeg ;
- toute commande lancée **via un shell** (il ne doit y en avoir aucune).

## 2. Poussières et rayures de pellicule (recherche)

C'est la prochaine fonction envisagée, en option pour les pellicules scannées. Pistes à vérifier :
- **SpotLess** (poussières et taches) et **DeScratch** (rayures verticales) pour VapourSynth, cités
  dans l'historique de VapourBox : https://www.videohelp.com/software/VapourBox/version-history
- Pour chacun : dépôt officiel, licence, date de la dernière version, installation **par pip**
  (paquet `vapoursynth-...` ?) sous Windows et Linux, exemple d'appel minimal, risques connus
  (faux positifs sur des objets réels en mouvement, par exemple).
- Un projet nommé « **Analog Repair** » (MIT, bandes et pellicules, poussières/scintillement) nous a
  été signalé, mais je ne l'ai pas trouvé. S'il existe, donne le lien vers son dépôt ; sinon, dis-le.

Le logiciel utilise déjà VapourSynth R82 + vs-jetpack 3.0 installés par pip
(`requirements-qtgmc.txt`), et appelle un script `.vpy` fixe via `vspipe -a` (voir `qtgmc.vpy`) :
précise si SpotLess/DeScratch s'intègrent de la même façon.

## 3. Fabrication Windows (relecture)

Relis `VHSRestoreAI.spec`, le workflow GitHub Actions et `scripts/installer_outils.ps1` :
- risques de **faux positifs antivirus** ou de blocage SmartScreen avec un exécutable PyInstaller non
  signé, et moyens gratuits de les limiter ;
- modules Qt inutiles encore embarqués (taille du paquet) ;
- compatibilité FFmpeg : l'installateur télécharge la dernière version « release essentials » de
  gyan.dev (9.0.2 au 15/11/2026). Faut-il figer une version, et laquelle ?

---

Merci ! Les points 1 et 2 sont les plus utiles.
