# VHS Restore AI

Application Windows gratuite et locale pour restaurer des films familiaux numérisés des années
1970 à 1995 : cassettes vidéo (VHS, VHS-C, Video8, Hi8, Betamax…), pellicules scannées (Super 8,
8 mm, 16 mm, 9,5 mm) et pellicules copiées sur vidéo. Elle désentrelace, réduit le bruit, corrige
couleurs et netteté, exporte en Full HD, et propose en option la stabilisation et l'agrandissement IA. Elle sert d'**orchestrateur** : FFmpeg fait le travail, et
Real-ESRGAN intervient si vous l'installez. Aucun cloud, aucun abonnement.

## Installation (Windows 10/11)

**Le plus simple : l'application prête à l'emploi.** Dans l'onglet « Actions » du dépôt GitHub,
ouvrez la dernière exécution réussie de « VHS Restore AI (Windows) » et téléchargez l'artefact
`VHSRestoreAI-Windows` (environ 130 Mo, conservé 90 jours). Décompressez-le et lancez
`VHSRestoreAI.exe` : FFmpeg est inclus, il n'y a rien d'autre à installer. Le mode d'emploi est
dans `LISEZMOI.txt`. Le téléchargement d'un artefact demande d'être connecté à GitHub.

**Pour développer** (ou ajouter les options QTGMC et IA) :

1. Installez [Python 3.10 ou plus](https://www.python.org/downloads/) en cochant « Add python.exe to PATH ».
2. Double-cliquez sur **`installer.bat`**. Il crée un environnement isolé `.venv`, installe
   PySide6 et télécharge FFmpeg (somme SHA-256 vérifiée) dans `tools\ffmpeg`.
   - Option IA : lancez `installer.bat -AvecIA` dans une invite de commandes. Le script ajoute
     Real-ESRGAN dans `tools\realesrgan` (il faut une carte graphique compatible Vulkan).
   - Option QTGMC (meilleur désentrelacement) : lancez `installer.bat -AvecQTGMC`. Il faut
     **Python 3.12 ou plus**. Le script installe VapourSynth et les plugins par pip dans `.venv`.
   - Option poussières et rayures (pellicules) : `installer.bat -AvecPoussieres` installe le
     moteur Analog Repair (licence MIT, version figée). Il est déjà inclus dans l'application prête
     à l'emploi.
     Les options se combinent : `installer.bat -AvecIA -AvecQTGMC -AvecPoussieres`.
3. Double-cliquez sur **`lancer.bat`**.

Vous avez déjà FFmpeg ? Il suffit qu'il soit dans le PATH, ou dans les variables `VHSRA_FFMPEG`,
`VHSRA_FFPROBE`, `VHSRA_REALESRGAN` et `VHSRA_VSPIPE`. Les journaux se trouvent dans `%LOCALAPPDATA%\VHSRestoreAI\logs`.

## Utilisation

**Mode simple** (écran d'accueil) : « 1. Choisir le film » → « 2. Voir l'avant / après » →
« 3. Restaurer le film ». Les réglages sont automatiques : origine suggérée par l'analyse et profil
Équilibré. Le film restauré est enregistré à côté de l'original. « Restaurer tous les films d'un
dossier… » traite d'un coup toutes les vidéos d'un dossier et les range dans un sous-dossier
« Films restaurés ». Un fichier illisible est signalé sans interrompre les autres.

Si l'analyse détecte un défaut du son (un seul côté enregistré, côtés en opposition de phase, son
saturé, ronflement électrique), elle l'explique en une phrase sous la description du film et propose
une case « Appliquer ces conseils », décochée par défaut.

**Options avancées** (lien en bas à droite) : tous les réglages ci-dessous.

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

## Son

Case « Restaurer le son », cochée par défaut. Le profil choisi s'applique aussi à la piste :

| | Fidèle | Équilibré | Maximum |
|---|---|---|---|
| Souffle | très léger | modéré | plus marqué, ou DeepFilterNet |
| Clics | non | oui | oui |
| Écarts de volume | non | oui, gain limité | oui, gain limité |

Une piste absente ou vide n'est pas remplacée. Le mono reste mono. Les rires, la musique et
les bruits de la pièce ne sont pas isolés pour être supprimés.

Dans les options avancées :

- **Décalage** (ms) : le son est en avance ou en retard d'une valeur fixe.
- **Dérive** (ms par minute) : le décalage s'aggrave. Exemple : +100 ms/min = 1 seconde de
  retard au bout de 10 minutes. La hauteur des voix est conservée. Rien n'est corrigé tout
  seul : l'analyse peut seulement signaler un écart déjà écrit dans le fichier.
- **Ronflement** 50 Hz (Europe) ou 60 Hz, encoche étroite, désactivé par défaut.
- **Vent et grondements** : passe-haut doux à 80 Hz, désactivé par défaut. L'analyse le
  conseille seulement si les graves sont forts et irréguliers. Les voix restent.
- **Voix plus claires** : présence de +3 dB vers 3 kHz, désactivé par défaut.
- **Copie WAV ou FLAC** du son restauré, à côté du film.
- Après un aperçu : « Écouter l'original » et « Écouter le son restauré ».

- **Souffle de la voix (RNNoise)** : désactivé par défaut. Cochez-le pour remplacer le
  souffle FFmpeg d'Équilibré et de Maximum par le modèle Xiph inclus (35 % ou 55 % du
  signal nettoyé, le reste de la pièce reste). Fidèle n'est pas concerné.

DeepFilterNet est facultatif, profil Maximum seulement. `installer.bat -AvecSon` télécharge
le binaire officiel 0.5.6 dans `tools\deepfilter\`
([dépôt](https://github.com/Rikorose/DeepFilterNet), licence libre). L'atténuation est
plafonnée à 12 dB pour garder l'ambiance. Sans lui, Maximum garde le souffle FFmpeg du profil.
RNNoise ne se substitue pas tout seul.

## Couleur

Dans les options avancées, case **Dominante de couleur**, décochée. Si vous la cochez, ou si
l'analyse la conseille (une teinte forte couvre tout le film) et que vous appliquez les conseils,
trois gains fixes rééquilibrent le rouge, le vert et le bleu, une seule fois pour tout le film.
Un noir et blanc reste gris. Une image pâle n'est pas ravivée.

## Bande VHS (Analog Repair)

Dans les options avancées, pour une cassette seulement, trois cases désactivées par défaut.
Même module que les poussières (`installer.bat -AvecPoussieres`, licence MIT) :

- bruit de bande : poursuite, lignes qui ondulent, bande déchirée du bas ;
- couleur des décrochages : arcs-en-ciel et couleur perdue, sans toucher à la lumière ;
- taches présentes sur une seule image.

Le tampon date n'est pas effacé. Le grain n'est pas lissé. Une pellicule garde seulement
« poussières et rayures ».

## DVD (plusieurs fichiers VOB)

Un film sur DVD (`VIDEO_TS\VTS_01_1.VOB`, `VTS_01_2.VOB`…) est restauré en **un seul fichier**
par titre. Les menus ne sont pas traités. Le disque n'est pas modifié : s'il est protégé en
écriture, le résultat va dans `Vidéos\Films restaurés`.

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

**Testé sur deux vraies archives libres de droits** (film amateur couleur des années 1970 scanné
à 18 i/s, VOB d'un caméscope VHS de 1988, voir DECISIONS.md) : analyse correcte après deux
corrections (couleur décolorée, piste son vide), aperçu réaligné. Jugement visuel seulement sur
ces deux extraits.

**Non testé** : de vraies pellicules ou de vrais transferts (rayures, poussières, décoloration,
scintillement réels) ; usage interactif sur un vrai PC Windows (la suite de tests et l'autotest de
l'application fabriquée passent sur la machine Windows de GitHub Actions, avec FFmpeg 9.0.2, mais
personne n'a encore cliqué dans l'interface sous Windows) ; `installer.bat`/`lancer.bat` et QTGMC
sous Windows ; l'indexation BestSource sur un long film ;
le vrai Real-ESRGAN (pas de GPU ici) ; de vraies cassettes numérisées (aucun échantillon fourni,
donc aucune évaluation visuelle réelle) ; la détection BFF sur du contenu réel ; de longs films.

Poussières et rayures (option pellicule, Analog Repair) : poussières supprimées, objets rapides
clairs ou sombres intacts sur un film de synthèse ; grain conservé à 97 % sur une vraie pellicule.

**Prévu ensuite** : suppression optionnelle des images répétées d'un transfert, masquage du
bruit de tête en bas d'image, encodage GPU.

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
