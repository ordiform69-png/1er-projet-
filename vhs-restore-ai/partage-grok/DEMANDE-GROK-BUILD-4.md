Bonjour Grok,

Merci pour les PR #1 et #2 : elles sont fusionnées. J'ai résolu leur conflit dans `pipeline.py`,
étendu la protection « DVD en plusieurs morceaux » à la réparation de bande (elle n'aurait lu que
le premier VOB) et imposé une cadence standard après Analog Repair (sortie NTSC irrégulière sur
la vraie VHS). Ta réparation de bande a été exécutée pour de vrai sur la VHS de 1988 et sur une
cassette entrelacée : elle fonctionne.

Nouveau depuis : les **conseils de l'analyse** pour le son (`audio_check.py`, `advice.py`, voir
`DECISIONS.md` phase 11). Ils couvrent le canal muet, l'opposition de phase, la saturation
(`adeclip`) et le ronflement, avec une case « Appliquer ces conseils » décochée en mode simple.
**94 tests** verts.

Les règles de `DEMANDE-GROK-BUILD-3.md` restent valables : une branche `grok/<sujet>` et une PR
par sujet, des tests qui vérifient l'effet **mesuré** dans le fichier exporté (pas seulement la
chaîne de filtres), « non testé » écrit noir sur blanc, rien d'activé par défaut. Pars de la
dernière version de `ccr-5856e8d6-8xt8uh` et **rebase avant chaque PR** pour éviter les conflits.

## Tâches, dans cet ordre (FFmpeg seul, aucune nouvelle dépendance)

1. **Vent et grondements** — `grok/son-vent` : case avancée « Réduire le vent et les grondements »
   (`highpass` vers 80 Hz, pente douce). Conseil automatique si l'énergie sous 80 Hz est forte et
   irrégulière (vent), à mesurer dans `audio_check.py`. Test : bruit grave ajouté, réduit après ;
   une voix de synthèse (300 Hz à 3 kHz) inchangée.
2. **Son étouffé** — `grok/son-clarte` : case « Rendre les voix plus claires », légère présence
   (`equalizer` vers 3 kHz, +3 dB au plus). Jamais par défaut. Test : énergie 2-4 kHz en hausse,
   pas d'écrêtage créé.
3. **Noirs gris et blancs ternes** — `grok/niveaux` : mesurer les niveaux réels du film
   (percentiles `signalstats` YLOW/YHIGH sur l'échantillon de l'analyse), puis proposer une
   correction **fixe** (`colorlevels` ou `eq`) en conseil, jamais image par image. Test :
   capture aux niveaux écrasés (16-200 étirés en 40-180) corrigée ; film déjà correct sans
   conseil. Ajoute le conseil dans `advice.py` (clé `levels`).
4. **Couleur décalée (VHS)** — `grok/chroma-decalage` : réglage avancé en pixels (`chromashift`,
   −8 à +8, 0 par défaut). Test : décalage de synthèse annulé, mesuré par l'alignement des bords
   luma/chroma.
5. **Dominante de couleur** — `grok/dominante` : case avancée « Corriger la dominante de couleur »
   (`grayworld`, ou `colorbalance` calculé une fois pour tout le film). Conseil seulement si la
   dominante mesurée est forte. Test : dominante verte ajoutée puis retirée ; une image en noir
   et blanc reste neutre ; une couleur pâle n'est pas sursaturée.
6. **Bords abîmés** — `grok/bords` : masquer les bords gauche et droite (et le cadre d'une
   pellicule) en noir, **même taille d'image, même 4:3** (comme `mask_bottom`). Test : taille et
   proportions inchangées.
7. **Analyse plus rapide** — si possible, regrouper les lectures du son de `audio_check.py` en
   une seule commande FFmpeg (mesurer avant et après sur un fichier de 10 minutes).

Termine chaque PR par **Fait / Testé (comment, avec les mesures) / Non testé / Risques**.

Ne pas faire : colorisation, effacement de la date incrustée, interpolation d'images,
« amélioration » des visages par IA, correction du pleurage.

Merci !
