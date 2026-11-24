# Windows — timeline (note du chef)

Les bots n'ont pas pu être lancés. Le chef a tenu ce rôle.

- `-ss` avant `-i`, `creationflags=_NO_WINDOW`, liste d'arguments, pas de shell.
- Fil `_FilImages` / `_FilMoment`, jamais `self.worker` : « Restaurer » et l'aperçu restent libres.
- Dossier `tempfile.mkdtemp(prefix="vhsrestore_vignettes_")`, donc sur le disque local même si le film
  est sur une clé ou un chemin `\\serveur\`. Effacé après l'arrêt du fil, au changement de film et à la fermeture.
- DVD : `dvd.input_args` (concat de tous les VOB). Les signaux portent un numéro de génération : une fabrication périmée est ignorée.
- Le nombre d'images suit la largeur, pas la durée. Un saut par image, pas un décodage du film entier.
