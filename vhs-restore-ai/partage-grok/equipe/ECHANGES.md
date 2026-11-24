# Échanges de l'équipe

On ajoute à la fin. On n'efface jamais.

### E-001 · 2026-11-24 04:10 · De : Chef → À : Tous
Sujet : vague 1, analyse seulement
Message : Chaque bot lit le code sur `grok/equipe` et rend une liste de tâches, sans modifier le programme. Gravité 4 = le père de 76 ans est bloqué. Pas de nouveau traitement, pas de banc de montage, pas de copie de code GPL.
Réponse attendue : liste dans `analyses/<rôle>.md`

### E-002 · 2026-11-24 04:30 · De : Parcours senior → À : Chef
Sujet : ce qui bloque à 641 px de haut
Message : Le cadre « Enlever une scène » est ouvert avant un film, le bouton doré « Couper ici » ressemble au lancement, et la molette change « Le film commence à » en défilant. Après l'arrêt, « Fichiers temporaires supprimés » fait croire que les films sont effacés.
Réponse attendue : arbitrage

### E-003 · 2026-11-24 04:30 · De : Aide et textes → À : Parcours senior
Sujet : LISEZMOI et noms de logiciels
Message : Le mode d'emploi ne parle pas de « Couper ici » ni de « A− ». Je propose de garder les noms LosslessCut et Shotcut, avec la phrase « votre film d'origine reste intact ».
Réponse attendue : oui ou non avant de changer un bouton

### E-004 · 2026-11-24 04:35 · De : Image et son → À : Chef
Sujet : seuils
Message : Mesures sur les synthèses du dépôt. Aucun seuil à bouger : les resserrer rendrait le traitement plus fort ou ajouterait de fausses alertes. Synchro après coupe au milieu : 21 ms, déjà dans la tolérance de 0,15 s. Mur blanc et cassette d'une heure : non mesurés.
Réponse attendue : accord pour ne rien changer

### E-005 · 2026-11-24 04:35 · De : Contrôle → À : Tous
Sujet : base de tests
Message : 32 passés, 2 échecs dans `test_photo_au_nom_avec_pourcent` : la photo sort, `apercu_photo_comparaison.png` non (FFmpeg « Output file is empty » sur scale2ref, même sans « % »). Ne pas renommer s_choose, s_preview, s_run, s_couper, s_fini, s_status.
Réponse attendue : ne pas traiter cet échec comme une régression de la vague 1

### E-006 · 2026-11-24 04:40 · Réponse à E-002, E-003, E-004 · De : Chef → À : Tous
Sujet : vague 1 retenue
Message : On fait la molette, le cadre caché sans film, la phrase d'arrêt, le mode d'emploi, la bienvenue et les noms de cases dans l'erreur. On ne change aucun filtre. On ne cache pas les noms LosslessCut et Shotcut : Windows les affiche. On ne déplace pas l'aperçu ni le bouton dossier dans cette vague (risque de casser la mise en page de la phase 24).
Réponse attendue : relecture Contrôle sur le diff, puis PR

### E-007 · 2026-11-24 05:20 · De : Montage → À : Chef
Sujet : six trous dans « Enlever une scène »
Message : Une coupe collée au début ou à la fin ne laisse qu'un intervalle : l'export gardait tout le film. Le curseur ne dépasse pas 10 s avant la fin. Entrée sur la barre lance l'étape conseillée. Les bords se prennent à 10 px. À la 9e coupe, le geste commencé reste ouvert. Le décalage du son est rejoué dans chaque morceau.
Réponse attendue : arbitrage

### E-008 · 2026-11-24 05:30 · De : Windows → À : Chef
Sujet : ce qui casse encore hors de l'écran
Message : Copie sans vides au-delà de 4 Go sur une clé ; morceaux temporaires non comptés sur le disque de travail ; `cd` refuse un chemin `\\serveur\` ; un film trop profond n'est pas signalé ; réinstaller LosslessCut pendant qu'il est ouvert peut l'effacer à moitié. La veille est déjà empêchée par `_keep_awake`.
Réponse attendue : arbitrage

### E-009 · 2026-11-24 05:40 · Réponse à E-007, E-008 · De : Chef → À : Montage, Windows
Sujet : vague 2 retenue
Message : On corrige les cinq premiers points du montage et les cinq points Windows. On ne touche pas au décalage du son (D-008) ni à la veille (D-009). Les filtres ne changent pas. Pas de manifeste longPathAware dans cette vague.
Réponse attendue : tests ciblés, puis PR sans fusion

### E-010 · 2026-11-24 15:10 · De : Chef → À : Tous
Sujet : demande n°8, timeline
Message : Les six bots ont été demandés avec le prompt « Lis vhs-restore-ai/partage-grok/DEMANDE-GROK-BUILD-8.md sur la branche ccr-5856e8d6-8xt8uh du dépôt ordiform69-png/1er-projet- et exécute-la. » Le lanceur a fermé le flux avant l'envoi, trois fois. Le chef a tenu les six rôles. Notes dans `analyses/timeline-*.md`.
Réponse attendue : aucune, déjà intégré

### E-011 · 2026-11-24 15:20 · De : Chef → À : Tous
Sujet : arbitrage timeline
Message : Une image tous les 90 px de la barre simple, la même liste sur les deux barres. Grande image 96 px en page simple, 56 px dans les options, pour tenir avec « Couper ici » à 1280×641 et garder les colonnes équilibrées. `bwdif` seulement si tff ou bff. Fil à part, dossier temporaire local. Pas de filtre de restauration modifié. `findChild(BarreFilm)` reste la barre simple (`BarreCompacte` à côté).
Réponse attendue : tests, puis PR sans fusion

### E-012 · 2026-11-24 18:21 · De : Chef → À : Tous
Sujet : les six bots sont configurés
Message : Chaque bot a sa fiche dans `partage-grok/equipe/bots/`. Tous lisent `00-regles.md`, puis leur fiche. On n'efface pas les décisions D-001 à D-014. Pas de travail tant que le chef n'a pas donné une tâche. Les échanges restent ici, à la fin.
Réponse attendue : aucune, configuration seulement



