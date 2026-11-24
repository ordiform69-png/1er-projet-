# Rapport d'équipe pour Claude

Branche `grok/equipe`, à relire. Non fusionnée. Le chef ne fusionne pas.

## Ce que chaque bot a fait

- **Parcours senior** : parcours à 641 px. Vague 1 : molette, cadre caché sans film, phrase d'arrêt. Écarté : déplacer l'aperçu et le bouton dossier (phase 24).
- **Aide et textes** : LISEZMOI, Bienvenue, noms des cases dans l'erreur. Aucun libellé de bouton changé. Vague 2 : les phrases déjà claires (chemin du film, FAT32, logiciel ouvert) ne sont pas remplacées par le message générique.
- **Image et son** : mesures sur les films de synthèse. Aucun seuil changé (D-003). Coupe au milieu : 21 ms, dans la tolérance de 0,15 s.
- **Montage** : analyse dans `partage-grok/equipe/analyses/montage.md`. Cinq corrections (E-007, D-010). Le décalage du son à chaque morceau est écarté (D-008).
- **Windows** : analyse dans `analyses/windows.md`. Place des morceaux, FAT32 de la copie sans vides, chemin d'origine, lancement UNC, installation si le programme est ouvert. La veille était déjà faite (`_keep_awake`, D-009).
- **Contrôle** : pas de suite complète dans cet environnement. Sélection ciblée verte. L'échec photo `%` / `scale2ref` est antérieur (D-007).

Discussions : E-002 à E-009 dans `partage-grok/equipe/ECHANGES.md`. Décisions D-001 à D-010.

## Fait

- Molette ignorée sans focus. « Enlever une scène » seulement après un film. Arrêt : le film n'est pas modifié.
- LISEZMOI, Bienvenue, noms des cases à l'écran.
- Coupe au début ou à la fin vraiment appliquée (`bornes_a_exporter`). Curseur jusqu'au bout du film. Entrée sur la barre = « Couper ici ». Prise des bords 44 px. Neuvième coupe et annulation du geste commencé.
- Morceaux : la place du dossier temporaire est comptée. Copie sans vides : refus FAT32 au-delà d'environ 4 Go, et place disque. Film d'origine trop long pour Windows : on demande de le déplacer. `lancer.bat` utilise le chemin complet (`start /D`), `installer.bat` utilise `pushd`. Un outil de montage ouvert n'est plus effacé à la réinstallation.

## Testé

```
QT_QPA_PLATFORM=offscreen
pytest tests/test_coupes_bords.py tests/test_pieges_windows.py tests/test_vides_montage.py \
  tests/test_montage.py tests/test_barre_montage.py tests/test_passages_gui.py \
  -k "not photo_au_nom and not mode_ia"
```

36 tests passés en 53 s. Les 3 tests écartés sont l'aperçu photo `%` (déjà rouge avant cette branche) et le mode IA du dossier temporaire (long, non modifié).

## Non testé

- Toute la suite (environ 240 tests).
- Construction Windows de l'exe. Pas de ligne « RÉSULTAT : OK » : cet environnement est Linux, l'exe n'a pas été fabriqué.
- Cassette d'une heure, mur blanc, vraie clé FAT32, vrai chemin `\\serveur\`, vrai fichier de plus de 260 caractères.
- Manifeste `longPathAware` de l'exe.

## Risques

- Le curseur peut maintenant dépasser les 10 dernières secondes. L'aperçu est toujours ramené dans le film par `make_preview`. Le temps affiché sur la barre peut donc être plus loin que l'extrait montré.
- La prise de 44 px autour d'un bord doré prend le pas sur un clic pour se placer, si l'on clique tout près d'une coupe.
- L'estimation FAT32 de la copie sans vides est haute (10 Mbit/s). Une copie qui aurait tenu peut être refusée. Mieux que d'écrire une heure pour échouer à 4 Go.
- `start /D` vers un chemin `\\serveur\` n'a pas été exécuté ici. `cmd` n'accepte pas `cd` vers ce chemin ; l'API Windows, si. À vérifier sur un vrai disque réseau.
- L'échec photo `scale2ref` reste rouge ici. Ce n'est pas une régression de ces vagues, mais la suite complète n'est pas verte dans cet environnement.

## Écarté

- Changer un seuil d'image ou de son (D-003).
- Retirer le décalage du son sur chaque morceau (D-008) : ce serait un dérive, pas une correction.
- Ajouter un appel de veille : déjà en place, sans `ES_DISPLAY_REQUIRED` (D-009).
- Cacher les noms LosslessCut et Shotcut (D-005).
- Vignettes, levée du refus IA / poussières / bande / cadence, banc de montage.
- Déplacer le bouton dossier et réduire l'aperçu (D-006).
- Manifeste `longPathAware` : la construction Windows n'a pas été relancée.
