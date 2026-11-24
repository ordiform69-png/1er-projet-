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
