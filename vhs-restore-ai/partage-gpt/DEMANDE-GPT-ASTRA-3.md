# Demande Astra n°3 : Real-ESRGAN et DeepFilterNet, l'avant / après dit-il vrai ? (pour ChatGPT)

Merci pour la vérification indépendante du calage voix-lèvres et de la timeline : tes mesures
recoupent celles de Claude, et la timeline est bien dans `ccr-5856e8d6-8xt8uh` (fusion `4372164`).

Ton rapport laissait une question ouverte : **l'effet de Real-ESRGAN et de DeepFilterNet dans
l'avant / après n'a pas été mesuré.** C'est ce travail. La question de l'utilisateur, pour son père
de 76 ans : « Ce que je vois et j'entends dans l'aperçu, est-ce ce que j'aurai dans le film ? »

## Base, branche, fichiers

- Base : `origin/ccr-5856e8d6-8xt8uh` au commit `15b6e75` ou plus récent.
- Branche : `gpt/ia-apercu`. Rapport : `partage-gpt/RAPPORT-GPT-IA-APERCU.md` sur cette branche.
- Fichiers que tu peux modifier, seulement ces fonctions :
  - `vhs_restore/pipeline.py` : `_try_deepfilter`, `essayer_ia`, `make_preview` ;
  - `vhs_restore/gui.py` : `_preview_done`, `start_preview`, et les messages de fin d'export ;
  - `vhs_restore/assistant.py` : le résumé (`_ecrire_resume`) si un message doit y figurer.
- Tests nouveaux : `tests/test_ia_apercu.py`. Ne déplace pas de code, ne renomme rien.

## Déjà tranché (ne pas changer)

- L'aperçu passe par le même traitement que l'export (`make_preview` → `export(start, duration)`,
  encodage `veryfast` seulement). Avec une dérive du son, l'extrait part de la correction
  accumulée à sa position (`15b6e75`).
- L'image de comparaison côte à côte est réduite à 540 lignes, en couleurs BT.601 (`f711ba4`).
  L'apport de Real-ESRGAN (netteté en grand) s'y voit peu : **c'est voulu**. Pour juger l'image,
  compare `apercu_restaure.mp4` (pleine taille), pas `apercu_comparaison.mp4`.
- Avec une dérive, atempo avance le son de 15 à 20 ms (limite connue, dans `DECISIONS.md`). Ne la
  confonds pas avec un effet de DeepFilterNet.
- Real-ESRGAN n'agit que si « Amélioration IA » est cochée. DeepFilterNet n'agit qu'avec
  « Nettoyage au plus fort », le son restauré, et un film qui a du son.

## P0 : DeepFilterNet (le son)

Installe le binaire Linux de la même version que `paquets.json` (DeepFilterNet v0.5.6, release
GitHub `Rikorose/DeepFilterNet`), et donne son chemin par `VHSRA_DEEPFILTER`. Ne commite jamais le
binaire.

1. **Calage.** Avec le film à repères de `tests/test_calage_apercu_export.py` (éclair et bip toutes
   les 2 s), profil « Nettoyage au plus fort » : l'écart bip − éclair est-il le même avec et sans
   DeepFilterNet, dans l'aperçu et dans l'export ? L'appel utilise `-D` (compensation du retard) :
   vérifie qu'il n'ajoute aucun retard. Tolérance : 5 ms.
2. **Même son dans l'aperçu et dans le film.** Sur un passage avec voix et bruit de fond (voix de
   synthèse ou enregistrement libre de droits, plus du souffle ajouté), compare le son de l'aperçu
   à celui de l'export au même instant de la source : niveau du bruit de fond dans les silences
   (dB), niveau des voix, corrélation des formes d'onde après alignement. Le début d'un extrait
   peut différer (le modèle démarre) : mesure à partir d'1 s dans l'extrait et donne la durée de
   cette mise en route.
3. **Échec silencieux.** Si DeepFilterNet échoue, `_try_deepfilter` revient au nettoyage habituel
   (`afftdn`) en l'écrivant seulement dans le journal. L'aperçu peut alors avoir DeepFilterNet et
   le film non, ou l'inverse, sans que personne le sache. Vérifie en le faisant échouer (binaire
   factice qui sort en erreur, puis binaire absent). Si l'écran ne dit rien, ajoute une phrase
   simple, visible après l'aperçu et dans le bilan de l'export, par exemple : « DeepFilterNet n'a
   pas pu nettoyer le son : le nettoyage habituel a été utilisé. » Ajoute un test.

## P1 : Real-ESRGAN (l'image)

Real-ESRGAN demande Vulkan. Essaie le binaire Linux de la même version (`realesrgan-ncnn-vulkan`
20220424) avec le Vulkan logiciel (mesa « lavapipe ») : c'est lent, donc travaille sur des extraits
de 2 s en petite taille. Si c'est impossible, écris « non lancé » avec la raison exacte, et fais
quand même les points 2 et 3 avec un Real-ESRGAN factice : un script qui agrandit les images ×4
avec FFmpeg, donné par `VHSRA_REALESRGAN`.

1. **Même image.** Même instant de la source : image de `apercu_restaure.mp4` contre image de
   l'export. Donne le SSIM (ou le PSNR) et l'écart des moyennes R, G, B. Pour la couleur, utilise
   les scènes réalistes de `tests/test_couleur_film.py`, jamais une mire seule.
2. **Aperçu fait sans IA.** Si le calcul de l'aperçu dépasse 2 minutes, `essayer_ia(apercu=True)`
   propose de continuer sans l'IA, puis l'aperçu se fait sans elle alors que la case reste cochée
   pour le film. L'écran le dit-il ? Si non, l'étiquette de l'image doit le dire (par exemple
   « APRÈS (sans IA) »), et la ligne d'état aussi. Ajoute un test, avec `demander_ia` remplacé
   pour répondre « sans ».
3. **Calage avec l'IA.** Le chemin de l'IA (`_export_ai`) traite le son à part : l'écart bip −
   éclair doit être le même qu'avec le traitement normal, dans l'aperçu et dans l'export
   (tolérance 5 ms), avec et sans dérive.

## Tests et mesures

- Pour chaque mesure : l'extrait, le réglage, la valeur dans l'aperçu, la valeur dans l'export,
  la méthode et la précision. Un petit tableau par point, dans le rapport.
- Lance seulement : `tests/test_ia_apercu.py`, `tests/test_calage_apercu_export.py`,
  `tests/test_apercu_perime.py`, `tests/test_pipeline.py`, `tests/test_couleur_film.py`.
  Pas la suite complète : Claude la lance avant la fusion.
- Un test nouveau doit échouer avec l'ancien code quand il prouve une correction : dis-le dans le
  rapport, avec la sortie.

## Règles

- Un commit par point, poussé tout de suite, avec `[skip ci]` à la fin du titre.
- Aucune nouvelle dépendance Python (onnxruntime, onnx et numpy sont déjà là). Aucun test existant
  affaibli. Un texte d'écran changé : l'assertion vérifie le nouveau texte.
- Jamais de binaire, de modèle ni de vidéo de famille dans le dépôt.
- Fenêtre : rien ne doit dépasser à 1280 × 641 (100, 125 et 150 %) ; `tests/test_ecran_unique.py`
  le vérifie si tu touches à l'écran.
- Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request. L'utilisateur dira « fusionner ».
- Si ton environnement ne peut pas lancer un outil, écris « non lancé » avec la raison : Claude
  mesurera à la livraison.
