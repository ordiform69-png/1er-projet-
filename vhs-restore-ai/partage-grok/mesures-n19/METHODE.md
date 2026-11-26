# Méthode de mesure — demande n°19 (reprise d'une restauration)

Script : `mesurer.py`. Aucune dépendance nouvelle, aucun changement du moteur
ni des tests. Les films de synthèse sont régénérés à chaque fabrication, hors
dépôt (`--films-dir`, par défaut `/tmp/mesures-n19/films`). Aucune vidéo,
capture ou archive n'est versionnée.

```bash
python3 vhs-restore-ai/partage-grok/mesures-n19/mesurer.py --fabriquer
python3 vhs-restore-ai/partage-grok/mesures-n19/mesurer.py --mode une-fois
# après fusion de R1 :
python3 vhs-restore-ai/partage-grok/mesures-n19/mesurer.py --mode parties
```

Le modèle suit `mesures-n17/mesurer_temps_claude.py` (horloge autour de
`pipeline.export`, 3 passages, médiane, mêmes familles de fichiers).

## Films

Deux fichiers, **3 minutes** chacun, 720 × 576, entrelacé TFF, avec son :

| Clé | Encodage |
|---|---|
| `ffv1_422` | FFV1, `yuv422p`, PCM |
| `mpeg2_420` | MPEG-2, `yuv420p`, `+ilme+ildct`, 8 Mbit/s, PCM |

Recette lavfi figée :

```
testsrc2=size=720x576:rate=50,tinterlace=mode=interleave_top,setfield=tff,setsar=16/15
sine=frequency=440:sample_rate=48000
-t 180
```

## Restauration mesurée

Profil Équilibré, `preset=medium`, crf=18, résolution source, son restauré,
désentrelacement bwdif (scan détecté : TFF), pas d'IA ni de stabilisation ni
de réparation de bande. Horloge : `time.perf_counter` autour de l'export
seulement (`analyze` est noté à part).

- **Une fois** : `pipeline.export` tel qu'il existe aujourd'hui (chemin unique).
  Cette mesure peut tourner avant R1.
- **Par parties** : `pipeline.export` après R1 (constantes forcées : parties
  de 60 s, seuil 1 s, chauffe de production 8 s). Un film de 3 min est sous
  le seuil de production (20 min) : sans ce forçage, l'export resterait en
  une fois. Le surcoût des raccords est attendu de quelques pourcents.

Trois passages, on retient la **médiane**, en secondes d'horloge et en
secondes de calcul par minute de film.

## Fichiers produits

| Fichier | Contenu |
|---|---|
| `resultats-une-fois.json` / `.txt` / `.csv` | Mesure en une fois, les deux formats |
| `resultats-parties.json` / `.txt` / `.csv` | Mesure par parties (après R1) |
| `resultats-production-une-fois.json` / `.txt` / `.csv` | 25 min, constantes de production, une fois |
| `resultats-production-parties.json` / `.txt` / `.csv` | 25 min, constantes de production, par parties |

## Mesure de production (25 min, parties de 10 min)

Demandée avant fusion (agent R3, relance a/b/c). Un film de 3 min est sous
le seuil de production (20 min) et ne peut pas mesurer le surcoût réel des
raccords de 10 minutes. On fabrique donc un film de **25 minutes**
(1500 s) : 10 + 10 + 5 min. Justification : 21 min donnerait un reste
d'1 min (toujours > chauffe de 8 s, donc une 3ᵉ partie à part), trop
court pour représenter un reliquat typique ; 25 min laisse un reliquat
de 5 min, au-dessus du seuil (20 min), sans rallonger démesurément
l'horloge. Hors dépôt, mêmes recettes lavfi, 720×576 TFF, son PCM,
FFV1 4:2:2 et MPEG-2 4:2:0.

```bash
python3 vhs-restore-ai/partage-grok/mesures-n19/mesurer.py \
  --fabriquer --duree 1500 --films-dir /tmp/mesures-n19/films-1500s
python3 vhs-restore-ai/partage-grok/mesures-n19/mesurer.py \
  --mode une-fois --duree 1500 --production --etiquette production --runs 2 \
  --films-dir /tmp/mesures-n19/films-1500s --workdir /tmp/mesures-n19/work-1500s
python3 vhs-restore-ai/partage-grok/mesures-n19/mesurer.py \
  --mode parties --duree 1500 --production --etiquette production --runs 2 \
  --films-dir /tmp/mesures-n19/films-1500s --workdir /tmp/mesures-n19/work-1500s
```

`--production` ne force pas `DUREE_PARTIE` / `SEUIL` / `CHAUFFE` : on
prend les constantes du moteur (600 / 1200 / 8). Le film de 1500 s est
au-dessus du seuil, donc `pipeline.export` découpe tout seul. Après un
export réussi, le dossier de parties est effacé (`reprise.supprimer`) :
chaque passage repart de zéro.

Nombre de passages : idéalement 2 ou 3. Un seul passage par mode est
admis si 3 dépasse le raisonnable (un export de 25 min dure plusieurs
minutes) ; le rapport le dit alors. Médiane : `statistics.median`
(moyenne des deux valeurs centrales s'il y a un nombre pair de passages).

Surveillance : un fil échantillonne toutes les 5 s `MemAvailable` et
l'espace libre de `/`, `/tmp`, `/workspace` et des dossiers de travail.
Les minima sont écrits dans le JSON/TXT.

Les anciens fichiers `resultats-une-fois.*` et `resultats-parties.*`
(film de 3 min, parties forcées à 60 s) restent la série officielle
courte ; ils ne sont pas écrasés.
