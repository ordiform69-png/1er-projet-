# Parcours senior — vague 1 (analyse, sans code)

Fenêtre utile : 1280×641 (1920×1080 à 150 %) et 1366×768, texte 100 % et 150 %, thèmes sombre et clair.
Hauteurs déduites des minimums de `gui.py` (`_build_simple`, `CompareView`, `TempsSpin`, `_montrer_apercu`). Pas de capture dans le dépôt.
Il veut : choisir, voir si c'est mieux, lancer, retrouver le résultat. Il ne lit pas les infobulles. Un mot technique l'arrête. Il a peur de casser le film.

## Parcours

### Restaurer un film
- Accueil. Il voit le bandeau, la phrase du haut (« bouton 1 »), les trois étapes (la 1 est encadrée) et, juste dessous, le cadre « Enlever une scène ». Il comprend qu'il faut commencer par « 1. Choisir le film ou la photo ». Il hésite : « Couper ici » est doré et actif (`#action`, comme « Regarder le film ») alors que « 3. Restaurer » est encore éteint. Un clic avant un film n'écrit que dans la ligne d'état, au-dessus du cadre — s'il a un peu défilé, rien ne bouge à l'écran.
- Film choisi. La phrase du haut et « 2. Voir l'avant / après » sont clairs. La case « Corriger aussi ces défauts, avec prudence » est cochée, avec un « ? » (pas seulement une infobulle) : il peut la laisser. À 150 %, le résumé du fichier pousse « 3. Restaurer » et la phrase « jamais modifié » sous le bord des 641 px.
- Aperçu. L'image (hauteur ≈ fenêtre − 150, au moins 240) et « Original » / « Comparer les deux » / « Restauré » arrivent à l'écran. Il voit la différence. Il ne voit plus « 3. Restaurer » : le cadre de coupe (barre, cinq boutons, deux temps) est entre les étapes et l'image. Le bouton visible qui ressemble au lancement s'appelle « Restauré » et ne lance rien. « Écouter le son restauré » est sous l'image, souvent hors écran. La consigne « bouton 3 » est dans la ligne d'état, au-dessus du cadre.
- Travail. Barre, temps restant et « Arrêter » sont ramenés sous les étapes. La phrase « Vous pouvez utiliser l'ordinateur ou le laisser travailler » est à l'écran. Il comprend qu'il faut attendre.
- « C'est prêt ». Titre, « Regarder le film », « Ouvrir le dossier », « Restaurer un autre film ». À 100 % il retrouve le résultat sans défiler. Entrée ouvre le film. À 150 % les trois boutons s'empilent encore dans la fenêtre ; le chemin du fichier, plus bas, n'est pas indispensable.

### Une photo
Le cadre « Enlever une scène » disparaît. Le même trou reste après l'aperçu : « Restaurer » au-dessus, image trop haute. Noir et blanc : « Coloriser aussi (IA) », la note « couleurs inventées » est écrite (pas seulement en infobulle) et le « ? » ouvre une boîte. « C'est prêt » dit « Voir la photo ». Parcours plus court, même hésitation au lancement.

### Un dossier
« Restaurer tout un dossier (films et photos)… » est sous l'aperçu vide (déjà ≈ fenêtre − 150) et sous le cadre de coupe. À 641 px il est à plus de deux écrans ; rien en haut ne le nomme (l'aide non plus). Il ne le trouve pas. S'il dépose un dossier, la question est claire. « C'est prêt » cache « Regarder » et donne « Ouvrir le dossier » : le résumé se comprend. Entrée ne fait rien (le bouton regarder est caché).

### Enlever une scène
Le cadre est un petit banc de montage sur la page simple, ouvert avant toute demande. Il voit une barre, « Couper ici », « Enlever 10 / 30 secondes / 1 minute », « Le film commence à », « Le film s'arrête à ». Il ne comprend pas qu'il peut tout ignorer. Il a peur : « L'original n'est pas modifié » est sous les deux temps, pas à côté du bouton doré. La molette, en défilant pour rejoindre l'aperçu, change ces temps sans focus (Qt 6.12, `TempsSpin` n'ignore pas la molette) : la copie est coupée sans qu'il l'ait demandé. Les carrés blancs font 12 px : il ne peut pas les tirer. « Couper ici » deux fois est le seul geste lisible, et la confirmation part dans la ligne d'état hors écran.

### Retirer les passages vides
Sur « C'est prêt », le bouton ne dit pas (hors infobulle) que c'est une copie. Le clic ouvre une liste puis « Créer la copie » / « Garder le film tel quel » : là, il comprend, et l'original est nommé. S'il n'y a rien, la boîte le dit. Ce n'est pas le blocage.

### Arrêter puis reprendre
« Arrêter » demande confirmation si le travail dure : « le travail déjà fait sur ce film sera perdu », « Oui, arrêter » / « Non, continuer ». Il comprend qu'il n'y a pas de reprise. Après l'arrêt, ce qu'il a sous les yeux est « Opération annulée. Fichiers temporaires supprimés. » Il croit que ses films ont été effacés. « Rien n'a été modifié » est dans le bandeau, souvent au-dessus de l'écran. Rien ne lui dit de recliquer « Restaurer ».

### Comprendre une erreur
La boîte dit ce qui s'est passé et quoi faire ; le technique est derrière « Détails pour l'aide ». Le bandeau dit « Cela n'a pas abouti » et l'étape suivante. Ce parcours-là tient. Il s'arrête seulement si la boîte cite un autre logiciel ou un chemin (montage, installation).

## Tâches
- G4 | Le cadre « Enlever une scène » reste ouvert sur la page simple | vhs_restore/gui.py | Entre les étapes 1-2-3 et l'aperçu, barre, « Couper ici » doré et actif avant un film, cinq boutons et deux temps ; à 641 px il cache « Restaurer » et il croit que « Couper ici » découpe l'original | Ne montrer ce cadre qu'après un film, replié derrière un seul bouton « Enlever une scène… », et écrire « L'original n'est pas modifié » à côté de ce bouton.
- G4 | Après l'aperçu, « Restaurer » n'est plus à l'écran | vhs_restore/gui.py | L'image fait environ la hauteur de la fenêtre moins 150 px : « 3. Restaurer » et « Écouter le son restauré » sortent, et le bouton visible « Restauré » ne lance rien | Laisser dans la même vue l'image, « Original », « Voir le restauré », « Écouter le son restauré » et un bouton « 3. Restaurer ».
- G4 | La molette change « Le film commence à » et « Le film s'arrête à » | vhs_restore/gui.py | Pour rejoindre l'aperçu il défile sur ces champs : Qt 6.12 accepte la molette sans focus, la copie est coupée sans qu'il l'ait demandé | Ignorer la molette tant que le champ n'a pas le focus, pour qu'elle ne fasse que défiler la page.
- G4 | « Restaurer tout un dossier » est hors de portée | vhs_restore/gui.py | Le bouton est sous le cadre de coupe et sous l'aperçu vide déjà presque aussi haut que la fenêtre : à 641 px il ne le voit pas et rien en haut ne le nomme | Le placer sous les trois étapes, et ne donner à l'aperçu sa grande hauteur qu'une fois l'image prête.
- G3 | « Arrêter » dit « Fichiers temporaires supprimés » | vhs_restore/gui.py | Il croit ses films effacés, et rien sous ses yeux ne dit de recliquer « Restaurer » (il n'y a pas de reprise) | Remplacer par « Arrêté. Votre film n'a pas été modifié. Pour recommencer, cliquez sur « Restaurer ». »
- G3 | « Faire un montage » quitte le logiciel | vhs_restore/gui.py | Sur « C'est prêt », la boîte cite LosslessCut et Shotcut et dit que le film peut changer s'il enregistre : un nom technique ou un autre logiciel l'arrête | Garder un seul choix « Couper ou assembler », avec la phrase « une copie est créée, votre film n'est pas modifié », sans nom de logiciel ; laisser « Montage complet » dans les options avancées.
