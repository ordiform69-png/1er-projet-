# Rapport n°16 pour Claude

Assistant selon les trois maquettes. Branche `grok/design-maquettes`.
Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request.

## Où

Base : `ccr-5856e8d6-8xt8uh`, commit `383fcc6`.

Branches sources (têtes) :

| Branche | Tête | Rôle |
|---|---|---|
| `grok/design-navigation` | `d65683a` | Repères, boutons, vert d'action |
| `grok/design-rendu` | `29103dd` | Noms des rendus et étape 1 en liste |
| `grok/design-lumiere` | `2b94512` | Jauges à sept crans |
| `grok/design-lancer` | `5244ae7` | Résumé et pastilles AVANT / APRÈS |

Commits de ces branches, au-dessus de `383fcc6` :

- Navigation : `5491cb7` (branche vide), `fb21bd1` (vert), `2bdf2ff` (repères), `23eab04` (icône blanche), `d65683a` (en-tête 16 pt).
- Rendu : `d78b7e8` (noms), `29103dd` (liste verticale).
- Lumière : `2b94512`.
- Lancer : `5244ae7`.

Fusion sur `grok/design-maquettes`, dans l'ordre demandé :

- `7b1f541` : fusion de `grok/design-navigation`.
- `23aff3e` : fusion de `grok/design-rendu`.
- `a5cdee9` : fusion de `grok/design-lumiere`.
- `0c3c2ac` : fusion de `grok/design-lancer`.
- Le commit qui ajoute ce rapport (tête de la branche) aligne le mot « ← Revenir » sur le bouton et étend le test de taille.

## Fait

- Étape 1 : ligne grise « Votre cassette, sans changement », puis trois lignes cliquables avec la vraie petite image, le nom en gras et le sous-titre. Choix en cours : bordure bleue et pastille. Lien « Voir ces images en grand ». `a.tuiles[cle]` est gardé.
- Noms affichés, clés inchangées : « Nettoyage léger », « Bien nettoyé, naturel (conseillé) », « Nettoyage au plus fort ».
- Lumière et couleurs : jauge à 7 crans, clic ou flèches, pas de glisser. Boutons « Plus sombre » / « Plus clair » (et les équivalents). Phrase : « La grande image change à chaque clic : à gauche avant, à droite après. » `p.lignes[cle]` est gardé. Pas d'image dans le panneau.
- Vérifier et lancer : résumé en lignes, libellés en gras. Durée et place une seule fois, via `estimation.lignes`. S'il manque de la place, cette ligne est rouge et passe en premier. Avant l'avant / après : « La durée s'affichera après l'avant / après. » Pastilles « AVANT » et « APRÈS ». « Lancer la restauration » reste le bouton du pied de fenêtre.
- Repères à gauche : Rendu, Lumière, Coupes, Son, Lancer (Son seulement s'il y a du son ; pas de Coupes pour une photo). Étape faite cliquable, étape à venir non cliquable. `REPERES_VERTICAUX = True`. En-tête « Étape N sur M » et titre sur une ligne. « Rien à changer ? Cliquez sur Suivant. » sous le titre des étapes facultatives. « ← Revenir » et « Suivant → » (Suivant vert).
- Le calcul de `estimation.py` et `pipeline.py` ne sont pas modifiés.
- `test_chaque_etape_tient_a_1280_641` couvre maintenant 100, 125 et 150 %, film et photo : fenêtre 1280 × 641, pas de défilement horizontal, « Suivant » et « Lancer la restauration » dans la fenêtre.

## Vérifié

Relecture des textes dans `vhs_restore/` (pas d'exécution) :

- Plus de « Fidèle », « Équilibré » ni « Maximum » comme nom affiché. Il en reste dans des commentaires (`profiles.py`, `pipeline.py`, `estimation.py`) et dans un libellé de test (`test_sources.py`, mesure de pellicule). Ce n'est pas à l'écran.
- « RESTAURÉ » n'est plus dessiné : `set_after_label` le remplace par « APRÈS ». « COULEURS IA » ne change pas.
- `python3 -m py_compile` des fichiers touchés : code 0. Ce n'est pas la suite de tests.

## Repères

`REPERES_VERTICAUX` reste `True`.

Le commit `d65683a` dit que le titre le plus long tient à 100 % et à 125 % avec les repères verticaux. Cette mesure n'a pas été refaite ici (voir Non testé). Si une étape dépasse à 100 ou 125 %, passer la constante à `False` : les mêmes repères passent alors sur une ligne de 30 px au-dessus du titre.

## Non testé

- Tous les fichiers de tests cités par la demande (`test_assistant.py`, `test_bande.py`, `test_coupe_un_clic.py`, `test_sources.py`, `test_ecran_unique.py`, `test_lumiere.py`, `test_estimation.py`, `test_gui.py`, `test_theme.py`, `test_senior.py`, `test_etats_interface.py`, `test_ergonomie.py`). Aucun n'a été lancé. Pas de nombre de tests, pas de code de sortie pytest.
- Tailles 1280 × 641 à 100, 125 et 150 % (film et photo), y compris le défilement horizontal et la visibilité de « Suivant » et de « Lancer la restauration ».
- Choix des repères verticaux ou horizontaux : non mesuré. La constante est laissée à `True` en attendant cette mesure.
- Vrai Windows, vrai écran, contraste mesuré à l'œil. Le test de contraste est dans `test_theme.py`, non lancé.

## Bloqué

Rien dans le code. Les tests et les mesures de taille ne sont pas faits : à lancer de votre côté avant toute fusion.
