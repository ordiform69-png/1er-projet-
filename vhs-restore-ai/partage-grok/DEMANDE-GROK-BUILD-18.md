# Demande n°18 : essai mesuré d'IA légères pour choisir le meilleur rendu (pour le chef des bots)

L'utilisateur veut que l'IA analyse les images pour obtenir le meilleur rendu. Principe retenu par
Claude : **l'IA regarde quelques images par scène et choisit des réglages ; FFmpeg les applique**
à toute la scène. Pas d'IA image par image sur tout le film (des heures sur le PC du père, sans
carte graphique).

Cette demande est un ESSAI : rien ne change dans le logiciel livré (`vhs_restore/` intouché).
On décide ensuite, chiffres à l'appui, ce qui entre dans le logiciel (demande suivante).

## Base, branches, équipe

- Base : `ccr-5856e8d6-8xt8uh`, commit indiqué dans le message (ou plus récent). Indépendant de
  la demande n°17 (en cours) : rien à fusionner avec elle.

| Agent | Essai | Branche |
|---|---|---|
| F1 | Lumière et couleurs réglées par IAT | `grok/ia-lumiere` |
| F2 | Un juge de qualité choisit la force du débruitage et de la netteté | `grok/ia-juge` |
| F3 | Modèles entraînés sur de la vraie VHS (OpenModelDB) contre l'IA actuelle | `grok/ia-vhs` |
| F4 | Banc d'essai commun, synthèse, rapport | `grok/ia-essai` |

## Règles communes

- **Rien dans `vhs_restore/`**, rien dans `requirements*.txt`, rien dans le paquet Windows. Les
  scripts d'essai vont dans `essais/n18/` (hors du paquet : vérifier `VHSRestoreAI.spec`).
- Le logiciel n'aura que ce qu'il a déjà : `onnxruntime`, `onnx`, `numpy`, FFmpeg. Les modèles
  testés doivent donc tourner en **ONNX sur processeur**. La conversion vers ONNX (PyTorch,
  spandrel…) se fait à part, une fois ; le fichier ONNX obtenu est ce qui compte.
- **Aucun poids, aucune image, aucune vidéo dans le dépôt.** Les scripts les téléchargent depuis
  leur source, avec l'empreinte SHA-256 vérifiée. Les extraits de vraies cassettes que
  l'utilisateur fournira restent hors dépôt.
- **Licence** de chaque modèle ET de ses données d'entraînement, vérifiée à la source et citée.
  Exclure tout ce qui est « recherche seulement » (exemple : poids appris sur MIT-Adobe FiveK).
  Non commercial (CC-BY-NC-SA) : acceptable (logiciel gratuit), à signaler.
- Chaque essai doit pouvoir être **relancé par Claude en une commande**
  (`python essais/n18/<essai>.py`), qui écrit ses chiffres dans un fichier CSV.
- Sans bac à sable : pousser les scripts, écrire « non mesuré », ne tirer AUCUNE conclusion.
  Claude lancera les scripts. Pas de chiffres inventés.
- Chaque commit poussé tout de suite. Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request.

## Agent F4 : banc d'essai commun (à faire en premier, les autres s'en servent)

- Images de référence propres sous licence libre (CC0 ou domaine public : Wikimedia Commons,
  films du domaine public…), variées : intérieur sombre, extérieur, visages, peau, ciel. URL,
  licence et SHA-256 de chacune dans `essais/n18/references.csv`.
- Dégradation « façon VHS » réglable, avec FFmpeg : définition réduite, couleur étalée
  horizontalement, bruit, image assombrie (gamma), dominante, couleurs ternes, noirs relevés.
  On connaît ainsi l'image d'origine : on peut mesurer qui s'en rapproche le plus.
- Mesures : PSNR, SSIM, écart de couleur ΔE2000 moyen (numpy, sans nouvelle dépendance), et
  temps par image (processeur, 720 × 576, nombre de cœurs indiqué).
- Méthode actuelle comme point de comparaison : la chaîne du logiciel
  (`pipeline.filter_chain`, profil « Bien nettoyé, naturel »).
- Rapport final `partage-grok/RAPPORT-N18-POUR-CLAUDE.md` : un tableau par essai (gain mesuré,
  temps estimé pour un film de 2 heures, taille, licence, verdict) et une recommandation.

## Agent F1 : lumière et couleurs réglées par IAT

- IAT (« Illumination Adaptive Transformer », environ 90 000 paramètres) : poids officiels du
  dépôt des auteurs (vérifier licence et données d'entraînement), export ONNX.
- Piste : sa partie « globale » donne une matrice de couleur et un gamma pour toute l'image.
  Vérifier dans le code que c'est bien le cas. Les estimer sur 3 à 5 images d'une scène, en
  faire des filtres FFmpeg (`colorchannelmixer` et gamma), les appliquer à toute la scène.
- Comparer, sur le banc de F4 : (1) méthode actuelle (niveaux et dominante, une fois pour le
  film), (2) IAT partie globale seulement, (3) IAT complet image par image (pour référence).
  Écart à l'image d'origine (ΔE, PSNR), temps.
- Garde-fous : mêmes plafonds que le logiciel (`safe_levels`, `safe_gains`) ; montrer ce que
  donne l'IA SANS plafond, pour voir si elle dérape.

## Agent F2 : un juge de qualité choisit les réglages

- Juges candidats, en ONNX : CLIP-IQA+, LIQE, MUSIQ (dépôt Hugging Face `86Cao/IQA-ONNX-Models`,
  vérifier la licence) ; facultatif : DOVER-Mobile (vidéo, dépôt `teowu/DOVER`).
- Essai : pour chaque image dégradée du banc, 6 à 9 réglages sûrs (force du débruitage ×
  netteté, dans les plages des trois rendus). Le juge choisit-il le réglage le plus proche de
  l'image d'origine (selon PSNR, SSIM, ΔE) ? Corrélation, taux de bon choix.
- Biais à mesurer : le juge préfère-t-il une image trop nette ou trop colorée (aspect « trop
  moderne ») ? Taille du modèle, temps par image.

## Agent F3 : modèles entraînés sur de la vraie VHS

- Candidats OpenModelDB (architecture compacte) : « 1x VHS Sharpen », « 1x BaldrickVHSFix »
  (bruit de couleur, source déjà désentrelacée), « 2x VHS upscale and denoise Film ». Licence de
  chacun (plusieurs sont CC-BY-NC-SA).
- Comparer à l'IA actuelle (Real-ESRGAN du rendu « Nettoyage au plus fort ») et à la chaîne sans
  IA, sur le banc de F4 : écart à l'origine, détails inventés (visible sur les visages et le
  texte), temps par image sur processeur en ONNX, et temps estimé pour un film de 2 heures.

## Extraits réels

L'utilisateur fournira peut-être quelques extraits de 30 s de vraies cassettes. Les scripts
acceptent un dossier d'extraits (`--extraits <dossier>`) : sans image d'origine connue, on y
mesure seulement les notes des juges et les temps, et on produit des images avant / après que
Claude regardera (hors dépôt).
