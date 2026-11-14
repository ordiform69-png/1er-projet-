# VHS Restore AI

Application Windows gratuite et locale pour restaurer des vidéos de caméscope numérisées
(VHS-C, Video8, Hi8…) : désentrelacement, réduction du bruit, couleurs, netteté, Full HD, et
agrandissement IA en option. Elle sert d'**orchestrateur** : FFmpeg fait le travail, et
Real-ESRGAN intervient si vous l'installez. Aucun cloud, aucun abonnement.

## Installation (Windows 10/11)

1. Installez [Python 3.10 ou plus](https://www.python.org/downloads/) en cochant « Add python.exe to PATH ».
2. Double-cliquez sur **`installer.bat`**. Il crée un environnement isolé `.venv`, installe
   PySide6 et télécharge FFmpeg (somme SHA-256 vérifiée) dans `tools\ffmpeg`.
   - Option IA : lancez `installer.bat -AvecIA` dans une invite de commandes. Le script ajoute
     Real-ESRGAN dans `tools\realesrgan` (il faut une carte graphique compatible Vulkan).
3. Double-cliquez sur **`lancer.bat`**.

Vous avez déjà FFmpeg ? Il suffit qu'il soit dans le PATH, ou dans les variables `VHSRA_FFMPEG`,
`VHSRA_FFPROBE` et `VHSRA_REALESRGAN`. Les journaux se trouvent dans `%LOCALAPPDATA%\VHSRestoreAI\logs`.

## Utilisation

1. **Choisir une vidéo** (ou la glisser dans la fenêtre). L'analyse affiche la résolution, la
   cadence, le format 4:3, l'entrelacement mesuré, la norme probable et le son. Si une
   caractéristique est incertaine, un avertissement s'affiche et vous pouvez la forcer
   (balayage, format).
2. **Choisir un profil** : Fidèle, Équilibré ou Maximum. Choisissez aussi la résolution de sortie
   et, en option, l'IA.
3. **Générer l'aperçu** d'un extrait de 10 s. Passez la souris sur l'image pour déplacer le rideau
   avant/après. « Lire la comparaison vidéo » ouvre l'extrait côte à côte dans votre lecteur.
4. **Lancer la restauration.** Le fichier `<nom>_restaure_<profil>.mp4` est créé dans le dossier
   choisi. L'original n'est jamais modifié, et vous pouvez annuler à tout moment.

## Profils (paramètres exacts dans `vhs_restore/profiles.py`)

| | Fidèle | Équilibré | Maximum |
|---|---|---|---|
| Désentrelacement (si mesuré) | bwdif 50p | bwdif 50p | bwdif 50p |
| Parasites ponctuels | – | removegrain 1 | removegrain 1 |
| Bruit hqdn3d | 1.5:3:2:4 | 3:5:4.5:7 | 4:7:6:10 |
| Contraste / saturation | inchangés | ×1,04 / ×1,08 | ×1,06 / ×1,12 |
| Netteté cas | – | 0,30 | 0,45 (aucune si IA) |
| Sortie par défaut | origine | origine (Full HD au choix) | Full HD (+ IA si installée) |

Ces réglages sont des points de départ, pas une garantie : jugez toujours sur l'aperçu, surtout
les visages. La 4K n'est proposée qu'avec l'IA, et elle n'apporte aucun détail authentique de plus.

## État des fonctions

**Opérationnel et testé automatiquement** (Linux, FFmpeg 6.1, PySide6 hors écran, vidéos de synthèse) :
analyse (accents et espaces dans les noms), détection TFF/progressif, 4:3 et pixels 16:15,
PAL/NTSC, les trois profils, l'export (taille, 50 i/s, son présent et synchronisé, durée, original
intact, pas d'écrasement), l'annulation avec nettoyage, les erreurs (fichier corrompu, dossier absent,
moteur IA manquant), l'aperçu avant/après et le parcours complet dans l'interface. La chaîne IA a
été testée avec un **faux** moteur qui agrandit sans IA.

**Non testé** : exécution réelle sous Windows (`installer.bat`, `lancer.bat`, script PowerShell) ;
le vrai Real-ESRGAN (pas de GPU ici) ; de vraies cassettes numérisées (aucun échantillon fourni,
donc aucune évaluation visuelle réelle) ; la détection BFF sur du contenu réel ; de longs films.

**Prévu ensuite** : QTGMC via VapourSynth (désentrelacement supérieur), stabilisation (vid.stab),
débruitage lent haute qualité (nlmeans/bm3d), masquage du bruit de tête en bas d'image,
encodage GPU, traitement par lots.

## Développement

```
pip install -r requirements-dev.txt
python -m pytest tests          # nécessite ffmpeg/ffprobe dans le PATH
python -m vhs_restore           # lance l'interface
```

Architecture : `tools.py` (détection et exécution des outils) · `probe.py` (analyse) ·
`profiles.py` · `pipeline.py` (filtres, aperçu, export) · `upscaler.py` (adaptateur IA) · `gui.py`.
Les choix techniques sont expliqués dans [`DECISIONS.md`](DECISIONS.md).

Licences des outils : FFmpeg (build gyan.dev, GPLv3), PySide6 (LGPLv3), Real-ESRGAN (BSD-3).
Les outils sont téléchargés sur votre poste ; si vous **redistribuez** un paquet qui les contient,
les obligations de la GPL s'appliquent (fournir les sources ou un lien vers celles-ci).
