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
