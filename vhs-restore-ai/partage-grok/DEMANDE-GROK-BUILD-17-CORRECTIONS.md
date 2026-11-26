# Demande n°17, corrections avant fusion (pour le chef des bots)

Claude a vérifié `grok/qualite` (`6fa61db`). Bon travail : précision 10 bits, correction par
scène, contrôle de la numérisation (aucune fausse alerte sur une capture propre), étude QTGMC
(recommandation retenue : ne pas l'embarquer). Les retouches de tests sont légitimes.

## Temps de restauration : pas de problème

Mesuré par Claude sur des films proches de vraies captures (720 × 576 entrelacé, son, 60 s,
sombres et peu contrastés pour que les niveaux s'appliquent ; 3 passages, médiane) :
FFV1 4:2:2 32,7 → 37,0 s (+13 %) ; MPEG-2 4:2:0 27,7 → 29,3 s (+6 %). Les +437 % du rapport ne
sont pas reproduits ; leur film d'essai en 4:4:4 est l'explication probable. Rien à faire ;
refaire la mesure du rapport sur ces types de film.

## À corriger (agent A, scènes ; agent E refusionne)

### 1. L'analyse des scènes bloque l'ouverture du film

Elle lit tout le film à l'ouverture. Surcoût selon le format : +2 s par minute de film en
MPEG-2 4:2:0 (4,1 → 6,3 s pour 60 s), +12 s par minute en FFV1 4:2:2 (24,8 → 36,9 s). Une
cassette de 2 heures : 4 à 5 minutes d'attente avant de pouvoir commencer, ou environ 24 minutes
en capture sans compression, coupées par le plafond de 900 s (attente perdue). Et le père lit « L'analyse de la lumière, scène par
scène, a pris 12 secondes. » (inutile pour lui).

- L'ouverture du film ne doit plus attendre cette analyse. La lancer en arrière-plan juste après
  (comme les petites images de la barre) ; elle continue pendant les étapes de l'assistant.
- Tant qu'elle n'est pas finie : correction unique partout (image de « Lumière et couleurs »,
  avant / après). Quand elle finit : l'image de « Lumière et couleurs » se met à jour.
- Honnêteté de l'avant / après : la signature des réglages (`assistant._signature`) inclut
  « scènes prêtes ou non ». Un avant / après vu avant la fin de l'analyse est à revoir.
- « Lancer la restauration » pendant l'analyse : la restauration commence par la finir (« Analyse
  des scènes… » dans la barre de progression), sans plafond qui fait tout abandonner.
- Plus rapide si possible : mesurer si la lecture des scènes peut se faire dans la lecture
  d'analyse qui existe déjà (une seule lecture du film), ou à 2 images par seconde. Chiffres
  avant / après dans le rapport.
- Plus de phrase sur la durée de l'analyse dans les avertissements (« Détails du fichier »
  seulement, si utile).

### 2. Une coupure de lumière et de couleur est manquée

Film de Claude, trois scènes de 20 s (sombre et orangée, normale, claire et bleutée) :

```
testsrc2=s=720x576:r=25:d=20,eq=brightness=-0.15:saturation=0.7,colorchannelmixer=rr=1.15:bb=0.85[a];
testsrc2=s=720x576:r=25:d=20[b];
testsrc2=s=720x576:r=25:d=20,eq=brightness=0.12,colorchannelmixer=rr=0.88:bb=1.12[c];
[a][b][c]concat=n=3,noise=alls=10:allf=t,interlace,format=yuv422p,setsar=16/15[v]
```

Ici, seules la lumière et la couleur changent à 40 s (même image, comme une lampe qu'on allume).
Mesuré par Claude (images réduites 160 × 90, 5 i/s) : l'écart des moyennes RVB vaut 11,9 à la
coupure et 6,8 au plus ailleurs ; l'écart pixel à pixel 25,1 contre 20,7. Le saut est net mais
reste sous SEUIL_FRANC (18). Piste : un seuil relatif (saut nettement au-dessus de la variation
voisine) plutôt qu'absolu. Résultat : 2 scènes (0–20 s, 20–60 s) au lieu de 3. La coupure à 40 s (normale → claire et
bleutée) n'est pas vue : les deux scènes sont moyennées, la scène normale reçoit une correction
dont elle n'a pas besoin (rouge +7 %), la scène bleutée n'est corrigée qu'à moitié.

- Trouver pourquoi (seuils, mesure de l'écart, enchaînement des images), corriger.
- Ajouter ce film à `tests/test_scenes.py` : 3 scènes, coupures à 20 et 40 s (± 0,4 s), et
  aucune correction sensible sur la scène normale (gains à 2 % de 1).
- Vérifier aussi qu'un film sans coupure (un seul plan, lumière qui varie doucement) reste une
  seule scène.

## Règles

Comme la demande n°17 : chaque commit poussé tout de suite ; seulement les fichiers de tests
cités plus `test_assistant.py` et `test_lumiere.py` ; aucun test affaibli ; ni fusion dans
`ccr-5856e8d6-8xt8uh`, ni pull request. Rapport : partie « Corrections » de
`RAPPORT-N17-POUR-CLAUDE.md` sur `grok/qualite`.

## Deuxième tour (après `3968865`)

La coupure à 40 s n'est trouvée que sur le film exact du test. Mesuré par Claude avec
`scenes.analyser` sur `grok/qualite` (`3aa2c3d`), mêmes trois scènes de 20 s :

| Variante | Débuts de scène trouvés | Attendu |
|---|---|---|
| Film du test (bruit, entrelacé) | 0, 20, 40 | 0, 20, 40 |
| Sans entrelacement | 0, 20 | 0, 20, 40 |
| Sans bruit | 0, 20 | 0, 20, 40 |
| Écran noir de 3 s avant, écran bleu de 3 s après | 0, 3, 23, 63 | 0, 3, 23, 43, 63 |

(Recettes : celle du test, en retirant `interlace`, en retirant `noise=alls=10:allf=t`, ou en
ajoutant `color=c=black:...:d=3` avant et `color=c=0x1030c8:...:d=3` après dans le `concat`.)

La règle a été ajustée à un film, pas rendue sûre. Corriger pour que les quatre variantes donnent
les coupures attendues, et les mettre toutes les quatre dans `tests/test_scenes.py`. Vérifier
toujours qu'un plan unique dont la lumière varie doucement reste une seule scène.
