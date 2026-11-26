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
- **Par parties** : `vhs_restore.reprise.restaurer` (constantes de production :
  parties de 10 min, seuil de 20 min, chauffe de 8 s). Un film de 3 min est
  sous le seuil de 20 min : le script force le découpage en trois parties de
  60 s (chauffe de production 8 s) pour mesurer le surcoût des raccords,
  attendu de quelques pourcents. Cette mesure attend R1.

Trois passages, on retient la **médiane**, en secondes d'horloge et en
secondes de calcul par minute de film.

## Fichiers produits

| Fichier | Contenu |
|---|---|
| `resultats-une-fois.json` / `.txt` / `.csv` | Mesure en une fois, les deux formats |
| `resultats-parties.json` / `.txt` / `.csv` | Mesure par parties (après R1) |
