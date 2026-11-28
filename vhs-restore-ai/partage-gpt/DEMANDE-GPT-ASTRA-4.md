# Demande Astra n°4 : corriger le chemin de l'IA, et deux retouches de la n°3 (pour ChatGPT)

Claude a vérifié `gpt/ia-apercu` (`f9cc499`) : tes 16 tests passent chez lui (1 écarté :
DeepFilterNet absent), le code fait ce que dit le rapport, et ta mesure du décalage d'une image
dans l'export IA est **reproduite** avec un Real-ESRGAN factice. Excellent travail, et rapport
très clair. Claude n'a pas pu refaire la mesure de `-D` (le téléchargement d'un exécutable
extérieur est refusé dans son environnement) : ta mesure fait foi.

Cette fois, `_export_ai` t'est ouvert. Continue sur la même branche **`gpt/ia-apercu`**, à partir
de `f9cc499`. Rapport : compléter `partage-gpt/RAPPORT-GPT-IA-APERCU.md` (nouvelle partie « n°4 »).

## P0 : l'export IA décale l'image d'une image (40 ms)

**Cause trouvée par Claude** (film à repères AVI MPEG-2, Real-ESRGAN factice) :
- la source décodée commence à 0,04 s (première image), le son à 0 ; le fichier intermédiaire
  `inter.mkv` garde ce rapport (éclair à 1,08 s comme la source) ;
- l'extraction des PNG (`-frames:v cnt … %08d.png`) passe par la cadence fixe de la sortie image2 :
  elle **ajoute une image en tête** pour combler 0 → 0,04 s (201 PNG au lieu de 200 pour tout le
  fichier ; chaque paquet commence aussi par un doublon, et son dernier cadre tombe) ;
- l'encodeur final ajoute **en plus** `-itsoffset v_off` (0,04 s) : l'avance est comptée deux fois.
  Essai à la main sur `inter.mkv` : avec `-itsoffset`, bip − éclair = −60 ms ; sans, −20 ms
  (= la source et l'export normal).

**À faire** : une seule des deux compensations. Choix conseillé : extraction sans doublon ni
perte (`-fps_mode passthrough`, présent dans FFmpeg 5.1 et plus ; le logiciel utilise 6.1 à 9.1),
et garder `-itsoffset v_off` et les sauts `-ss` des paquets, qui supposent « image k du paquet =
image `done + k` de `inter.mkv` ». Vérifie :
- le nombre de PNG de chaque paquet est exactement `cnt`, et aucune image n'est perdue ni doublée
  aux limites des paquets (`AI_CHUNK_FRAMES`) : compare l'image k de l'export à l'image k de
  `inter.mkv` (même motif, par exemple un numéro d'image dessiné dans la source) ;
- bip − éclair identique à l'export normal (tolérance 5 ms), sans dérive et avec ±400 ms/min,
  aperçu et export, extrait au début **et** au milieu du film, sources AVI (MPEG-2) et MKV (FFV1).

## P0 bis : l'aperçu IA plante quand le son doit être retardé

Avec une dérive négative, l'aperçu pris au milieu part d'un décalage positif (le son est
retardé) : `audio_filters` met alors `adelay` au début d'un son déjà avancé par `-ss`. On savait
déjà que `adelay` au début d'une entrée sautée donne des horodatages invalides. Ici, ils passent
dans `inter.mkv`, et `v_off` devient absurde : chez toi, `Invalid duration for option itsoffset:
192153584101141` ; chez Claude, aucune image extraite. Corrige la cause dans `_export_ai`, sans
changer le son de l'export normal. Par exemple : son lu à part, comme pour les morceaux
(`premier = (départ − décalage) × vitesse`), ou `v_off` calculé seulement à partir de l'image. Le
même cas doit aussi passer avec un « Retarder la voix » simple (décalage positif, sans dérive),
aperçu au milieu.

## P1 : deux retouches de la n°3

1. **Pas d'alerte quand DeepFilterNet n'est pas installé du tout.** Le père de l'utilisateur
   n'installera pas DeepFilterNet (conseil de Claude). Avec « Nettoyage au plus fort », il verrait
   « DeepFilterNet indisponible » à chaque aperçu. L'alerte reste quand DeepFilterNet est
   **présent mais inutilisable** (par exemple « Accès refusé » par l'antivirus, `tools.deepfilter.path`
   renseigné mais pas `ok`), ou quand il échoue. Adapte le test (les deux cas).
2. **L'alerte s'ajoute à la phrase de fin d'aperçu, elle ne la remplace pas.** Aujourd'hui,
   « Aperçu prêt (extrait de …). Comparez avec les boutons « Avant » et « Après ». » et la durée
   annoncée disparaissent. Garde-les, et mets l'alerte (et « sans agrandissement IA ») à la suite.
   La ligne doit rester lisible à 1280 × 641 et 150 % (`tests/test_ecran_unique.py`).

## P2 : le volume de l'aperçu (à mesurer, puis à corriger si c'est simple)

Ta mesure P0.2 montre une voix jusqu'à 4 à 10 dB plus faible dans l'aperçu que dans le film, au
même endroit, avec « Nettoyage au plus fort ». Cause probable : `dynaudnorm` (fenêtre d'environ
4 s) et DeepFilterNet démarrent sans passé au début de l'extrait. Le logiciel a déjà une
« chauffe » (`export(…, chauffe=…)`, utilisée par la reprise) : des secondes lues avant l'extrait,
traitées, puis retirées. Attention : le son de la chauffe n'est retiré qu'avec `morceau=True`, et
ce chemin gère déjà le décalage et la dérive à la bonne position. Si tu l'utilises pour l'aperçu,
retire alors la correction accumulée ajoutée dans `make_preview` (`15b6e75`), sinon elle compterait
deux fois. Mesure avant et après (niveau de la voix et du souffle, à 0,5 s, 2 s et 5 s dans
l'extrait). Si le chemin de l'IA ne permet pas la chauffe, dis-le simplement.

## Tests

- Lance : `tests/test_ia_apercu.py`, `tests/test_calage_apercu_export.py`, `tests/test_apercu_perime.py`,
  `tests/test_pipeline.py`, `tests/test_son.py`, `tests/test_reprise.py`, `tests/test_ecran_unique.py`.
- Le Real-ESRGAN factice pour les tests : un petit script écrit dans `tmp_path` qui agrandit les PNG
  ×4 avec FFmpeg et garde les noms, plus `models/realesrgan-x4plus.param` (fichier vide) à côté :
  c'est ce que la détection vérifie. Donné par `VHSRA_REALESRGAN`.
- Chaque correction a un test qui échoue avec l'ancien code : donne la sortie dans le rapport.

## Règles (inchangées)

Un commit par point, poussé tout de suite, `[skip ci]` à la fin du titre. Aucune nouvelle
dépendance. Aucun test affaibli ; un texte d'écran changé → l'assertion vérifie le nouveau texte.
Jamais de binaire, de modèle ni de vidéo de famille dans le dépôt. Ni fusion ni pull request :
l'utilisateur dira « fusionner ». Ce que tu ne peux pas lancer : « non lancé », avec la raison.
