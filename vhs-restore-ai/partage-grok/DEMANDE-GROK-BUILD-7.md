# Demande n°7 à Grok Build : une équipe de bots pilotée par Grok Build

Bonjour Grok,

Merci pour le montage « Enlever une scène » (branche `grok/montage`) : il est fusionné dans la
version n°65 (commit `b66f960` et suivants, branche `ccr-5856e8d6-8xt8uh`), avec les 4 points du
rapport faits et 240 tests verts.

Cette fois, l'utilisateur demande que **Grok Build pilote une équipe de bots**. Chaque bot a son
rôle et son prompt (ci-dessous). Les bots **discutent entre eux** pour améliorer le projet.
Toi, Grok Build, tu es **chef d'orchestre** : tu lances les bots avec ces prompts, tu répartis le
travail, tu tranches les désaccords, tu intègres, et tu rends compte.

Lis d'abord, sur la branche `ccr-5856e8d6-8xt8uh` : `README.md`, `DECISIONS.md` (surtout les
phases 21 à 26), `LISEZMOI.txt`, puis le code.

---

## 1. Qui utilise le logiciel (pour tous les bots)

- Le père de l'utilisateur, **né en 1950**, sous **Windows**, écran 1920 × 1080 à 150 %.
  Il se sert peu d'un ordinateur. Il ne lit pas les infobulles. Un message technique l'arrête.
  Il a peur de « casser » un film.
- Il restaure des films de famille numérisés (VHS, Video8 / Hi8, Betamax, Super 8 scanné) et
  des photos. Il veut : choisir, voir si c'est mieux, lancer, retrouver le résultat.

## 2. Règles non négociables (pour tous les bots)

- **Fidélité** : l'original n'est jamais modifié ; 4:3 gardé ; son gardé ; aucun traitement
  agressif ; résultats décrits honnêtement (jamais « parfait » ni « HD réelle »).
- **Ne change pas les filtres de restauration ni les réglages par défaut** (débruitage, netteté,
  profils, désentrelacement, IA, poussières) sans mesures avant / après et l'accord du chef,
  noté dans `DECISIONS-EQUIPE.md`. La case « Corriger aussi ces défauts » reste **cochée d'office**
  quand des défauts sont repérés (décision de l'utilisateur, phase 21).
- **Montage** : pas de banc de montage (pas de titres, de musique, de plusieurs films collés,
  de vignettes sur la barre). Ne lève pas le refus de l'IA, des poussières, de la réparation de
  bande et de la cadence de tournage pour une coupe au milieu. L'assemblage reste `-c copy`.
  Les coupes d'un film ne s'appliquent jamais à un dossier. Pas de `deleteLater` sur les lignes
  de passages.
- **Licences** : ne copie aucun code d'OpenShot, LosslessCut, Shotcut ou Clipchamp. LosslessCut
  et Shotcut restent des programmes séparés, lancés tels quels.
- Français, **vouvoiement**, phrases courtes ; les options sont nommées **comme à l'écran**.
- **Aucune nouvelle dépendance** Python sans accord du chef (et de l'utilisateur).
- Garde les noms utilisés par les tests (`s_choose`, `s_preview`, `s_run`, `s_info`, `s_status`,
  `s_cancel`, `s_fini`, `s_couper`, `compare`, `s_compare`, `segments`, `run_btn`, `pages`,
  `voyants`, `profile_buttons`, `edge_spin`, `a_advice`…) ou renomme-les partout.
- **Tous les tests restent verts** (240 aujourd'hui), y compris `tests/test_tous_reglages.py`
  (chaque réglage restauré pour de vrai) et `tests/test_pieges_windows.py`. Chaque comportement
  nouveau a son test. Aucun défilement horizontal à 1366 × 740, 1280 × 720 et 1093 × 600, texte
  100 / 125 / 150 %. Contrastes ≥ 4,5:1 dans les deux palettes.
- Protections Windows à garder et à utiliser pour tout nouveau fichier écrit :
  `tools.finaliser` / `effacer` / `verifier_chemin` / `ff_input`, `pipeline.check_fat32`,
  `CREATE_NO_WINDOW` (`_NO_WINDOW`) pour tout sous-processus.
- **Jamais dans le dépôt** : exe, zip, captures d'écran, médias de test. Les captures vont dans
  la description de la PR ou restent dans ton espace de travail.
- Pas d'identifiant de modèle d'IA dans les commits, le code ou les PR.

## 3. Comment les bots se parlent

Le canal commun est un dossier du dépôt, sur la branche d'intégration `grok/equipe` :
`vhs-restore-ai/partage-grok/equipe/`.

- `TABLEAU.md` : une ligne par tâche — n°, bot responsable, fichiers touchés, état
  (à faire / en cours / à relire / fini), branche ou PR.
- `ECHANGES.md` : le fil de discussion, **on ajoute à la fin, on n'efface jamais** :

  ```
  ### E-012 · 2026-11-24 14:05 · De : Windows → À : Contrôle (ou : Tous)
  Sujet : finaliser() pour les copies WAV du montage
  Message : …
  Réponse attendue : oui, avant l'intégration n°2
  ```

  La réponse cite le numéro (« Réponse à E-012 »).
- `DECISIONS-EQUIPE.md` : chaque arbitrage du chef, en une ou deux lignes, avec la raison.

Si Grok Build sait faire dialoguer ses bots directement, sers-t'en, **mais recopie dans
`ECHANGES.md` toute question ou décision qui concerne un autre bot** : l'utilisateur et Claude
doivent pouvoir suivre la discussion.

Règles de l'équipe :
1. Chaque bot travaille sur sa branche `grok/equipe-<rôle>`, partie de `grok/equipe`, et
   `git pull --rebase` avant d'écrire dans `partage-grok/equipe/`.
2. Avant de modifier un fichier qui appartient à un autre bot (carte ci-dessous), on le
   demande dans `ECHANGES.md` et on attend la réponse ou l'arbitrage du chef.
3. Le bot **Contrôle** relit chaque branche avant intégration et écrit ses remarques dans
   `ECHANGES.md` ; le bot concerné répond et corrige.
4. Un désaccord : chacun écrit son argument en trois lignes au plus ; le chef tranche et note
   la décision.
5. Petits commits, un sujet par commit ; tests verts avant de demander l'intégration.

### Carte des fichiers

| Bot | Fichiers dont il est responsable |
|---|---|
| Parcours senior | `gui.py` : page simple (`_build_simple`, textes, tailles), `theme.py` |
| Windows | `tools.py`, `installer.py`, `__main__.py`, lecture / écriture de fichiers dans `pipeline.py`, `photo.py`, `colorize.py` |
| Image et son | `probe.py`, `advice.py`, `profiles.py` (mesures d'abord, voir règles) |
| Montage | `gui.py` : cadre « Enlever une scène » et `BarreFilm` ; `pipeline.passages_gardes`, `_export_morceaux`, `_concat_sans_recompression` ; `vides.py` |
| Aide et textes | `LISEZMOI.txt`, `README.md`, fenêtre « Bienvenue », `ergonomie.py` (phrases) |
| Contrôle | `tests/`, `scripts/audit_interface.py`, `scripts/captures_ergonomie.py` |

## 4. Les prompts des bots

Donne à chaque bot : la section 1, la section 2, la section 3, puis **son** prompt ci-dessous.

### Bot « Parcours senior »

Tu es l'avocat de l'utilisateur de 76 ans. Fais le parcours, écran par écran, à 1280 × 641
(1920 × 1080 à 150 %, fenêtre agrandie) et à 1366 × 768, texte 100 et 150 %, thèmes sombre et
clair, pour : restaurer un film ; une photo ; un dossier ; enlever une scène ; retirer les
passages vides ; arrêter puis reprendre ; comprendre une erreur. À chaque écran : ce qu'il voit,
ce qu'il comprend, où il hésite. Corrige d'abord ce qui le bloque (gravité 4 et 3). Vérifie
qu'aucun texte n'est coupé, qu'aucune information indispensable n'est seulement en infobulle, et
que l'étape suivante est toujours évidente. Captures réelles (`widget.grab()`), hors dépôt.

### Bot « Windows »

Tu chasses ce qui casse seulement chez un vrai utilisateur Windows : chemins (`C:\`, accents,
apostrophes, `%`, OneDrive, clé USB, DVD, disque réseau), fichiers verrouillés, encodages,
fenêtres console, droits, antivirus, mises en veille pendant un long travail. Pour chaque cas :
reproduis-le (sous Linux en l'imitant, ou en raisonnant précisément), corrige, ajoute un test.
Vérifie en particulier le montage par morceaux et la copie « sans passages vides ». Propose au
chef un moyen d'éviter la mise en veille de Windows pendant une restauration (sans dépendance).

### Bot « Image et son »

Tu mesures, tu ne devines pas. Sur des films de synthèse (FFmpeg `lavfi`) et les mesures déjà
décrites dans `DECISIONS.md` : fiabilité des détections (entrelacement, bords abîmés, dominante,
niveaux, son saturé, ronflement, vent, passages vides), fausses alertes, synchronisation son /
image après coupe au milieu, vitesse de l'analyse et de l'aperçu. Rends un rapport chiffré.
Toute modification de seuil ou de réglage : avant / après mesurés, accord du chef, ligne dans
`DECISIONS-EQUIPE.md`. Tu ne rends jamais un traitement plus fort.

### Bot « Montage »

Tu finis « Enlever une scène » sans en faire un banc de montage. Vérifie : clavier (flèches,
Entrée), accessibilité (noms pour le lecteur d'écran), cibles ≥ 44 px, comportement avec 8
coupes, coupes au tout début ou à la toute fin, film sans son, film très court, annulation
pendant l'assemblage, synchronisation son / image du résultat (mesure-la). Les avertissements
avant « Restaurer » restent justes quand une option change. Discute avec « Parcours senior »
de la place du cadre sur la page simple et avec « Windows » des fichiers intermédiaires.

### Bot « Aide et textes »

Tu relis chaque phrase visible : mode simple, options avancées, messages d'erreur
(`ergonomie.expliquer`), fenêtre « Bienvenue », `LISEZMOI.txt`. Mots de tous les jours,
vouvoiement, phrases courtes, options nommées comme à l'écran, guillemets « » avec espaces
insécables. Mets à jour `LISEZMOI.txt` pour : enlever une scène, retirer les passages vides,
faire un montage (LosslessCut / Shotcut), taille du texte, affichage clair. Demande à
« Parcours senior » avant de changer un libellé de bouton (les tests en dépendent parfois).

### Bot « Contrôle »

Tu es le relecteur et le testeur de l'équipe. Pour chaque branche à intégrer : lis le diff,
lance toute la suite de tests et `scripts/audit_interface.py`, cherche les régressions
(boutons actifs sans effet, textes coupés, défilement horizontal, contrastes, tests affaiblis
ou supprimés, fichiers inachevés laissés, sous-processus sans `_NO_WINDOW`). Écris tes
remarques dans `ECHANGES.md` (fichier:ligne, scénario, correction proposée). Tu refuses
l'intégration tant qu'un test est rouge ou qu'une règle de la section 2 est enfreinte.

## 5. Ton rôle de chef (Grok Build)

1. Crée `grok/equipe` à partir de la dernière `ccr-5856e8d6-8xt8uh`, avec
   `partage-grok/equipe/TABLEAU.md`, `ECHANGES.md` et `DECISIONS-EQUIPE.md`.
2. Lance les six bots avec leurs prompts. Demande d'abord à chacun **son analyse et sa liste
   de tâches** (sans coder) ; fusionne ces listes dans `TABLEAU.md` ; écarte ce qui enfreint la
   section 2 ; ordonne par gravité pour l'utilisateur.
3. Fais travailler les bots par vagues courtes. À la fin de chaque vague : relecture par
   « Contrôle », corrections, intégration dans `grok/equipe`, toute la suite de tests verte.
4. Tranche les désaccords et note-les dans `DECISIONS-EQUIPE.md`.
5. Livraison : **une PR** de `grok/equipe` vers `ccr-5856e8d6-8xt8uh`, que tu ne fusionnes pas
   toi-même (Claude la relit, l'utilisateur décide). Dans la PR et dans
   `partage-grok/RAPPORT-EQUIPE-POUR-CLAUDE.md` :
   - ce que chaque bot a fait, et les discussions importantes entre bots ;
   - **Fait / Testé (comment) / Non testé / Risques** ;
   - la construction Windows verte (essai automatique de l'exe « RÉSULTAT : OK ») ;
   - ce qui a été écarté, et pourquoi.

Merci !
