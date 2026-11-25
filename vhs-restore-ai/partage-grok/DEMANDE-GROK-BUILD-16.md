# Demande n°16 : l'assistant selon les trois maquettes

L'utilisateur a choisi trois maquettes (jointes à son message) : « Choisir la beauté de
l'image », « Lumière et couleurs », « Vérifier et lancer ». On les suit, avec les
adaptations ci-dessous, décidées par Claude : elles évitent de rétrécir la grande image et de
tromper un homme de 76 ans. Ne pas les rediscuter : si un point bloque, voir « Si ça bloque ».

## Base, branches, équipe

- Base : `ccr-5856e8d6-8xt8uh`, commit indiqué dans le message de l'utilisateur (ou plus récent).
- Cinq agents, une branche chacun, partie de la base :

| Agent | Rôle | Branche | Fichiers à lui |
|---|---|---|---|
| 1 | Étape 1 et noms des rendus | `grok/design-rendu` | `profiles.py`, `assistant.py` (`_construire_rendu`, `PHRASES_RENDU`, `_rendus_prets`, `_choisir_rendu`), textes de profils dans `gui.py` |
| 2 | Lumière et couleurs | `grok/design-lumiere` | `lumiere.py` (classe `Panneau`, nouvelle classe `Jauge`) |
| 3 | Vérifier et lancer | `grok/design-lancer` | `assistant.py` (`_construire_fin`, `_ecrire_resume`), `CompareView` dans `gui.py` (pastilles) |
| 4 | Repères, boutons, couleurs | `grok/design-navigation` | `assistant.py` (`__init__` : en-tête, repères, navigation ; `aller` ; `style_assistant`), `theme.py`, `ecran.py` |
| 5 | Intégrateur et contrôleur | `grok/design-maquettes` | fusion des quatre branches, tests de taille, relecture des textes, rapport |

- Un agent ne modifie que ses fichiers ou ses fonctions. Besoin d'autre chose : il le note
  dans son commit, l'agent 5 l'ajoute à l'intégration.
- Chaque commit est poussé tout de suite. Rien ne reste seulement en local.

## Règles communes

- Moteur de restauration inchangé : aucun filtre, aucun réglage, rien dans `pipeline.py`.
- Ne pas toucher au calcul de `estimation.py` (`calcul`, `facteur`, `extrapoler`) : Claude
  l'a corrigé (durée mesurée contre la vraie restauration). Utiliser `estimation.lignes(w)`.
- Fenêtre 1280 × 641 : à 100, 125 et 150 % de texte, la fenêtre ne grandit pas, aucun
  défilement horizontal, « Suivant » et « Lancer la restauration » restent visibles.
- Vouvoiement, mots simples, les options nommées partout comme à l'écran.
- Aucune nouvelle dépendance. Python 3.12+. Thèmes clair et sombre.
- Tests : NE PAS lancer la suite complète (50 min, la tâche serait coupée). Seulement les
  fichiers cités, chacun avec `timeout 900`. Claude lance la suite complète avant la fusion.
- Aucun test affaibli. Un texte renommé : l'assertion vérifie le nouveau texte, elle n'est
  jamais supprimée. Garder les noms d'objets que les tests utilisent (`a.tuiles`,
  `a.compteur`, `a.titre`, `a.suivant`, `a.retour`, `a.voir`, `a.resume`, `p.lignes`…).
- Aucune capture, aucun zip dans le dépôt.
- Si ça bloque plus de 20 minutes : pousser ce qui marche, noter le blocage, passer à la suite.

## Agent 1 : étape 1 et noms des rendus (maquette 1)

Noms des rendus, partout (assistant, réglages libres, résumé, infobulles) ; les clés
`fidele`, `equilibre`, `maximum` et les noms de fichiers ne changent pas :

| Clé | Nom | Sous-titre dans l'assistant |
|---|---|---|
| `fidele` | Nettoyage léger | Garde l'aspect d'époque |
| `equilibre` | Bien nettoyé, naturel | Bon équilibre (titre : « Bien nettoyé, naturel (conseillé) ») |
| `maximum` | Nettoyage au plus fort | Plus long |

« Garder l'image d'origine » (maquette) est refusé : il croirait que rien ne change et le
confondrait avec la cassette d'origine.

Étape 1 : une liste verticale, comme la maquette.
- En haut, ligne grise non cliquable « Votre cassette, sans changement », avec la petite
  image de l'original (environ 80 × 60).
- Puis trois grandes lignes cliquables (toute la ligne) : à gauche la VRAIE petite image de ce
  rendu (environ 112 × 84 ; pas d'icône : c'est l'image qui permet de choisir), puis le nom en
  gras et le sous-titre dessous.
- Choix en cours : bordure bleue épaisse et pastille ronde ✓ à gauche, comme la maquette.
- « Voir ces images en grand » : petit lien sous la liste.
- Garder `a.tuiles[cle]` (`click()`, `text()` contient le nom et « Conseillé » pour
  `equilibre`, `icon()` non vide quand l'image est prête).
- Tests : `test_assistant.py`, `test_bande.py`, `test_coupe_un_clic.py`, `test_sources.py`,
  `test_ecran_unique.py` (les tuiles de « Qualité » en réglages libres doivent tenir).

## Agent 2 : Lumière et couleurs (maquette 2)

- Mode assistant : plus de phrase d'introduction (l'agent 4 met « Rien à changer ? Cliquez
  sur Suivant. » en tête) ; une ligne courte à la place : « La grande image change à chaque
  clic : à gauche avant, à droite après. »
- Chaque ligne : nom en gras · bouton « Plus sombre » · jauge · bouton « Plus clair » (et de
  même : Plus doux / Plus marqué, Plus pâles / Plus vives, Plus froide / Plus chaude).
  On garde les mots, pas « − » et « + » seuls : plus clair pour votre père.
- `Jauge` : 7 crans dessinés, un rond plein sur la valeur, la valeur écrite dessous
  (« Normal », « +2 », « −1 »). Clic sur un cran = cette valeur. AUCUN glisser (geste trop
  précis à 76 ans). Flèches gauche / droite au clavier. Nom accessible « Lumière : Normal ».
  Largeur 140 à 180 px.
- Pas d'image dans le panneau : la grande image à gauche reste l'aperçu (plus grande que
  celle de la maquette, avec avant et après).
- Garder `p.lignes[cle] == (bouton_moins, valeur, bouton_plus)` avec `valeur.text()` qui
  rend « Normal » ou « +3 », et `p.remettre`, `p.autre`, `p.note`.
- Réglages libres (`guide=False`) : mêmes lignes, plus serrées.
- Tests : `test_lumiere.py`, `test_assistant.py`, `test_ecran_unique.py`.

## Agent 3 : Vérifier et lancer (maquette 3)

- Résumé en lignes, libellé en gras : « Rendu : », « Lumière et couleurs : », « Passages
  enlevés : » (avec le début et la fin s'ils sont réglés ; « aucun » sinon), « Son : »
  (film avec son seulement). Texte enrichi avec les parties variables échappées (`html.escape`).
- Sous un trait : la durée et la place, en gras et un peu plus grand, UNE SEULE fois (la
  maquette les répète : non). Deux lignes de `estimation.lignes(w)`. S'il manque de la place,
  cette ligne en premier et en rouge. Avant l'avant / après : « La durée s'affichera après
  l'avant / après. »
- « Voir l'avant / après » reste sur cette page (obligatoire avant de lancer).
- « Lancer la restauration » reste le bouton du pied de fenêtre, en bas à droite (même
  place que la maquette) ; pas de second bouton « Lancer ».
- Pastilles sur la grande image : « AVANT » et « APRÈS » (au lieu d'« ORIGINAL » et
  « RESTAURÉ ») : ce sont les mots du bouton « Voir l'avant / après ». « COULEURS IA » ne
  change pas.
- La maquette montre deux photos portrait côte à côte : impossible (un film VHS est en 4:3,
  chaque image ferait 260 px de large). On garde la grande image partagée en deux.
- Tests : `test_assistant.py`, `test_estimation.py`, `test_ecran_unique.py`, `test_gui.py`.

## Agent 4 : repères, boutons, couleurs (les trois maquettes)

- Repères d'étapes à GAUCHE de la colonne de l'assistant (entre la grande image et le
  contenu), comme la maquette : rond numéroté, ✓ pour une étape faite, rond plein pour
  l'étape en cours (fond clair sur la ligne), gris pour la suite. Noms courts : Rendu,
  Lumière, Coupes, Son, Lancer (film, sans « Son » si pas de son) ; Rendu, Lumière, Lancer
  (photo). Les noms de la maquette (« Importer », « Stabiliser », « Enregistrer la vidéo »)
  n'existent pas dans le logiciel : non.
- Largeur des repères : 150 px au plus à 100 %. Une étape faite est cliquable (on revient
  en arrière) ; une étape à venir ne l'est pas.
- Constante `REPERES_VERTICAUX = True`. À `False` : les mêmes repères sur une ligne au-dessus
  du titre (30 px de haut). L'agent 5 choisit selon les mesures.
- En-tête : « Étape 2 sur 5 » et le titre sur une ligne, gros (garder `a.compteur`, `a.titre`).
- Étapes facultatives (Lumière et couleurs ; Début, fin et passages ; Le son) : sous le titre,
  en gras, « Rien à changer ? Cliquez sur Suivant. » (`a.rien_a_changer`).
- Navigation : « ← Revenir » et « Suivant → » ; « Suivant » vert, gros.
- Vert pour l'action principale : « Suivant », « Voir l'avant / après » tant qu'il reste à
  faire, « Lancer la restauration » quand il est allumé. Thèmes clair et sombre, texte blanc
  sur vert avec un contraste d'au moins 4,5 : 1 (le vérifier dans `test_theme.py`).
- Le nom de la fenêtre ne change pas (pas « Restauration VHS »).
- Tests : `test_assistant.py`, `test_theme.py`, `test_ecran_unique.py`, `test_senior.py`,
  `test_etats_interface.py`, `test_ergonomie.py`.

## Agent 5 : intégration et contrôle

1. Branche `grok/design-maquettes` depuis la base ; fusionner dans l'ordre : navigation,
   rendu, lumière, lancer. Conflits : garder l'intention des deux côtés.
2. Étendre `test_chaque_etape_tient_a_1280_641` (`test_assistant.py`) à 100, 125 et 150 %
   (`set_taille_texte`) : fenêtre 1280 × 641, pas de défilement horizontal, « Suivant » et
   « Lancer la restauration » visibles à chaque étape, film et photo.
3. Si une étape ne tient pas à 100 ou 125 % avec les repères verticaux : passer
   `REPERES_VERTICAUX` à `False`, et le dire dans le rapport.
4. Relecture : plus aucun « Fidèle », « Équilibré », « Maximum », « ORIGINAL », « RESTAURÉ »
   visible à l'écran (rechercher dans `vhs_restore/`) ; vouvoiement ; mêmes noms partout.
5. Lancer tous les fichiers de tests cités plus haut (pas la suite complète).
6. Rapport `partage-grok/RAPPORT-N16-POUR-CLAUDE.md` : Où (branche, hash de chaque commit) ·
   Fait · Vérifié (fichiers lancés, nombre, code de sortie) · Repères verticaux ou
   horizontaux, et pourquoi · Non testé · Bloqué (s'il y a lieu).

Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request : Claude vérifie, lance la suite
complète, et fusionne quand l'utilisateur le dit.
