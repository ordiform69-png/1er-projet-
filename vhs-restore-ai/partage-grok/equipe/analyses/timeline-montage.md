# Montage — timeline (note du chef)

Les bots n'ont pas pu être lancés (le flux se fermait avant l'envoi). Le chef a tenu ce rôle.

- La grande image est au-dessus de `BarreFilm`, dans le cadre « Enlever une scène ».
- La carte « Enlever un passage » a une `BarreCompacte` (même code, autre classe) pour que
  `findChild(BarreFilm)` reste la barre de la page simple.
- Un seul état : `_coupes`, `start_spin`, `trim_start` / `trim_end`. `_rafraichir_barre` met les deux barres à jour.
- Une liste d'images pour les deux, calculée sur la largeur de la barre simple (un pas de 90 px).
- Clic près d'un bord : inchangé (prise 22 px de chaque côté, glisser dès 4 px).
