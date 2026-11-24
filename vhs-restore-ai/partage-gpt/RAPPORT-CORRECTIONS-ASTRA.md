# Corrections de VHS Restore AI

24 novembre 2026. Branche `astra/corrections`, issue de `ccr-5856e8d6-8xt8uh` au commit `6b00a5b`. Trois lots successifs, sans fusion.

## Lot 1 — Protéger les fichiers et terminer les travaux

| Constat | Commit | Travail livré |
|---|---|---|
| 1 | 33c9ecd | Réservation exclusive du jeu de noms, partiels uniques et publication sans remplacement. Un nouveau nom est pris si le MP4, la photo ou une copie est déjà présente. |
| 2 | eebde03 | Reçu interne de reprise par chemin, taille, date, réglages et sorties attendues. Deux extensions homonymes restent distinctes. |
| 4 | 4858941 | Sondages annulables dans le travail graphique. La fermeture demande l’arrêt puis attend le signal de fin sans bloquer Qt. |
| 12 | 096bb15 | Un dépassement de délai est inscrit au bilan du fichier concerné. Le dossier continue. |
| 10 | a094660 | Paquet identifié par numéro de fabrication et commit. Empreinte du ZIP distribuée avec lui. Le dépôt de l’artefact dépend des tests et de l’autotest. |
| Fin inconnue | 4ad40fe | Un départ à cinq secondes sans fin connue produit une recherche à cinq secondes, sans durée négative. |

**Vérifié.** Linux, Python 3.12, PySide6 6.12, FFmpeg 7.1.5. Dix tests ciblés réussis, code 0 (23 s), dont les exports concurrents, le WAV et le partiel témoins, les homonymes, le dossier après délai dépassé et la fermeture contrôlée en sous-processus. La suite complète est lancée séparément. Le bilan final précise son résultat.

**Limites.** Les verrous de réservation laissés par une extinction brutale peuvent faire choisir le numéro suivant. Les anciens résultats sans reçu sont conservés et la première relance produit une nouvelle copie. La publication Windows utilise un renommage sans remplacement. Le test du workflow porte sur sa configuration. La fabrication Windows, le lecteur FAT32 et le verrouillage par un lecteur réel restent à valider.

**Périmètre.** Les paramètres de restauration, le dessin des barres et les fils de vignettes de Grok restent ceux de la base.

## Lot 2 — Raccords, couleur, écoute et estimation IA

| Constat | Commit | Travail livré |
|---|---|---|
| 3 | 9bdbb0f | Lecture du son aux dates corrigées de la source. Bornage du morceau, silence aux bords manquants, assemblage par copie. Un WAV temporaire par morceau est évité. |
| 5 | 21b7110 | Conservation des indications de matrice, primaires, transfert et plage à taille d’origine. En HD, conversion de matrice vers BT.709. Les primaires et transferts connus sont gardés. La matrice RGB est adaptée à la sortie YUV. |
| 6 | 5867896 | Sondages du début, du milieu et de la fin. La tonalité à 301 s est reconnue. L’écoute reste accessible dès qu’une piste existe. |
| 7 | bd16e8e | Un résultat principal publié reste accessible si l’annexe échoue. La reprise d’un dossier produit l’annexe manquante. Le test interrompt la colorisation et vérifie la date du PNG principal après reprise. |
| 8 | 20280fb | Estimation des deux volumes avant l’encodage, avec cumul sur un volume commun. |
| 9 | af15776 | Mesure sur un lot d’une image puis un lot de deux, estimation à la cadence de sortie, choix explicite pour ce travail. Le comptage des paquets est annulable. |

**Mesures du raccord.** Mire progressive 25 i/s, son 48 kHz, deux flashs et deux bips, intervalles [0, 2] et [4, 6]. Le cas à +400 ms mesurait 4,821 s et présentait 440 ms entre deux images au raccord dans l’audit. Ici, les trois fichiers mesurent **4,021333 s** et l’intervalle maximal est **40 ms**. L’attaque du bip est le premier échantillon dépassant 0,1 en valeur absolue. L’heure du flash vient du paquet vidéo correspondant à l’image blanche décodée sans duplication.

| Correction appliquée | Bip moins flash avant le raccord | Bip moins flash après le raccord |
|---|---:|---:|
| +400 ms | +0,4 ms | +27,1 ms |
| −400 ms | +0,4 ms | +27,1 ms |
| Dérive +600 ms/min | −20,3 ms | +6,8 ms |

**Mesure IA.** Avec l’horloge de test, un lancement de 4 s et 30 s par image donnent 34 et 64 s pour les deux lots. L’extrapolation à 500 images, traitées par groupes de 60, donne 15 036 s (4 h 10 min 36 s). L’option « Continuer sans l’IA » garde le réglage initial disponible pour le prochain travail. Un test Qt vérifie aussi les trois réponses et la mention Full HD lors du choix en 4K. Il s’agit du temps de l’agrandisseur. Les entrées-sorties et les filtres peuvent allonger le temps total. Aucun chronométrage GPU familial.

**Vérifié.** 22 tests ciblés réussis, code 0 (27 s). Sont inclus les coupes de bord, l’export sans traiter le trou, la mire RGB et la reprise de la colorisation. Le modèle de colorisation de cette série est simulé. Les profils, intensités de restauration et choix par défaut sont conservés.

**Contrôle complémentaire de couleur.** Quatre contrôles de non-régression sont passés après essai sur une source RGB pleine plage : conversion effective vers la plage de sortie, plafonds de dominante, chaîne PAL historique et mire BT.709. Le répertoire livré au lot 1 exclut les caches Python depuis le commit 8f6e999.

## Lot 3 — Installation, DVD et fin de session

| Constat | Commit | Travail livré et vérification |
|---|---|---|
| 11 | be8f4d3 | Le script PowerShell utilise l’installateur Python du projet. Les deux parcours lisent `vhs_restore/paquets.json`, téléchargent en zone temporaire, vérifient l’empreinte et publient après validation. Les essais avec serveur HTTP local couvrent l’empreinte erronée, l’annulation et la reprise d’un transfert interrompu. |
| 13 | a87e6dc | Vérification par composants des chemins ZIP et 7z, inspection préalable des membres, refus des liens signalés. L’entrée au nom de dossier voisin et le membre 7z déclaré comme lien sont refusés. Essai complémentaire avec 7-Zip 26.06 sous Linux : une archive ordinaire a été listée puis extraite avec succès. Une seconde archive contenant un lien symbolique interne a été refusée à la lecture de la liste, avant extraction. |
| 14 | 4087439 | Un travail possède sa liste DVD et la libère en sortie, y compris sur exception. Un morceau absent est nommé avant l’analyse du titre. Essais avec un titre DVD synthétique et avec le morceau 2 absent. |
| 15 | 87f5073 | À la fin du travail, Qt libère sa référence dans la liste et la fonction qui capturait le média. Le test automatisé vérifie les références après 50 travaux. Un essai distinct ouvre une photo, produit un aperçu, puis recommence 50 fois avant de fermer. |

**Endurance mesurée.** Sur Linux, la mémoire résidente du processus graphique était de 79 752 Kio après le premier cycle, 80 096 au dixième, 80 596 au vingt-cinquième et 81 356 au cinquantième. La liste des fils était vide après chaque cycle. La fermeture a effacé le dossier d’aperçu et le sous-processus s’est terminé avec le code 0. Une progression de 1,6 Mio sur cette série ne permet pas à elle seule de conclure sur une session de plusieurs jours.

**Autres contrôles.** Les 23 tests ciblés du lot 3 ont réussi, code 0. Dans un essai supplémentaire du lot 1, un fichier arrivé entre la réservation et la publication a conservé ses octets. Le partiel terminé est resté disponible au chemin donné dans le message. Un essai Qt du lot 2 a annulé la colorisation après publication du PNG. L’écran « C’est prêt » affichait « Votre photo restaurée est prête. La copie en couleur a été interrompue. » avec le dossier du principal.

### Proposition pour la page simple

**Proposition à décider en famille.** À l’ouverture d’un film, consacrer le premier écran au nom du film, à la prochaine action et à la certitude de retrouver l’original. Les commandes de coupe se déploient quand l’utilisateur choisit « Enlever une scène ». Voici le croquis de l’état où un film vient d’être choisi.

| **VHS Restore AI** | **Aide** · **A− A A+** |
|---|---|
| **Votre film** · Noël 1988 | Changer de film |
| **Voir l’avant / après** | Aperçu du film, puis commandes d’écoute |
| ▸ **Enlever une scène** | Film entier conservé |
| **Restaurer** | Une copie sera enregistrée à côté de l’original. |
| ▸ Autres actions | Restaurer un dossier · Options avancées |

Dans cet exemple, le dossier de l’original est accessible en écriture. Afficher le vrai dossier prévu si la personne en choisit un autre ou si le logiciel utilise le dossier de secours. Après un aperçu, le bouton principal devient « Restaurer ». Pendant le traitement, l’avancement et « Arrêter » occupent l’emplacement du bouton. Pour une photo, masquer la ligne de coupe et conserver la proposition explicite de colorisation si elle s’applique. Garder « Ouvrir le dossier » sur l’écran final. Critère à essayer avec l’utilisateur à 1280 × 641 : ouvrir le film, repérer « Restaurer » et lire le dossier de sortie sans défilement. Vérifier aussi le parcours avec A+. Ce croquis n’a donné lieu à aucune modification de l’interface.

### Périmètre et limites

Aucune modification de la timeline de Grok, des intensités de débruitage, des profils ou du modèle de restauration. Les mesures de couleur ont été faites sur des mires. L’essai de vitesse utilise un agrandisseur factice. La vitesse effective, les couleurs de peau et le rendu des voix sur cassette familiale restent à vérifier sur le PC destinataire. Tests Windows physiques restant à faire : lecteur DVD, retrait d’une clé, volume FAT32, chemin réseau, publication sur fichier verrouillé et lancement du ZIP distribué. Le workflow fabrique et contrôle un ZIP nommé à l’intérieur de l’artefact, avec son fichier SHA-256.

**Essai avec le vrai paquet FFmpeg Windows.** L’archive 9.1 de l’éditeur, téléchargée en entier (119 467 219 octets), donne le SHA-256 `b9bbbb3acece000cbeec994f856649354e52c773807841e78908374b24d658fd`, identique au manifeste. Sous Linux, l’installateur a relu l’archive par le chemin de téléchargement, revérifié l’empreinte, extrait et publié les deux fichiers attendus sous `ffmpeg/bin/`. Le test a autorisé la sélection du paquet Windows, sans exécuter les binaires. Le lancement sous Windows et le comportement réel de 7zr restent à tester. [Empreinte publiée](https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.1-essentials_build.zip.sha256)

## Verdict de la suite complète

**Version finale des trois lots : 279 tests réussis, 7 ignorés, 0 échec, code de sortie 0, en 10 min 05 s.** Commande exécutée sous Linux avec FFmpeg dans le PATH : `QT_QPA_PLATFORM=offscreen python -m pytest -q`, avec un emplacement temporaire dédié passé à pytest. Python 3.12.14, PySide6 6.12.0, FFmpeg 7.1.5 et module facultatif Analog Repair du projet installé. Les sept cas ignorés correspondent au modèle de colorisation réel et à QTGMC indisponibles. Un avertissement de dépréciation provient du plugin pytest d’AnyIO.

Avec les seules dépendances principales et de développement, la suite du lot 1 a donné 257 réussis, 15 ignorés, 1 échec (code 1). Cet échec de `test_gui.py::test_source_selector` a été reproduit sur la base avant corrections : le test coche par code le contrôle « poussières » alors que le module facultatif manque. La suite finale utilise le module déclaré dans `requirements-poussieres.txt`, également prévu dans la fabrication Windows. Aucune dépendance n’a été ajoutée au projet.

Les essais intermédiaires ont révélé des écarts dans la lecture des bornes et les métadonnées couleur. Les corrections ont été intégrées aux commits concernés avant livraison. Le contrôle final du code confirme que les paramètres par défaut, les profils, les fonctions de filtrage du son et de prétraitement de l’image, et la classe `BarreFilm` correspondent à la base. Le croquis reste une proposition pour décision de l’utilisateur.
