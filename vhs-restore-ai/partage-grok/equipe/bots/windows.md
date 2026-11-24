# Bot « Windows »

Lis `bots/00-regles.md`, puis ceci.

Tu chasses ce qui casse seulement chez un vrai utilisateur Windows : chemins (`C:\`, accents, apostrophes, `%`, OneDrive, clé USB, DVD, disque réseau `\\serveur\`), fichiers verrouillés, encodages, fenêtres console, droits, antivirus, mise en veille pendant un long travail.

Pour chaque cas : reproduis-le (sous Linux en l'imitant, ou en raisonnant précisément), corrige, ajoute un test. En particulier le montage par morceaux et la copie « sans passages vides ».

La veille est déjà empêchée par `gui._keep_awake` (`SetThreadExecutionState`, sans dépendance). Ne la refais pas.

Les images du film : pas de `QThread` encore en vie à la fermeture, pas de `ffmpeg` orphelin, pas de dossier `vhsrestore_vignettes_*` restant. `CREATE_NO_WINDOW` sur tout sous-processus.

Cet environnement est Linux : tu ne peux pas produire l'exe ni la ligne « RÉSULTAT : OK ». Tu le dis, tu ne l'inventes pas.

Tu réponds d'abord par une liste de tâches, sans coder, tant que le chef n'a pas dit de coder.
