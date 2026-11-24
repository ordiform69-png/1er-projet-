# Corrections de VHS Restore AI

Branche `astra/corrections`, issue de `6b00a5b`. Trois lots successifs, sans fusion.

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

**Limites.** Les verrous de réservation laissés par une extinction brutale peuvent faire choisir le numéro suivant. Les anciens résultats sans reçu sont conservés et la première relance produit une nouvelle copie. La publication Windows utilise un renommage sans remplacement. Le test du workflow porte sur sa configuration ; la fabrication Windows, le lecteur FAT32 et le verrouillage par un lecteur réel restent à valider.

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

**Mesure IA.** Avec l’horloge de test, un lancement de 4 s et 30 s par image donnent 34 et 64 s pour les deux lots. L’extrapolation à 500 images, traitées par groupes de 60, donne 15 036 s (4 h 10 min 36 s). L’option « Continuer sans l’IA » garde le réglage initial disponible pour le prochain travail. Un test Qt vérifie aussi les trois réponses et la mention Full HD lors du choix en 4K. Il s’agit du temps de l’agrandisseur ; les entrées-sorties et les filtres peuvent allonger le temps total. Aucun chronométrage GPU familial.

**Vérifié.** 22 tests ciblés réussis, code 0 (27 s). Sont inclus les coupes de bord, l’export sans traiter le trou, la mire RGB et la reprise de la colorisation. Le modèle de colorisation de cette série est simulé. Les profils, intensités de restauration et choix par défaut sont conservés.

**Contrôle complémentaire de couleur.** Quatre contrôles de non-régression sont passés après essai sur une source RGB pleine plage : conversion effective vers la plage de sortie, plafonds de dominante, chaîne PAL historique et mire BT.709. Le répertoire livré au lot 1 exclut les caches Python depuis le commit 8f6e999.
