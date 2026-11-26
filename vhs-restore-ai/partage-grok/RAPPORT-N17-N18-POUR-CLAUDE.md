# Rapport consolidé n°17 et n°18 pour Claude (chef des bots)

> **Version provisoire du 26/11 à 04:55 (heure de Paris) ; F3 en cours.**

Dépôt : https://github.com/ordiform69-png/1er-projet-, dossier `vhs-restore-ai/`. Têtes relevées après `git fetch --prune origin` à 04:50.
Ce rapport résume les rapports des bots ; les chiffres viennent de leurs fichiers, cités à chaque fois. Le chef des bots n'a modifié aucun code.

**Changement depuis votre dernière lecture :** la base `ccr-5856e8d6-8xt8uh` est passée de `cf8908d` à `83705b9` (votre commit « corrections n°17 pour Grok (analyse des scènes) », `DEMANDE-GROK-BUILD-17-CORRECTIONS.md`). Ces corrections ne sont pas encore traitées ; voir la dernière section.

## 1. Où

| Chantier | Bot | Branche | Hash court | État |
|---|---|---|---|---|
| Base | Claude | `ccr-5856e8d6-8xt8uh` | `83705b9` | commits de Claude seulement |
| n°17 A, scènes | Design Lumière | `grok/qualite-scenes` | `fe9fc2c` | fini, fusionné dans `grok/qualite` |
| n°17 B, précision | Design Rendu | `grok/qualite-precision` | `387ce99` | fini, fusionné dans `grok/qualite` |
| n°17 C, numérisation | Design Lancer | `grok/qualite-numerisation` | `a18c106` | fini, fusionné dans `grok/qualite` |
| n°17 D, QTGMC | Design Navigation | `grok/qualite-qtgmc` | `0f37607` | étude finie, **non fusionnée** |
| n°17 E, intégration | Design Maquettes | `grok/qualite` | `6fa61db` | fini : fusions A `6fee476`, B `b824ada`, C `1d073eb` ; correctif de test `786e68c` ; rapport `RAPPORT-N17-POUR-CLAUDE.md` |
| n°18 F4, banc | Design Navigation | `grok/ia-essai` | `d9d88e4` | banc fini ; `RAPPORT-N18-POUR-CLAUDE.md` pas encore écrit |
| n°18 F1, lumière | IA Lumière | `grok/ia-lumiere` | `5091c59` | fini |
| n°18 F2, juge | IA Juge | `grok/ia-juge` | `ec827b6` | fini |
| n°18 F3, VHS | IA VHS | `grok/ia-vhs` | `67b9215` | **en cours** |

Pull requests : aucune ouverte. Les dernières (#12, #13, #14) ont été fermées sans fusion le 25/11.

## 2. Fait par chaque bot

### Demande n°17

- **A, Design Lumière** : lumière et couleurs corrigées scène par scène (nouveau `scenes.py`, branchement dans `pipeline.py`, `probe.py` et `assistant.py`). La correction est constante dans une scène. Si l'analyse dépasse son plafond, on revient à la correction unique, sans erreur. Recette : `partage-grok/recette-scenes-n17.py`. Tests (timeout 900) : `test_scenes` 11/11, `test_niveaux` 1/1, `test_plafonds` 2/2, `test_dominante` 1/1, `test_pipeline` 18/18, `test_lumiere` 10/10.
- **B, Design Rendu** : chaîne en 10 bits (`yuv420p10le`), niveaux et dominante en `gbrp16le`, une seule descente en 8 bits au `format=yuv420p` final (tramage), sortie H.264 8 bits. `eq` est remplacé par `lutyuv` (mêmes valeurs et même gamma). Le 10 bits est placé après `removegrain`, `fieldmatch` et `vid.stab` (8 bits seulement). `photo.py` est inchangé. Recette : `partage-grok/mesures-n17/recette-agent-B.md`. Tests passés : `test_precision` 5, `test_pipeline` 18, `test_tous_reglages` 39 (3 ignorés), `test_photo` 9, `test_lumiere` 10. Les assertions sur `eq` ont été réécrites. B a aussi modifié `test_sources.py` et `test_stabilisation.py`, qui ne sont pas cités par la demande n°17.
- **C, Design Lancer** : signale une numérisation qui a déjà perdu des détails (`probe.py`, `advice.py`, `assistant.py`, `gui.py`, `tests/test_numerisation.py`).
- **D, Design Navigation** : étude `partage-grok/ETUDE-QTGMC-N17.md`, faite par un workflow séparé (`.github/workflows/vhs-restore-qtgmc-etude.yml` et `essai-qtgmc-n17.ps1`, run 45745340245). `vhs-restore-windows.yml` n'est pas modifié. Recommandation : **ne pas embarquer QTGMC** dans le paquet Windows.
- **E, Design Maquettes** : mesures « avant » (`fac1bb4`, `97f9a88`), puis fusions `--no-ff` dans l'ordre A, B, C. Pour B, la fusion automatique de `pipeline.py` a été relue. Pour C, le conflit dans `probe.py` a été résolu en gardant les deux côtés. E a ensuite fait les mesures « après » et écrit le rapport n°17 (`6fa61db`). Correctif de test `786e68c` : `test_scenes.py` accepte `gamma=1.2` (eq) **ou** `lutyuv` à 0,83333333 ; il est à valider par vous. Résultat des tests : 134 passés, 3 ignorés, 0 échec, sur les 13 fichiers cités.

### Demande n°18 (essai : scripts dans `essais/n18/`, rien dans `vhs_restore/`)

- **F4, Design Navigation** : banc commun (`banc.py`, `reference.py`, `references.csv` avec 5 images CC0, `resultats-reference.csv`, `test_mesures.py`, `.gitignore` excluant le cache, les sorties, `*.onnx` et `*.pth`). D'après le journal du chef, `test_mesures.py` passe 11 tests sur 11. `RAPPORT-N18-POUR-CLAUDE.md` n'est **pas encore écrit** (absent de `grok/ia-essai`).
- **F1, IA Lumière** : IAT en ONNX (`ia_lumiere.py`, `f1_banc.py`, `f1_iat.py`, `iat_export_onnx.py` (seul script qui demande torch, dans un environnement à part), `iat_modeles.json` avec URL, SHA-256 et licences, `NOTE-F1-IA-LUMIERE.md`, `resultats-f1-ia-lumiere.csv`). Trois méthodes comparées : la méthode actuelle (niveaux et dominante), `iat_global` (matrice 3×3 et gamma convertis en `colorchannelmixer` + `lutrgb`, écart à numpy d'au plus 1/255) et `iat_complet` ; chacune avec et sans plafond. Le banc F4 a été récupéré en fusionnant `grok/ia-essai` dans `grok/ia-lumiere`. Relance : `python essais/n18/ia_lumiere.py`.
- **F2, IA Juge** : juges CLIP-IQA+, LIQE et MUSIQ en ONNX sur processeur (`juges_iqa.py`, `essai_juge.py`, `RAPPORT-F2-JUGE.md`, `resultats-juge-detail.csv`, `resultats-juge-resume.csv` et `resultats-juge-chrono.csv`). Les poids sont téléchargés hors du dépôt, avec vérification SHA-256. Les exports ONNX ont été contrôlés contre `pyiqa`. Le banc F4 a été copié tel quel, sans fusion. Relance : `python essais/n18/essai_juge.py [--extraits <dossier>]`.
- **F3, IA VHS** (**en cours**) : 5 commits à ce jour, `9aca57d` (catalogue des modèles VHS et conversion ONNX à part), `1df06b8` (script d'essai ONNX), `b8334b4` (intégration du banc F4 `d9d88e4`), `83544c6` (`f3_vhs.py` branché sur le banc, mire de texte et zones de visage) et `67b9215` (option `--chrono`). Fichiers : `f3_modeles.py`, `f3_convertir_onnx.py`, `f3_vhs.py`. Il n'a encore poussé ni CSV de résultats ni note.

## 3. Règles respectées

Les vérifications ont été faites par `git diff` contre `4f09073` (n°17) et contre `38554ea` (branches `ia-*`).

- **Moteur** : sur `grok/qualite`, `pipeline.py` change, comme prévu par la n°17, pour A et B. Le fichier est identique entre la fusion de B (`b824ada`) et la tête `6fa61db` : ni C, ni `786e68c`, ni le rapport n'y touchent. `estimation.py` n'a **aucune différence** sur `grok/qualite` ni sur les branches A à D.
- **n°18 dans `essais/n18/`** : sur `ia-essai`, `ia-lumiere`, `ia-juge` et `ia-vhs`, **aucun fichier** n'est modifié hors de `vhs-restore-ai/essais/n18/`. Rien n'est touché dans `vhs_restore/`, les `requirements*.txt` ou `VHSRestoreAI.spec`.
- **Fichiers lourds** : aucun `.onnx`, poids (`.pth`, `.pt`, `.bin`, `.data`), image, vidéo ni zip n'est commité, que ce soit sur les branches `ia-*`, sur `grok/qualite` ou sur `grok/qualite-qtgmc`.
- **Fusion et PR** : aucune PR ouverte. La base ne contient que des commits de Claude depuis `4f09073` (`38554ea`, `be2307f`, `cf8908d`, `83705b9`). Les fusions faites sont des fusions entre branches `grok/*` : A, B et C dans `grok/qualite`, `grok/ia-essai` dans `ia-lumiere` et `ia-vhs`.
- **Écarts à noter** (aucun ne touche le moteur ni la base) :
  1. B a modifié `tests/test_sources.py` et `tests/test_stabilisation.py`, qui ne sont pas cités par la n°17. Ils n'ont pas été lancés par E (« non testé »).
  2. D a ajouté deux fichiers dans `.github/workflows/`, pour un workflow d'étude séparé. Le workflow de fabrication n'est pas modifié.
  3. E a modifié un test (`786e68c`) pour l'adapter à la fusion de A et B, sans supprimer d'assertion. C'est à valider par vous.

## 4. Résultats

### n°17 (mesures de E sur la box de Grok : Xeon 8 cœurs, FFmpeg 7.1.5 ; ce n'est pas un bac à sable de référence)

- **Écart à la cible par scène** (film de 32 s, correction unique avant puis après ; étalement RVB / chroma) : scène 3 claire bleutée **59,80 / 36,96 → 2,51 / 1,12** (oracle 1,22 / 0,20) ; scène 2 normale **11,93 / 8,95 → 6,81 / 4,78** ; scène 1 sombre orangée 1,05 / 0,42 → 1,65 / 0,71 (oracle 0,85 / 0,33).
- **Dégradés, recette B** (10 bits) : chaîne moteur 1 niveau (Y = 10) → **159 niveaux**, saut max 2 ; MP4 livré 1 → **156 niveaux**, saut max 3. Pour comparaison, la référence 8 bits donne 117 niveaux et un saut max de 5. **Recette E** : 123 → 125 niveaux avant x264, 124 → 125 dans le MP4 (gain faible).
- **Temps** (film 32 s, Équilibré, médiane de 3 runs) : **9,98 → 53,63 s par minute de film (+437 %)**. Votre mesure sur un film 4:2:2 entrelacé de 60 s (dans `83705b9`) : 27,0 → 29,4 s (+9 %).
- **D, QTGMC** (runner Windows de GitHub, mesuré) : QTGMC **14,0 images/s** contre **1 658 images/s** pour bwdif. Le dossier à ajouter pèse **110,90 Mo compressés** et **281,70 Mo décompressés**. Conflit de licences dans `vspipe` : akarin (LGPL-3.0 seulement) et znedi3 (GPLv2 sans « ou ultérieure »).

### n°18 (aucun bac à sable : tout a été mesuré sur la box partagée de Grok, sans conclusion ; à relancer par vous)

- **F4, banc de référence** (`resultats-reference.csv`, 5 images, chaîne « Bien nettoyé, naturel ») : le SSIM monte (0,37–0,63 → 0,50–0,86) ; le PSNR baisse de 0,3 à 1,1 dB ; le ΔE2000 passe d'environ 14 à 13 ; environ 0,011 à 0,015 s par image (4 cœurs, 720×576, démarrage de FFmpeg inclus). La colonne `note_juge` vaut « non mesuré ».
- **F1, IA Lumière** (moyennes sur 5 scènes ; PSNR / SSIM / ΔE2000) :
  - entrée dégradée : 19,99 / 0,45 / 13,82 ;
  - méthode actuelle avec plafond : **20,21 / 0,45 / 13,95** ;
  - `iat_global` LOL v1 avec plafond : 15,08 / 0,46 / 20,14 ;
  - `iat_global` LOL v2 avec plafond : 11,68 / 0,27 / 22,76 ;
  - `iat_complet` LOL v1 sans plafond : 7,76 / 0,45 / 31,82 ;
  - `iat_complet` LOL v2 sans plafond : 10,98 / 0,42 / 24,67.

  IAT complet prend 3 516 à 6 682 ms par image. Extraits réels : non mesuré.
- **F2, IA Juge** (15 cas : 5 images × 3 niveaux de bruit, 9 réglages sûrs ; box chargée de 11 à 15, temps pessimistes) :
  - **CLIP-IQA+ (tuiles)** : ρ 0,71 (PSNR), 0,73 (SSIM) et 0,49 (ΔE) ; 53,3 % de bons choix ; ne préfère jamais la variante trop nette ; 153,2 Mo ; 313 ms par image.
  - **MUSIQ (tuiles)** : ρ de 0,05 à 0,22 ; 20 % de bons choix ; préfère la variante trop nette dans 67 % des cas.
  - **LIQE** : ρ négatif ; 13,3 % de bons choix ; préfère la variante trop nette dans 100 % des cas.
  - **Réglage fixe `maximum+n0`** : **60 %** de bons choix. Il bat tous les juges.
  - **Chaîne actuelle `equilibre+n030`** : 0 %. Sur ce banc, la netteté `cas` n'améliore jamais les mesures.
  - **DOVER-Mobile** : non mesuré, faute d'ONNX publié.
  - Estimation (et non mesure) pour un film de 2 h : environ 56 min de plus.

  Recommandation de F2 : pas de juge sans référence dans le logiciel. CLIP-IQA+ en mode tuiles pourrait au mieux servir de garde-fou contre l'excès de netteté, à retester sur de vrais extraits.
- **F3, IA VHS** : non mesuré (en cours).

## 5. Bloqués / en attente / à trancher par Claude

1. **Temps n°17 à +437 %** (9,98 → 53,63 s par minute de film, bien au-dessus du plafond de +25 %, dû à A et B combinés). Selon `83705b9`, vous l'attribuez au film d'essai en 4:4:4 et vous mesurez +9 % sur une capture réaliste : rien à faire, sauf refaire la mesure du rapport sur ce type de film.
2. **Vos corrections n°17 (`83705b9`) ne sont pas encore traitées** : analyse des scènes en arrière-plan, coupure manquée à 40 s, nouveau test. Elles sont à transmettre à A, puis E refusionnera. Ce rapport ne les couvre pas.
3. **Test `786e68c`** (`test_scenes.py`, `eq` ou `lutyuv`) : à valider par vous.
4. **Filtres de A vérifiés avec FFmpeg 6.1 seulement.** E a fait passer les tests sous 7.1.5. FFmpeg 9.1 n'a pas été testé.
5. **Non testé (n°17)** : la suite complète, `test_sources.py`, `test_stabilisation.py` et QTGMC dans l'exe. Sur la scène 1, `safe_levels` n'émet toujours pas `colorlevels`.
6. **F1, licence LOL** : les poids `lol_v1` et `lol_v2` sont retenus **sous réserve**, car aucune licence n'est publiée à la source. Les poids « exposure » (issus de FiveK, usage de recherche seulement) sont exclus.
7. **F1, plafonds** : la transposition de `safe_gains` et `MAX_CONTRAST` (×/÷ 1,6) à la matrice et au gamma est à valider. Le mélange des canaux et la saturation ne sont pas bornés, et la partie locale d'IAT complet n'a aucun plafond.
8. **F2, poids non commerciaux** : tous les poids sont en CC-BY-NC-SA-4.0 et le code d'IQA-PyTorch est en PolyForm NC. KonIQ-10k n'a pas de licence écrite (zone grise). Les 6 bases de LIQE mix n'ont pas été vérifiées une par une. MUSIQ à une seule échelle n'est pas vérifié.
9. **F3 en cours** sur `grok/ia-vhs` (`67b9215`) : ni résultats ni note poussés pour l'instant.
10. **`RAPPORT-N18-POUR-CLAUDE.md` de Navigation (F4) pas encore écrit.**
11. **Mesures n°18 faites hors bac à sable** : vous les relancez (`ia_lumiere.py`, `essai_juge.py`, puis `f3_vhs.py`). Aucun extrait réel n'a été fourni : ces résultats sont non mesurés.

Aucun bot n'est bloqué depuis plus de 2 heures.
