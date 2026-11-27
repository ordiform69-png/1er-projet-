# Rapport n°20 — agent E (fin du travail, arrêt, erreurs, copies à partager)

Branche `grok/bugs-e-fin`, partie de `1abf947` (`ccr-5856e8d6-8xt8uh`).
Rien n'a été modifié dans `vhs_restore/`. Aucune vidéo n'est dans le dépôt :
les films des tests sont créés dans le dossier temporaire de pytest.

Les dix tests de `tests/test_bugs_n20_e.py` sont en `@pytest.mark.xfail(strict=True)`.
Ils décrivent le comportement attendu et échouent sur le code actuel.

Preuve lancée ici (Linux, Python 3.12.3, FFmpeg 6.1.1, PySide6 6.12.0, hors écran) :

```
cd vhs-restore-ai && QT_QPA_PLATFORM=offscreen timeout 900 python3 -m pytest tests/test_bugs_n20_e.py -q
```

Résultat : **10 xfailed**, code de sortie **0**, 22,69 s.

## Constats

### 1. La copie d'une capture SD sort en 5:4 — bloquant — PROUVÉ

**Où :** `vhs_restore/partage.py:151` (le format lu à la ligne 127).

**Scénario.** Une capture 720 × 576 dont le fichier dit « pixels carrés » (SAR 1:1).
L'analyse du logiciel suppose le 4:3, comme pour les caméscopes (`probe.py:421`).
Le père envoie la copie légère ou la copie pour la télévision.
La copie légère fait 600 × 480 et celle pour la télévision 720 × 576 : les deux sont en 5:4.
Les visages sont trop étroits.

**Preuve.** Film réaliste de la demande (plan qui se déplace, bruit, lumière variable,
entrelacé), durée 4 s, `setsar=1`. `analyze` donne bien `dar = 4/3`.
`faire_copie` mesure :

| Copie | Taille obtenue | Taille 4:3 | Son | Durée |
|---|---|---|---|---|
| légère | 600 × 480 | 640 × 480 | 2 canaux | 4,000 s |
| télévision | 720 × 576 | 768 × 576 | 2 canaux | 4,000 s |

Le son et la durée complète sont bons. Le format ne l'est pas.
Test : `test_copie_sd_sans_sar_reste_en_4_3`.

**Correction.** Pour une image SD sans vrai format 4:3 dans le fichier, utiliser la même règle que l'analyse (4:3), donc 640 × 480 et 768 × 576.

### 2. Un décalage fixe est annoncé comme une dérive d'une seconde et demie par minute — gênant — PROUVÉ

**Où :** `vhs_restore/probe.py:368` (calcul à la ligne 366).

**Scénario.** Un film de 20 s dont le son dure 19,5 s (un décalage fixe, pas une accélération).
L'écran dit : « La piste son dure -0.50 s de plus que l'image (environ -1500 ms par minute).
Si le décalage s'aggrave, réglez « Dérive du son ». L'application ne détecte pas les lèvres. »
S'il suit ce conseil sur un film de 3 h, le son se décale d'environ 4,5 minutes.

**Preuve.** Fichier mesuré (vidéo 20,000 s, son 19,500 s). Le texte ci-dessus est exactement
celui de `info.warnings`. « -1500 ms par minute » et « lèvres » y sont.
Test : `test_avertissement_derive_ne_transforme_pas_un_decalage_fixe`.

**Correction.** Dire « le son est une demi-seconde plus court que l'image », sans « ms par minute » ni « lèvres ».

### 3. « Arrêter » pendant la séparation laisse le premier film — gênant — PROUVÉ

**Où :** `vhs_restore/partage.py:288`.

**Scénario.** Une cassette est séparée en « Noël 1988 » puis « Vacances ».
Le père clique sur « Arrêter » au début du second film.
Le premier fichier est déjà dans le dossier, mais l'écran dit
« Arrêté. Votre film n'a pas été modifié. » (`gui.py:4691`).
Il recommence : le logiciel ajoute « (2) » à côté du premier.

**Preuve.** Séparation `(0–2 s, 2–14 s)`, annulation dès le message « Film 2 ».
`Cancelled` est bien levée, et `Noël 1988.mp4` reste dans le dossier de sortie.
Test : `test_arreter_la_separation_ne_laisse_pas_de_film`.

**Correction.** En cas d'arrêt, effacer les films déjà écrits par cette séparation, ou en donner les noms au lieu de dire que rien n'a changé.

### 4. Un travail d'1 h 19 est annoncé « environ 1 heure » — gênant — PROUVÉ

**Où :** `vhs_restore/estimation.py:52`.

**Scénario.** Film de 3 h, aperçu de 10 s chronométré à 2,5 s, profil Équilibré.
Le calcul donne 4 725 s (1 h 19). L'écran dit « environ 1 heure ».
De 1 h 00 à 1 h 29 c'est toujours « environ 1 heure » ; à 1 h 30 cela saute à « environ 2 heures ».
Le père peut éteindre l'ordinateur avant la fin. Le commentaire du fichier demande pourtant d'annoncer plutôt trop long.

**Preuve.** `estimation.calcul` renvoie 4 725 s.
`estimation.annonce` renvoie : « Durée estimée : environ 1 heure sur cet ordinateur. Il faut environ 10 Go ; il en reste 263 Go. »
`phrase_temps(5399)` vaut « environ 1 heure ».
Test : `test_duree_annoncee_film_de_trois_heures_nest_pas_trop_courte`.

**Correction.** Entre 1 h et 2 h, annoncer par quarts d'heure arrondis vers le haut (1 h 19 → « environ 1 h 30 »).

### 5. Si la durée est inconnue, la barre est à 100 % dès la première image — gênant — PROUVÉ

**Où :** `vhs_restore/pipeline.py:751`.

**Scénario.** Certains VOB ou captures n'ont pas de durée (l'analyse l'écrit déjà :
« Durée inconnue : la progression sera approximative »).
Le total utilisé vaut alors 0,001 s. La première image dépasse ce total, et la barre
reste pleine pendant tout le film. Sur 1 à 3 h, le père croit que c'est fini.

**Preuve.** Export d'un film de 3 s avec `info.duration = 0` et le préréglage `ultrafast`.
Les trois annonces sont `(1.0, « Restauration… »)`, `(1.0, « Restauration… »)`, `(1.0, « Terminé »)`.
Aucune valeur intermédiaire.
Test : `test_progression_duree_inconnue_ne_saute_pas_a_100`.

**Correction.** Durée inconnue : barre indéterminée, pas un total de 0,001 s qui sature à 100 %.

### 6. « Arrêter » laisse tourner la copie de lecture — gênant — PROUVÉ

**Où :** `vhs_restore/gui.py:4603`.

**Scénario.** Le père ouvre un film entrelacé. Une copie désentrelacée démarre toute seule
pour le lecteur (`copie_lecture`), sans message. Il lance une restauration, puis « Arrêter ».
Le travail affiché s'arrête. FFmpeg continue la copie du film entier (1 à 3 h) et remplit le disque.

**Preuve.** Film réaliste entrelacé de 8 s, analyse `scan = tff`.
La copie a un processus vivant. Après `cancel(confirmer=False)`, le fil de travail est arrêté
(`_busy()` faux) mais `proc.poll()` vaut encore `None` et `annuler` de la copie n'est pas levé.
Test : `test_arreter_coupe_aussi_la_copie_de_lecture`.

**Correction.** Dans `cancel`, appeler aussi `_copie.stop()` pour tuer le FFmpeg de la copie de lecture.

### 7. Un verrou oublié fait sortir le film sous le nom « (2) » — gênant — PROUVÉ

**Où :** `vhs_restore/tools.py:204`.

**Scénario.** L'ordinateur est coupé pendant une restauration. Le fichier `.reserve` reste,
le film lui n'existe pas. Au prochain essai, le logiciel croit le nom pris et écrit
`vacances_restaure_equilibre (2).mp4`. Le père cherche le nom annoncé et ne le trouve pas.

**Preuve.** On pose seulement `.vacances_restaure_equilibre.mp4.reserve`.
`reserver_sorties` rend `vacances_restaure_equilibre (2).mp4`.
Le fichier `.mp4` prévu n'existait pas.
Test : `test_verrou_perime_ne_renomme_pas_la_sortie`.

**Correction.** Un verrou sans film à côté ne doit pas changer le nom : l'effacer et garder le nom prévu.

### 8. Remettre le même nom ajoute « (2) » — gênant — PROUVÉ

**Où :** `vhs_restore/partage.py:310`.

**Scénario.** Le fichier s'appelle déjà `Noël 1988.mp4`. Le père ouvre « Nommer » pour y écrire
la date du 25 décembre 1988, et il retape le même nom. Le fichier devient
`Noël 1988 (2).mp4`. L'ancien nom disparaît.

**Preuve.** `nommer(..., "Noël 1988", "25/12/1988")` sur un fichier qui porte déjà ce nom
renvoie `Noël 1988 (2).mp4`.
Test : `test_nommer_le_meme_nom_garde_le_fichier`.

**Correction.** Réécrire le film sous le même nom par un fichier temporaire, et n'ajouter « (2) » que si un autre fichier porte déjà ce nom.

### 9. La copie du son reste affichée à 99 % — gênant — PROUVÉ

**Où :** `vhs_restore/pipeline.py:1522`.

**Scénario.** À la fin d'un film de plusieurs heures, la copie WAV du son restauré
est lancée sans suivi. La barre passe à 99 % (« Copie du son restauré… ») et n'en bouge plus
pendant toute la copie. Le père croit que le logiciel est bloqué juste avant la fin.

**Preuve.** `_write_audio_copy` n'envoie qu'une fraction, `0.99`.
La commande FFmpeg n'a pas `-progress`, et `on_line` n'est pas branché.
Test : `test_copie_du_son_fait_avancer_la_barre`.

**Correction.** Brancher `-progress` et `on_line` sur la copie WAV, et terminer à 100 %.

### 10. Au démarrage, les noms des filtres sont montrés tels quels — gênant — PROUVÉ

**Où :** `vhs_restore/gui.py:4876`.

**Scénario.** FFmpeg est là mais il lui manque un filtre. La première fenêtre dit
« FFmpeg trop ancien » et « Filtres manquants : bwdif, hqdn3d ».
La phrase prévue pour lui (« Le logiciel est incomplet… Réinstallez-le ») existe dans
`ergonomie.expliquer`, mais cet écran ne l'utilise pas.

**Preuve.** `main()` avec `missing_filters = ["bwdif", "hqdn3d"]` ouvre une boîte dont le texte est
« FFmpeg trop ancien Filtres manquants : bwdif, hqdn3d ».
Test : `test_message_ffmpeg_incomplet_est_lisible`.

**Correction.** Afficher « Le logiciel est incomplet. Réinstallez-le à partir du fichier téléchargé, puis recommencez. » et garder les noms de filtres derrière « Détails pour l'aide ».

## Ce qui a été mesuré et n'est pas un bug

Film réaliste de la demande avec `setsar=16/15` (vrai 4:3), 6 s, son :

- copie légère : 640 × 480, SAR 1:1, 4:3, 25 i/s, durée 6,000 s, son stéréo AAC ;
- copie télévision : 768 × 576, mêmes constats, durée 6,000 s, son stéréo ;
- écart de couleur moyen contre le film source, après le même passage à l'échelle : environ 2,4 niveaux sur 255.

La durée complète, le son et les couleurs tiennent quand le fichier annonce déjà le 4:3.
Le défaut du constat 1 apparaît quand le fichier ne l'annonce pas, alors que l'analyse, elle, suppose le 4:3.
