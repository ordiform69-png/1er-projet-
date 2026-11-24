# Rapport n°11 pour Claude

## Où

- `grok/photos` : redresser puis enlever le bord, tours de 90°, test EXIF 6
- `grok/enregistrement` : un seul FFmpeg, arrêt par « q », tests lavfi
- `grok/rapport` : zip Bureau/Documents, sans film ni photo
- `grok/installateur` : Inno Setup sans admin, Release sur v* seulement

Base : `grok/integration` `1090e99`. Aucune fusion, aucune pull request, aucune étiquette.

## Fait, ne pas refaire

**Photos.** D'abord redresser (coins remplis de la couleur du bord), ensuite enlever le bord. Case cochée seulement si bord ou inclinaison nette. « Tourner à gauche » / « Tourner à droite ». Orientation EXIF appliquée une fois.

**Enregistrement.** Un seul processus FFmpeg. Image et son dans la même entrée (`-i video=…:audio=…`) avec `-rtbufsize` et `-thread_queue_size`. Petite image = deuxième sortie du même processus (`-update 1`). Arrêt par « q » sur l'entrée standard (pas de `-nostdin`). Tuer seulement en dernier recours. Tests avec lavfi.

**Rapport.** Bouton « Préparer un rapport pour mon fils » dans l'aide et en tête des options avancées (commit à part des boutons de Claude). Zip sans film ni photo. Bureau, sinon Documents, sinon dossier du logiciel.

**Installateur.** `setup.iss` : `PrivilegesRequired=lowest`, `{localappdata}\Programs\VHS Restore AI`, icône Bureau et menu Démarrer. Pas de `UninstallDelete` : tools et réglages restent. Workflow : job release seulement si `refs/tags/v`, aucune étape ne crée d'étiquette. SmartScreen dans LISEZMOI.

## Interdit respecté

- Pas de touch à `partage.py`, écran « C'est prêt », boutons « Restauration complète » des options avancées.
- Aucune fusion, aucune PR, aucune étiquette, aucune nouvelle dépendance Python.

## Vérifié

- Python 3.12.7, FFmpeg 7.0.2.
- `tests/test_photos_scanner.py` : 3 passed (bord+4°, photo droite, EXIF 6 avant/après tours).
- `tests/test_enregistrement.py` : 4 passed (une ouverture, lavfi+q, rien écrasé, parse appareils).
- `tests/test_rapport.py` : 2 passed (sans média, Bureau absent).
- `tests/test_installateur.py` : 3 passed (sans admin, pas d'étiquette, SmartScreen).

## Mesures

- Photo 4° + bord blanc : inclinaison détectée entre 2,5° et 6°, résiduelle après correction < 0,5°.
- EXIF orientation 6 : 200×100 devient 100×200 une fois ; un tour de plus redonne 200×100.
- Enregistrement simulé : fichier MKV > 1 Ko après arrêt par « q », code 0.

## Non testé

- Vrai boîtier de numérisation, vrai magnétoscope.
- Vrai Windows, exe installé, désinstallation réelle, SmartScreen.
- Suite complète rejouée (seuls les tests des quatre chantiers ont été lancés ici).
- FFmpeg 6.1.
