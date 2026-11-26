# Rapport n°19 pour Claude — reprise d'une restauration (agent R3)

## Où

Dépôt : https://github.com/ordiform69-png/1er-projet-

| Référence | SHA | Note |
|---|---|---|
| Demande `DEMANDE-GROK-BUILD-19.md` sur `ccr-5856e8d6-8xt8uh` | `f484b4013122af0d86e7e593feaaad1a36771b9a` | lue en entier ; pas de fichier CORRECTIONS n°19 |
| Base `grok/qualite` | `3aa2c3d1aa3fa7c337de0d2697166ec076350605` | point de départ de `grok/reprise` |
| `grok/reprise` avant fusions R1/R2 | `7230f48134a2c8881f1d0a68277e1717514add86` | tests préparés, script de mesure, « une fois » préliminaire |
| R1 `grok/reprise-moteur` | `93c27a157658124dadad5a553034acf0d80752fb` | tête annoncée, confirmée sur origin |
| Fusion R1 dans `grok/reprise` | `c95bbb72429f6191b3b838ba2c76d0245a124b5a` | `merge --no-ff`, conflit `tests/test_reprise.py` résolu |
| R2 `grok/reprise-ecran` | `e990fa4c9a18916f89b65fe9153d4163ac05b58c` | tête annoncée (`e990fa4`), confirmée |
| Fusion R2 | `92813ab74925e4c26f5ab0eb58dc70ea695a2ca0` | `merge --no-ff`, aucun conflit |
| Alignement du script de mesure sur l'API R1 | `a8a3dd6ceb2e4d59bb7646c6a2df1c63d3047e5c` | SHA des mesures avant correctif |
| Mesures intégrées (avant correctif) | `58626b45be4d0c432acf736cc47cbf48849c5895` | résultats versionnés |
| Rapport initial n°19 | `93e06b9e3ca45c2d5b8c53cb26f47d582d265035` | bloqués : écart son/image 54 ms, sonder DVD |
| Correctif R1 `grok/reprise-moteur` | `0bc34a769aaa02a972fbae4a813d298095af9678` | tête annoncée (`0bc34a7`), confirmée |
| Fusion du correctif dans `grok/reprise` | `c9a670f234d4d4a722daa6f19f00bdc4a6dfc129` | `merge --no-ff`, aucun conflit |
| Mesures après correctif | `7306116d11e8aeafd599fb2b055e4a51c729853a` | « une fois » et « par parties », même SHA moteur `c9a670f` |
| **Tête de `grok/reprise` (ce rapport)** | voir le commit de ce fichier | |

Rien n'a été fusionné dans `ccr-5856e8d6-8xt8uh`. Pas de PR, pas de force-push. `estimation.py` : diff vide contre `3aa2c3d` (calcul intact). Aucune nouvelle dépendance. Pas de vidéo, capture ni zip ajoutés au dépôt.

Copie de travail : `/workspace/ctrl-vhs/reprise`.

## Fait

1. **Vérification des têtes.** `origin/grok/reprise-moteur` = `93c27a157658124dadad5a553034acf0d80752fb`, `origin/grok/reprise-ecran` = `e990fa4c9a18916f89b65fe9153d4163ac05b58c`. Correspondance exacte.

2. **Périmètre de R1** depuis `3aa2c3d` : `vhs_restore/reprise.py` (nouveau), `tests/test_reprise.py` (nouveau), `pipeline.py` uniquement. `estimation.py` intact. Dans `pipeline.py` : le corps de `export()` est inchangé ; les modifications portent sur `_export` (chauffe, `_partie`), `_export_morceaux` n'est pas le chemin de reprise (nouveau helper `_export_parties`), plus les aides `_duree_gardee` et `_tenter_reprise`, et un ajustement de `_concat_sans_recompression` (`inpoint 0` pour l'assemblage AAC). Cet ajustement de concat est un helper d'assemblage, cohérent avec le périmètre annoncé même s'il n'était pas nommé explicitement.

3. **Fusion R1 puis R2**, chacune en `--no-ff`, poussée tout de suite. R2 touche `gui.py`, `assistant.py`, `ergonomie.py` et `tests/test_ergonomie.py`. (La mention « Rendu n'a rien eu à changer » ne correspond pas au contenu de la branche : le commit `e990fa4` est substantiel et a été fusionné comme demandé.)

4. **Conflit `tests/test_reprise.py`** (ajout des deux côtés). Résolution sans affaiblir les tests :
   - base = fichier de R1, aligné sur l'API réelle (`decouper`, `applicable`, `possible`, `parties_faites`, `racine`, `calculer_cle`, `chauffe_partie`, `pipeline.export` — il n'existe pas de `reprise.restaurer`) ;
   - tous les tests unitaires et d'intégration de R1 conservés (commande FFmpeg, ménage 30 jours, DVD, disque, `possible`) ;
   - les 8 cas de la demande sont présents ; assertions les plus strictes des deux côtés : calage des bips à 20 ms (la demande, au lieu de 40 ms chez R1), test d'interruption qui vérifie que seules les parties restantes sont refaites (mtime inchangé), test de scènes de part et d'autre du raccord, textes d'écran exacts via `ergonomie` (R2) ;
   - règle réelle de découpage, documentée par des cas ajoutés : « dernière trop courte » = reste **plus court que la chauffe**, pas que `DUREE_PARTIE` (un reste de 10 s sur une partie de 20 s reste une partie). Aucune assertion de R1 n'a été supprimée ni relâchée.

5. **Tests** : uniquement les fichiers cités par la demande, un par un, `timeout 900`, `QT_QPA_PLATFORM=offscreen`, jamais la suite complète. `test_ergonomie.py` (R2) n'est pas dans la liste citée : non lancé. Quatre échecs dans `test_reprise.py`, analysés, dus au moteur de R1 (pas à la fusion). Aucune correction d'intégration, moteur inchangé, tests non affaiblis. Voir Vérifié et Bloqué.

6. **Mesures** sur la tête intégrée (`a8a3dd6`, même moteur que `92813ab`), mêmes films 3 min 720×576 TFF avec son, hors dépôt (`/tmp/mesures-n19/films`). « Une fois » refaite, puis « par parties » (constantes forcées : parties 60 s, seuil 1 s, chauffe 8 s, parce qu'un film de 3 min est sous le seuil de production de 20 min). 3 passages, médiane. Bruts dans `partage-grok/mesures-n19/`.

7. **Correctif R1 (`0bc34a7`)**, annoncé comme ne touchant que `_export`, `_concat_sans_recompression` et `_export_parties` dans `pipeline.py`, `estimation.py` intact. Tête distante confirmée. Le diff `93c27a1..0bc34a7` ne touche que `pipeline.py` et laisse `estimation.py` intact. Écart de périmètre : ajout d'un helper **`_assembler_parties`** (image copiée, son réencodé une seule fois en AAC) que `_export_parties` appelle à la place de `_concat_sans_recompression` ; ce dernier gagne un paramètre `sans_audio`. Fusion `--no-ff` `c9a670f`, aucun conflit, poussée tout de suite. Tests cités relancés (aucun test relâché). Mesures « une fois » et « par parties » refaites sur le SHA du merge. Les 4 bloqués **ne sont pas levés** (voir ci-dessous).

## Mesures

Matériel : Intel Xeon, 8 cœurs, 16 002 Mio RAM (environ 12,8 Gio disponibles), Linux 6.12.113+, Python 3.13, FFmpeg 7.1.5-0+deb13u1. Date : 26 nov. 2026, 16:36 (« une fois ») et 16:41 (« par parties ») Europe/Paris (UTC+1). SHA `a8a3dd6ceb2e4d59bb7646c6a2df1c63d3047e5c`. Profil Équilibré, `preset=medium`, crf=18, bwdif (scan TFF).

| Film | Une fois (médiane) | Par parties (médiane) | Écart |
|---|---|---|---|
| FFV1 4:2:2 | 52,555 s (17,52 s/min) — 52,555 / 49,984 / 55,474 | 69,668 s (23,22 s/min) — 70,826 / 69,148 / 69,668 | **+17,113 s (+32,6 %)** |
| MPEG-2 4:2:0 | 51,269 s (17,09 s/min) — 49,766 / 51,269 / 53,305 | 58,057 s (19,35 s/min) — 54,566 / 60,256 / 58,057 | **+6,788 s (+13,2 %)** |

La chauffe de 8 s sur les 2ᵉ et 3ᵉ parties ajoute 16 s de source (+8,9 %). Le surcoût MPEG-2 (+13 %) est un peu au-dessus de « quelques pourcents » ; celui du FFV1 (+33 %) est nettement plus élevé. Les deux modes ont tourné à la suite, même machine, RAM confortable.

Une mesure « une fois » avait déjà été faite avant les fusions (`84041e3`, 26 nov. 16:02 Europe/Paris, RAM disponible seulement ~2,7 Gio) : FFV1 62,380 s, MPEG-2 59,280 s. Elle n'est pas comparable (autre SHA, machine plus chargée).

### Après correctif R1 (`c9a670f`, 26 nov. 2026)

Même machine, FFmpeg 7.1.5, mêmes films, ~13 Gio RAM disponibles. SHA `c9a670f234d4d4a722daa6f19f00bdc4a6dfc129`.

« Par parties » : 17:26 Europe/Paris (UTC+1). « Une fois » : une première série à 17:20 était trop dispersée (FFV1 73,632 / 69,536 / 62,973 s, tendance à la baisse, machine encore chargée) et n'est pas retenue pour la comparaison ; la série stable ci-dessous a été relancée à 17:32, juste après.

| Film | Une fois (médiane, série stable) | Par parties (médiane) | Écart |
|---|---|---|---|
| FFV1 4:2:2 | 51,301 s (17,10 s/min) — 52,767 / 51,301 / 51,017 | 58,831 s (19,61 s/min) — 58,831 / 54,925 / 59,954 | **+7,530 s (+14,7 %)** |
| MPEG-2 4:2:0 | 46,116 s (15,37 s/min) — 46,116 / 45,655 / 47,165 | 51,297 s (17,10 s/min) — 51,297 / 51,719 / 50,445 | **+5,181 s (+11,2 %)** |

Comparaison au SHA `a8a3dd6` (avant correctif, même recettes) :

| Film | Surcoût parties avant | Surcoût parties après |
|---|---|---|
| FFV1 4:2:2 | +32,6 % (69,668 vs 52,555 s) | +14,7 % (58,831 vs 51,301 s) |
| MPEG-2 4:2:0 | +13,2 % (58,057 vs 51,269 s) | +11,2 % (51,297 vs 46,116 s) |

Le surcoût FFV1 se rapproche du MPEG-2 et de l'ordre de grandeur de la chauffe (+8,9 % de source). Il reste au-dessus de « quelques pourcents ». L'écart exact entre sessions doit être lu avec prudence : le chemin « une fois » n'est pas censé changer avec ce correctif, et les durées absolues bougent un peu d'une session à l'autre.

## Vérifié

Fichiers cités, un à un, le 26 nov. 2026 de 16:29 à 16:34 Europe/Paris (UTC+1), SHA `a8a3dd6` (avant correctif), puis relance le 26 nov. de 17:14 à 17:19 Europe/Paris (UTC+1), SHA `c9a670f` (après correctif), FFmpeg 7.1.5. Même décompte à chaque fois :


| Fichier | Résultat |
|---|---|
| `tests/test_reprise.py` | 12 passés, **4 échoués** (voir Bloqué) |
| `tests/test_pipeline.py` | 18 passés |
| `tests/test_scenes.py` | 13 passés |
| `tests/test_passages_gui.py` | 4 passés |
| `tests/test_arret_travail.py` | 2 passés |
| `tests/test_vides_montage.py` | 6 passés (3 DeprecationWarning pathlib, déjà présents) |
| `tests/test_assistant.py` | 9 passés |
| `tests/test_estimation.py` | 6 passés |

Dans `test_reprise.py`, les cas de la demande qui passent : découpage et chauffe, `possible` / `applicable`, film court / IA / stab / bande / cadence sans dossier, réglages changés (ancien dossier effacé), scènes identiques de part et d'autre du raccord à 20 s (écart d'image < 2/255 contre la restauration en une fois), messages d'ouverture / progression / arrêt (textes exacts, vouvoiement, mot « partie »). Les tests de commande FFmpeg, de ménage à 30 jours et de place disque passent aussi.

Les trois tests d'export 80 s qui échouent (même résultat, partie abîmée, interruption) vont au bout de l'export : 2000 images, reprise des seules parties restantes, partie abîmée refaite, dossier ménagé. Ils butent ensuite sur l'assertion « durée du son = durée de l'image à 20 ms près ». Après le correctif, l'écart est passé de 54 ms à 40 ms, toujours au-dessus du seuil. Le test DVD échoue toujours. Aucun test n'a été relâché.

## Non testé

- `tests/test_ergonomie.py` (ajout R2 : phrases, lecture tolérante, annonce à l'écran 1280×641) : **non cité** par la demande, donc non lancé.
- Mesure par parties avec les constantes de *production* (parties de 10 min, seuil de 20 min) : un film de 3 min ne déclencherait pas le découpage ; le script force 60 s / 1 s / 8 s, comme prévu dans `METHODE.md`.
- Box en FFmpeg 7.1.5 uniquement (la demande mentionne aussi 6.1 et 9.1 sous Windows).

## Bloqué

Les quatre échecs **ne sont pas levés** après le correctif `0bc34a7`. Reproduits hors pytest sur le SHA `c9a670f`. Ce n'est pas un conflit d'intégration : les assertions sont celles de R1. Le moteur n'a pas été retouché par R3. Les tests n'ont pas été relâchés.

### 1. Durée du son et de l'image à 20 ms près (3 tests) — partiellement amélioré, non levé

`test_meme_resultat_que_d_une_fois`, `test_reprise_partie_abimee_et_menage`, `test_interruption_puis_reprise`.

| | Image | Son | Écart |
|---|---|---|---|
| Avant correctif (`a8a3dd6`) | 79,920 s | 79,866 s | **54 ms** |
| Après correctif (`c9a670f`) | 79,920 s | 79,880 s | **40 ms** (toujours > 20 ms) |
| En une fois (inchangé) | 80,000 s | 80,000 s | 0 |

Diagnostic après correctif, même film de 80 s, 25 im/s (identique à avant pour les parties elles-mêmes) :

- restauration **en une fois** : image et son à **80,000 s**, 2000 images, écart 0 ;
- **partie 1** (pas de chauffe) : 20,000 s, 500 images, `sonder` vrai ;
- **parties 2, 3 et 4** (chauffe de 3 s) : image **19,960 s / 499 images**, son 19,946 s. `sonder(..., duree=20, fps=25)` reste vrai (tolérance 41 ms, écart 40 ms).

Le correctif (ordre `setpts` puis `trim`, marge de lecture élargie, `_assembler_parties` qui recoupe le son sur la durée de l'image) **n'a pas rétabli la 500ᵉ image** des parties avec chauffe, sur cette box FFmpeg 7.1.5. L'assemblage du son est un peu plus juste (54 → 40 ms) mais l'assertion à 20 ms échoue encore. À retravailler du côté R1.

### 2. DVD en plusieurs VOB (`test_dvd_en_plusieurs_morceaux`) — non levé

Inchangé : `open_media` annonce **40,032 s**. La 2ᵉ partie est attendue à **20,032 s**. Après `_export`, ffprobe lit **19,960 s** (500 images). `sonder` refuse : |19,960 − 20,032| = 72 ms > 41 ms, d'où `ToolError: Une partie restaurée est incomplète. Relancez pour la refaire.`

## Interprétations et ambiguïtés (déjà relevées, confirmées)

- Pas de contradiction entre le brief et `DEMANDE-GROK-BUILD-19.md`. Le fichier prime ; il est plus détaillé.
- « La dernière trop courte rejoint la précédente » : R1 l'implémente comme un reste **plus court que la chauffe**. C'est l'API réelle, conservée dans les tests.
- Dossier Linux : `~/.local/share/VHSRestoreAI/reprise` (demande, et `racine()` de R1), pas `~/.local/state`.
- Messages d'écran dans `ergonomie.py` (R2), pas dans `reprise.py`.
- Seuil de production 20 min vs film de mesure 3 min : le script force le découpage, écrit dans `METHODE.md`.
