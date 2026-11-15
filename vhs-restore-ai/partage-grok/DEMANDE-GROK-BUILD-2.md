Bonjour Grok,

Merci pour le lien vers Analog Repair : le projet existe bien. Il a été évalué puis **intégré**
pour les poussières et rayures (détails ci-dessous). Ce document te transmet le projet pour que tu
**continues le développement**. Il remplace la demande n° 1 : ses points restent valables et sont
repris en section 4.

## 1. Le projet en bref

**VHS Restore AI** est un logiciel Windows, gratuit et local, qui restaure les films de famille
numérisés d'un homme né en 1950 (cassettes 1980-1995, pellicules Super 8 des années 1970, films
copiés sur cassette). Priorités, dans l'ordre : **simplicité, fidélité aux souvenirs, fiabilité**.
Un résultat plus net mais infidèle n'est pas meilleur.

- Dépôt `ordiform69-png/1er-projet-`, branche `ccr-5856e8d6-8xt8uh`, dossier `vhs-restore-ai/`.
  Le reste du dépôt est un autre projet : n'y touche pas.
- À lire en premier : `README.md` (utilisation, état), puis `DECISIONS.md` (tous les choix, avec
  mesures et sources).

## 2. Carte du code (`vhs_restore/`)

| Fichier | Rôle |
|---|---|
| `tools.py` | Recherche des outils (FFmpeg, vspipe, Real-ESRGAN, module poussières), exécution **sans shell**, annulation, tube vspipe → ffmpeg |
| `probe.py` | Analyse : ffprobe, entrelacement mesuré (`idet` + trames répétées), 4:3, norme, son vide, noir et blanc ou couleurs pâles, origine suggérée |
| `profiles.py` | Profils Fidèle / Équilibré / Maximum et leurs variantes par origine (`SOURCE_OVERRIDES`) |
| `pipeline.py` | Chaîne de filtres FFmpeg, export, aperçu avant/après aligné, IA par paquets, stabilisation en 2 passes, QTGMC, poussières, dossier entier |
| `dust.py` | Adaptateur Analog Repair (version figée `561ba5a`), sous-processus `--poussieres`, intermédiaire ProRes |
| `upscaler.py` | Adaptateur Real-ESRGAN (facultatif) |
| `qtgmc.vpy` | Script VapourSynth fixe (QTGMC), piloté par `vspipe -a` |
| `gui.py` | PySide6 : mode simple (3 gros boutons, dossier entier) + « Options avancées » |
| `__main__.py` | Entrée, journal, `--autotest DOSSIER` (vérifie une installation sans fenêtre), `--poussieres` |

Règles déjà en place, à garder : le fichier source n'est jamais modifié ; une sortie n'apparaît
qu'une fois complète (`*.partiel.mp4`) et n'écrase jamais un fichier existant ; les proportions et
le son sont conservés ; aucune colorisation ; une seule compression finale.

## 3. Commandes

```
pip install -r requirements-dev.txt -r requirements-poussieres.txt
python -m pytest tests                 # 71 tests (Linux, FFmpeg 6.1) ; QTGMC : voir requirements-qtgmc.txt
python -m vhs_restore                  # interface
python -m vhs_restore --autotest OUT   # contrôle complet sans fenêtre
pyinstaller --noconfirm VHSRestoreAI.spec
```

GitHub Actions (`.github/workflows/vhs-restore-windows.yml`) tourne à chaque push du dossier : tests
sous Windows (FFmpeg 9.0.2), fabrication, autotest de l'application fabriquée, puis artefact
`VHSRestoreAI-Windows`. **Le dernier run vert date d'avant l'intégration des poussières** : le
premier travail est de vérifier le run qui suit ce commit (voir 4.1).

## 4. Tâches, par priorité

Règles : travaille sur une branche `grok/...` et propose une pull request vers la branche
ci-dessus ; un sujet par PR ; chaque changement de comportement vient avec un test ; garde la suite
verte sous Linux **et** Windows ; ajoute une ligne dans `DECISIONS.md` pour chaque choix. Ne
présente aucune mesure ni aucun résultat que tu n'as pas obtenu toi-même.

### 4.1 Faire passer au vert la fabrication Windows avec le module poussières (P0)
- `requirements-poussieres.txt` installe Analog Repair depuis une archive zip GitHub, sans Git.
  NumPy et OpenCV sont inclus dans le paquet via `collect_submodules`/`collect_data_files` dans le
  `.spec`. L'autotest fait un vrai export « poussières » depuis l'exe fabriqué : vérifier qu'il
  passe.
- Mesurer la taille de l'artefact avant et après (environ 131 Mo avant). Retirer d'OpenCV et de
  Qt ce qui est inutile si c'est simple.
- Inclure dans `licences/` les licences des bibliothèques embarquées (NumPy, OpenCV, PySide6/Qt,
  FFmpeg ; Analog Repair est déjà fait).

### 4.2 Relecture critique du code (P0, reprise de la demande n° 1)
Fichier source jamais touché, synchronisation image/son (extrait, re-cadencement `setpts` +
`atempo`, IA par paquets, QTGMC `-itsoffset`, intermédiaire poussières), pièges Windows (accents,
annulation, fichiers temporaires), aucun shell. Format attendu, un bloc par point :
**POINT / Fichier / Ligne / Problème / Correction proposée / Preuve (test ou mesure)**.

### 4.3 Antivirus, SmartScreen, version de FFmpeg (P1)
- Un exécutable PyInstaller non signé est-il bloqué ou signalé ? Quels moyens gratuits pour
  limiter le problème ? Ne pas acheter de certificat sans notre accord.
- FFmpeg n'est pas figé (dernière version « release essentials » de gyan.dev, via
  `scripts/installer_outils.ps1`). Proposer de le figer sur une version et une somme SHA-256
  précises.

### 4.4 Vérifications sur de vrais films (P1, dès que des extraits seront fournis)
Protocole : mêmes extraits, profils Fidèle / Équilibré / Maximum, avec et sans poussières.
Juger visages, grain, couleurs, poussières, et objets rapides (risque d'effacement).
Les extraits d'archives libres utilisés jusqu'ici sont décrits dans `DECISIONS.md` (archive.org).

### 4.5 Plus tard (P2, ne pas commencer sans demande)
Suppression optionnelle des images répétées d'un transfert, masquage du bruit de tête en bas
d'image VHS, encodage GPU, DeScratch (déjà évalué, moins efficace qu'Analog Repair).

## 5. Ce qu'il ne faut pas faire
- Pas de nouveau moteur maison quand un outil maintenu existe ; pas de nouvelle dépendance sans
  justification écrite dans `DECISIONS.md`.
- Ne pas activer par défaut un traitement qui modifie l'image au-delà du profil choisi
  (stabilisation, poussières, IA et débruitage haute qualité restent facultatifs).
- Ne pas complexifier le mode simple : trois boutons, aucun réglage technique.

Merci !
