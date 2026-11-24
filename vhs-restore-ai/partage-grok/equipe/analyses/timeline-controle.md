# Contrôle — timeline (note du chef)

Les bots n'ont pas pu être lancés. Le chef a tenu ce rôle.

Tests dans `tests/test_timeline.py` : ordre des couleurs, clic pendant l'extraction, dossier effacé au changement de film, deux barres, dernière demande, trio visible à 1280×641, durée 0, film court, bwdif seulement si entrelacé, SAR 4:3, DVD concat.

À ne pas casser : `test_barre_montage`, `test_coupes_bords`, `test_page_avancee` (colonnes), `test_ergonomie.py::test_texte_sans_defilement_horizontal`.

```
QT_QPA_PLATFORM=offscreen LD_LIBRARY_PATH=/tmp/qtlibs/usr/lib/x86_64-linux-gnu PATH=/tmp/ffbin:$PATH
python -m pytest tests/test_timeline.py
```

Toute la suite (environ 260) n'a pas été relancée ici. Pas d'exe Windows.
