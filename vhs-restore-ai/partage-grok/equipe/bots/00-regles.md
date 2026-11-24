# Règles communes — à donner à chaque bot

Le chef est Grok Build. Un bot ne livre pas à Claude et ne fusionne pas.

## Qui utilise le logiciel

- Le père de l'utilisateur, né en 1950, sous Windows, écran 1920 × 1080 à 150 % (environ 1280 × 641).
- Il se sert peu d'un ordinateur. Il ne lit pas les infobulles. Un message technique l'arrête. Il a peur de casser un film.
- Il restaure des films de famille (VHS, Video8 / Hi8, Betamax, Super 8 scanné) et des photos.
- Il veut : choisir, voir si c'est mieux, lancer, retrouver le résultat.

## Règles

- L'original n'est jamais modifié. Le 4:3 et le son restent. Jamais « parfait » ni « HD réelle ».
- Pas de filtre de restauration ni de réglage par défaut modifié sans mesures avant / après et une décision du chef dans `DECISIONS-EQUIPE.md`. La case « Corriger aussi ces défauts » reste cochée d'office quand des défauts sont repérés.
- Pas de banc de montage (pas de titres, musique, plans déplacés, transitions). Les petites images sur la barre sont autorisées (décision D-011) : ce n'est pas un banc de montage. Assemblage `-c copy`. Les coupes d'un film ne partent pas avec un dossier. Pas de `deleteLater` sur les lignes de passages.
- Ne copie aucun code d'OpenShot, LosslessCut, Shotcut ou Clipchamp. Ces deux derniers restent des programmes séparés.
- Français, vouvoiement, phrases courtes. Les options sont nommées comme à l'écran. Guillemets « ».
- Aucune nouvelle dépendance sans accord du chef.
- Garde les noms des tests (`s_choose`, `s_preview`, `s_run`, `s_couper`, `s_moment`, `compare`, `pages`…).
- Clic près d'un bord doré : se placer. Glisser de 4 px : tirer le bord. Prise 44 px. Ne pas y revenir.
- Image du moment : au moins 180 px de haut sur la page simple. L'image, la barre et « Couper ici » restent visibles ensemble à 1280 × 641, texte 100 % et 150 %.
- Les images du film ne passent pas par un `QThread`. FFmpeg est tué à l'annulation. L'écran n'est jamais bloqué.
- Protections Windows pour tout fichier écrit : `finaliser`, `effacer`, `verifier_chemin`, `ff_input`, `check_fat32`, `CREATE_NO_WINDOW`.
- Jamais dans le dépôt : exe, zip, captures, médias de test. Pas d'identifiant de modèle dans les commits.
- Quatre tests sont déjà rouges ici (`test_source_selector`, `test_preview_and_folder`, `test_photo_au_nom_avec_pourcent` ×2). Ce n'est pas une régression nouvelle. Ne les « corrige » pas en affaiblissant le test.

## Comment parler

Ajoute à la fin de `partage-grok/equipe/ECHANGES.md`. N'efface rien.

```
### E-0xx · date · De : Ton rôle → À : Un rôle (ou Tous)
Sujet : …
Message : …
Réponse attendue : …
```

La réponse cite le numéro. Un désaccord : trois lignes au plus, puis le chef tranche.

Avant de modifier un fichier de la carte d'un autre bot, demande-le dans `ECHANGES.md` et attends.

## Carte des fichiers

| Bot | Fichiers |
|---|---|
| Parcours senior | `gui.py` page simple, `theme.py` |
| Windows | `tools.py`, `installer.py`, `__main__.py`, écriture dans `pipeline.py`, `photo.py`, `colorize.py` |
| Image et son | `probe.py`, `advice.py`, `profiles.py`, mesures de `vignettes.py` |
| Montage | cadre « Enlever une scène », `BarreFilm`, `pipeline` passages et morceaux, `vides.py` |
| Aide et textes | `LISEZMOI.txt`, `README.md`, « Bienvenue », phrases de `ergonomie.py` |
| Contrôle | `tests/`, `scripts/audit_interface.py` |

Branche de travail : `grok/equipe-<rôle>`, partie de la branche indiquée par le chef. Petits commits. Tests du sujet verts avant de demander l'intégration.
