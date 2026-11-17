Bonjour Grok,

Merci pour la refonte visuelle (PR #10, fusionnée). Depuis, l'interface a beaucoup bougé : lis
d'abord `DECISIONS.md`, phases 14 à 20. Cette fois, la demande porte sur **l'ergonomie** :
rendre le logiciel **vraiment intuitif pour l'utilisateur final, un homme de 76 ans** qui se
sert peu d'un ordinateur. Va au fond des choses, mais sans casser ce qui marche.

## Qui utilise le logiciel

- Né en 1950, il lit moins bien les petits textes et le texte clair sur fond sombre. La souris
  est parfois imprécise. Il ne survole pas les éléments pour lire les infobulles.
- Il veut : choisir un film (cassette VHS numérisée, pellicule, photo), voir si c'est mieux,
  lancer, retrouver le résultat. Rien d'autre.
- Il a peur de « casser » quelque chose ou de perdre un film. Un message technique l'arrête net.

## Ce qui existe déjà (ne pas refaire, améliorer)

- Mode simple : bandeau avec « Aide » et « Affichage clair / sombre », cadre d'information en mots
  simples, trois grands boutons d'étape (`StepButton`, le suivant est encadré : `suggested`),
  aperçu avant / après avec trois boutons « Original / Comparer les deux / Restauré »
  (`CompareView.set_mode`), barre de progression avec temps restant, « Restaurer tout un dossier ».
- Fenêtre « Bienvenue » au premier lancement (`show_welcome`, `maybe_welcome`).
- Options avancées : cartes (`Carte`), tuiles de profil (`ProfileTile`), interrupteurs, icônes
  (`icons.py`, 48 icônes SVG dessinées dans le code), voyants des outils cliquables avec
  installation (`installer.py`).
- Deux palettes (`theme.SOMBRE`, `theme.CLAIR`, `theme.set_mode`) ; contrastes testés.
- Robot d'audit : `scripts/audit_interface.py` (chaque bouton, dans six états : actif ?
  visible ? branché ? efficace ?).

## Méthode demandée (avant de coder)

1. **Parcours cognitif**, pour la personne décrite ci-dessus, sur ces six tâches, en notant à
   chaque écran ce qu'il voit, ce qu'il comprend, et où il peut hésiter ou se tromper :
   a) restaurer un film ; b) restaurer une photo ; c) restaurer tout un dossier ;
   d) retrouver et regarder le film restauré ; e) arrêter un traitement en cours puis reprendre ;
   f) comprendre et surmonter une erreur (fichier abîmé, disque plein, clé USB retirée).
2. **Revue selon les 10 principes de Nielsen** (visibilité de l'état, langage de
   l'utilisateur, contrôle et liberté, cohérence, prévention des erreurs, reconnaissance plutôt
   que rappel, souplesse, sobriété, aide à corriger les erreurs, aide).
3. Mets ces deux analyses dans la PR (un tableau : problème, gravité 1 à 4, correction proposée),
   puis corrige en commençant par les gravités 4 et 3.

## Pistes à étudier (à confirmer ou écarter avec ton analyse)

1. **Fin de restauration** : au lieu d'une boîte de dialogue, un écran « C'est prêt » avec trois
   gros boutons : « Regarder le film » (lecteur Windows), « Ouvrir le dossier »,
   « Restaurer un autre film ». Pour une photo : « Voir la photo ».
2. **Pendant un long traitement** : temps restant en mots (« environ 25 minutes »), phrase
   rassurante (« Vous pouvez utiliser l'ordinateur ou le laisser travailler »), signal clair à la
   fin (son discret et clignotement dans la barre des tâches Windows), et confirmation avant
   « Arrêter » quand le travail est long (« Le travail déjà fait sera perdu »).
3. **Choisir le fichier** : la boîte de dialogue s'ouvre dans « Vidéos » ou « Images » (puis dans
   le dernier dossier utilisé) ; glisser-déposer accepté sur **toute** la page simple (aujourd'hui
   seulement dans les options avancées) ; liste des derniers fichiers ouverts.
4. **Erreurs en langage clair** : chaque erreur dit ce qui s'est passé et **que faire**, en une ou
   deux phrases ; le détail technique est derrière un bouton « Détails pour l'aide » (avec
   « Copier »). Repars des messages existants (`ToolError`) et du journal.
5. **Taille du texte** : réglage « A– / A / A+ » (100 / 125 / 150 %) dans le bandeau, mémorisé,
   qui agrandit tout le mode simple sans défilement horizontal.
6. **Infobulles** : tout ce qui est indispensable doit être **visible**, pas seulement en
   infobulle (il ne survole pas). Un petit bouton « ? » à côté des éléments qui en ont besoin.
7. **Clavier et cibles** : ordre de tabulation logique, Entrée active le bouton encadré, cibles
   d'au moins 44 × 44 px, focus clavier bien visible dans les deux palettes.
8. **Restaurer tout un dossier** : afficher « Film 3 sur 12 : nom… » et un résumé final clair
   (réussis, déjà faits, en échec avec la raison en mots simples).
9. **Accessibilité** : `setAccessibleName` / `setAccessibleDescription` sur les boutons
   (lecteur d'écran Windows), rien qui ne repose sur la couleur seule.
10. Tout autre problème trouvé par ton analyse.

## Règles non négociables

- **Aucun changement de traitement** : mêmes filtres, mêmes profils, mêmes réglages par défaut,
  aucune correction activée d'office (règle de fidélité du projet). La case « Corriger aussi ces
  défauts » reste décochée d'avance. La colorisation reste une copie à part, jamais par défaut.
- Français, vouvoiement, phrases courtes, pas de jargon dans le mode simple.
- Garder les attributs utilisés par les tests (`s_choose`, `s_preview`, `s_run`, `s_info`,
  `s_advice`, `s_colorize`, `segments`, `compare`, `run_btn`, `pages`, `voyants`, `profile_buttons`…)
  et les `objectName` du QSS, ou les renommer partout.
- Les **153 tests** restent verts. Ajoute des tests pour chaque comportement nouveau.
- Les deux palettes : contrastes ≥ 4,5:1 (`theme.contrastes()`), testés.
- Aucun défilement horizontal à 1366×740, 1280×720 et 1093×600 (`tests/test_theme.py`), y
  compris avec le texte agrandi.
- Aucune nouvelle dépendance Python. Pas d'animation permanente pendant un traitement.
- Lance `scripts/audit_interface.py` avant et après : aucun bouton actif sans effet.

## Livraison

- Une branche `grok/ergonomie` partie de la dernière `ccr-5856e8d6-8xt8uh`. Plusieurs PR petites
  et thématiques valent mieux qu'une seule énorme (par exemple : fin de restauration, erreurs,
  taille du texte, clavier et accessibilité). Rebase avant chaque PR.
- Dans chaque PR :
  - le tableau d'analyse (problème, gravité, correction) ;
  - des **captures réelles** (hors écran, `widget.grab()`) avant / après, dans les deux palettes ;
  - la construction Windows verte avec l'autotest de l'exe ;
  - pour finir : **Fait / Testé (comment) / Non testé / Risques**.

Merci !
