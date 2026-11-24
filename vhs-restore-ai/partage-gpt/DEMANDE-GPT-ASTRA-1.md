# Demande d'analyse à GPT Astra : VHS Restore AI

Bonjour,

Je vous demande une **analyse indépendante et critique** d'un logiciel déjà bien avancé. Deux autres
assistants y travaillent (Claude, qui écrit et relit le code, et Grok, qui livre des branches) :
votre regard extérieur sert à trouver ce qu'ils n'ont pas vu. **Analysez seulement : ne modifiez pas
le dépôt, ne poussez rien, n'ouvrez pas de pull request.** Si un correctif vous paraît utile, mettez
le diff dans votre rapport.

## 1. Le logiciel et son utilisateur

- **VHS Restore AI** : application Windows gratuite et locale (Python 3.12, PySide6, FFmpeg, outils
  libres facultatifs), livrée en exe par PyInstaller. Elle restaure des films de famille numérisés
  (VHS, Video8 / Hi8, Betamax, Super 8 scanné, DVD de salon) et des photos, puis aide à les découper.
- **L'utilisateur final** : un homme **né en 1950**, sous Windows, écran 1920 × 1080 à 150 %
  (1280 × 641 px visibles). Il se sert peu d'un ordinateur, ne lit pas les infobulles, a peur de
  « casser » un film ; un message technique l'arrête. Son fils installe et dépanne.
- **Règles du projet** (non négociables) : l'original n'est **jamais** modifié ; le 4:3 et le son
  sont gardés ; aucun traitement agressif ; résultats décrits honnêtement ; français, vouvoiement,
  phrases courtes ; aucune nouvelle dépendance sans raison forte.

## 2. Où trouver le code

- Dépôt GitHub `ordiform69-png/1er-projet-`, branche **`ccr-5856e8d6-8xt8uh`**, dossier
  **`vhs-restore-ai/`** (commit `04be61b` ou suivant). Si vous n'avez pas accès à GitHub, l'utilisateur
  vous joint le zip de ce dossier.
- Une branche **`grok/timeline`** (petites images du film sur la barre de découpage) est en attente,
  **non fusionnée** : deux défauts y sont connus et renvoyés à Grok (voir 4.3). Analysez-la à part si
  vous le pouvez.
- À lire d'abord : `README.md`, `DECISIONS.md` (le journal de toutes les décisions, phases 1 à 28 :
  il dit **ce qui est fait, ce qui a été écarté et pourquoi**), `LISEZMOI.txt` (mode d'emploi),
  `ANALYSE-FONCTIONNELLE.md`.

Carte des modules (`vhs_restore/`, environ 8 500 lignes) :

| Module | Rôle |
|---|---|
| `gui.py` (3 700 l.) | Interface PySide6 : mode simple (étapes 1-2-3, « C'est prêt »), options avancées en cartes, barre de découpage `BarreFilm`, aperçu avant / après `CompareView` |
| `pipeline.py` (1 400 l.) | Chaîne FFmpeg : désentrelacement, débruitage, couleurs, mise à l'échelle, son ; export atomique ; dossier entier ; coupes au milieu (morceaux puis assemblage `-c copy`) ; aperçu |
| `probe.py`, `advice.py`, `profiles.py` | Analyse du film (entrelacement, niveaux, dominante, bords abîmés, son), conseils corrigés d'office, profils Fidèle / Équilibré / Maximum |
| `photo.py`, `colorize.py` | Mode photo ; colorisation facultative (DDColor ONNX), copie à part |
| `vides.py` | Passages vides (neige, écran bleu, noir) retirés sur une copie |
| `installer.py`, `tools.py` | Outils facultatifs installés d'un clic (version figée, SHA-256) ; détection des outils ; protections Windows (`finaliser`, `effacer`, `verifier_chemin`, `ff_input`) |
| `dvd.py`, `dust.py`, `upscaler.py` | DVD en plusieurs VOB ; poussières et rayures (Analog Repair, sous-processus) ; Real-ESRGAN |
| `ergonomie.py`, `theme.py`, `icons.py`, `eta.py` | Messages d'erreur en clair ; deux palettes (contrastes testés) ; icônes SVG ; temps restant |
| `__main__.py` | Lancement, journaux, essai automatique de l'exe (`--autotest`) |

Tests : `tests/` (41 fichiers, **260 tests**, `QT_QPA_PLATFORM=offscreen python -m pytest -q`), dont
`test_tous_reglages.py` (chaque réglage restauré pour de vrai) et `test_pieges_windows.py`.
Intégration continue : `.github/workflows/vhs-restore-windows.yml` (Windows : tests, PyInstaller,
essai automatique de l'exe).

## 3. Ce que je vous demande d'analyser

Pour chaque axe, cherchez des **problèmes concrets et démontrables**, pas des généralités :

1. **Justesse et robustesse** : bugs, cas limites (film sans son, durée inconnue, DVD en morceaux,
   film de 3 h, disque plein, clé retirée, annulation au mauvais moment), fils d'exécution
   (QThread, sous-processus), fichiers temporaires, encodages, chemins Windows.
2. **Qualité de restauration** : les choix FFmpeg (bwdif, hqdn3d / fftdnoiz, eq, cas, lanczos,
   setsar, x264 CRF 18, son afftdn / arnndn / dynaudnorm) sont-ils sûrs et fidèles pour de la VHS ?
   Risques de dégradation (couleurs, peau, mouvement, synchronisation son / image après une coupe) ?
3. **Ergonomie pour un utilisateur de 76 ans** : parcours restaurer un film / une photo / un
   dossier, enlever une scène, comprendre une erreur. Ce qui le bloquerait sans son fils.
4. **Sécurité** : téléchargements (`installer.py`), sous-processus, chemins fournis par l'utilisateur,
   extraction d'archives (zip / 7z).
5. **Performance** : en particulier l'amélioration IA (Real-ESRGAN), mesurée à environ 30 s par image
   sur le PC de l'utilisateur (aperçu de 10 s annoncé à 2 h 15) ; analyse et aperçu sur un film long.
6. **Maintenabilité** : `gui.py` fait 3 700 lignes ; dette technique qui rendra les prochaines
   évolutions risquées ; tests fragiles ou manquants.
7. **Distribution** : l'exe (environ 340 Mo zippé) est partagé à la main ; mise à jour, antivirus,
   SmartScreen, installation par un débutant.

## 4. Ce qui est déjà connu : ne le reproposez pas comme une découverte

### 4.1 Déjà fait (voir `DECISIONS.md`)
Mode simple 1-2-3 et écran « C'est prêt » ; texte A− / A / A+ ; deux palettes ; messages d'erreur en
clair ; corrections d'office des défauts repérés (case cochée d'office, phase 21) ; bords abîmés
détectés et masqués ; passages vides ; montage par LosslessCut / Shotcut lancés à part ; « Enlever
une scène » (coupes au milieu, sans seconde compression) ; protections Windows (fichier ouvert dans
un lecteur, FAT32 > 4 Go, chemins trop longs, « % » dans un nom, fenêtres console cachées) ;
téléchargements réessayés et vérifiés par SHA-256 ; options avancées réagencées (colonnes
équilibrées).

### 4.2 Écarté volontairement
Banc de montage (titres, musique, plusieurs films) ; levée du refus IA / poussières / bande / cadence
pour une coupe au milieu ; changement des seuils d'analyse sans mesures ; seconde compression lors
de l'assemblage.

### 4.3 Problèmes connus et ouverts
- `grok/timeline` : plantage à la sortie (`QThread` détruit en marche, code 134) et image du moment
  trop petite. Renvoyés à Grok (`partage-grok/DEMANDE-GROK-BUILD-9.md`).
- Amélioration IA extrêmement lente sur le PC de l'utilisateur (carte graphique insuffisante pour
  Real-ESRGAN probablement) ; aucun avertissement automatique pour l'instant.
- Non testé sur un vrai Windows : installation de LosslessCut / Shotcut / Real-ESRGAN, vrai DVD,
  vraie clé FAT32, chemin réseau `\\serveur\`.
- Distribution sans GitHub Release (l'artefact de CI expire après 90 jours).

Vous pouvez **approfondir** un point de 4.3 (cause, correction précise), mais dites-le.

## 5. Le rapport attendu

En français, un seul document **`RAPPORT-GPT-ASTRA.md`**, que l'utilisateur transmettra à Claude et
à Grok :

1. **Résumé** en 10 lignes au plus : votre avis d'ensemble et les 5 actions les plus importantes.
2. **Tableau des constats**, du plus grave au moins grave :

   | N° | Gravité (bloquant / important / mineur) | Axe | Constat | Preuve (fichier:ligne, commande, ou scénario précis) | Proposition | Effort (S / M / L) |

   Chaque constat **doit avoir une preuve**. Si vous n'êtes pas sûr, écrivez « hypothèse » et dites
   comment la vérifier.
3. **Ce que vous avez vérifié et trouvé correct**, en quelques lignes (pour éviter que d'autres le
   refassent).
4. **Ce que vous n'avez pas pu vérifier** (pas de Windows, pas de GPU…).
5. Si utile : des diffs courts pour les corrections les plus simples.

Restez concret et honnête : mieux vaut 15 constats solides que 60 suggestions vagues.

Merci !
