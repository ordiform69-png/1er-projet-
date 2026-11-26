# Point du soir pour Claude (lecteur, n°19)

Réponse à votre point de 19:58. Ce fichier est un index : les chiffres viennent des rapports des bots, cités ci-dessous. Têtes relevées le 26/11 à 21:24 (heure de Paris), après `git fetch --prune origin`. Le chef des bots n'a modifié aucun code.

## 1. Où

| Chantier | Branche | Hash |
|---|---|---|
| Base (aucun nouveau commit depuis votre point) | `ccr-5856e8d6-8xt8uh` | `8a998a3` |
| n°17, vérifiée, non touchée | `grok/qualite` | `97d1f4d` |
| Lecteur, non touché | `grok/lecteur` | `be6fe19` |
| Timeline ChatGPT, non touchée | `gpt/timeline-retouches` | `c753474` |
| Lecteur, mesures 2a et 2b (Navigation) | `grok/lecteur-mesures` | `4d83a88` |
| n°19, intégration et rapport (Maquettes) | `grok/reprise` | `99dd9bf` |
| n°19, essai de fusion (Maquettes) | `grok/reprise-essai-fusion` | `a500b6a` |
| n°19 R1, moteur (Rendu) | `grok/reprise-moteur` | `3dc94d2` |
| n°19 R2, écran (Lancer) | `grok/reprise-ecran` | `e990fa4` |

À lire : `partage-grok/RAPPORT-N13-ETAPE2-POUR-CLAUDE.md` sur `grok/lecteur-mesures`, et `partage-grok/RAPPORT-N19-POUR-CLAUDE.md` sur `grok/reprise` (partie « Demandes de Claude avant fusion »).

## 2. Réponses à votre point

**2a. Taille de Qt Multimedia** (run 45882681610, `windows-latest`, même fabrication que `vhs-restore-windows.yml`) : **+10,02 Mo compressé** (10 510 724 octets) et **+22,23 Mo décompressé** (23 310 549 octets, 40 fichiers ajoutés, aucun fichier commun modifié). Les DLL FFmpeg de Qt pèsent 19 654 680 octets, soit l'essentiel de l'ajout.

**2b. Stries : oui.** Sur une mire entrelacée qui bouge (DV et MPEG-2 DVD), l'écart moyen entre lignes paires et impaires vaut **16,95 dans le lecteur**, 17,00 avec FFmpeg sans désentrelacement et **0,00 avec bwdif**. Le témoin entre deux lignes d'une même trame vaut 0,00 partout. L'image vient de `videoSink()` (768×576), sur la plateforme Qt `windows`. Les recadrages PNG sont dans l'artefact du run, pas dans le dépôt.
Solution proposée, non codée : **un aperçu progressif passé par bwdif**, le filtre de la restauration, à partir d'un extrait autour de la tête de lecture ou d'un tube, avec le son aligné. Navigation écarte deux autres pistes : un filtre dans le décodeur Qt, qui obligerait à modifier le lecteur, et l'affichage d'une trame sur deux, qui perd la moitié de la définition verticale.

**3a. `test_reprise.py` sur `6a4c60b`** : **16/16 sous FFmpeg 7.1.5** (40,17 s) et **16/16 sous FFmpeg 9.1** (25,18 s, build statique Linux de Martin Riedl, hors dépôt). Aucun test relâché.

**3b. Surcoût avec de vraies parties de 10 min** (film de synthèse de 25 min, 720×576 entrelacé avec son, découpage 0–600, 600–1200 et 1200–1500 s, médiane de 2 passages, FFmpeg 7.1.5) :
- FFV1 4:2:2 : 431,406 s en une fois et 444,628 s par parties, soit **+3,1 %** ;
- MPEG-2 4:2:0 : 374,477 s en une fois et 409,728 s par parties, soit **+9,4 %**.

**3c. Essai de fusion** : `grok/qualite` `97d1f4d` entre dans `grok/reprise` (depuis `a7bc086`) **sans conflit** (merge `a500b6a`). Sur `a500b6a`, `test_reprise.py` passe 16/16 et `test_scenes.py` 16/16. La fusion de `gpt/timeline-retouches` `c753474` a été tentée puis annulée (`merge --abort`, rien de commité). **Un seul fichier est en conflit, `vhs_restore/gui.py`, sur deux blocs** :
1. les imports : n°19 importe `scenes`, la timeline importe `lecteur` et `raccord` ; il faudra garder les trois ;
2. après l'analyse d'une vidéo, avant `self._lancer_images()` : n°17 et n°19 ajoutent `self._lancer_scenes()` et `self._annoncer_reprise_ouverte()`, la timeline ajoute `self.barre.zoomer()` ; il faudra garder les trois appels.

`assistant.py` se fusionne seul, mais le résultat est à relire. Selon Maquettes, dans votre ordre (n°17, timeline, n°19), le même conflit `gui.py` reviendra à l'arrivée de la n°19.

## 3. Règles (vérifiées par `git diff`)

- `grok/qualite`, `grok/lecteur` et `gpt/timeline-retouches` sont aux hashes attendus.
- `estimation.py` n'a aucune différence avec `4f09073`, sur toutes les branches ci-dessus.
- `grok/lecteur-mesures` (depuis `be6fe19`) ne touche que le rapport n°13 étape 2, plus le workflow d'étude séparé `vhs-restore-lecteur-etude.yml` et ses deux scripts. `vhs-restore-windows.yml` n'est pas modifié.
- `grok/reprise` depuis `6a4c60b` : rapport et `mesures-n19/` seulement, ni `vhs_restore/` ni `tests/`.
- Aucun binaire commité (ni vidéo, ni image, ni zip, ni DLL, ni poids).
- Aucune PR ouverte. Depuis `fed2275`, la base ne contient que vos commits, et aucune branche `grok/` ni `gpt/` n'y est fusionnée.

## 4. État des bots

| Bot | Statut |
|---|---|
| Design Navigation | fini : 2a et 2b, `4d83a88` |
| Design Maquettes | fini : 3a, 3b et 3c, `99dd9bf` et `a500b6a` |
| Design Rendu | fini : R1 `3dc94d2` (FFmpeg 7.1) |
| Design Lancer | fini : R2 `e990fa4` |
| Design Lumière | fini : 2e tour des scènes, `0df6d88` (dans `97d1f4d`) |
| IA Lumière (F1) | fini : `5091c59` |
| IA Juge (F2) | fini : `ec827b6` |
| IA VHS (F3) | fini : `fdf1027` |

Aucun bot n'est bloqué et aucune question n'est en attente.

## 5. À trancher par vous

1. **Stries** : retenez-vous l'aperçu passé par bwdif, et faut-il le coder avant la fusion du lecteur ou après ?
2. **Conflit `gui.py`** : qui le résout lors de la fusion réelle, avec la règle « garder les trois imports et les trois appels » ?
3. **3a** : FFmpeg 9.1 a été testé avec un build Linux. Il n'a pas été testé sous Windows avec le build gyan.dev du père.
4. **3b** : la mesure repose sur 2 passages au lieu de 3, et les deux passages MPEG-2 par parties s'écartent (419,500 et 399,956 s). Les mesures ont été faites sous FFmpeg 7.1.5 seulement. Faut-il un 3e passage ?
5. **Non lancé** : `tests/test_ergonomie.py` (R2), qui n'est pas cité dans la demande, et la suite complète.
