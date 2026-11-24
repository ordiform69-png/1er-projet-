# Décisions du chef

- D-001 · 2026-11-24 · La vague 1 commence par une analyse. Le code n'est intégré qu'après l'arbitrage du chef.
- D-002 · 2026-11-24 · Les filtres de restauration et la case « Corriger aussi ces défauts » cochée d'office ne bougent pas sans mesures et accord noté ici.
- D-003 · 2026-11-24 · Image et son : aucun seuil modifié. Les mesures (analyses/image-son.md) montrent qu'un seuil plus sensible corrigerait plus fort ou ajouterait de fausses alertes.
- D-004 · 2026-11-24 · Vague 1 : molette ignorée sans focus ; cadre « Enlever une scène » seulement après un film ; arrêt dit que le film n'est pas modifié ; LISEZMOI et Bienvenue parlent de « Couper ici » ; l'erreur de coupe nomme les cases de l'écran.
- D-005 · 2026-11-24 · LosslessCut et Shotcut restent nommés. Les cacher contredit la phase 22 : ce sont des programmes séparés, et Windows affiche leur nom.
- D-006 · 2026-11-24 · Pas de déplacement de l'aperçu ni de « Restaurer tout un dossier » dans cette vague. La phase 24 a déjà placé la barre sous les étapes 1-2-3.
- D-007 · 2026-11-24 · L'échec `test_photo_au_nom_avec_pourcent` (aperçu comparaison vide, scale2ref) est antérieur à cette vague. Pas corrigé ici : ce n'est pas le montage, et le FFmpeg de cet environnement écrit un fichier vide même sans « % ».
- D-008 · 2026-11-24 · On ne retire pas le décalage du son sur les morceaux. Chaque morceau est un film neuf qui part à zéro : un décalage constant doit s'appliquer dans chaque morceau, sinon les suivants dérivent. L'assemblage reste `-c copy`. L'écart mesuré de 21 ms vient de l'amorçage AAC, déjà dans la tolérance de 0,15 s.
- D-009 · 2026-11-24 · La veille est déjà empêchée : `gui._keep_awake` appelle `SetThreadExecutionState` (ctypes, sans dépendance) au début et à la fin d'un travail. On n'ajoute pas `ES_DISPLAY_REQUIRED` : l'écran peut s'éteindre, l'ordinateur ne s'endort pas.
- D-010 · 2026-11-24 · Vague 2 : une coupe collée au début ou à la fin part vraiment ; le curseur va jusqu'au bout du film ; Entrée sur la barre coupe sans lancer l'étape ; la prise des bords fait 44 px ; la 9e coupe et « Annuler » referment le geste commencé. Windows : place pour les morceaux, FAT32 de la copie sans vides, chemin du film d'origine, lancement UNC, installation laissée en place si le programme est ouvert. Pas de manifeste `longPathAware` (construction Windows non relancée ici).
- D-011 · 2026-11-24 · Timeline : la règle « pas de vignettes » est levée. Le reste de l'interdit tient (pas de banc de montage, pas de levée du refus IA / poussières / bande / cadence, assemblage `-c copy`, pas de code copié).
- D-012 · 2026-11-24 · Une image tous les 90 px, même liste pour les deux barres. Hauteur d'image 96 px (simple) et 56 px (options). `bwdif` seulement si le balayage est tff ou bff. Aucun seuil de restauration modifié.
- D-013 · 2026-11-24 · L'extraction ne passe pas par `self.worker`. Dossier temporaire local, supprimé au changement de film. Les signaux d'une génération périmée sont ignorés. La dernière demande d'image du moment gagne.
- D-014 · 2026-11-24 · Les bots de la demande n°8 n'ont pas démarré (flux fermé). Le chef a fait le travail des six rôles. Pas d'exe Windows dans cet environnement : pas de ligne « RÉSULTAT : OK ».


