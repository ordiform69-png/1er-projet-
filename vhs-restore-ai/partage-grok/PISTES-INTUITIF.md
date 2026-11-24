# Pistes pour la suite

## Déjà en place

- La barre (`BarreFilm`) est dessinée dans l’application. Un clic ou un glisser place l’extrait. Le doré marque ce qui ne sera pas restauré. Les flèches déplacent d’une seconde.
- « Couper ici » ouvre le passage ; le même bouton, devenu « Le film reprend ici », le ferme. Les deux boutons « Ce passage inutile commence ici » et « Le film reprend ici » sont encore affichés en dessous, sur la page simple comme dans les options avancées. Un clic sur la barre cite encore ces deux anciens libellés.
- Trois raccourcis enlèvent d’un coup 10 secondes, 30 secondes ou 1 minute à partir du curseur.
- Les bords dorés (petit carré blanc) se tirent. Rien n’est fusionné tant que le bouton de la souris reste enfoncé.
- Seuls les morceaux gardés sont restaurés (`passages_gardes`, puis un export par morceau). Une coupe ou un morceau de moins d’une demi-seconde est ignoré. Huit passages au plus. Les trous ne sont pas traités.
- L’assemblage se fait sans seconde compression (`-c copy`). Chaque morceau n’a donc été compressé qu’une fois.
- Ce chemin est refusé si l’amélioration IA, les poussières, la réparation de bande (bruit, couleur ou décrochages) ou le re-cadencement de la pellicule est actif. La phrase affichée ne nomme pas le re-cadencement.
- « Restaurer tout un dossier » n’envoie ni ces coupes, ni le début, ni la fin : chaque fichier part en entier.

## À ne pas faire

- Copier le code d’OpenShot, LosslessCut ou Clipchamp (GPL ou propriétaire).
- Un vrai banc de montage (titres, musique, plusieurs films).

## Pistes classées

### 1. Cacher les boutons en double sur la page simple — priorité haute

Masquez « Ce passage inutile commence ici » et « Le film reprend ici » sur la page simple. « Couper ici » appelle déjà les mêmes actions. Gardez les raccourcis 10 / 30 / 60, « Annuler la dernière coupe », « Remettre », et les temps de début et de fin. Alignez le message du clic sur la barre.

Moins de boutons qui ont l’air de faire la même chose : la personne de 76 ans hésite moins sur lequel appuyer.

Risque faible si la phrase sous la barre reste. Les deux boutons peuvent demeurer dans les options avancées.

### 2. Dire l’incompatibilité avant « Restaurer »

Si au moins deux morceaux sont gardés et qu’une option refusée est cochée, écrivez-le dans la note, avant le lancement. Aujourd’hui le refus part seulement dans `export()`, donc après le clic, et la phrase omet le re-cadencement.

Elle ne prend pas une erreur tardive pour une panne, et elle sait quoi décocher.

Risque : la note s’allonge. Ne décochez rien à sa place. Ce n’est pas prioritaire pour le temps de calcul.

### 3. Vignettes sur la barre

`BarreFilm` ne dessine que la piste, le doré et le curseur. Quelques images le long de la barre montreraient la scène à l’endroit choisi.

Voir la neige ou un visage évite de deviner une heure, ce qui est plus clair qu’un curseur seul.

Risque : extraire des images prend du temps et de la place, et la barre est basse. Aucun gain sur la restauration. Ne reprenez pas de code extérieur. Pas prioritaire.

### 4. Prévenir que le dossier ignore les coupes

Au clic sur « Restaurer tout un dossier », dites que les coupes du film affiché ne sont pas reprises. `restore_folder` appelle `export` sans passages, sans début et sans fin.

Elle ne croira pas que la neige enlevée sur une cassette l’est pour toutes les autres.

Risque si vous appliquez les mêmes secondes à tout le dossier : chaque film est différent, de mauvaises scènes partiraient. Ne le faites pas.

### 5. Lever le blocage IA seulement après un essai concluant

Ne retirez pas le refus de `export()` tant qu’un film court n’a pas prouvé que des morceaux encodés à part s’assemblent encore avec `-c copy`, sans seconde compression. L’IA est relancée une fois par morceau. Laissez le blocage pour les poussières, la bande et le re-cadencement. `filtres_passages` n’est pas utilisé à l’export : il filtre avant de couper, donc il traiterait les trous.

Si l’essai est bon, enlever la moitié d’une cassette éviterait l’IA sur ce qui est jeté. Aujourd’hui il faut choisir entre les deux.

Risque sinon : jointures illisibles ou saccadées. Réencoder l’assemblage pour « réparer » casserait la règle d’une seule compression. Pas prioritaire tant que l’essai n’est pas fait.
