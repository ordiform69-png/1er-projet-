# Rapport consolidé n°17 et n°18 pour Claude

Index des chantiers. Le détail et les tableaux sont dans les rapports des bots, cités ci-dessous. Têtes relevées le 26/11 à 15:17 (heure de Paris), après `git fetch --prune origin`.

## 1. Où

| Chantier | Branche | Hash |
|---|---|---|
| Base (commits de Claude seulement) | `ccr-5856e8d6-8xt8uh` | `fed2275` |
| n°17 A, scènes | `grok/qualite-scenes` | `3968865` |
| n°17 B, précision 10 bits | `grok/qualite-precision` | `387ce99` |
| n°17 C, numérisation | `grok/qualite-numerisation` | `a18c106` |
| n°17 D, étude QTGMC (non fusionnée) | `grok/qualite-qtgmc` | `0f37607` |
| n°17 E, intégration (refusion de A en `84203b7`) | `grok/qualite` | `3aa2c3d` |
| n°18 F4, banc et synthèse | `grok/ia-essai` | `e65c4e9` |
| n°18 F1, IAT | `grok/ia-lumiere` | `5091c59` |
| n°18 F2, juges | `grok/ia-juge` | `ec827b6` |
| n°18 F3, modèles VHS | `grok/ia-vhs` | `fdf1027` |

À lire :
- `vhs-restore-ai/partage-grok/RAPPORT-N17-POUR-CLAUDE.md` sur `grok/qualite` (lire en priorité la partie « Corrections ») ;
- `vhs-restore-ai/partage-grok/RAPPORT-N18-POUR-CLAUDE.md` sur `grok/ia-essai`.

## 2. En bref

**n°17**
- Vos corrections sont faites (A `3968865`, refusionné par E). L'analyse des scènes ne bloque plus l'ouverture : elle tourne en arrière-plan.
- Sur votre film de 60 s, l'analyse trouve 3 scènes, avec des coupures à **20,0 s et 40,0 s**. Les gains sur la scène normale valent **1,0000** (rr, gg et bb). Les tests passent : `test_scenes` 13, `test_assistant` 9 et `test_lumiere` 10.
- Temps mesuré avec votre méthode (720×576 entrelacé, son, 60 s) : **−3 %** en FFV1 4:2:2 et **+15 %** en MPEG-2 4:2:0, donc sous la limite de 25 %. Les +437 % ne se reproduisent pas : ils venaient du film d'essai en 4:4:4.
- `pipeline.py` et `estimation.py` ne changent pas entre `6fa61db` et `3aa2c3d`. Pas de QTGMC dans l'exe (étude de D).

**n°18**
- Recommandation **provisoire** de F4 : ne faire entrer aucune IA dans `vhs_restore`. IAT s'éloigne de l'origine. Aucun juge ne bat le réglage fixe `maximum+n0` (60 % de bons choix, contre 53 % pour CLIP-IQA+). Les modèles VHS demandent environ 850 à 900 h de calcul pour un film de 2 h, sans mieux se rapprocher de l'origine que la chaîne actuelle.
- Toutes les mesures ont été faites **hors bac à sable** (machines partagées, 5 images, dégradation synthétique). Aucun extrait de cassette n'a été fourni : non mesuré.
- Écart dû à la mise à l'échelle : le `scale` bilinéaire diffère entre FFmpeg 6.1 et 7. Les chiffres du CSV de F4 (6.1.1) et ceux de F1, F2 et F3 (7.1.5) s'écartent de **0,08 à 1,8 dB** selon l'image. F1, F2 et F3 restent comparables entre eux.

## 3. Règles (vérifiées par `git diff`)

- Moteur intact : `estimation.py` n'a aucune différence avec `4f09073`. `pipeline.py` ne change que pour A et B, comme prévu ; la refusion des corrections n'y touche pas.
- n°18 : les branches `ia-*` ne touchent rien hors de `essais/n18/`, à part `partage-grok/RAPPORT-N18-POUR-CLAUDE.md` sur `ia-essai`. Rien dans `vhs_restore/`, les requirements ou le `.spec`.
- Aucun binaire commité : ni `.onnx`, ni poids, ni image, ni vidéo, ni zip.
- Ni fusion dans la base ni PR : la base ne contient que des commits de Claude, et aucune PR n'est ouverte.
- Petits écarts :
  - B a modifié `tests/test_sources.py` et `tests/test_stabilisation.py`, qui ne sont pas cités dans la demande et n'ont pas été lancés.
  - D a ajouté `.github/workflows/vhs-restore-qtgmc-etude.yml` et `essai-qtgmc-n17.ps1` (workflow d'étude séparé, celui de fabrication est inchangé).

## 4. À trancher par vous

1. **Test `786e68c`** : `test_scenes.py` accepte `eq` ou `lutyuv` (gamma 0,83333333). Il reste nécessaire tant que B est fusionné.
2. **Licence LOL (F1)** : les poids `lol_v1` et `lol_v2` sont retenus sous réserve, car les auteurs ne publient aucune licence. Les poids « Exposure » (FiveK) sont exclus.
3. **Plafonds de F1** : la transposition de `safe_gains` et `MAX_CONTRAST` (×/÷ 1,6) à la matrice et au gamma est à valider. Le mélange des canaux n'est pas borné, et la partie locale d'IAT n'a aucun plafond.
4. **Poids non commerciaux** : F2 (CC-BY-NC-SA-4.0, code IQA-PyTorch en PolyForm NC, KonIQ-10k en zone grise) et F3 (modèles VHS en CC-BY-NC-SA-4.0, données d'entraînement non trouvées).
5. **Real-ESRGAN** (BSD-3-Clause) : c'est le plus proche de l'origine sur le banc, mais ses données DIV2K sont réservées à la recherche académique.
6. **FFmpeg 9.1 non testé** : les filtres de A ont été vérifiés en 6.1, et la n°17 a été testée en 7.1.5. La suite complète n'a pas été lancée.
7. **Mesures n°18 à relancer** sur une machine au repos, avec un seul FFmpeg (7.1), depuis `vhs-restore-ai/` :
   - `python essais/n18/reference.py`
   - `python essais/n18/ia_lumiere.py [--extraits <dossier>]`
   - `python essais/n18/essai_juge.py [--extraits <dossier>]`
   - `python essais/n18/f3_vhs.py [--extraits <dossier>]`, puis `python essais/n18/f3_vhs.py --chrono 3`
