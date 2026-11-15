Bonjour Grok,

Merci pour le travail sur le son : il fonctionne. Je l'ai vérifié et j'ai ajouté les tests qui
manquaient (`tests/test_son.py`). Voici la suite. Le contexte du projet est dans
`DEMANDE-GROK-BUILD-2.md` (sections 1 à 3) et la feuille de route dans `ANALYSE-FONCTIONNELLE.md`.

État au 15/11/2026 : branche `ccr-5856e8d6-8xt8uh`, **79 tests** verts sous Linux, construction
Windows verte. Les points 2, 4 et 5 de l'analyse sont faits : sortie de secours si le dossier du
film est en lecture seule, films déjà restaurés sautés quand on relance un dossier, espace disque
vérifié avant tout traitement. L'empêchement de la veille était déjà en place, avec ton travail
sur le son.

## Règles (obligatoires, rappel après le dernier envoi)

1. **Ne pousse plus directement sur `ccr-5856e8d6-8xt8uh`.** Une branche `grok/<sujet>` par sujet,
   puis une pull request vers cette branche. La PR décrit ce qui a été testé et comment.
2. **Chaque comportement nouveau est livré avec ses tests** (`tests/`), et la suite complète passe
   sous Linux et dans la construction Windows (GitHub Actions) avant la demande de fusion.
3. **N'annonce que ce que tu as mesuré.** Si quelque chose n'a pas été essayé (DeepFilterNet, un
   vrai DVD, une vraie cassette), écris « non testé ».
4. Pas de nouvelle dépendance sans une ligne de justification dans `DECISIONS.md`. Rien de
   nouveau activé par défaut. Le mode simple garde ses trois boutons.

## Tâches, dans cet ordre

### 1. Films de DVD découpés en VOB (point 3 de l'analyse) — branche `grok/dvd-vob`
Un DVD de transfert range un film en `VIDEO_TS\VTS_01_1.VOB`, `VTS_01_2.VOB`… (1 Go chacun), plus
`VTS_01_0.VOB` (menu) et des `.IFO`.
- Choisir un fichier `VTS_xx_N.VOB`, ou le dossier `VIDEO_TS`, doit donner **un seul film** par
  titre, les morceaux étant enchaînés (protocole `concat:` de FFmpeg ou démultiplexeur concat).
  Ignorer `VTS_xx_0.VOB` et `VIDEO_TS.VOB` (menus).
- « Dossier entier » sur un `VIDEO_TS` : un film par titre, et non un par morceau.
- Tests : fabriquer un faux `VIDEO_TS` de 2 ou 3 morceaux MPEG-2 (`-f dvd`) ; vérifier une seule
  sortie, la durée totale, l'absence de saut ou de répétition à la jonction, la synchronisation
  du son (voir `test_preview_aligned_when_video_starts_after_audio`, cas réel déjà rencontré).
- Le dossier source est en lecture seule : la sortie de secours (`pipeline.output_dir_for`)
  existe déjà.

### 2. Vérifier DeepFilterNet pour de vrai — branche `grok/deepfilter-verif`
Les options `-D` et `-a 12` de `deep-filter` n'ont été vérifiées par personne. Installe-le
(`installer.bat -AvecSon`, ou le binaire Linux), confirme les options dans sa documentation
officielle (donne le lien), et ajoute un test qui ne tourne que si le binaire est présent :
même durée, même nombre de canaux, son synchronisé, échantillon de voix + ambiance (bruit de
foule ou musique) dont l'ambiance n'est pas effacée (énergie mesurée avant et après, à documenter).

### 3. Temps restant (P1, point 7) — branche `grok/temps-restant`
Afficher « environ 1 h 20 restantes » dans les deux pages, d'après la progression réelle (moyenne
glissante, rien avant 5 % de progression). Test sur la fonction de calcul, pas sur l'horloge.

### 4. Couper le début et la fin (P1, point 11) — branche `grok/debut-fin`
Dans les options avancées seulement : début et fin (en secondes ou mm:ss), appliqués à l'export
(`-ss`/`-t`, comme l'aperçu). Tests : durée exportée, son synchronisé, pellicule re-cadencée
comprise.

### 5. Bouton « Vérifier l'installation » (P1, point 13) — branche `grok/verifier-installation`
Dans les options avancées : lance `--autotest` dans un dossier temporaire, puis affiche le rapport
`autotest.txt` dans une fenêtre lisible. Test hors écran.

## À ne pas faire sans notre accord
- **Publier une version GitHub (Release)** : c'est le point 6, il rend le logiciel public. Prépare
  seulement le workflow, sans l'exécuter.
- Changer les réglages de son des profils. La question « Fidèle doit-il toucher au son ? » est en
  attente de décision : le comportement actuel est conservé.
- Colorisation, interpolation d'images, montage, titres, partage en ligne.

Pour chaque PR, termine par un bloc court : **Fait / Testé (comment) / Non testé / Risques**.

Merci !
