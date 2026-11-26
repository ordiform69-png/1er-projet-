# N°13, étape 2 — lecteur et vérification d’une coupe

## Où

Branche `grok/lecteur`, partie de `gpt/timeline` au commit `f3d0237` (écran unique et
barre avec zoom, repères et vignettes). Dépôt `ordiform69-png/1er-projet-`.

| Commit GitHub | Contenu |
|---|---|
| `2e6ecf3` | Lecteur intégré et barre unique sous l’image |
| `476db49` | Aperçu du raccord image et son |
| `71d4661` | Géométrie, essais de lecture et vérification du paquet |

## Fait

- « Lire le film » ouvre l’original dans la zone image. « Pause » et « Reprendre »
  commandent la lecture. L’espace fait de même quand la barre est sélectionnée.
  L’horloge affiche le temps et la durée. La tête de lecture suit le film et un clic sur
  la barre déplace la lecture de l’original.
- « Voir l’avant / après » garde la comparaison d’images. « Lire la comparaison »
  affiche la vidéo côte à côte dans le même moniteur. « Image fixe » ramène les
  vignettes ou la comparaison fixe. Si Qt ne peut pas lire le fichier, l’application
  revient à ces images et explique comment se déplacer.
- Sur un DVD en plusieurs VOB, la navigation dans le film entier utilise les petites
  images. Le lecteur Qt ouvre les fichiers individuels. « Vérifier la coupe » utilise
  la liste concaténée de FFmpeg pour préparer son court extrait.
- Après une coupe, « Vérifier la coupe » lit jusqu’à trois secondes de chaque côté
  du raccord le plus proche du curseur. Pour un changement au début ou à la fin,
  il lit jusqu’à six secondes près de la borne gardée. L’extrait contient le son
  de la source lorsqu’il existe et se prépare en arrière-plan. Il reste temporaire.
- PyInstaller inclut Qt Multimedia et Qt Multimedia Widgets. La fabrication
  Windows vérifie la lecture d’un MPG de DVD, d’un AVI DV et d’un MKV dans l’exe.
  L’essai vérifie une image décodée avec la lecture en cours et la présence d’une
  piste audio, sans périphérique de son.

## Interdit respecté

- Aucune fusion ni pull request. Aucune dépendance Python ajoutée.
- Le moteur de restauration, ses filtres et ses réglages par défaut restent inchangés.
- L’original reste intact. La préparation du raccord conserve le rapport d’affichage,
  utilise les protections de chemin et de publication existantes, puis supprime le partiel.
- Aucun média, capture ou exécutable dans le dépôt.

## Vérifié

- Python 3.12.14 et PySide6 6.12.0 sous Linux.
- À 1280 × 641 et aux tailles de texte 100, 125 et 150 %, contrôle des widgets pendant la
  lecture et du parcours à l’arrêt. Le contrôle comprend la barre, l’horloge, le lecteur
  et « Lancer la restauration ». Contrôle des écrans standard, dont 1093 × 535.
- Le raccord d’essai joint une image rouge et un son de 440 Hz à une image bleue et un
  son de 660 Hz. L’image verte et le son de 880 Hz du passage retiré sont sautés. L’extrait
  de deux secondes conserve le 4:3. Le même test couvre un export sans piste audio.
- PyInstaller 6.22.3 sous Linux, vérification du paquet au code de sortie 0. Les deux
  modules Qt, leurs bibliothèques et le greffon FFmpeg sont présents. Les trois fichiers
  de synthèse fournissent une image décodée alors que la lecture a avancé de 0,20 à 0,24 s.
  Leurs pistes audio sont reconnues. L’essai passe avec FFmpeg 7.1.5 et FFmpeg 9.0.2.
- Les 28 tests ciblés (`test_lecteur.py`, `test_ecran_unique.py` et `test_ecrans.py`)
  passent en 190 s, code de sortie 0.
- La suite complète avec FFmpeg 9 est en cours. Le premier passage a rencontré un
  test d’estimation qui attend 3,4 Go libres sur le disque temporaire. Le même échec
  se reproduit sur `f3d0237` avec 2,3 Go libres. Le test isolé passe lorsque le dossier
  temporaire est placé sur un disque plus grand. La suite a été relancée dans ce dossier.

## Non testé

- Exécutable et sortie audio sur un PC Windows réel. La vérification est intégrée à la
  prochaine fabrication Windows de cette branche.
- Lecture d’un DVD en plusieurs VOB avec « Vérifier la coupe » sur un DVD physique.
