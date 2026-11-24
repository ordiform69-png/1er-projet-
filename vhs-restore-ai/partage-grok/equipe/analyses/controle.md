# Contrôle — vague 1 (analyse seulement, aucun code)

Branche `grok/equipe`, identique à `origin/ccr-5856e8d6-8xt8uh` (`3ace343`). Suite complète non lancée.

## Pytest

Les 6 fichiers demandés existent. Commande hors écran (`QT_QPA_PLATFORM=offscreen`, Qt et FFmpeg de `/tmp`).

**32 passent, 2 échouent** (34 tests, 67 s).

Échecs, les deux du même test :

- `tests/test_pieges_windows.py::test_photo_au_nom_avec_pourcent[Photo%20dimanche.jpg]`
- `tests/test_pieges_windows.py::test_photo_au_nom_avec_pourcent[Couleur%03d.png]`
- assertion ligne 36 : `apercu/apercu_photo_comparaison.png` absent.

La restauration de la photo passe (nom avec `%` conservé, fichier écrit à côté). `photo.make_photo_preview` revient sans erreur : FFmpeg (`/tmp/ffbin/ffmpeg`, Lavf 61.1.100) quitte avec le code 0 sur le `scale2ref` + `hstack`, avec « No filtered frames for output stream » et « Output file is empty ». La même commande sans `%` dans le nom ne produit pas non plus le PNG. Le code ne vérifie que le code de retour. Rien d'autre de ces 6 fichiers n'est rouge (vides, montage, barre, passages, ergonomie, autres pièges Windows).

Non couvert par cette commande (cités phase 24) : `tests/test_installer.py`, `tests/test_bords_auto.py`.

## Ce que couvre `scripts/audit_interface.py`

Robot d'interface, pas une suite pytest. Usage : `python scripts/audit_interface.py FILM PHOTO_NB PHOTO_COULEUR` (`QT_QPA_PLATFORM=offscreen`).

- Boîtes de message, dialogues fichier/dossier et ouverture d'URL sont bouchés (rien n'attend un clic humain).
- Instantanés : vide, film chargé, film + aperçu, OCCUPÉ (faux travail), photo N&B, photo couleur.
- Pages simple et avancée : boutons, listes, compteurs, champ de sortie. Tableau « actif / grisé / caché ».
- Boutons sans `clicked` ni `toggled`.
- Clic de chaque bouton actif (hors cases à cocher et hors `ProfileTile`) : si événements, texte de `status`, page et « occupé » ne bougent pas, le clic est signalé « sans effet ».
- Les widgets sont nommés par leur attribut sur la fenêtre (`s_choose`, etc.). Un renommage les fait apparaître comme `<QPushButton « … »>`.
- Fin par `os._exit(0)` pour éviter un faux échec PySide au ramassage des threads.

Ce n'est pas les ~330 captures de la phase 24 (1280×720 à 150 %, 1366×768, 1920×1040, thèmes sombre et clair, texte 100 et 150 %). Cet audit n'a pas été relancé (il exige trois médias en arguments).

## 4 risques si on touche `gui.py` ou `pipeline.export`

Ne pas renommer ni débrancher : `s_choose`, `s_preview`, `s_run`, `s_couper`, `s_fini`, `s_status`.

1. **États des six widgets.** `s_choose` reste actif tant que ce n'est pas occupé (Entrée = choisir ; nom accessible contient « choisir »). `s_preview` et `s_run` seulement si un fichier est chargé et que ce n'est pas occupé (`s_run` : nom accessible « restaurer »). `s_status` est le miroir de `status` : « Prêt. », « Vous êtes à… », « continue ». `s_fini` / `s_fini_texte` = « C'est prêt » : ne pas le cacher si la recherche de vides est vide, refusée ou annulée, ni si une installation échoue ; Entrée ouvre le film, ne relance pas la restauration. `s_couper` : texte « Couper ici », puis un libellé qui contient « reprend » (recopié sur `trim_couper`). L'audit et `test_ergonomie` / `test_passages_gui` / `test_vides_montage` / `test_barre_montage` lisent ces noms.

2. **Coupe au milieu : la fenêtre et `export(..., passages=)` doivent refuser la même chose.** Deux clics sur `s_couper` remplissent `_coupes` (10 s → 25 s dans les tests). Avec au moins deux intervalles, `pipeline.export` lève `ToolError` (« passage au milieu ») si amélioration IA, poussières, réparation de bande (bruit, chroma, taches) ou cadence de tournage. La note avant « Restaurer » cite les libellés de l'écran (« Amélioration IA », « Bruit de bande », …), ne décoche rien et ne lance pas l'export. Un dossier n'envoie aucune coupe ; la phrase est en haut de page et dans `s_fini_texte` (la ligne `s_status` est tout de suite remplacée par « Film 1 sur … »).

3. **Le résultat n'existe qu'une fois complet.** `export` écrit un `.partiel.mp4` puis `finaliser`. Si le fichier est ouvert dans un lecteur (`FichierOccupe`), le partiel n'est pas effacé. `check_fat32` a lieu avant l'encodage : avec `passages`, la taille estimée est celle des morceaux gardés, pas du film entier. Ne pas écraser l'original. Les morceaux du milieu sont assemblés en `-c copy` (pas de seconde compression). Changer `cancel`, `progress`, `start`, `duration` ou `passages` casse l'appel depuis la fenêtre.

4. **Durées et écran « C'est prêt » liés au même export.** Durée mesurée en lisant le film (VOB dont les horodatages repartent à zéro). Dernier morceau gardé = jusqu'au bout. Copie plus courte que prévu : refus, rien n'est retiré. Ouvrir un autre film ne doit pas hériter du restauré précédent. Modifier `export` sans les garde-fous d'affichage de `s_fini` / `s_status` désynchronise l'écran et le fichier.
