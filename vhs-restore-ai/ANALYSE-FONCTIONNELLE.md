# VHS Restore AI — analyse fonctionnelle (15 novembre 2026)

But : savoir ce qui manque pour que **l'utilisateur final (né en 1950) restaure seul ses films**,
sur son PC Windows, sans aide. Chaque manque est marqué *vérifié dans le code* ou *supposé*.

## 1. Ce qui existe

| Domaine | Fonctions | Validation |
|---|---|---|
| Utilisation | Mode simple (3 boutons), dossier entier, options avancées, aperçu avant/après aligné, annulation | Tests + interface hors écran |
| Analyse | Entrelacement mesuré, 4:3 et pixels non carrés, PAL/SECAM/NTSC, origine suggérée (vidéo/pellicule/transfert), noir et blanc ou couleurs pâles, son absent ou silencieux | Synthèse + 2 archives réelles |
| Image | Désentrelacement bwdif ou QTGMC, débruitage standard ou HQ, parasites, couleurs/contraste modérés, netteté, Full HD/4K, stabilisation, scintillement, poussières et rayures, cadence de tournage, IA Real-ESRGAN | Synthèse ; poussières et grain sur une archive réelle |
| Sécurité | Source jamais modifiée, sortie atomique, jamais d'écrasement, sans shell, nettoyage des fichiers temporaires | Tests |
| Diffusion | Paquet Windows autonome (FFmpeg inclus), autotest, LISEZMOI | CI Windows |

## 2. Ce qui manque, par priorité

### P0 — bloquant ou risqué pour un usage autonome

| # | Manque | Constat | Proposition |
|---|---|---|---|
| 1 | **Aucun essai humain sous Windows** | La CI teste sans écran ; personne n'a encore cliqué dans l'interface | Essai par l'utilisateur sur son PC avant de l'installer chez son père |
| 2 | ~~Sources sur DVD ou clé protégée~~ **Fait** | Test d'écriture réel ; sinon sortie dans `Vidéos\Films restaurés`, avec une note dans l'interface et un message ; même chose pour un dossier entier | Testé (lecture seule simulée) |
| 3 | ~~Films sur DVD découpés en VOB~~ **Fait** | Un titre `VTS_xx_1` + `VTS_xx_2`… devient un seul film (concat FFmpeg). Menus ignorés. Dossier `VIDEO_TS` ou disque : un film par titre. Sortie de secours si le DVD est en lecture seule | Testé sur un DVD de synthèse (durée, jonction, son, aperçu). Pas sur un vrai DVD du commerce |
| 4 | ~~Relancer un dossier refait tout~~ **Fait** | Un film déjà restauré avec les mêmes réglages est sauté et compté (« déjà restauré ») | Testé |
| 5 | ~~Longs films : veille et espace disque~~ **Fait** | Veille empêchée (Windows) ; espace vérifié avant de commencer, pour tous les traitements (fichier final + ProRes poussières + WAV DeepFilterNet), avec un message clair | Testé (disque plein simulé) |
| 6 | **Téléchargement durable** | L'artefact GitHub expire au bout de 90 jours et demande un compte GitHub | Publier une version (GitHub Release) téléchargeable sans compte |
| 7 | Son (souffle, clics, volume, sync) | Fait : trois profils, décalage, dérive manuelle, ronflement, copie WAV/FLAC, DeepFilterNet plafonné à 12 dB | Écoute sur de vraies cassettes |

### P1 — confort et qualité

| # | Manque | Proposition |
|---|---|---|
| 7 | ~~Durée restante~~ **Fait** non affichée | Estimation « environ 1 h 20 restantes » à partir de la progression |
| 8 | Bande de parasites en bas des images VHS | Option en place (lignes noires, taille inchangée), désactivée par défaut. À juger sur de vraies cassettes |
| 9 | Dominante de couleur (VHS verte) | Volontairement non corrigée (fidélité). Pas de bouton tant qu'une cassette réelle n'a pas été vue |
| 11 | **Fait** — Couper le début et la fin (neige, écran bleu) | Début/fin simples dans les options avancées |
| 12 | Réglages mémorisés | Fait : profil, options de son et dossier de sortie (`QSettings`) |
| 13 | **Fait** — Vérifier l'installation sans ligne de commande | Bouton « Vérifier l'installation » qui lance l'autotest |
| 14 | Compatibilité des vieilles télés (Full HD 50 i/s) | Réglage « compatibilité maximale » si un téléviseur réel pose problème |

### P2 — plus tard

QTGMC et IA dans le paquet Windows (testés sous Linux seulement) ; FFmpeg figé ; taille du paquet
(environ 390 Mo sous Linux avec le module poussières, à mesurer sous Windows) ; suppression des
images répétées d'un transfert ; encodage GPU ; signature de l'exécutable.

## 3. Ce qu'il ne faut pas ajouter

Montage, titres, musique, colorisation, interpolation d'images, partage sur Internet : hors
sujet, et chaque fonction en plus complique le mode simple.
