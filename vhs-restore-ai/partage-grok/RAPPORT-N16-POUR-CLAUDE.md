# Rapport n°16 pour Claude — maquettes de l'assistant

Intégration des quatre branches design sur `grok/design-maquettes`.
Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request. La suite complète n'a pas
été lancée (demandé : trop longue, environ 50 min).

## Où

- Dépôt : `https://github.com/ordiform69-png/1er-projet-`
- Branche d'intégration : `grok/design-maquettes`
- Base : `ccr-5856e8d6-8xt8uh` au commit `383fcc6` (pas d'avance depuis, 25 nov. 2026, 22:39 Europe/Paris)

| Élément | Commit (SHA court) | SHA complet |
|---|---|---|
| Base | `383fcc6` | `383fcc6a7207ec81e1ebcce9af462717c2c3c5fd` |
| `grok/design-navigation` (tête) | `d65683a` | `d65683a26f1f1c6f98d9c0d1dcd37fcf960eadbd` |
| Fusion navigation (`--no-ff`) | `7b1f541` | `7b1f54172a64f02ea6f3aab5bd977ee8da32292b` |
| `grok/design-rendu` (tête) | `29103dd` | `29103dd63be095fb38a9029ef73b80c330401456` |
| Fusion rendu (`--no-ff`) | `23aff3e` | `23aff3ed88f35090c6b25c0e2fdadd2aa3174981` |
| `grok/design-lumiere` (tête) | `2b94512` | `2b94512f57e7a22e963a5c9a8d169d469ae9b3b2` |
| Fusion lumière (`--no-ff`) | `a5cdee9` | `a5cdee946b787f0b5597f7a1fa3354fe2c82ed64` |
| `grok/design-lancer` (tête) | `5244ae7` | `5244ae7ff5afa40f9a590256e2e15cd3db0d554b` |
| Fusion lancer (`--no-ff`) | `0c3c2ac` | `0c3c2ac359e36d0d76d9d393fa37553ed3f13593` |
| Test de taille, « ← Revenir » dans le résumé, première version de ce rapport | `583c488` | `583c48838a279c9aead17e1551ee35c6fbfc7a84` |

Le SHA final de `grok/design-maquettes` est celui du commit qui met à jour ce rapport avec les résultats des tests (tête de la branche une fois poussé).

## Fait

1. Branche `grok/design-maquettes` créée depuis `383fcc6`, puis fusion des quatre branches **dans l'ordre demandé** : navigation, rendu, lumière, lancer. Merges `--no-ff`, sans réécriture, poussés au fur et à mesure. Rien dans `ccr-5856e8d6-8xt8uh`, pas de force-push, pas de PR.

2. **Conflits, tous design, intentions claires, résolus sans toucher au moteur :**
   - `assistant.py` à la fusion de `grok/design-rendu` : imports Qt. Union de `QPoint` (rendu, pastille ✓) et de `QFontMetrics` / `QGridLayout` (navigation, repères).
   - `assistant.py` à la fusion de `grok/design-lancer` : les deux classes ajoutées au même endroit. `_Repere` (navigation) et `_Resume` (lancer) sont toutes les deux conservées. `gui.py` s'est fusionné tout seul (pastilles AVANT / APRÈS).

3. **Moteur inchangé.** `git diff 383fcc6...HEAD -- vhs-restore-ai/vhs_restore/pipeline.py vhs-restore-ai/vhs_restore/estimation.py` est vide. `calcul`, `facteur` et `extrapoler` n'ont pas bougé. Aucune nouvelle dépendance.

4. **Fichiers touchés** par les quatre fusions : `assistant.py`, `ecran.py`, `gui.py`, `lumiere.py`, `profiles.py`, `theme.py`, `tests/test_assistant.py` (noms des rendus, déjà par l'agent 1), `tests/test_theme.py`. Ensuite, `583c488` : `test_chaque_etape_tient_a_1280_641` étendu à 100, 125 et 150 % (film et photo, pas de défilement horizontal, « Suivant » et « Lancer la restauration » dans la fenêtre) ; le texte d'aide après l'avant / après dit « ← Revenir » (le nom réel du bouton) au lieu de « Retour ».

5. **Relecture des textes.** Les noms à l'écran sont « Nettoyage léger », « Bien nettoyé, naturel », « Nettoyage au plus fort ». Plus de « Fidèle », « Équilibré », « Maximum », « ORIGINAL » ou « RESTAURÉ » visibles. `set_after_label("RESTAURÉ")` existe encore dans `gui.py` (`_preview_done`) mais est immédiatement remappé en « APRÈS ». Les commentaires internes de `pipeline.py`, `profiles.py` et `estimation.py` citent encore les anciens noms ; ce n'est pas l'écran. Un libellé de test dans `test_sources.py` (« pellicule Fidèle ») n'est pas l'interface. Vouvoiement conservé dans les fichiers d'interface modifiés.

## Repères verticaux ou horizontaux

**`REPERES_VERTICAUX` reste à `True`.**

Sur la base seule, la fenêtre reste 1280 × 641 à 100, 125 et 150 % (hauteur minimale 494 à 537 px). Après navigation seulement, elle tient encore (hauteur minimale 514 à 585 px). Dès la fusion de `grok/design-rendu` (liste verticale de l'étape 1, tuiles d'environ 112 × 84 plus la ligne « Votre cassette, sans changement »), la hauteur minimale du `QStackedWidget` augmente pour **toutes** les étapes :

| Moment | 100 % étape 1 | 100 % Lumière | 125 % étape 1 | 150 % étape 1 |
|---|---|---|---|---|
| Base `383fcc6` | 641 / min 506 | 641 / min 506 | 641 / min 522 | 641 / min 536 |
| + navigation | 641 / min 514 | 641 / min 543 | 641 / min 530 | 641 / min 544 |
| + rendu (et ensuite) | 641 / min 630 | **659** / min 659 | **647** / min 647 | **661** / min 661 |

La ligne « Rien à changer ? Cliquez sur Suivant. » (navigation) ajoute environ 29 px à partir de Lumière : à 100 %, on passe de 630 px (encore juste sous 641) à 659 px. `grok/design-lumiere` et `grok/design-lancer` n'aggravent pas ces mesures. Pas de défilement horizontal. « Suivant » et « Lancer la restauration » restent dans l'écran, mais **la fenêtre grandit**.

Passer `REPERES_VERTICAUX` à `False` **empire** la hauteur (rangée de 30 px au-dessus du titre : 666 px dès l'étape 1 à 100 %). Ce n'est donc pas le levier prévu par la demande. Le correctif appartient aux agents (surtout l'étape 1 en liste verticale, pour que le `QStackedWidget` ne force pas une hauteur supérieure à 641, y compris à 125 et 150 %). Aucun correctif d'intégration n'a été appliqué sur leur code.

## Vérifié

Commande, Linux, hors écran, **un fichier à la fois**, chacun sous `timeout 900` (pas la suite complète) :

```
cd vhs-restore-ai
QT_QPA_PLATFORM=offscreen timeout 900 python -m pytest -q --tb=line tests/<fichier>.py
```

Environnement de cette machine : Python 3.13.5, PySide6 6.12.0, pytest 9.2.0, FFmpeg 7.1.5 (paquet Debian). Ce n'est pas l'environnement des rapports précédents (Python 3.12.7, FFmpeg 7.0.2-static).

Les tests ont été lancés sur `0c3c2ac` (les quatre fusions) avec une extension équivalente de `test_chaque_etape_tient_a_1280_641` (mêmes exigences : 100/125/150 %, film et photo, taille, défilement, visibilité des boutons). Le test poussé ensuite en `583c488` est le même contrôle, écrit en boucles plutôt qu'en paramètres pytest.

| Fichier | Résultat pytest | Code de sortie | Durée |
|---|---|---|---|
| `tests/test_assistant.py` | **7 failed, 7 passed** | 1 | 43,08 s |
| `tests/test_bande.py` | 4 passed | 0 | 0,45 s |
| `tests/test_coupe_un_clic.py` | 2 passed | 0 | 11,54 s |
| `tests/test_sources.py` | 14 passed | 0 | 59,59 s |
| `tests/test_ecran_unique.py` | 9 passed | 0 | 12,70 s |
| `tests/test_lumiere.py` | 10 passed | 0 | 12,11 s |
| `tests/test_estimation.py` | 5 passed | 0 | 41,72 s |
| `tests/test_gui.py` | 8 passed | 0 | 36,82 s |
| `tests/test_theme.py` | 11 passed | 0 | 3,70 s |
| `tests/test_senior.py` | 5 passed | 0 | 14,19 s |
| `tests/test_etats_interface.py` | 4 passed | 0 | 12,79 s |
| `tests/test_ergonomie.py` | 7 passed | 0 | 25,90 s |

**Total des fichiers cités : 86 passed, 7 failed, 0 skipped.** Aucun test affaibli ni supprimé.

Les 7 échecs sont tous une fenêtre plus haute que 641 px :

- `test_parcours_complet_d_un_film` : 1280 × 653 à la fin du parcours (assertion déjà présente).
- `test_chaque_etape_tient_a_1280_641` (les 6 combinaisons film/photo × 100/125/150 %) : à 100 %, l'étape 1 tient encore (641) et « Lumière et couleurs » passe à 659 ; à 125 % et 150 %, déjà l'étape 1 (647 et 661).

Cause : voir la section des repères. Branche principalement responsable : **`grok/design-rendu`**. Contribution de **`grok/design-navigation`** (ligne « Rien à changer », +29 px) qui fait dépasser 641 px à l'étape Lumière à 100 %.

`test_sources.py` a d'abord échoué une fois (`test_couleur_declaree_et_mire_rgb`, `ModuleNotFoundError: numpy`) faute de numpy dans l'environnement local de test. Numpy n'est pas une nouvelle dépendance du logiciel (déjà utilisé par `colorize.py` et ce test). Relancé ensuite : 14 passed, code 0, 59,59 s. C'est ce résultat qui est retenu ci-dessus.

`test_theme.py` (contraste du vert d'action ≥ 4,5 : 1, thèmes clair et sombre) est vert.

`python3 -m py_compile` des fichiers Python fusionnés : code 0.

## Non testé

- Suite complète (demandé : ne pas la lancer ; Claude la lance avant la fusion).
- Exe Windows, installateur, vraie cassette, vraies photos.
- Contrôle visuel des trois maquettes sur un écran réel (seulement mesures et tests hors écran).
- Python 3.12 (les tests ont tourné en 3.13.5).

## Bloqué

La fenêtre de l'assistant **grandit en hauteur** dès que `grok/design-rendu` est fusionné, à 125 % et 150 % dès l'étape 1, et à 100 % dès « Lumière et couleurs ». Les boutons restent visibles, il n'y a pas de défilement horizontal, mais l'exigence « fenêtre 1280 × 641, elle ne grandit pas » n'est pas tenue. `REPERES_VERTICAUX = False` n'arrange rien. Pas de correctif d'intégration appliqué : il faudrait retravailler la liste verticale de l'étape 1 (et le calcul de hauteur du `QStackedWidget`) côté agents.

Le reste de l'intégration (fusions, textes, moteur intact, autres fichiers de tests cités, mot « ← Revenir ») est en place sur `grok/design-maquettes`.
