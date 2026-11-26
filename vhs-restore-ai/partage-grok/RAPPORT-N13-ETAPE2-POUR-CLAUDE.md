# N°13, étape 2 — mesures avant fusion du lecteur

Étude seulement. Rien n'est livré, le lecteur n'a pas été modifié, le moteur non plus.
Le compte rendu d'implémentation qui occupait ce fichier au commit `be6fe19`
(branche `grok/lecteur`, non modifiée) reste à ce commit.

« Mo » veut dire 1 048 576 octets, comme dans l'étude QTGMC. Les octets sont le chiffre exact.
Les mots entre crochets disent d'où vient le chiffre : **[mesuré]**, **[non retenu]**.

## Où

- Dépôt `ordiform69-png/1er-projet-`. Branche d'essai `grok/lecteur-mesures`, créée depuis `be6fe19` (`be6fe197d088d4ed38b3ff91653e509400c5e1c4`, tête de `grok/lecteur`).
- `grok/lecteur` est resté sur `be6fe19`. `gpt/timeline-retouches` est resté sur `c753474`. Aucun push sur ces branches. Aucune fusion, aucune pull request.
- Workflow séparé `.github/workflows/vhs-restore-lecteur-etude.yml`, scripts `.github/workflows/essai-lecteur-n13.ps1` et `.github/workflows/mesure-stries-n13.py`. `vhs-restore-windows.yml` n'a pas été modifié.
- Run retenu : https://github.com/ordiform69-png/1er-projet-/actions/runs/45882681610 — succès, job `etude-lecteur`, 3 min 55 s, commit `8170a0aa0770f2d2e0469ad6e1be5b5fbc25689e`. Numéro de run du workflow : **2**.
- Artefact `etude-lecteur-n13-2` sur ce run : `mesures.txt`, `fichiers-ajoutes.txt`, et les recadrages PNG (moins de 5 Ko au total). Aucune vidéo, aucun zip, aucune DLL dans le dépôt.
- Machine **[mesuré]** : `windows-latest`, image `win25-vs2026` `20261116.315.1`, AMD EPYC 7763, 2 cœurs / 4 processeurs logiques, 17 174 360 064 octets de mémoire. Python 3.12.10, PySide6 6.12.0, PyInstaller 6.22.3, NumPy 2.5.5. FFmpeg du logiciel : `9.1-essentials_build-www.gyan.dev`.

Un premier run, https://github.com/ordiform69-png/1er-projet-/actions/runs/45881988494 (commit `58f26ab`), a mesuré les tailles puis a échoué en créant la mire : FFmpeg 9.1 refuse l'option `-top`. Le correctif est le commit `8170a0a`. Les tailles décompressées de ce premier run sont identiques à celles du run retenu. Les zips différaient de quelques centaines d'octets (horodatage de `Compress-Archive`) ; les deux deltas compressés s'arrondissent à 10,02 Mo. Les chiffres officiels sont ceux du run réussi.

## a) Taille ajoutée par Qt Multimedia

**Conclusion.** Embarquer le lecteur ajoute **10 510 724 octets compressés (10,02 Mo)** et **23 310 549 octets décompressés (22,23 Mo)** au paquet Windows.

| | Sans Qt Multimedia | Avec Qt Multimedia | Delta |
|---|---:|---:|---:|
| Dossier décompressé | 694 757 941 octets (662,57 Mo), 330 fichiers | 718 068 490 octets (684,80 Mo), 370 fichiers | **23 310 549 octets (22,23 Mo)** |
| Zip `Compress-Archive` | 338 707 694 octets (323,02 Mo) | 349 218 418 octets (333,04 Mo) | **10 510 724 octets (10,02 Mo)** |

**[mesuré]** sur le run 45882681610. Aucun fichier retiré. Aucun fichier commun n'a changé de taille (`COMMUNS_DELTA_OCTETS=0`). Le delta décompressé est donc exactement la somme des 40 fichiers ajoutés.

### Méthode

Même fabrication que `vhs-restore-windows.yml`, sur le même runner : Python 3.12, `pip install` de `requirements-dev.txt`, `requirements-poussieres.txt`, `requirements-couleurs.txt` et `pyinstaller==6.22.3`, `scripts/installer_outils.ps1 -AvecCouleurs`, puis `pyinstaller --noconfirm VHSRestoreAI.spec`, les mêmes copies (FFmpeg, `LISEZMOI.txt`, licence DDColor, modèle, licence Analog Repair) et le même `Compress-Archive` du dossier `dist/VHSRestoreAI`.

Les tests pytest et l'autotest de l'exe n'ont pas été relancés : ils ne changent pas les octets du paquet. Le spec du dépôt n'a pas été modifié dans Git. Pour le paquet « sans », le script a ajouté le temps du build `PySide6.QtMultimedia` et `PySide6.QtMultimediaWidgets` aux `excludes`, puis a restauré le spec octet pour octet (`SPEC_RESTAURE=oui`) avant le paquet « avec », qui est le spec tel que la fabrication Windows le lance. Le code du lecteur importe déjà ces modules : PyInstaller 6.22.3 les embarque, avec le greffon `multimedia` et les DLL FFmpeg liées au greffon.

Le paquet « sans » ne contenait aucun de ces fichiers (`FICHIERS_MULTIMEDIA_AVANT=0`). Le paquet « avec » les contient.

### Ce qui pèse

| Fichier | Octets | Rôle |
|---|---:|---|
| `avcodec-63.dll` | 14 123 832 | FFmpeg de Qt, décodeur |
| `avformat-63.dll` | 2 856 248 | FFmpeg de Qt, conteneurs |
| `Qt6Multimedia.dll` | 1 399 096 | module Qt |
| `swscale-10.dll` | 1 265 976 | FFmpeg de Qt, pixels |
| `avutil-61.dll` | 1 166 136 | FFmpeg de Qt |
| `ffmpegmediaplugin.dll` | 758 584 | greffon de lecture |
| `QtMultimedia.pyd` | 579 384 | liaison Python |
| `windowsmediaplugin.dll` | 315 704 | greffon Windows du module |
| `swresample-7.dll` | 242 488 | FFmpeg de Qt, audio |
| `QtMultimediaWidgets.pyd` | 144 184 | liaison du widget vidéo |
| `Qt6MultimediaWidgets.dll` | 62 264 | module du widget |
| 29 traductions `qtmultimedia_*.qm` | 396 653 | textes Qt |
| **Total** | **23 310 549** | 40 fichiers |

Les DLL FFmpeg de Qt (avcodec, avformat, avutil, swscale, swresample) font 19 654 680 octets, soit l'essentiel de l'ajout. Ce n'est pas le FFmpeg du logiciel (`tools/ffmpeg`), déjà présent dans les deux paquets.

## b) Un film entrelacé s'affiche-t-il strié ?

**Conclusion.** Oui. Pendant un mouvement, le lecteur affiche l'image tissée, striée. Sur la mire, l'écart moyen entre une ligne paire et la ligne impaire voisine est **16,95** dans le lecteur, **17,00** chez FFmpeg sans désentrelacement, et **0,00** avec bwdif. Le témoin entre deux lignes de la même trame (`ligne 2k` et `ligne 2k+2`) est **0,00** dans les trois cas. Le lecteur se comporte comme le décodage brut, pas comme bwdif.

La mesure a été faite sur le runner Windows, plateforme Qt `windows` (pas `offscreen`), avec le widget `Lecteur` du logiciel (`QMediaPlayer` + `QVideoWidget`). L'image retenue vient de `videoSink().videoFrameChanged` puis `QVideoFrame.toImage()`, à 0,576 s, pendant que la barre se déplace. `grab()` du widget n'a pas contenu la barre : il n'est pas utilisé comme preuve. L'image du sink est celle que le widget reçoit pour l'affichage. Elle fait 768×576, taille d'écran 4:3 d'une source 720×576 : le redimensionnement d'affichage n'enlève pas les stries.

### La mire

Script `.github/workflows/mesure-stries-n13.py`. Une barre blanche verticale de 32 px avance de 24 px par champ sur fond noir (720×576). L'image entrelacée met le champ du temps 2k sur les lignes paires et le champ du temps 2k+1 sur les lignes impaires. Deux encodages, avec les drapeaux d'entrelacement (`setfield=tff`, `-flags +ildct+ilme`, `-field_order tt`) :

| | DV | MPEG-2 DVD |
|---|---|---|
| Fichier | AVI, `dvvideo`, 720×576, 25 im/s, son PCM | MPEG-2, `-target pal-dvd`, aspect 4:3, son du preset |
| Drapeaux **[mesuré]** | trame entrelacée, trame haute d'abord (`interlaced_frame=1`, `top_field_first=1`). Le flux ne donne pas `field_order`. | `field_order=tt`, trame entrelacée, trame haute d'abord |
| FFmpeg sans désentrelacement, image 15 | D1 17,00 / D2 0,00, 48 colonnes au-dessus de 15 | D1 17,00 / D2 0,00, 48 colonnes |
| FFmpeg `bwdif=mode=send_frame:parity=tff:deint=all` | D1 0,00 / D2 0,00, 0 colonne | D1 0,00 / D2 0,00, 0 colonne |
| Lecteur, image du sink | D1 **16,95** / D2 **0,00**, 53 colonnes, 768×576 | D1 **16,95** / D2 **0,00**, 53 colonnes, 768×576 |
| Verdict du script | `strie` | `strie` |

D1 est la moyenne de `|ligne 2k − ligne 2k+1|` sur la bande verticale de la barre (niveaux de gris 0–255, NumPy). D2 est la moyenne de `|ligne 2k − ligne 2k+2|`, le témoin : deux lignes du même champ, donc la même position de barre. Quand D2 vaut 0,00, le script écrit un rapport 999 : ce n'est pas un quotient mesuré, c'est le signe que le témoin est nul et l'écart voisin ne l'est pas. Les 48 colonnes du décodage brut sont les deux bords décalés de 24 px. Les 53 colonnes du lecteur viennent du passage de 720 à 768 px.

Avant l'encodage, la même image tissée donne D1 17,00 et D2 0,00. bwdif sur cette image donne D1 0,00. Le codec DV et le MPEG-2 n'effacent pas les stries : seul bwdif le fait. Les recadrages du run le montrent : deux peignes décalés pour le lecteur et pour FFmpeg sans filtre, une barre pleine pour bwdif.

### Contrôle hors du runner

Le même script, en local, Linux, `QT_QPA_PLATFORM=offscreen`, PySide6 6.12.0, greffon FFmpeg de Qt (« FFmpeg version 9.0.1 »), FFmpeg système 6.1.1 pour fabriquer la mire. DV et DVD : lecteur D1 16,95 / D2 0,00, FFmpeg sans filtre 17,00 / 0,00, bwdif 0,00 / 0,00, verdict `strie`. L'écran X du poste n'a pas pu ouvrir le greffon `xcb` ; le repli offscreen a servi. Ce n'est pas la mesure retenue. Elle dit la même chose que Windows.

## Si l'on veut enlever les stries

Rien n'a été codé. Trois pistes, de la plus adaptée à la plus pauvre.

1. **Aperçu progressif avec bwdif**, le filtre que la restauration utilise déjà. La mesure montre que D1 passe de 17,00 à 0,00. L'aperçu ressemble alors à ce que le film restauré montrera. FFmpeg est déjà dans le paquet, aucune nouvelle dépendance. Ce n'est plus l'original affiché tel quel : il faut un extrait temporaire ou un flux, le son doit rester aligné, et préparer tout un long film d'avance serait lourd. Un extrait autour de la tête de lecture, ou un tube, limite ce coût.

2. **Désentrelacer dans le décodeur Qt** (le greffon FFmpeg déjà ajouté au paquet). La lecture resterait dans `QMediaPlayer`, sans fichier temporaire. Qt 6.12 n'offre pas d'interrupteur sur `QMediaPlayer` pour cela : il faudrait un filtre dans le pipeline, donc modifier le lecteur. Dans cette mesure, le FFmpeg de Qt (`avcodec-63.dll`) a rendu l'image tissée, comme FFmpeg lancé sans filtre.

3. **N'afficher qu'un champ sur deux.** Plus simple et plus léger. On perd la moitié de la définition verticale et le mouvement est moins fluide. bwdif, déjà mesuré, fait mieux.

La piste 1 est celle qui colle au logiciel : bwdif est déjà le désentrelacement de la restauration, et il est le seul des trois décodages mesurés à supprimer les stries.

## Non fait

- Le paquet « sans » n'est pas un ancien exe publié : c'est la même fabrication, avec les deux modules exclus le temps du build. Les fichiers communs n'ont pas bougé, donc le delta est bien celui de Qt Multimedia.
- `grab()` n'a pas photographié la vidéo, ni sur la plateforme `windows` du runner, ni en offscreen sous Linux.
- Pas de cassette réelle, pas de DVD du commerce : la mire est synthétique, à bords francs, pour que l'écart de lignes soit lisible. Un film flou donnerait un D1 plus petit ; le sens du résultat (tissé ou désentrelacé) resterait le même.
- La suite de tests du logiciel n'a pas été relancée : le lecteur, le moteur et les tests n'ont pas changé. Seuls les scripts d'étude ont été exécutés.

## Copie de lecture

La mesure ci-dessus reste celle de `grok/lecteur-mesures` (`4d83a88`). Cette partie décrit la correction, sur `grok/lecteur-copie`, partie de `gpt/timeline-retouches` au commit `c753474`. Le code est le commit `98b729b`. `grok/lecteur`, `grok/lecteur-mesures` et `gpt/timeline-retouches` n'ont pas reçu de push. Pas de fusion, pas de pull request.

**Conclusion.** Pour un film dont `info.scan` vaut `tff` ou `bff`, le lecteur prépare en arrière-plan une copie désentrelacée, puis s'y met à la même position en gardant la lecture ou la pause. Un film progressif reste sur l'original. S'il manque de la place, il n'y a pas de copie, et rien ne casse : aucun message de plus, le lecteur continue sur l'original.

### Ce qui est fait

- `bwdif=mode=send_frame` avec la parité mesurée (`tff` ou `bff`) : une image par image source, donc les mêmes instants. L'image est ensuite ramenée à la taille d'affichage, 720 px de large au plus, format gardé. Une VHS 720×576 en pixels 16/15 (4:3) devient 720×540. Codage H.264 `veryfast`, CRF 18, son AAC par `tools.AAC` à 160 kbit/s quand le film a une piste, `-movflags +faststart`.
- Un DVD en plusieurs VOB est couvert en entier, comme les vignettes (`dvd.input_args`).
- Le travail est un fil à part, en priorité basse (`nice` 10, et la classe « below normal » sous Windows). Il attend la fin de l'analyse des scènes (`_suivi_scenes`, si la fenêtre en a une) et ne lance pas FFmpeg en même temps qu'elle. Un délai de 0,4 s laisse cette analyse démarrer quand elle est lancée dans le même tour d'ouverture. Au changement de film et à la fermeture, FFmpeg est tué et le dossier temporaire `vhsrestore_lecture_*` est effacé, sur le modèle des vignettes.
- La place disque est vérifiée avant. L'estimation réserve 25 Mbit/s fois deux (fichier et réécriture faststart). Pas assez de place, ou FFmpeg en échec : pas de copie, pas de message.
- Jusqu'à ce que la copie soit prête, « Lire le film » ouvre l'original. Un DVD en plusieurs morceaux garde le message des petites images. Quand la copie est prête, la lecture en cours bascule sans repartir du début. La barre continue d'utiliser la durée du film d'origine.
- Le moteur de restauration et le calcul de la durée ne sont pas modifiés. Aucune dépendance ajoutée.

### Mesures

Mire du rapport (barre blanche de 32 px, 24 px par champ, 720×576, TFF, pixels 16/15), image à 0,72 s. Même mesure que `.github/workflows/mesure-stries-n13.py` : D1 est la moyenne de `|ligne 2k − ligne 2k+1|`, D2 celle de `|ligne 2k − ligne 2k+2|`. **[mesuré]**

| | D1 | D2 |
|---|---:|---:|
| Original, sans désentrelacement | 17,00 | 0,00 |
| Copie de lecture | 0,00 | 0,03 |

Même image que l'original passé par le même `bwdif` et le même cadrage, à 0,24 s, 0,72 s et 1,20 s. L'écart moyen des pixels (0–255) est 0,01 aux trois instants. Le centre de la barre est le même : 255,5 px, 191,5 px, 127,5 px. **[mesuré]**

Vitesse de préparation sur un film 720×576 entrelacé TFF, pixels 16/15, 25 i/s, 8,000 s, 200 images. C'est une mire `testsrc2` tissée, avec un bruit léger (`noise=alls=12`) et un son. Le temps compte l'encodage seul (`preparer`), pas la fabrication du film d'essai. **[mesuré]**

| | |
|---|---|
| Images par seconde | 221,1 |
| Temps pour une heure de film | 407,0 s (6 min 47 s) |
| Machine | Linux 6.12.113+, x86_64, Intel Xeon, 4 cœurs, 16 387 328 kio de mémoire |
| Outils | Python 3.12.3, FFmpeg 6.1.1-3ubuntu5, PySide6 6.12.0 pour les tests du lecteur en hors écran |

Ce n'est pas une cassette. Un film très détaillé ou très bruité irait moins vite. L'ordre de grandeur est celui d'un `veryfast` en 720×540.

### Tests

`QT_QPA_PLATFORM=offscreen`, 400,69 s. **60 réussis, 0 échoué.** Fichiers lancés : `tests/test_copie_lecture.py`, `tests/test_lecteur.py`, `tests/test_timeline.py`, `tests/test_ecrans.py`, `tests/test_assistant.py`. Aucun test déjà présent n'a été affaibli.

Les tests ajoutés couvrent la mire (écart proche de 0 sur la copie, élevé sur l'original), le film progressif (aucune copie), les trois instants, le changement de film pendant la préparation (FFmpeg arrêté, aucun fichier laissé), le passage du lecteur sur la copie sans quitter la lecture, le manque de place, et la commande d'un DVD en plusieurs morceaux.

### Non fait ici

- Pas de cassette réelle pour la vitesse : le chiffre est celui du film synthétique décrit plus haut.
- L'analyse des scènes n'est pas dans `c753474`. Le fil sait l'attendre si `_suivi_scenes` est là. Sur cette branche, il n'y en a pas : la copie part après l'ouverture du film.
- La position rendue par Qt au moment de la bascule a été vérifiée à moins d'une seconde près, lecture toujours en cours. L'identité des images, elle, est celle du fichier (écart de pixel 0,01).

## Corrections

Demandées avant la fusion (n°19, section 2). Le code est le commit `783b128`, sur `grok/lecteur-copie`. L'enchaînement après l'analyse des scènes n'est pas touché : il sera fait à l'assemblage.

**CRF.** La copie de lecture passe de `-crf 18` à `-crf 27`. Le preset reste `veryfast`. Le filtre `bwdif=mode=send_frame`, la taille d'affichage et le son AAC ne changent pas.

**Place réservée.** `besoin_octets` ne part plus de 25 Mbit/s. La formule est `int(durée × 4 000 000 / 8 × 2) + 1 048 576` octets : 4 Mbit/s de marge au-dessus du débit mesuré ci-dessous, fois deux pour la réécriture `faststart`, plus 1 Mio. Pour une heure, cela fait **3 601 048 576 octets** (3 434,23 Mo, 3,35 Go ; 1 Mo = 1 048 576 octets).

**Taille d'une heure, mesurée.** **[mesuré]**

Méthode. Mire synthétique 720×576, entrelacée TFF, pixels 16/15 : `testsrc2` à 50 trames/s, tissée par `tinterlace=interleave_top`, champ haut d'abord, bruit léger `noise=alls=12:allf=t`, son sinusoïdal, MPEG-2 8 Mbit/s dans un AVI. L'extrait demandé dure 30 s. L'encodage est celui de la copie (`copie_lecture.preparer`) : `bwdif=mode=send_frame`, 720×540, H.264 `veryfast` CRF 27, AAC, `faststart`. Aucune vidéo n'est entrée dans le dépôt.

| | |
|---|---|
| Durée du fichier obtenu | 30,040 s |
| Taille de l'extrait | 4 874 114 octets |
| Débit du fichier | 1,298 Mbit/s (vidéo 1,212 Mbit/s, AAC 79 kbit/s) |
| Taille pour une heure | 4 874 114 / 30,040 × 3 600 = **584 114 860 octets**, soit **557,06 Mo** (0,544 Go) |
| Machine | Linux 6.12.113+, x86_64, Intel Xeon, 4 cœurs, 16 387 328 kio de mémoire, FFmpeg 6.1.1-3ubuntu5, Python 3.12.3 |

L'extrapolation multiplie la taille mesurée par 3 600 / 30,040. Ce n'est pas une cassette : une image plus bruitée pèse davantage, d'où la réserve à 4 Mbit/s plutôt qu'au débit mesuré.

**Tests.** `QT_QPA_PLATFORM=offscreen`, fichier `tests/test_copie_lecture.py`, 23,86 s. **10 réussis, 0 échoué.** Les seuils déjà présents (stries, écart d'image, durée) n'ont pas été relâchés. Sur la même mire qu'avant, D1 reste 17,00 sur l'original et 0,00 sur la copie ; l'écart moyen des pixels aux trois instants est 0,02, 0,02 et 0,04. **[mesuré]**
