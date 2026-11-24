# Vérification par Claude du rapport de GPT Astra (24 novembre 2026)

Base : branche `ccr-5856e8d6-8xt8uh`, commit `4cd647d` (celui du rapport). Chaque constat a été
reproduit (« reproduit ») ou relu dans le code (« lu »). Aucun code n'a été modifié.

| N° | Constat de GPT Astra | Vérification | Résultat ici |
|---|---|---|---|
| 1 | WAV existant écrasé ; partiel prévisible | reproduit | WAV témoin remplacé par la copie du son (`unique_output_path` ne regarde que le .mp4) |
| 2 | Deux originaux de même nom (Noel.jpg / Noel.png) : le second sauté | reproduit | `restore_folder` : faits `Noel_restaure_equilibre.png`, sautés `['Noel.png']`, 0 erreur |
| 3 | Coupe au milieu + décalage son +400 ms : pause d'image au raccord | reproduit | 0 ms : 4,021 s, écart max 40 ms ; +400 ms : **4,821 s, écart de 440 ms au raccord** |
| 4 | Fermeture pendant une analyse lente : `wait(15000)` ignoré | lu | `closeEvent` accepte la fermeture quel que soit le résultat de `wait` |
| 5 | Source BT.709 étiquetée BT.470BG en résolution d'origine | reproduit | entrée `bt709,bt709` → sortie `bt470bg,bt470bg` (profil Fidèle) |
| 6 | Cinq minutes de silence = film déclaré muet | lu | `volumedetect` sur les 300 premières secondes seulement (`probe.py`) |
| 7 | Résultat principal publié, puis échec d'une copie : écran « n'a pas abouti » | lu | MP4 publié avant la copie WAV ; PNG avant la colorisation |
| 8 | Mode IA : place sur le disque de destination non vérifiée | lu | `export` saute `check_disk_space` en IA ; `_export_ai` ne regarde que le dossier de travail |
| 9 | Estimation de l'IA trop tardive | lu | confirmé ; rejoint la lenteur connue (≈ 30 s / image chez l'utilisateur) |
| 10 | Artefact déposé même si les tests échouent | lu | tests en `continue-on-error`, dépôt de l'artefact avant l'échec final. Les exe envoyés jusqu'ici avaient tous leurs tests verts (vérifié dans chaque journal) |
| 11 | Installateur PowerShell moins sûr que le bouton | lu | plausible (sommes SHA partielles) ; concerne `installer.bat`, pas l'exe |
| 12 | Délai dépassé (`TimeoutExpired`) arrête tout le dossier | lu | `TimeoutExpired` n'est pas un `OSError` : non intercepté par `restore_folder` |
| 13 | Contrôle d'archive par préfixe de texte | reproduit | l'entrée `../installe-voisin/hors.txt` est acceptée (risque faible : archives à empreinte figée) |
| 14 | Liste DVD temporaire jamais effacée ; morceau manquant accepté | lu | confirmé |
| 15 | Test de raccord trop large ; liste de travaux qui grossit | lu | confirmé (`self._fils`) |
| — | `bornes_a_exporter(0, 5, 0, [])` | reproduit | renvoie une durée de **−5 s** |

Constat complémentaire de Claude (non relevé par GPT Astra) : page simple chargée pour un utilisateur
de 76 ans. Film ouvert : 19 boutons, 1 case, 2 champs, page de 2 561 px de haut pour 641 px visibles
(environ 4 écrans) ; sans film : 9 boutons, 1 181 px.

Conclusion : les 15 constats sont exacts ; aucun n'est une fausse alerte.
