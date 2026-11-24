# Prompt complet pour Claude

Cette branche `grok/montage` part de `grok/ergonomie` (`a26cfd9`), pas de la version n°64. Le rapprochement avec la n°64 est à faire de ton côté. Cette copie n'a pas encore : la barre de progression et « Arrêter » sous les boutons 1-2-3, la touche Entrée sur « C'est prêt », ni les protections fichiers inachevés / FAT32 / chemins trop longs. En rapprochant, fais profiter les morceaux du montage de ces protections.

Tu travailles dans le dépôt GitHub `ordiform69-png/1er-projet-`, branche `grok/montage`. PySide6, français, vouvoiement, utilisateur de 76 ans.

## Interdit

- Ne copie aucun code d'OpenShot, de LosslessCut ou de Clipchamp. Les deux premiers sont sous GPL, le troisième n'est pas libre. Le montage déjà présent a été écrit ici.
- Ne fais pas un banc de montage (pas de titres, pas de musique, pas de plusieurs films collés, pas de vignettes sur la barre).
- Ne change pas les filtres de restauration : débruitage, netteté, profils, désentrelacement, IA, poussières. Tu ne modifies pas leurs réglages.
- Ne lève pas le refus de l'IA, des poussières, de la réparation de bande, ni du re-cadencement dans `pipeline.export`. Chaque morceau est déjà encodé une fois puis assemblé avec `-c copy`. Réencoder l'assemblage est interdit.
- N'applique pas les coupes du film ouvert à tout un dossier : chaque cassette est différente.
- Pas de `deleteLater` sur les lignes de passages (le robot d'audit plante). Pas de nouvelle dépendance. Pas de commit.

## Déjà en place, ne pas le refaire

Page simple, cadre « Enlever une scène » dans `vhs_restore/gui.py` :

- `BarreFilm` : glisser pour se placer, triangle, repères de temps si la hauteur est au moins 80 px, carrés blancs tirables (`borde` / `_bord_bouge`). `sizeHint` 88 px, `minimumHeight` 56 (un test force `resize(400, 56)`).
- Bouton `self.s_couper`, texte « Couper ici », `objectName` « action ». Il appelle `_couper_ici` : premier clic = début du passage, le libellé contient alors « reprend », second clic = fin, puis le texte redevient « Couper ici ».
- Raccourcis « Enlever 10 secondes ici », « Enlever 30 secondes ici », « Enlever 1 minute ici » → `_passage_duree`.
- « Annuler la dernière coupe », liste « Remettre », huit passages maximum (`_MAX_COUPES`).
- Plus bas : « Le film commence à » / « Le film s'arrête à », « Tout garder », « Montrer ce début dans l'aperçu ».
- Encore visibles sur la page simple, sous « Autre façon, en deux temps » : `self.s_passage_deb` « Ce passage inutile commence ici » et `self.s_passage_fin` « Le film reprend ici ». Les mêmes existent dans les options avancées (`trim_passage_deb`, `trim_passage_fin`).
- Légende : « Bleu : ce qui sera restauré. Doré : ce qui est enlevé. »

Moteur, `vhs_restore/pipeline.py` :

- `passages_gardes(duree, debut, fin, coupes)` → intervalles absolus à garder. Fin à 0 = jusqu'au bout. Coupe ou morceau gardé de moins de 0,5 s ignoré. Tout coupé : `ToolError` « Il ne resterait plus rien du film. Laissez au moins un passage. »
- `export(..., passages=)` : si au moins deux intervalles, `_export_morceaux` restaure chaque morceau seul (les trous ne sont pas décodés) puis `_concat_sans_recompression`. Si IA, `dust`, `_tape_job` ou `retime`, `ToolError` : « Enlever un passage au milieu ne va pas avec cette option. Décochez l'amélioration IA, les poussières ou la réparation de bande, ou bien n'enlevez que le début et la fin. » Cette phrase ne nomme pas le re-cadencement.
- `restore_folder` appelle `export` sans `passages`, sans début et sans fin.

`_barre_cliquee` dit encore : « Vous êtes à … Pour enlever un passage : « Ce passage inutile commence ici », puis « Le film reprend ici ». »

`_phrase_passages` alimente `self.s_passages_note`. Elle ne prévient pas qu'une option cochée rendra la coupe impossible.

## À faire, dans cet ordre

### 1. Page simple : un seul geste

Cache `self.s_passage_deb`, `self.s_passage_fin` et le libellé « Autre façon, en deux temps » sur la page simple (`setVisible(False)`). Ne les détruis pas. Garde ces deux boutons visibles dans les options avancées.

Dans `_barre_cliquee`, remplace la phrase par : « Vous êtes à X. Cliquez sur « Couper ici », puis une seconde fois là où le film reprend. » Le statut doit toujours commencer par « Vous êtes à » (un test le vérifie).

Adapte `tests/test_passages_gui.py` pour qu'il ne dépende plus des anciens libellés visibles :

- `start_spin` à 10, clic sur « Couper ici », `start_spin` à 25, second clic sur le même bouton (son texte contient « reprend »).
- La coupe reste (10, 25). Un libellé commence par « De » et contient « 10 ».
- « Annuler la dernière coupe » vide `win._coupes`.
- Un clic « Couper ici » une seule fois, sans second clic, ne crée pas de coupe, change le statut, et le statut contient « commence ».
- Le clic au milieu de la barre (200, 28 sur une barre de 400×56) place `start_spin` vers la moitié et le statut contient « Vous êtes à ».

Ne casse pas `tests/test_barre_montage.py` : il exige les textes « Couper ici » et « reprend », un glisser qui place l'extrait, et un bord droit tiré d'au moins 5 secondes avec un statut contenant « ajusté » ou « restaur ».

### 2. Prévenir avant la restauration

Dans `_phrase_passages`, s'il y a au moins une coupe et que `passages_gardes` renvoie au moins deux intervalles, regarde `self.settings()` :

- `use_ai`, ou `dust`, ou (`source != "film"` et `tape_noise` ou `chroma_repair` ou `dropouts`), ou `retime(self.info, self.settings())` vrai.

Si c'est le cas, ajoute une phrase claire, vouvoiement, qui nomme l'option avec les mots affichés à l'écran, pas le mot technique. La case s'appelle « Cadence de tournage », pas « re-cadencement ». De même « Poussières et rayures », « Bruit de bande », « Couleur », « Décrochages », « Amélioration IA » (vérifie le libellé exact dans `gui.py` avant d'écrire la phrase). Exemple : « Cette coupe ne partira pas avec l'amélioration IA. Décochez-la, ou n'enlevez que le début et la fin. » Ne décoche rien. Ne lance pas d'export. La note reste en `wordWrap`.

Complète le message de `pipeline.export` pour citer aussi le re-cadencement, et aligne `ergonomie.expliquer` (branche « passage au milieu ») pour que la phrase claire le nomme. Le test `tests/test_montage.py::test_export_milieu_refuse_les_options` doit rester vert (`match="passage au milieu"`).

### 3. Le dossier ignore les coupes

Dans `restore_folder`, si `self._coupes` n'est pas vide, ne te contente pas de `self.status` : cette ligne est remplacée tout de suite par « Film 1 sur N ». Écris la phrase dans le texte du haut de la page (le bandeau ou la note déjà visible avant le travail) et répète-la dans le résumé « C'est prêt » (`_montrer_fini` / le texte passé à `_folder_done`). Phrase : « Les coupes de ce film ne seront pas appliquées aux autres fichiers du dossier. Chaque film part en entier. » Pas de fenêtre à fermer. N'envoie pas `passages` à `restore_folder`. Le dossier part comme aujourd'hui.

Test court, sans restauration réelle : une coupe posée, le texte du haut contient « ne seront pas appliquées ». Le résumé « C'est prêt » d'un dossier doit pouvoir contenir la même phrase (teste la fonction qui construit ce texte, sans ffmpeg).

### 4. Vérifier

```
cd /tmp/vhs/vhs-restore-ai
export LD_LIBRARY_PATH=/tmp/qtlibs/usr/lib/x86_64-linux-gnu
export PATH=/tmp/ffbin:$PATH
export QT_QPA_PLATFORM=offscreen
python -m pytest tests/test_barre_montage.py tests/test_coupe_un_clic.py tests/test_passages_gui.py tests/test_montage.py tests/test_ergonomie.py::test_texte_sans_defilement_horizontal -q --tb=short
```

Le défilement horizontal à 1093×600 et texte à 150 % doit rester à 0 : boutons empilés, `minimumWidth` 0, `wordWrap`, `QSizePolicy.Expanding`.

Ajoute trois lignes en fin de `DECISIONS.md` : boutons en double cachés sur la page simple, avertissement avant restauration, dossier qui ignore les coupes.

Termine par la liste des tests passés et ce qui a été laissé de côté (vignettes, levée du refus IA).
