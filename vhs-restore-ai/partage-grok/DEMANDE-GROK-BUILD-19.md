# Demande n°19 : reprendre une restauration interrompue (pour le chef des bots)

Une cassette demande plusieurs heures de restauration. Aujourd'hui, un redémarrage de Windows
Update la nuit, une coupure de courant, la fenêtre fermée ou « Arrêter » par erreur font tout
perdre. But : la relance repart de là où elle s'était arrêtée, sans couture visible ni audible.

## Base, branches, équipe

- Base : `grok/qualite` au commit `3aa2c3d` (la n°17, qui va être fusionnée ; la correction par
  scène et le 10 bits sont dedans).

| Agent | Rôle | Branche | Fichiers à lui |
|---|---|---|---|
| R1 | Moteur : découpage, raccords, parties gardées, reprise | `grok/reprise-moteur` | nouveau `reprise.py`, `pipeline.py` (seulement `export`, `_export`, `_export_morceaux` et leurs aides) |
| R2 | Interface : annoncer la reprise, message à l'arrêt | `grok/reprise-ecran` | `gui.py`, `assistant.py`, `ergonomie.py` (textes) |
| R3 | Intégration, mesures, rapport | `grok/reprise` | fusion R1 puis R2, `tests/test_reprise.py` complété, rapport |

## Choix déjà faits (ne pas rediscuter)

- **Par parties de 10 minutes** du film, restaurées avec la machinerie qui existe déjà pour les
  passages gardés (`_export(..., morceau=True, start=..., duration=...)`), puis assemblées sans
  recompression (`_concat_sans_recompression`).
- **Seulement quand c'est sûr** : film gardé de 20 minutes ou plus, sans IA, sans poussières ni
  réparation de bande, sans changement de cadence, sans stabilisation (sa détection porte sur
  tout le film). Sinon : restauration en une fois, exactement comme aujourd'hui.
- **Raccords invisibles** : chaque partie commence 8 s plus tôt (image ET son), puis ces 8 s sont
  retirées. Les filtres qui regardent les images voisines (débruitage, désentrelacement,
  scintillement) et ceux du son qui ont une mémoire (normalisation, débruitage, RNNoise) sont
  ainsi déjà lancés au raccord. Constantes réglables dans `reprise.py`.
- **Parties gardées** dans `%LOCALAPPDATA%\VHSRestoreAI\reprise\<clé>` (Linux :
  `~/.local/share/...`), jamais dans le dossier de la cassette. Clé = empreinte de : chemin, taille
  et date du fichier source, signature des réglages (scènes comprises), passages gardés, longueur
  des parties, chauffe, version du format.
- **Une partie compte comme faite** seulement si elle est complète : écrite sous un nom
  provisoire, renommée à la fin, puis un fichier témoin avec sa durée attendue. À la reprise, chaque
  partie faite est vérifiée (ffprobe : durée à une image près, image et son présents) ; douteuse,
  elle est refaite.
- **Reprise automatique** au lancement si des parties existent pour la même clé. Réglages changés :
  autre clé, on repart de zéro et l'ancien dossier est effacé.
- **Ménage** : dossier effacé après une restauration réussie ; dossiers de plus de 30 jours effacés ;
  place disque vérifiée (parties + résultat) avant de commencer.
- `estimation.py` : NE PAS toucher.

## Pièges connus

- **Le temps des scènes.** La correction par scène suit le temps de la SOURCE (`scenes.filtres`,
  paramètre `origine`). Une partie qui commence 8 s plus tôt doit garder la bonne correction de
  chaque côté du raccord.
- **Le son** : décalage et dérive (`_tempo_factor`, `audio_offset_ms`) déjà gérés par morceau ; la
  chauffe se compte en temps source pour le son (vitesse de dérive), et `apad` / `atrim` gardent
  la durée exacte (voir les commentaires FFmpeg 9.1 dans `_export`).
- **Le nombre d'images** de chaque partie est imposé (`-frames:v`) ; aucune image perdue ni doublée
  aux raccords.
- **DVD en plusieurs morceaux** et passages enlevés au milieu : les parties de 10 minutes se font
  à l'intérieur des passages gardés.
- **AAC** toujours par `tools.AAC`.

## Interface (R2)

- À l'ouverture d'un film dont une restauration s'est arrêtée : « Une restauration de ce film
  s'était arrêtée à 45 %. « Lancer la restauration » la reprendra. » (ligne d'état, et résumé de
  « Vérifier et lancer »).
- Pendant : « Reprise : 6 parties sur 12 déjà faites. » puis la progression habituelle.
- Après « Arrêter » ou une erreur : « Arrêté. Les parties déjà restaurées sont gardées : relancez
  pour reprendre. »
- Vouvoiement, mots simples, aucun mot technique (« partie », pas « morceau » ni « chunk »).

## Tests attendus (nouveau `tests/test_reprise.py`, constantes raccourcies : parties de 20 s,
seuil 30 s, chauffe 3 s ; film de synthèse de 80 s, deux scènes, mouvement, son avec bips)

1. Découpage : passages → parties de 20 s au plus, la dernière trop courte rejoint la précédente,
   coupes au milieu respectées.
2. Même résultat qu'en une fois : même nombre d'images, durée du son = durée de l'image (20 ms
   près), bips toujours calés sur les mêmes images, aux raccords écart moyen d'image < 2/255 avec
   la restauration en une fois, aucun claquement (saut d'échantillon) aux raccords.
3. Interruption : arrêt après la 2e partie → 2 parties gardées ; relance → seules les autres sont
   restaurées ; résultat complet ; dossier effacé.
4. Partie à moitié écrite ou abîmée : refaite, jamais réutilisée.
5. Réglages changés : on repart de zéro, ancien dossier effacé.
6. Non concernés (IA, stabilisation, film court) : une seule fois, aucun dossier créé.
7. Scènes : correction identique de part et d'autre d'un raccord à l'intérieur d'une scène.
8. Interface : message d'ouverture, message d'arrêt.
Plus : `test_pipeline.py`, `test_scenes.py`, `test_passages_gui.py`, `test_arret_travail.py`,
`test_vides_montage.py`, `test_assistant.py`, `test_estimation.py`.

## Mesures (R3)

Temps d'une restauration de 3 minutes de film en une fois et par parties (raccords : surcoût
attendu de quelques %), sur un film 720 × 576 entrelacé avec son (4:2:2 FFV1 et 4:2:0 MPEG-2).

## Règles

Chaque commit poussé tout de suite. Pas la suite complète (seulement les fichiers cités). Aucun
test affaibli. Aucune nouvelle dépendance. Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request.
Sans bac à sable : pousser le code, écrire « non testé », Claude mesure à la livraison.
Rapport : `partage-grok/RAPPORT-N19-POUR-CLAUDE.md` sur `grok/reprise`.
