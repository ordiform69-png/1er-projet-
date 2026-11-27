# Demande n°20 : chasse aux bugs, avant toute nouvelle fonction (pour le chef des bots)

L'utilisateur a restauré un vrai film de famille : à 7,8 s, toute l'image passe d'un coup du
blanc au jaune, au milieu d'un même plan. Cause : la correction « scène par scène » (n°17), qui
inventait des coupures dans un plan continu. Tous nos essais l'avaient laissée passer, parce
qu'ils n'utilisaient que des mires (`testsrc2`), dont la couleur moyenne ne bouge pas. Elle est
désactivée (`scenes.ACTIF = False`, commit `b4ec2ef`, voir `DECISIONS.md`).

L'utilisateur demande une analyse de tout le logiciel : « je ne peux pas être sûr que tout
fonctionne correctement ». Son père (76 ans) restaure des films de 1 à 3 heures : DVD de
cassettes (MPEG-2 720 × 576 entrelacé, 4:3, plusieurs VOB) et captures, sur un écran 1920 × 1080
à 150 % (1280 × 641 utiles).

**Cette fois : trouver et prouver, pas corriger.** Aucune modification dans `vhs_restore/`.
Claude vérifie chaque constat, puis une demande n°21 corrigera ceux qui sont confirmés.

## Base, branches, équipe

- Base : `ccr-5856e8d6-8xt8uh` au commit `b4ec2ef` (ou plus récent).

| Agent | Domaine | Branche | Fichiers à lire en priorité |
|---|---|---|---|
| A | Films longs, raccords, son et image calés | `grok/bugs-a-temps` | `pipeline.py` (`export`, `_export`, `_export_morceaux`, montage, `-ss`, `-itsoffset`, `-frames:v`, `apad`, `atrim`, `_tempo_factor`), `reprise.py`, `dvd.py`, `probe.py` |
| B | Image : tout ce qui change d'une image à l'autre | `grok/bugs-b-image` | `pipeline.py` (`pre_filters`, `filter_chain` et leurs aides), filtres de bande, de couleur, de décrochages, poussières, stabilisation, scintillement, désentrelacement, `lumiere.py` |
| C | Écran : zoom de Windows 125 et 150 %, petits écrans | `grok/bugs-c-ecran` | `gui.py` (tous les `paintEvent`, `QPixmap`, `QIcon`, tailles fixes), `assistant.py`, `lumiere.py`, `ecran.py`, `vignettes.py`, `theme.py` |
| D | Windows, fichiers, disque | `grok/bugs-d-windows` | `tools.py`, `installer.py`, `reprise.py`, `partage.py`, `vignettes.py`, la copie de lecture (`gui.py`), `scripts/*.ps1`, `fabriquer_exe.bat` |
| E | Fin du travail, arrêt, erreurs, copies à partager | `grok/bugs-e-fin` | `gui.py` (lancement, « Arrêter », messages), `pipeline.py` (fin du film, fichiers provisoires), `partage.py`, `ergonomie.py`, `estimation.py` |
| Chef | Synthèse | `grok/bugs-n20` | réunit les cinq rapports, classe les constats |

## Ce que chaque agent cherche (exemples, pas une liste fermée)

- **A** :
  - le son qui se décale peu à peu sur 1 à 3 heures (dérive cumulée) ;
  - une image perdue ou doublée aux raccords (parties de 10 minutes, passages enlevés, VOB) ;
  - les dernières secondes du film (son coupé, images manquantes) ;
  - un film de plus de 4 Go ;
  - une cadence variable ;
  - un début de film décalé (`video_offset`).
- **B** :
  - un saut, un éclair ou un pompage de lumière ou de couleur ;
  - la première ou la dernière image différente des autres ;
  - un ordre des trames inversé ;
  - le 10 bits (`lutyuv`) ;
  - un réglage de « Lumière et couleurs » qui n'arrive pas dans le film ;
  - tout ce qui lit encore `info.scenes` alors que la correction par scène est désactivée.
- **C** : le défaut d'aujourd'hui sous d'autres formes. Sur l'écran à 150 %, les petites images de
  l'étape 1 sortaient aux deux tiers, collées en haut à gauche (corrigé, `2dc2f2a`).
  - Cause : `QIcon.pixmap()` puis `QPixmap.scaled()` gardent le `devicePixelRatio` de la source.
  - Chercher partout ce motif, les textes coupés, les tailles en pixels fixes, la fenêtre qui
    grandit.
- **D** :
  - les chemins avec accents, espaces, apostrophes, très longs, OneDrive ou disque réseau ;
  - les échappements dans les arguments de FFmpeg (`:`, `\`, `'` dans les listes de concat et
    les filtres) ;
  - le JSON écrit à la main (un test cassait sur les `\` de Windows) ;
  - le texte de FFmpeg décodé en cp1252 ;
  - un fichier verrouillé, le disque plein en cours de route, une clé USB en FAT32 ;
  - FFmpeg qui continue après la fermeture, les dossiers temporaires laissés.
- **E** :
  - « Arrêter » à chaque étape ;
  - les erreurs au milieu du travail, les fichiers partiels laissés ;
  - une progression qui n'atteint pas 100 %, une durée annoncée fausse sur un film long ;
  - les noms de sortie en double ;
  - la copie « pour la télévision » et la copie légère (durée complète, format 4:3, couleurs,
    son) ;
  - les messages incompréhensibles pour un homme de 76 ans.

## Règles des constats (les mêmes pour tous)

1. Chaque constat dans le rapport :
   - **Gravité** : bloquant (film abîmé, perdu ou faux), gênant, ou mineur ;
   - **Où** : fichier et ligne ;
   - **Scénario concret** : telle entrée donne tel mauvais résultat ;
   - **Preuve** ;
   - **Correction proposée**, en une ligne.
2. **PROUVÉ** : un test ou une commande, avec le résultat mesuré. **PLAUSIBLE** : un scénario
   précis, mais non lancé. Pas de « pourrait peut-être ».
3. Dix constats au plus par agent, les plus graves d'abord. La qualité compte plus que le nombre.
4. Ne pas signaler à nouveau ce qui est déjà connu :
   - la correction par scène (désactivée) ;
   - les petites images à 150 % (corrigé) ;
   - les 3 échecs Windows de `fabriquer_exe` (corrigés, `193a716`).

## Pièges connus : ne pas refaire l'erreur des mires

- `testsrc2` seul est interdit pour juger la couleur ou la lumière dans le temps : sa moyenne ne
  bouge pas.
- **Film réaliste.** Utilisez un plan qui se déplace sur une grande image, avec du bruit et une
  lumière qui varie un peu. La couleur moyenne y change alors avec le contenu, comme dans un vrai
  film :
  ```
  testsrc2=s=1440x1152:r=50:d=120,crop=720:576:x='min(t*6\,720)':y='min(t*4\,576)',
  eq=brightness='0.03*sin(2*PI*t/7)':eval=frame,noise=alls=8:allf=t,interlace,
  format=yuv422p,setsar=16/15
  ```
  (`r=50` : `interlace` réunit deux images en une, on obtient 25 images entrelacées par
  seconde.) Ajoutez de vraies coupures avec `concat` de plans différents.
- **Film long pour le temps.** 60 minutes en 320 × 240 (rapide), avec un bip toutes les 10
  secondes et un repère visible au même instant. On vérifie qu'à la fin, bip et repère sont
  encore ensemble (20 ms près).
- **Zoom d'écran.** Il ne se règle qu'au démarrage de Qt : programme à part avec
  `QT_SCALE_FACTOR=1.5`, comme `test_petite_image_du_rendu_entiere_et_centree`
  (`tests/test_assistant.py`).
- **Écrans** : 1280 × 641 à 100, 125 et 150 % de texte, et les écrans de `tests/test_ecrans.py`.
- **Votre bac à sable.** S'il ne peut pas lancer FFmpeg ou PySide6, écrivez quand même le test ou
  la commande et marquez « non lancé ». Claude les lance.

## Livraison

- Chaque agent livre deux fichiers sur sa branche :
  - `partage-grok/RAPPORT-N20-<lettre>.md` ;
  - `tests/test_bugs_n20_<lettre>.py`. Un test qui montre un bug est marqué
    `@pytest.mark.xfail(strict=True, reason="...")`, pour que la suite reste verte jusqu'à la
    correction. Une commande qui ne tient pas dans un test va dans le rapport.
- Le chef livre `partage-grok/RAPPORT-N20-SYNTHESE.md` sur `grok/bugs-n20` : les constats des cinq
  agents, classés du plus grave au moins grave pour le père, chacun avec sa branche et son
  commit, et qui l'a lancé ou non.
- Règles :
  - chaque commit poussé tout de suite ;
  - lancer seulement les fichiers de tests cités, pas la suite complète (une heure ; Claude la
    lance) ;
  - aucune modification dans `vhs_restore/` ;
  - aucune nouvelle dépendance ;
  - aucun test existant modifié ni affaibli ;
  - ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request.
