# VHS Restore AI

Application Windows gratuite et locale pour restaurer des films familiaux numérisés des années
1970 à 1995 : cassettes vidéo (VHS, VHS-C, Video8, Hi8, Betamax…), pellicules scannées (Super 8,
8 mm, 16 mm, 9,5 mm) et pellicules copiées sur vidéo. Elle désentrelace, réduit le bruit, corrige
couleurs et netteté, exporte en Full HD, et propose en option la stabilisation et l'agrandissement IA. Elle sert d'**orchestrateur** : FFmpeg fait le travail, et
Real-ESRGAN intervient si vous l'installez. Aucun cloud, aucun abonnement.

## Installation (Windows 10/11)

1. Installez [Python 3.10 ou plus](https://www.python.org/downloads/) en cochant « Add python.exe to PATH ».
2. Double-cliquez sur **`installer.bat`**. Il crée un environnement isolé `.venv`, installe
   PySide6 et télécharge FFmpeg (somme SHA-256 vérifiée) dans `tools\ffmpeg`.
   - Option IA : lancez `installer.bat -AvecIA` dans une invite de commandes. Le script ajoute
     Real-ESRGAN dans `tools\realesrgan` (il faut une carte graphique compatible Vulkan).
   - Option QTGMC (meilleur désentrelacement) : lancez `installer.bat -AvecQTGMC`. Il faut
     **Python 3.12 ou plus**. Le script installe VapourSynth et les plugins par pip dans `.venv`.
     Les deux options se combinent : `installer.bat -AvecIA -AvecQTGMC`.
3. Double-cliquez sur **`lancer.bat`**.

Vous avez déjà FFmpeg ? Il suffit qu'il soit dans le PATH, ou dans les variables `VHSRA_FFMPEG`,
`VHSRA_FFPROBE`, `VHSRA_REALESRGAN` et `VHSRA_VSPIPE`. Les journaux se trouvent dans `%LOCALAPPDATA%\VHSRestoreAI\logs`.

## Utilisation

1. **Choisir une vidéo** (ou la glisser dans la fenêtre). L'analyse affiche la résolution, la
   cadence, le format 4:3, l'entrelacement mesuré, la norme probable, le son, le noir et blanc et
   une **origine suggérée** (vidéo, pellicule, pellicule transférée), avec sa raison. Corrigez
   « Origine du film » si besoin : les réglages s'adaptent (grain préservé pour une pellicule,
   jamais de désentrelacement automatique). Pour une pellicule numérisée image par image, la
   « Cadence de tournage » (16, 18 ou 24 i/s) permet de retrouver la vitesse naturelle des
   mouvements, sans créer ni supprimer d'image. Laissez « Celle du fichier » en cas de doute.
2. **Choisir un profil** : Fidèle, Équilibré ou Maximum. Choisissez aussi la résolution de sortie
   et, en option, le débruitage haute qualité (plus lent), la stabilisation (caméra tenue à la
   main) et l'IA.
3. **Générer l'aperçu** d'un extrait de 10 s. Passez la souris sur l'image pour déplacer le rideau
   avant/après. « Lire la comparaison vidéo » ouvre l'extrait côte à côte dans votre lecteur.
4. **Lancer la restauration.** Le fichier `<nom>_restaure_<profil>.mp4` est créé dans le dossier
   choisi. L'original n'est jamais modifié, et vous pouvez annuler à tout moment.

## Profils (paramètres exacts dans `vhs_restore/profiles.py`)

Le tableau donne les réglages **vidéo**. Pour une pellicule, le débruitage est nettement plus
léger (Fidèle n'en applique aucun) ; pour un transfert, il est intermédiaire
(`SOURCE_OVERRIDES`). Option « Réduire le scintillement » pour les pellicules et transferts.

| | Fidèle | Équilibré | Maximum |
|---|---|---|---|
| Désentrelacement (si mesuré) | bwdif 50p | QTGMC 50p (bwdif si absent) | QTGMC 50p (bwdif si absent) |
| Parasites ponctuels | – | removegrain 1 | removegrain 1 |
| Bruit hqdn3d | 1.5:3:2:4 | 3:5:4.5:7 | 4:7:6:10 |
| Bruit « haute qualité » (option) | fftdnoiz σ5 + chroma 4:6 | σ8 + 6:9 | σ11 + 8:12 |
| Contraste / saturation | inchangés | ×1,04 / ×1,08 | ×1,06 / ×1,12 |
| Stabilisation (vid.stab) | case à cocher, désactivée par défaut | idem | idem |
| Netteté cas | – | 0,30 | 0,45 (aucune si IA) |
| Sortie par défaut | origine | origine (Full HD au choix) | Full HD (+ IA si installée) |

Ces réglages sont des points de départ, pas une garantie : jugez toujours sur l'aperçu, surtout
les visages. La 4K n'est proposée qu'avec l'IA, et elle n'apporte aucun détail authentique de plus.

## État des fonctions

**Opérationnel et testé automatiquement** (Linux, FFmpeg 6.1, PySide6 hors écran, vidéos de synthèse) :
analyse (accents et espaces dans les noms), détection TFF/progressif, 4:3 et pixels 16:15,
PAL/NTSC, les trois profils, l'export (taille, 50 i/s, son présent et synchronisé, durée, original
intact, pas d'écrasement), l'annulation avec nettoyage, QTGMC réel (VapourSynth R82 et vs-jetpack 3.0 :
export, extrait, aperçu, annulation, combinaison avec l'IA, plugin manquant signalé), stabilisation
(tremblement mesuré −59 % sur une vidéo de synthèse ; 4:3, cadence et son conservés ; extrait,
annulation, combinaisons avec QTGMC et avec l'IA), débruitage haute qualité (PSNR +2,9 à +4,8 dB
par rapport au débruitage standard sur une image bruitée artificiellement), les erreurs (fichier corrompu, dossier absent,
moteur IA manquant), l'aperçu avant/après et le parcours complet dans l'interface. La chaîne IA a
été testée avec un **faux** moteur qui agrandit sans IA.

Origines (vidéos de synthèse) : suggestion d'origine sur 4 cas (pellicule 18 i/s, transfert 25i
bruité, caméscope, noir et blanc) ; pellicule jamais désentrelacée automatiquement ; cadence de
tournage 16 et 24 i/s (108 images conservées, durée et son ajustés) ; 4:3 et son conservés ;
film muet resté muet ; transfert traité à 25p sans suppression d'image ni trame mélangée restante ;
grain mieux conservé qu'avec les réglages vidéo.

**Non testé** : de vraies pellicules ou de vrais transferts (rayures, poussières, décoloration,
scintillement réels) ; exécution réelle sous Windows (`installer.bat`, `lancer.bat`, script PowerShell,
QTGMC) ; l'indexation BestSource sur un long film ;
le vrai Real-ESRGAN (pas de GPU ici) ; de vraies cassettes numérisées (aucun échantillon fourni,
donc aucune évaluation visuelle réelle) ; la détection BFF sur du contenu réel ; de longs films.

**Prévu ensuite** : rayures et poussières image par image (aucun outil simple et maintenu
retenu pour l'instant), suppression optionnelle des images répétées d'un transfert, masquage du bruit de tête en bas d'image,
encodage GPU, traitement par lots.

## Préparer les fichiers (numérisation)

Pellicules :
- Préférez un scan image par image à la capture d'une projection sur un mur (scintillement,
  déformation, flou).
- Gardez un fichier maître de bonne qualité (peu compressé, ou sans perte), à la cadence de
  tournage si elle est connue. Sinon, notez celle du scanner.
- Numérisez aussi la piste son (magnétique ou optique) si la bobine en a une.

Cassettes vidéo :
- Utilisez un lecteur du bon format (VHS-C avec adaptateur, Video8/Hi8 sur un caméscope ou un
  lecteur 8 mm). Si possible, choisissez un magnétoscope avec correcteur de base de temps (TBC).
- Vérifiez la norme : PAL ou SECAM en France (625 lignes), NTSC pour des cassettes américaines
  ou japonaises.
- Capturez sans recompression destructive (sans perte, ou DV), sans désentrelacer ni
  redimensionner au moment de la capture : VHS Restore AI s'en charge.

## Développement

```
pip install -r requirements-dev.txt
python -m pytest tests          # nécessite ffmpeg/ffprobe dans le PATH
                                # tests QTGMC réels : pip install -r requirements-qtgmc.txt, vapoursynth config
python -m vhs_restore           # lance l'interface
```

Architecture : `tools.py` (détection et exécution des outils) · `probe.py` (analyse) ·
`profiles.py` · `pipeline.py` (filtres, aperçu, export) · `qtgmc.vpy` (script VapourSynth) ·
`upscaler.py` (adaptateur IA) · `gui.py`.
Les choix techniques sont expliqués dans [`DECISIONS.md`](DECISIONS.md).

Licences des outils : FFmpeg (build gyan.dev, GPLv3), PySide6 (LGPLv3), Real-ESRGAN (BSD-3),
VapourSynth (LGPL-2.1), vs-jetpack (MIT) ; chaque plugin a sa propre licence (voir PyPI).
Les outils sont téléchargés sur votre poste ; si vous **redistribuez** un paquet qui les contient,
les obligations de la GPL s'appliquent (fournir les sources ou un lien vers celles-ci).
