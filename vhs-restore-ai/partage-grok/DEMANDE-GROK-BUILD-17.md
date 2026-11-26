# Demande n°17 : meilleure qualité de restauration (pour le chef des bots)

L'utilisateur demande ce qui manque pour mieux restaurer. Claude a fait l'inventaire du moteur
(`pipeline.py`) et retenu quatre chantiers. Trois touchent l'image restaurée, un est une étude.
Ne pas rediscuter les choix ci-dessous ; si un point bloque, voir « Si ça bloque ».

## Base, branches, équipe

- Base : `ccr-5856e8d6-8xt8uh`, commit indiqué dans le message (ou plus récent).

| Agent | Chantier | Branche | Fichiers à lui |
|---|---|---|---|
| A | Lumière et couleurs scène par scène | `grok/qualite-scenes` | nouveau `scenes.py`, branchement dans `pipeline.py` (`_levels_filter`, `_cast_filter` et leurs appels), `probe.py` (analyse) |
| B | Calcul en haute précision | `grok/qualite-precision` | `pipeline.py` (formats de pixels de la chaîne, remplacement de `eq`), `photo.py` si utile |
| C | Contrôle de la numérisation | `grok/qualite-numerisation` | `probe.py` (mesures), `advice.py` (conseils), textes d'affichage dans `gui.py` / `assistant.py` (une ligne) |
| D | QTGMC dans l'exe : ÉTUDE seulement | `grok/qualite-qtgmc` | rapport, essai dans un job séparé du workflow (le paquet livré ne change pas) |
| E | Intégration et mesures | `grok/qualite` | fusion de A, B, C (pas D), mesures, rapport |

A et B touchent tous deux `pipeline.py` : A ne modifie que les fonctions de niveaux et de
dominante et leur appel ; B ne modifie que les formats de pixels et `eq`. L'agent E fusionne A
puis B.

## Règles communes

- Chaque commit poussé tout de suite. Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request.
- Aucune nouvelle dépendance Python. Filtres disponibles dans FFmpeg 6.1 (tests Linux) ET 9.1
  (celui que le logiciel installe sous Windows). AAC toujours par `tools.AAC`.
- Tests : PAS la suite complète (une heure). Seulement les fichiers cités, `timeout 900`.
  Claude lance la suite complète avant toute fusion.
- Aucun test affaibli. Un test dont le résultat attendu change à cause d'un chantier : le
  nouveau résultat est mesuré et justifié dans le commit, jamais l'assertion supprimée.
- Chaque changement visible de l'image est MESURÉ (moyennes, écarts, temps) sur des films de
  synthèse, avant / après, et les chiffres vont dans le rapport.
- Vouvoiement et mots simples pour tout texte à l'écran. Aucune capture ni zip dans le dépôt.
- Si ça bloque plus de 30 minutes : pousser ce qui marche, noter le blocage, passer à la suite.

## Agent A : lumière et couleurs scène par scène

Aujourd'hui, niveaux (noirs, blancs) et dominante sont mesurés et corrigés UNE fois pour tout le
film : les scènes d'intérieur restent sombres, l'extérieur délavé (plainte de l'utilisateur).

- Analyse : un passage rapide (image réduite, par exemple 160 px de large, 5 images par seconde)
  qui trouve les changements de scène et mesure, pour chaque scène, les niveaux et la dominante.
  Scène de 2 s au moins (les plus courtes rejoignent la voisine).
- Correction : par scène, avec les MÊMES limites qu'aujourd'hui (`safe_levels`, `safe_gains`,
  niveaux à moitié). Jamais image par image (pas de pompage). Passage d'une scène à l'autre
  progressif sur 0,5 s, sauf à une coupure franche. `colorlevels` et `colorchannelmixer`
  acceptent des commandes (`sendcmd`) : c'est la piste ; une chaîne de centaines de filtres
  `enable=...` est à éviter.
- PIÈGE : les temps. Avec `-ss` avant l'entrée (aperçu de 10 s, image de « Lumière et
  couleurs », images du rendu), les temps du filtre repartent de 0 ; les passages enlevés
  (trim + concat), le montage et les DVD en plusieurs morceaux décalent aussi les temps. La
  correction doit suivre le temps de la SOURCE. Tester ces cas.
- Les réglages de l'utilisateur (« Lumière et couleurs ») s'ajoutent par-dessus, inchangés.
- Analyse impossible ou trop longue : correction unique d'aujourd'hui, sans erreur.
- Durée de l'analyse ajoutée : mesurée, et annoncée dans l'attente si plus de quelques secondes.
- Tests (nouveau `tests/test_scenes.py`) : film de synthèse en trois scènes (sombre et
  orangée, normale, claire et bleutée) : chaque scène corrigée vers la cible mieux qu'avec la
  correction unique ; aucune variation d'une image à l'autre à l'intérieur d'une scène ; aperçu
  pris à 20 s = la correction de la scène 2 ; avec un passage enlevé, les scènes suivantes
  gardent leur correction. Plus `test_niveaux.py`, `test_plafonds.py`, `test_dominante.py`,
  `test_pipeline.py`, `test_lumiere.py`.

## Agent B : calcul en haute précision

Aujourd'hui tout est calculé en 8 bits : après niveaux, gamma et débruitage, les dégradés (ciel,
mur) peuvent faire des marches (« banding »).

- Garder 10 bits ou plus du décodage jusqu'à l'encodage, puis passer en 8 bits UNE fois à la fin,
  avec tramage (dither). Le fichier livré reste en 8 bits (H.264 8 bits, lisible partout).
- `eq` ne travaille qu'en 8 bits : le remplacer par des filtres qui gardent la précision (par
  exemple `colorlevels` / `curves` pour contraste et gamma, `huesaturation` pour la saturation),
  avec le MÊME résultat qu'aujourd'hui à 1/255 près en moyenne sur une image test. Vérifier
  chaque filtre de la chaîne : aucun retour en 8 bits caché (lire les conversions avec
  `-v debug`).
- Tests (nouveau `tests/test_precision.py`) : rampe de gris lisse, chaîne avec gamma et niveaux :
  nettement plus de niveaux distincts et plus petit saut entre voisins qu'en 8 bits ; image test
  ordinaire : moyennes égales à 1/255 près à la chaîne actuelle ; temps de restauration mesuré
  (au plus +25 %). Plus `test_pipeline.py`, `test_tous_reglages.py`, `test_lumiere.py`,
  `test_photo.py`.

## Agent C : contrôle de la numérisation

Ce qui est perdu à la numérisation ne revient pas. L'analyse repère déjà dominante, niveaux,
ronflement, son saturé, bords, canaux. Ajouter, avec une phrase simple et ce qu'il faut faire :

- copie déjà compressée à faible débit (MPEG-2, DV, H.264… en dessous d'un seuil par pixel) :
  « Cette copie est déjà compressée : les détails perdus ne reviendront pas. Si vous avez
  encore la cassette, une nouvelle numérisation sans compression donnera un meilleur résultat. » ;
- copie déjà désentrelacée ou réduite (progressive, hauteur autre que 576 / 480, lignes doublées) ;
- noirs ou blancs écrasés dès la numérisation (une part importante des pixels collée au minimum
  ou au maximum) ;
- facultatif : lignes qui tremblent (absence de correcteur de base de temps, TBC).
- Affichage : dans « Détails du fichier » et les conseils des réglages libres ; dans l'assistant,
  UNE ligne à l'étape 1 si un défaut est trouvé. Jamais bloquant. Aucun faux positif sur une
  copie sans compression (FFV1, HuffYUV, PCM).
- Tests (nouveau `tests/test_numerisation.py`) : MPEG-2 à faible débit, copie réduite en
  progressif, noirs écrasés : détectés ; FFV1 4:2:2 normale : rien. Plus `test_conseils.py`,
  `test_probe.py`, `test_assistant.py`.

## Agent D : QTGMC dans l'exe (étude, rien de livré)

Le meilleur désentrelacement pour la VHS. Aujourd'hui impossible dans l'exe (il faut Python et
VapourSynth ; voir `installer.py`, `qtgmc.vpy`). Répondre, chiffres à l'appui :
- quoi embarquer (VapourSynth portable, `vspipe`, greffons : mvtools, nnedi3, znedi3, fmtconv,
  havsfunc / QTGMC…), taille ajoutée au paquet ;
- licences de chaque morceau et ce qu'elles imposent pour une distribution gratuite ;
- vitesse sur le Windows de la fabrication (images par seconde en 720 × 576), comparée à bwdif ;
- un essai dans un job SÉPARÉ du workflow, qui ne change pas le paquet livré.
Rapport : `partage-grok/ETUDE-QTGMC-N17.md`, avec une recommandation.

## Agent E : intégration et mesures

1. `grok/qualite` depuis la base ; fusionner A, puis B, puis C (pas D).
2. Mesures avant / après sur les films de synthèse des agents : écart à la cible par scène,
   marches dans les dégradés, temps de restauration par minute de film.
3. Lancer tous les fichiers de tests cités (pas la suite complète).
4. Rapport `partage-grok/RAPPORT-N17-POUR-CLAUDE.md` : Où (branches, hash) · Fait · Mesures ·
   Vérifié (fichiers lancés, nombres, codes de sortie) · Non testé · Bloqué.
