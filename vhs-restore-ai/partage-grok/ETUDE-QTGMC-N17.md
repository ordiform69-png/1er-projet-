# Étude n°17 — QTGMC dans l'exe

Agent D. Étude seulement : rien n'est livré, le code du logiciel et le job de fabrication n'ont pas changé.

**Recommandation.** Ne pas embarquer QTGMC dans le paquet Windows. Le garder comme aujourd'hui : une option à part, pour qui a déjà Python. Sur le Windows de la fabrication, la même source 720×576 sort à **14,0 images/s avec QTGMC** et à **1 658 images/s avec bwdif**. Le dossier à ajouter pèse **111 Mo compressés** et **282 Mo décompressés**. En plus, deux morceaux chargés dans le même `vspipe` (znedi3 en GPLv2, akarin en LGPL-3.0 seulement) ne se redistribuent pas clairement ensemble.

Les mots entre crochets disent d'où vient le chiffre : **[mesuré]**, **[estimé]**, **[non testé]**.

## Où

- Branche `grok/qualite-qtgmc`, créée depuis `4f09073` (`4f090734fd9cfa670d2be04fc6b372327474b7eb`).
- Essai : workflow séparé `.github/workflows/vhs-restore-qtgmc-etude.yml` et script `.github/workflows/essai-qtgmc-n17.ps1`. Le fichier `vhs-restore-windows.yml` n'a pas été modifié. Pas de PyInstaller, pas d'artefact, pas de fusion, pas de pull request.
- Run : https://github.com/ordiform69-png/1er-projet-/actions/runs/45745340245 — succès, job `etude-qtgmc`, 2 min 37 s, commit `52fae44`.
- Machine **[mesuré]** : `windows-latest`, image `win25-vs2026` `20261116.315.1`, AMD EPYC 7763, 2 cœurs / 4 processeurs logiques, 17 174 360 064 octets de mémoire (16 Go). VapourSynth Core R82, 4 fils. FFmpeg `9.1-essentials_build-www.gyan.dev`, le même que le logiciel installe.
- Le script lancé est `vhs_restore/qtgmc.vpy` tel qu'il est (QTempGaussMC de vs-jetpack 3.0.0, réglages par défaut, `tff=1`). bwdif est celui du logiciel : `bwdif=mode=send_field:parity=tff:deint=all`. Les deux jettent l'image produite (tube vers NUL, ou `-f null`) : on mesure le désentrelacement, pas l'encodage H.264.

« Mo » veut dire 1 048 576 octets.

## 1. Quoi embarquer, et quelle taille

Le logiciel n'appelle pas havsfunc. `qtgmc.vpy` appelle `QTempGaussMC` (vs-jetpack) et BestSource. L'essai à blanc du script a réussi, puis le film entier. Au démarrage, les espaces chargés étaient **[mesuré]** : `akarin`, `avs`, `bs`, `mvu`, `resize`, `resize2`, `std`, `text`, `vszip`, `znedi3`. Pas de `fmtc`, pas de l'ancien `mvtools`, pas de `nnedi3`.

Il faut un dossier à côté de l'exe, pas des DLL soudées dedans (voir les licences). Python embarqué **3.13**, pas 3.12 : la fiche PyPI de `vsjetpack==3.0.0` dit `Requires-Python >=3.13` **[mesuré sur l'index PyPI]**. Python 3.12 n'a pas été relancé sur le runner **[non testé]**. Le script portable officiel de VapourSynth R82 ne suffit pas : son zip (31 801 679 octets) est la roue VapourSynth plus 12,5 Mo de documentation HTML. Il n'a ni Python, ni greffons.

### Dossier qui a vraiment tourné

Installé sur le runner : Python 3.13.12 embarqué, `pip install -r requirements-qtgmc.txt`, puis suppression des fichiers `.pdb` et de pip. C'est le dossier qui a exécuté `vspipe`.

| | Octets | Mo | |
|---|---:|---:|---|
| Dossier décompressé, sans PDB ni pip | 295 383 679 | 281,70 | [mesuré] |
| Zip de ce dossier (Deflate) | 116 290 542 | 110,90 | [mesuré] |
| Le même dossier avant nettoyage (avec pip et les PDB) | 390 020 237 | 372,00 | [mesuré] |

**Taille ajoutée au paquet : 110,90 Mo compressés, 281,70 Mo décompressés [mesuré].** C'est le zip du dossier portable, fait sur le runner. L'effet exact sur `VHSRestoreAI-Windows.zip` n'a pas été mesuré : le paquet livré n'a pas été reconstruit **[non testé]**.

`MSVCP140.dll` n'est pas dans ce dossier. `vspipe.exe` le demande. Le runner l'a trouvé dans le JDK Temurin, 575 056 octets **[mesuré]**. Un Windows sans ce fichier n'a pas été essayé **[non testé]**. Il faudrait le copier à côté de `vspipe.exe` (environ 0,55 Mo de plus).

### Morceau par morceau

Tailles des fichiers Windows publiés (roues PyPI et zip Python), relevées en les téléchargeant. Le total du dossier, plus haut, est plus gros d'environ 21 Mo à cause des fichiers `.pyc` créés à l'installation.

| Morceau | Version | Rôle | Compressé | Décompressé |
|---|---|---|---:|---:|
| Python embarqué | 3.13.12 | `python.exe`, `python313.dll` | 10 941 233 | 21 217 392 |
| VapourSynth + `vspipe` | R82 | cœur, `vspipe.exe` | 23 728 996 | 98 461 775 |
| dont symboles `.pdb` à ne pas livrer | | | (dans la roue) | 82 989 056 |
| VapourSynth sans les `.pdb` | | utile | (dans le zip du dossier) | 15 472 719 |
| akarin | 1.5.0 | expressions de vs-jetpack (`libakarin.dll`, 66,8 Mo) | 25 910 614 | 67 888 510 |
| BestSource | 23 | lecture du film (`core.bs`) | 16 086 999 | 37 188 417 |
| MVUtensils | 10 | mouvement, à la place de mvtools. Trois DLL (générique, AVX2, Zen 4) | 12 507 533 | 44 959 456 |
| znedi3 | 3.3 | interpolation, à la place de nnedi3. DLL 1,5 Mo + poids `nnedi3_weights.bin` 13,6 Mo | 13 179 222 | 15 108 225 |
| vszip | 24.0.0 | limiteurs et flou. Trois variantes CPU | 6 404 392 | 20 923 441 |
| resize2 | 0.5.1 | redimensionnement | 258 958 | 770 616 |
| numpy | 2.5.5 | exigé par vs-jetpack. OpenBLAS pèse 20,6 Mo | 12 573 354 | 41 953 406 |
| vs-jetpack | 3.0.0 | `QTempGaussMC` | 445 900 | 1 690 881 |
| jetpytools | 3.2.0 | dépendance | 32 979 | 91 700 |
| rich + pygments + markdown-it + mdurl | 15.0.0 / 2.21.0 / 4.3.0 / 0.1.2 | dépendance de vs-jetpack | 1 667 731 | 6 149 062 |
| psutil | 7.2.2 | dépendance | 137 737 | 451 054 |
| typing_extensions | 4.16.0 | dépendance | 45 571 | 182 767 |

Somme des fichiers publiés, Python compris, PDB encore dans la roue VapourSynth : 123 921 219 octets compressés (118,18 Mo), 357 036 702 octets décompressés (340,50 Mo), dont 82 989 056 octets de PDB **[mesuré]**.

Retirer les variantes AVX2 et Zen 4 réduirait MVUtensils et vszip. On ne l'a pas fait : le chargeur n'a pas été essayé sans elles **[non testé]**. `vsvfw.dll` (193 536 octets, VFW) est dans la roue et n'est pas utile à `vspipe`. On ne l'a pas retiré.

### Cités par la demande, pas chargés par le script

Tailles publiées **[mesuré]**. Aucun des quatre n'a été exécuté **[non testé]**.

| Morceau | Version | Compressé | Décompressé | Pourquoi il n'est pas dans le dossier |
|---|---|---:|---:|---|
| fmtconv | 31 | 2 250 910 | 3 526 292 | vs-jetpack ne l'appelle pas dans le réglage par défaut de QTempGaussMC |
| mvtools | 29 | 2 757 970 | 8 832 385 | remplacé par MVUtensils (`mvu`) |
| nnedi3 | v12, win64, 2018 | 88 801 | 247 296 | plus sur PyPI, dépôt archivé. La DLL seule, sans le fichier de poids. znedi3 le remplace |
| havsfunc | 34 | 5 879 | 14 821 | le script utilise `QTempGaussMC`, pas havsfunc |

## 2. Licences, et ce qu'elles imposent pour une distribution gratuite

Toutes autorisent de donner le logiciel sans le faire payer. Chacune demande au minimum de garder son texte et ses copyrights. Les roues les contiennent déjà.

| Morceau | Licence lue | Ce qu'il faut pour redistribuer |
|---|---|---|
| VapourSynth R82 | LGPL-2.1-or-later (expression SPDX de la roue, texte LGPL 2.1) | DLL à part, que l'utilisateur peut remplacer. Code source de cette version, ou un lien stable vers le dépôt et le numéro. |
| akarin 1.5.0 | LGPL-3.0-only (`pyproject.toml` et la roue) | Même chose, en LGPL-3. Pas de passage en « ou ultérieure » : le texte dit seulement la version 3. |
| resize2 0.5.1 | LGPL-2.1 (expression SPDX `LGPL-2.1`, texte LGPL 2.1, sans « ou ultérieure ») | DLL remplaçable et source. |
| MVUtensils 10 | GPL-2.0-or-later dans le `pyproject.toml` amont. La roue n'écrit que `GPL-2.0` | Source du greffon. « Ou ultérieure » permet de le distribuer sous GPL-3. |
| znedi3 3.3 | GPLv2. Le readme dit « GPLv2 » sans « ou toute version ultérieure ». La roue dit `GPL-2.0` | Source, y compris le traitement des poids `nnedi3_weights.bin` livrés dans la roue. |
| BestSource 23 | MIT | Garder le copyright et le texte MIT. |
| vszip 24 | MIT | Idem. |
| vs-jetpack 3.0.0 | MIT | Idem. |
| jetpytools, rich, markdown-it, mdurl | MIT | Idem. |
| numpy 2.5.5 | BSD-3-Clause | Garder le copyright et le texte. Ne pas utiliser le nom pour promouvoir le paquet. |
| psutil 7.2.2 | BSD-3-Clause | Idem. |
| pygments 2.21.0 | BSD-2-Clause | Garder le copyright et le texte. |
| typing_extensions | PSF-2.0 | Garder le texte PSF. |
| Python 3.13.12 embarqué | PSF-2.0 | Le zip officiel contient déjà `LICENSE.txt`. Le garder. |
| fmtconv (non embarqué) | WTFPL-2 | Rien d'autre que de pouvoir en garder une copie. |
| mvtools et nnedi3 (non embarqués) | GPL-2.0 | Source, si un jour on les livrait. |
| havsfunc (non embarqué) | Unlicense (domaine public) | Rien. |

### Avec le reste du paquet

Le paquet a déjà PySide6 (LGPLv3) et le FFmpeg de gyan.dev (GPLv3), lancés comme des programmes séparés. `vspipe` serait un troisième programme, relié par un tube, comme FFmpeg l'est déjà. La GPL des greffons s'applique à ce programme `vspipe`, pas à l'exe PySide, tant qu'on ne lie pas ces DLL dedans.

Le point dur est à l'intérieur de `vspipe`. L'essai a chargé en même temps akarin (LGPL-3.0 seulement) et znedi3 (GPLv2 sans « ou ultérieure »). Ces deux textes ne se combinent pas : la LGPL-3 ne se ramène pas à la GPL-2, et la GPL-2 seule n'accepte pas les conditions de la LGPL-3. MVUtensils, lui, est « ou ultérieure » : on peut le voir comme GPL-3, ce qui va avec la LGPL-3. VapourSynth est LGPL-2.1 « ou ultérieure » : on peut aussi le voir en LGPL-3. resize2 est LGPL-2.1 sans « ou ultérieure » : même famille de question, sur un DLL petit.

Tant que ce point n'est pas tranché (confirmation des auteurs de znedi3, ou un avis), on ne peut pas écrire que le dossier est redistribuable sans réserve. C'est une raison de plus de ne pas le mettre dans le paquet.

## 3. Vitesse sur le Windows de fabrication

Source **[mesuré]** : image de synthèse `testsrc2`, 720×576, entrelacée par `tinterlace` puis `setfield=tff`, FFV1, cadence annoncée 25/1, 13 366 216 octets, sans son. ffprobe n'a pas donné le nombre d'images (`nb_frames` vide) et a écrit `field_order=tb`. Les deux outils ont reçu l'ordre trame haute en premier, comme le logiciel, et ont écrit **750 images** chacun. 750 images en sortie, c'est le double de 375 images source, donc 15,0 s de film **[estimé à partir des 750 images mesurées]**. Une cassette réelle n'a pas été utilisée **[non testé]**.

Les deux passes se suivent. La première inclut le démarrage et, pour QTGMC, l'index de BestSource. Sur ce fichier court, la deuxième passe n'est pas plus rapide : l'index ne se voit pas. Pas de fichier d'index distinct repéré à part des fichiers de numpy dont le nom contient « index » **[mesuré : aucun index BestSource identifié]**.

| Passe | Outil | Images de sortie | Secondes au mur | Images/s au mur | Compteur de l'outil |
|---|---|---:|---:|---:|---:|
| 1 | QTGMC | 750 | 52,222 | 14,36 | 14,73 i/s (vspipe) |
| 2 | QTGMC | 750 | 53,632 | 13,98 | 14,26 i/s en 52,60 s |
| 1 | bwdif | 750 | 0,453 | 1 654 | |
| 2 | bwdif | 750 | 0,452 | 1 658 | |

**Chiffres retenus, deuxième passe, même méthode (images de sortie / temps au mur) [mesuré] : QTGMC 14,0 i/s, bwdif 1 658 i/s.** bwdif est 118,6 fois plus rapide (1 657,69 / 13,98). Le compteur de vspipe (14,26 i/s) enlève une seconde de lancement. On garde le mur pour que les deux outils soient comparés pareil.

L'essai à blanc (`check=1`, image vide) a fini en 0,782 s, dont 2 images en 0,04 s **[mesuré]**. Il dit seulement que les greffons se chargent.

Une heure de cassette PAL, en 50 images/s en sortie (180 000 images), prendrait environ **3 h 35 min** avec QTGMC à 13,98 i/s, et **1 min 49 s** avec bwdif à 1 658 i/s **[estimé : règle de trois, pas un film d'une heure]**. Le débruitage et l'encodage H.264, ensuite, n'ont pas été mesurés **[non testé]**. Sur une heure, ils pèsent peu à côté de QTGMC, et ils dépassent bwdif. Une vraie cassette bruitée peut ralentir l'analyse de mouvement **[non testé]**.

DECISIONS.md annonçait environ 31 i/s pour QTGMC seul sous Linux, 4 cœurs. Ici le runner a 2 cœurs. On n'a pas refait le chiffre Linux **[non testé dans cette étude]**.

## Ce qui n'a pas été testé

- Cassette VHS réelle, et la chaîne complète jusqu'au MP4.
- Film long : seule la règle de trois ci-dessus.
- Windows sans `MSVCP140.dll` déjà présent.
- Python 3.12 sur le runner.
- Dossier allégé (sans AVX2, sans Zen 4, sans `vsvfw.dll`, sans pygments).
- Qualité d'image de QTGMC comparée à bwdif : la demande portait sur la taille, les licences et la vitesse.
- Le paquet livré reconstruit avec ce dossier dedans.

## Bloqué

Rien. Le run `45745340245` a réussi du premier coup.
