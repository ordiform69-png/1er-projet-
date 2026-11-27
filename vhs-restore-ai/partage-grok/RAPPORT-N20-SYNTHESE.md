# Synthèse n°20 pour Claude (chasse aux bugs)

Index des cinq rapports d'agents. Les chiffres viennent de ces rapports, cités ci-dessous. Têtes relevées le 27/11/2026 à 15:31 (heure de Paris), après `git fetch --prune origin`. Le chef des bots n'a modifié aucun code. Branche `grok/bugs-n20` créée depuis `1abf947` (la base `ccr-5856e8d6-8xt8uh` a depuis avancé à `a31205d`, non reprise ici).

## 1. Où

| Agent | Bot | Branche | Hash | Constats | Tests lancés par le bot |
|---|---|---|---|---|---|
| A | Rendu | `grok/bugs-a-temps` | `b545143` | 4 | Preuves lancées sous FFmpeg 6.1.1 et 7.1.5 ; tests en xfail strict (pas de décompte pytest dans le rapport) |
| B | Lumière | `grok/bugs-b-image` | `3304c9e` | 4 | Preuves lancées sous FFmpeg 6.1.1 ; quatre tests en xfail strict (pas de décompte pytest dans le rapport) |
| C | Navigation | `grok/bugs-c-ecran` | `6afcf76` | 5 | **10 xfailed** (cinq constats × deux zooms), 5,02 s, PySide6 6.12.0, hors écran, `QT_SCALE_FACTOR` |
| D | Maquettes | `grok/bugs-d-windows` | `f997205` | 10 | **7 xfailed** (constats 1 à 7) ; 8 à 10 non lancés. FFmpeg 7.1.5 cité pour les chemins accentués (hors constats) |
| E | Lancer | `grok/bugs-e-fin` | `d36e135` | 10 | **10 xfailed**, 22,69 s, FFmpeg 6.1.1, PySide6 6.12.0, hors écran |

33 constats au total, 32 lignes ci-dessous après regroupement du doublon D4 / E7.

À lire : `partage-grok/RAPPORT-N20-A.md` sur `grok/bugs-a-temps`, `RAPPORT-N20-B.md` sur `grok/bugs-b-image`, `RAPPORT-N20-C.md` sur `grok/bugs-c-ecran`, `RAPPORT-N20-D.md` sur `grok/bugs-d-windows`, `RAPPORT-N20-E.md` sur `grok/bugs-e-fin`.

Hors constats (détails dans ces rapports) : raccords de 10 min et durée d'une heure calés (A, FFmpeg 6.1) ; ordre des trames et arrivée des réglages de lumière (B) ; tuiles de l'étape 1 déjà corrigées (C) ; chemins accentués et JSON (D, FFmpeg 7.1.5) ; copies 4:3 quand le fichier annonce déjà le 4:3 (E).

## 2. Constats, du plus grave au moins grave pour le père

Classement pour le père (film abîmé ou faux d'abord, puis travail perdu ou conseil dangereux, puis écran et messages). La gravité indiquée est celle de l'agent.

| n° | Gravité | Agent | Branche@commit | Où | Constat | Preuve | Lancé |
|---|---|---|---|---|---|---|---|
| 1 | Bloquant | E1 Lancer | `grok/bugs-e-fin`@`d36e135` | `partage.py:151` (format lu à 127) | La copie d'une capture SD à pixels carrés (SAR 1:1) sort en 5:4 (légère 600 × 480, télévision 720 × 576) alors que l'analyse suppose le 4:3 ; les visages sont trop étroits. Son et durée sont bons. | PROUVÉ | Lancer (FFmpeg 6.1.1) |
| 2 | Bloquant | A1 Rendu | `grok/bugs-a-temps`@`b545143` | `pipeline.py:1410` | Les passages enlevés font prendre du retard au son : 12 coupes d'une seconde, dernier bip à 11,054 s au lieu de 11 ; surplus d'environ 3 ms par raccord (30 ms après 12 coupes), en plus des 24 ms du constat A2. | PROUVÉ | Rendu (FFmpeg 6.1.1 et 7.1.5) |
| 3 | Bloquant | A3 Rendu | `grok/bugs-a-temps`@`b545143` | `pipeline.py:199` (`_atempo_chain`) | Une dérive inférieure à 6 ms/min n'est pas corrigée (`_atempo_filters` vide pour 0,4 à 5,9 ms/min). À 5 ms/min, le retard reste entier : 900 ms à la fin d'un film de 3 h. | PROUVÉ | Rendu (appel de `_atempo_filters`, pas d'export de 3 h) |
| 4 | Gênant | E2 Lancer | `grok/bugs-e-fin`@`d36e135` | `probe.py:368` (calcul à 366) | Un décalage fixe (son de 19,5 s pour 20 s d'image) est annoncé comme une dérive d'environ −1500 ms par minute, avec le conseil de régler « Dérive du son ». Sur un film de 3 h, suivre ce conseil décalerait le son d'environ 4,5 minutes. | PROUVÉ | Lancer |
| 5 | Gênant | A2 Rendu | `grok/bugs-a-temps`@`b545143` | `pipeline.py:284` (`afftdn`) | Le nettoyage du son (profil Nettoyage léger) retarde l'image de 24 ms du début à la fin de l'heure, en une fois et par parties ; les 24 dernières millisecondes du film sont coupées. Sans « Restaurer le son », les bips restent à l'heure. | PROUVÉ | Rendu (60 min sous 6.1 ; 20 s sous 7.1.5) |
| 6 | Gênant | A4 Rendu | `grok/bugs-a-temps`@`b545143` | `pipeline.py:272`, 283 et 285 | Le profil Bien nettoyé (`adeclick`, `afftdn` et `dynaudnorm`) efface le son du premier instant : le bip à 0 s disparaît, celui à 10,024 s reste. Chaque filtre seul le garde. | PROUVÉ | Rendu (FFmpeg 6.1.1 et 7.1.5, film de 12 s) |
| 7 | Bloquant | D1 Maquettes | `grok/bugs-d-windows`@`f997205` | `tools.py:462-464` (`terminate` à 517-524) | FFmpeg continue après la fin du processus père (`os._exit` sans `terminate`) : il peut poursuivre l'écriture du `.partiel` et verrouiller le dossier. `_eteindre_a_la_sortie` ne tue pas le FFmpeg de l'export. | PROUVÉ | Maquettes (Linux ; Job Object Windows non exercé) |
| 8 | Bloquant | D2 Maquettes | `grok/bugs-d-windows`@`f997205` | `pipeline.py:902-914` et 922 | Le contrôle FAT32 laisse passer un film de 3 h si le type de volume est inconnu (`""`). L'écriture peut échouer après des heures, fichier incomplet. | PROUVÉ (trou de logique) ; cas réel « partage Windows FAT32 » non lancé | Maquettes (logique seule) |
| 9 | Gênant | E6 Lancer | `grok/bugs-e-fin`@`d36e135` | `gui.py:4603` | « Arrêter » pendant une restauration laisse tourner la copie de lecture : le travail affiché s'arrête, FFmpeg continue la copie du film entier (1 à 3 h) et remplit le disque. | PROUVÉ | Lancer (film de 8 s) |
| 10 | Gênant | B1 Lumière | `grok/bugs-b-image`@`3304c9e` | `pipeline.py:580-581` | Le scintillement (`deflicker=size=5`) tire la couleur du plan suivant : le vert passe de 170 à 162 sur les quatre images avant la coupure (écart max 8,6 niveaux). Même dérive en Nettoyage léger (bleu 10 → 28). | PROUVÉ | Lumière (FFmpeg 6.1.1) |
| 11 | Gênant | B2 Lumière | `grok/bugs-b-image`@`3304c9e` | `pipeline.py:564-572` et 429-430 ; aperçu `lumiere.py:44-45` | « Plus chaude » (teinte +3) n'ajoute pas de rouge dans le film quand la dominante est déjà au plafond 1,18 (delta 0,0, le filtre reste `rr=1.1800`) ; l'aperçu, lui, ajoute +13,1. | PROUVÉ | Lumière (FFmpeg 6.1.1) |
| 12 | Gênant | B3 Lumière | `grok/bugs-b-image`@`3304c9e` | `pipeline.py:594-597` | Un décalage de couleur de 4 px en déplace 8 (colonne 360 → 368), en 4:2:0 et en 4:2:2. L'écran dit « px ». | PROUVÉ | Lumière |
| 13 | Gênant | B4 Lumière | `grok/bugs-b-image`@`3304c9e` | `pipeline.py:641-650` | La bande du bas reste visible en Full HD : 16 lignes demandées n'en masquent que 16 sur 1080, alors que 16 lignes de 576 en font 30 ; les lignes −30 à −17 restent rouges (R = 199,8). | PROUVÉ | Lumière (FFmpeg 6.1.1) |
| 14 | Gênant | E3 Lancer | `grok/bugs-e-fin`@`d36e135` | `partage.py:288` | « Arrêter » pendant la séparation laisse le premier film déjà écrit, alors que l'écran dit « Arrêté. Votre film n'a pas été modifié. » Un nouvel essai ajoute « (2) » au premier. | PROUVÉ | Lancer |
| 15 | Gênant | D4 Maquettes et E7 Lancer | `grok/bugs-d-windows`@`f997205` et `grok/bugs-e-fin`@`d36e135` | `tools.py:199-205` (`reserver_sorties`) | Un verrou `.reserve` orphelin (le film n'existe pas) fait sortir le film sous le nom « (2) ». Même bug : D4 « `.reserve` orphelin » et E7 « verrou oublié ». | PROUVÉ | Maquettes et Lancer |
| 16 | Gênant | E5 Lancer | `grok/bugs-e-fin`@`d36e135` | `pipeline.py:751` | Si la durée est inconnue, la barre est à 100 % dès la première image (total 0,001 s) et le reste pendant tout le film. | PROUVÉ | Lancer (film de 3 s) |
| 17 | Gênant | E4 Lancer | `grok/bugs-e-fin`@`d36e135` | `estimation.py:52` | Un travail calculé à 4 725 s (1 h 19) est annoncé « environ 1 heure » ; de 1 h 00 à 1 h 29, c'est toujours cette phrase. Le père peut éteindre l'ordinateur avant la fin. | PROUVÉ | Lancer (fonction `annonce`, sans restauration) |
| 18 | Gênant | E9 Lancer | `grok/bugs-e-fin`@`d36e135` | `pipeline.py:1522` | La copie du son restauré reste affichée à 99 % (« Copie du son restauré… ») : pas de `-progress`, `on_line` non branché. | PROUVÉ | Lancer |
| 19 | Gênant | C1 Navigation | `grok/bugs-c-ecran`@`6afcf76` | `gui.py:2150` | L'aide du premier lancement (« Bienvenue dans VHS Restore AI ») mesure 709 × 1169 (minimum 801) : sur 1280 × 641, « C'est parti » est sous le bord, et Échap n'est pas accepté. 1169 dépasse aussi 535, 689, 785 et 1001. | PROUVÉ | Navigation (hors écran, zooms 1 / 1,25 / 1,5) |
| 20 | Gênant | C2 Navigation | `grok/bugs-c-ecran`@`6afcf76` | `gui.py:1384` | La fenêtre remise à sa taille (1100 × 760) dépasse les petits écrans : « Lancer la restauration » sort de 641, 689 et 535 ; la largeur 1100 dépasse 1024 et 1093. | PROUVÉ | Navigation (zooms 1, 1,25 et 1,5) |
| 21 | Gênant | D3 Maquettes | `grok/bugs-d-windows`@`f997205` | `ergonomie.py:91-97` | Disque plein en cours de route : `No space left on device` devient « Cette étape n'a pas abouti », sans parler de place ni de disque. | PROUVÉ | Maquettes (`expliquer`, sans remplir un disque) |
| 22 | Gênant | E8 Lancer | `grok/bugs-e-fin`@`d36e135` | `partage.py:310` | Remettre le même nom dans « Nommer » transforme `Noël 1988.mp4` en `Noël 1988 (2).mp4` et fait disparaître l'ancien nom. | PROUVÉ | Lancer |
| 23 | Gênant | E10 Lancer | `grok/bugs-e-fin`@`d36e135` | `gui.py:4876` | Au démarrage, les noms des filtres manquants sont montrés tels quels (« FFmpeg trop ancien », « Filtres manquants : bwdif, hqdn3d ») au lieu de la phrase prévue par `ergonomie.expliquer`. | PROUVÉ | Lancer |
| 24 | Gênant | C3 Navigation | `grok/bugs-c-ecran`@`6afcf76` | `gui.py:253` | L'image du moniteur est floue à 125 % et à 150 % : contraste des bords 126 à 100 %, 116 à 125 % (rapport 0,92), 105 à 150 % (0,83). | PROUVÉ | Navigation |
| 25 | Gênant | C4 Navigation | `grok/bugs-c-ecran`@`6afcf76` | `gui.py:1224` | Les petites images de la barre sont floues à 125 % et à 150 % : contraste 105 à 100 %, 84 à 125 % (0,80), 70 à 150 % (0,67). | PROUVÉ | Navigation |
| 26 | Gênant | D5 Maquettes | `grok/bugs-d-windows`@`f997205` | `gui.py:1395` (nettoyage à 4766) ; `lumiere.py:125` | Les dossiers temporaires d'aperçu et de « Lumière » restent si `closeEvent` ne passe pas (`_eteindre_a_la_sortie` ne les efface pas). | PROUVÉ | Maquettes |
| 27 | Gênant | D6 Maquettes | `grok/bugs-d-windows`@`f997205` | `installer.py:141` | L'extraction 7-Zip n'a pas `-sccUTF-8` (la liste, ligne 138, l'a). Risque d'échec dans un profil Windows accentué. | PROUVÉ que le drapeau manque ; échec réel non lancé | Maquettes (commande seule) |
| 28 | Gênant | D7 Maquettes | `grok/bugs-d-windows`@`f997205` | `tools.py:259-267` | Chemin trop long : le refus se base sur le chemin résolu, le message peut afficher la longueur du nom court (ex. 11 caractères). | PROUVÉ | Maquettes (Windows simulé, `IS_WIN`) |
| 29 | Gênant | D8 Maquettes | `grok/bugs-d-windows`@`f997205` | `dvd.py:83-87` (même motif `pipeline.py:1303-1305`) | Liste concat et chemins UNC : `file '//NAS/films/…'` peut être refusé par FFmpeg sous Windows. | PLAUSIBLE | non lancé (Maquettes ; pas de partage UNC) |
| 30 | Gênant | D9 Maquettes | `grok/bugs-d-windows`@`f997205` | `tools.py:323` et 464 | Les sorties FFmpeg sont toujours décodées en UTF-8 : un chemin accentué en cp1252 peut arriver avec des « � » dans « Détails pour l'aide ». | PLAUSIBLE | non lancé (Maquettes ; FFmpeg 7.1.5 Debian émet de l'UTF-8) |
| 31 | Gênant | D10 Maquettes | `grok/bugs-d-windows`@`f997205` | ouverture (`probe` / `open_media` / `-i`) | Un fichier OneDrive « uniquement en ligne » peut faire échouer l'ouverture avec un message peu clair. | PLAUSIBLE | non lancé (Maquettes ; pas de compte OneDrive) |
| 32 | Mineur | C5 Navigation | `grok/bugs-c-ecran`@`6afcf76` | `ecran.py:231` | « Détails du fichier » s'ouvre à 850 × 580 et dépasse l'écran de 535 px de haut (les 45 px du bas, dont « Fermer », sortent). Sur 1280 × 641, 580 tient. | PROUVÉ | Navigation |

## 3. Règles (vérifiées par `git diff` et `git log` depuis `1abf947`)

- `vhs_restore/` est intact sur les cinq branches.
- Tous les commits portent `[skip ci]` à la fin du titre (un commit sur A, B et C ; deux sur D et sur E).
- Aucun test existant modifié : seulement les fichiers nouveaux `tests/test_bugs_n20_{a,b,c,d,e}.py` et les cinq rapports.
- Aucun binaire commité (ni vidéo, ni image, ni zip, ni DLL, ni poids).
- Aucune pull request ouverte. Aucune branche `grok/bugs-*` n'est fusionnée dans la base.

## 4. À trancher par vous

1. **Doublon D4 / E7** : même bug (verrou `.reserve` orphelin → nom « (2) »). Une seule correction suffit.
2. **PLAUSIBLE, non lancés** : D8 (liste concat UNC), D9 (stderr FFmpeg en cp1252), D10 (OneDrive « uniquement en ligne »). Ils demandent Windows.
3. **Preuves partielles qui demandent aussi Windows** : D2 (trou de logique prouvé ; cas réel volume FAT32 ou réseau non lancé) ; D6 (drapeau `-sccUTF-8` manquant prouvé ; extraction réelle dans un profil accentué non lancée). D1 est prouvé sous Linux (`os._exit`) ; le Job Object Windows n'a pas été exercé.
4. **Écran (C)** : les mesures ont été faites sous Linux avec `QT_SCALE_FACTOR`, hors écran, pas sur un Windows à 150 %.
5. **E2** : l'agent le classe gênant, mais suivre le conseil sur un film de 3 h décalerait le son d'environ 4,5 minutes. Faut-il le traiter comme bloquant dans la n°21 ?
