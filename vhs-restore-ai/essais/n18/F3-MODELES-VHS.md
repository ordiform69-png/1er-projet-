# Essai n°18, agent F3 : modèles VHS d'OpenModelDB contre l'IA actuelle

Branche `grok/ia-vhs` (banc commun de F4 intégré par fusion de `grok/ia-essai` d9d88e4).
Rien n'a été modifié dans `vhs_restore/`, dans `requirements*.txt` ni dans `VHSRestoreAI.spec`
(le `.spec` n'embarque que `vhs_restore/paquets.json` : `essais/` n'est pas dans le paquet).
Aucun poids, aucun `.onnx`, aucune image dans le dépôt : tout est dans un cache hors dépôt.

## Fichiers

| Fichier | Rôle |
|---|---|
| `f3_modeles.py` | catalogue des 4 modèles : source, SHA-256, licences (aucune dépendance) |
| `f3_convertir_onnx.py` | téléchargement des poids (SHA-256 vérifiée) et conversion ONNX, **à part, une fois** (torch + spandrel + cryptography, dépendances d'essai seulement) |
| `f3_vhs.py` | l'essai : onnxruntime, onnx, numpy, FFmpeg et le module `banc` de F4 |
| `f3_resultats/f3_resultats.csv` | écarts à l'origine, image entière et zones visage / texte |
| `f3_resultats/f3_temps.csv` | temps pendant l'essai complet (machine chargée, voir plus bas) |
| `f3_resultats/f3_chrono.csv` | temps de référence (`--chrono 3`) |

## Candidats (fiches vérifiées le 26/11/2026)

Sources : pages openmodeldb.info ; fiches JSON du dépôt
[OpenModelDB/open-model-database](https://github.com/OpenModelDB/open-model-database/tree/5a35f802749699031d5cbb6ea660b989ebd3ac3d/data/models)
(commit `5a35f80`) ; ancienne base upscale.wiki où les auteurs déclaraient leurs modèles
([archive du 30/05/2023](https://web.archive.org/web/20230530113220/https://upscale.wiki/wiki/Model_Database)).
Aucun dépôt personnel des trois auteurs n'a été trouvé : la licence est celle déclarée sur ces deux bases.

| Modèle | Auteur | Architecture | Échelle | Licence du modèle | Licence des données d'entraînement | Poids (source) | SHA-256 du `.pth` (vérifiée sur le fichier téléchargé) |
|---|---|---|---|---|---|---|---|
| [1x VHS Sharpen](https://openmodeldb.info/models/1x-VHS-Sharpen) | RTX 2080 ti hoarder | ESRGAN (RRDBNet 64nf 23nb), 16,6 M paramètres | 1x | **CC-BY-NC-SA-4.0** | non trouvée (« 4K Blu-Ray movie stills… ran through a VCR onto a VHS », 9 384 images : films du commerce) | [Mega](https://mega.nz/file/Z5IXBSrA#bE9VasE60zLqZ_NggOhs40Z9l2z8DapROZb5VX0F3h0) | `201b4702…2e3ec30e` |
| [1x BaldrickVHSFix V0.2](https://openmodeldb.info/models/1x-BaldrickVHSFixV0-2) | NimRodZorg | ESRGAN (RRDBNet 64nf 23nb), 16,6 M | 1x | **CC-BY-NC-SA-4.0** | non trouvée (« Old vhs film recording… Blu-ray rip of same film », 663 images) | [OpenModelDB (Oracle Cloud)](https://objectstorage.us-phoenix-1.oraclecloud.com/n/ax6ygfvpvzka/b/open-modeldb-files/o/1x-BaldrickVHSFixV0-2.pth) | `9c945b10…81cd5ea1` |
| [2x VHS upscale and denoise Film](https://openmodeldb.info/models/2x-VHS-upscale-and-denoise-Film) | Itewreed | ESRGAN (RRDBNet 64nf 23nb), 16,7 M | 2x | **CC-BY-NC-SA-4.0** | non trouvée (« VHS recording of a movie from TV… Blu-ray rip of that movie ») | [Google Drive](https://drive.google.com/file/d/1LFiaoiPDUoAIfNCTDBm2GzJnWvgjxft9/view) | `22b9b117…62f0ac55` |
| Real-ESRGAN x4plus (IA actuelle, référence) | Xintao Wang | ESRGAN (RRDBNet 64nf 23nb), 16,7 M | 4x | BSD-3-Clause ([LICENSE](https://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE)) | DIV2K : « academic research purpose only » ([page DIV2K](https://data.vision.ee.ethz.ch/cvl/DIV2K/)) ; Flickr2K et OST : non trouvée ([Training.md](https://github.com/xinntao/Real-ESRGAN/blob/master/docs/Training.md)) | [GitHub v0.1.0](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth) | `4fa0d389…9d682f1` |

Empreintes complètes dans `f3_modeles.py` (identiques à celles des fiches OpenModelDB).

**Point à signaler : ces trois modèles ne sont PAS à architecture compacte.** Les fiches indiquent
« ESRGAN 64nf 23nb », c'est-à-dire la même taille que Real-ESRGAN x4plus (environ 16,6 millions de
paramètres, fichier ONNX d'environ 67 Mo chacun ; compté sur les `.onnx` produits). Le temps de
calcul mesuré est donc du même ordre que celui de l'IA actuelle.

### Ce qu'implique CC-BY-NC-SA-4.0 (acceptable pour cet essai, à signaler)

Licence : <https://creativecommons.org/licenses/by-nc-sa/4.0/deed.fr>. À notre lecture (ce n'est pas un avis juridique) :
- **NC (pas d'usage commercial)** : distribuer le logiciel gratuitement avec ces poids est possible.
  Interdit : vendre le logiciel ou une version payante qui les contient, les inclure dans une offre
  payante (publicité, service de numérisation payant…). La restriction suit aussi les utilisateurs :
  une personne qui numérise des cassettes contre rémunération sortirait de la licence.
- **BY (attribution)** : citer l'auteur, le nom du modèle, la licence avec son lien, et indiquer les
  modifications (la conversion en ONNX en est une).
- **SA (partage à l'identique)** : le fichier ONNX converti doit rester sous CC-BY-NC-SA-4.0. Le
  code du logiciel, s'il charge les poids comme fichier séparé, ne nous semble pas devenir une
  adaptation ; à confirmer avant toute intégration.
- **Données d'entraînement** : images de films du commerce (Blu-ray), sans licence trouvée.
- Pour l'IA actuelle : le modèle est sous BSD-3-Clause, mais DIV2K est déclaré « recherche
  académique seulement ». La demande exclut ce cas pour les nouveaux modèles : nous le signalons
  pour Real-ESRGAN, sans conclure.

### L'IA actuelle dans le logiciel (lu, non modifié)

`vhs_restore/upscaler.py` : `RealEsrganUpscaler` appelle l'exécutable `realesrgan-ncnn-vulkan`
avec `-n realesrgan-x4plus -s 4 -f png -t <tuile>` (modèle ncnn, **pas ONNX**). Utilisé par
`pipeline.py` quand `use_ai` est vrai (rendu « Nettoyage au plus fort », profil `maximum`).
Pour comparer sur processeur, l'essai convertit les mêmes poids d'origine (`RealESRGAN_x4plus.pth`)
en ONNX. Le temps réel du logiciel (ncnn, carte graphique ou processeur) n'est pas mesuré ici.

## Méthode

1. `f3_convertir_onnx.py` (une fois) : télécharge chaque `.pth`, vérifie son SHA-256, charge le
   réseau avec spandrel, exporte en ONNX (opset 17, taille d'image libre), vérifie l'écart PyTorch /
   ONNX Runtime (au plus 1,7e-6 sur les 4 modèles) et note le SHA-256 du `.onnx` dans `<nom>.onnx.sha256`.
2. `f3_vhs.py` : pour chaque image de `references.csv` (banc F4, 720 × 576), `banc.degrader`
   (réglages par défaut, graine et nombre d'images inchangés), puis sur l'image du milieu :
   - `degradee` : repère ;
   - `sans_ia` : `banc.chaine_naturelle()` (profil « Bien nettoyé, naturel ») sur les 9 images ;
   - les trois candidats et `realesrgan_x4plus`, en ONNX Runtime (processeur, 8 fils, tuiles 256
     avec recouvrement de 16 pixels) ;
   - `rendu_maximum` : pre_filters du profil `maximum` (avec IA) puis Real-ESRGAN x4.
   Sorties x2 / x4 ramenées en 720 × 576 par moyenne de blocs (cette réduction lisse aussi l'image,
   ce qui avantage les modèles x2 / x4 sur le PSNR : biais à garder en tête).
3. Mesures : PSNR, SSIM, ΔE2000 moyen de `banc.mesurer`.
4. **Détails inventés** (mesure ajoutée par F3) : laplacien de la luminance.
   `hf_rapport` = énergie des fins détails / celle de l'origine (> 1 : détails ajoutés ou accentués ;
   < 1 : image lissée). `hf_ecart` = écart moyen absolu entre ces fins détails et ceux de l'origine.
   Sur l'image entière et sur des zones : deux visages de `visages-krampf` (cadres relevés à l'œil),
   et trois bandes d'une **mire de texte générée par FFmpeg** (`drawtext`, police « Sans » de la
   machine, ici Noto Sans), dégradée par `banc.degrader`. La mire n'est pas une référence du banc F4 ;
   ses lignes portent `banc = F4 banc.py + mire F3` et elle est exclue des moyennes « banc F4 ».
5. Images avant / après (images entières et planches origine | dégradée | sortie par zone) :
   écrites dans le cache hors dépôt (`<cache>/resultats/images`).
6. Temps : temps mur par image 720 × 576. Film de 2 h en PAL :
   **heures = secondes par image × 180 000 / 3 600** (180 000 = 25 images/s × 7 200 s).

## Commandes

Depuis `vhs-restore-ai/`, cache hors dépôt (`VHSRA_N18_CACHE`, défaut `~/.cache/vhsrestore-n18/f3`) :

```
# une fois, dans un environnement d'essai séparé :
pip install torch spandrel onnx onnxruntime cryptography
python essais/n18/f3_convertir_onnx.py
# l'essai (onnxruntime, onnx, numpy, FFmpeg) :
python essais/n18/f3_vhs.py                          # banc complet -> f3_resultats.csv, f3_temps.csv
python essais/n18/f3_vhs.py --extraits <dossier>     # + vrais extraits -> f3_extraits.csv, images avant / après
python essais/n18/f3_vhs.py --chrono 3               # temps seulement -> f3_chrono.csv
```

Les CSV et images sont écrits dans `<cache>/resultats` ; les CSV de ce dépôt (`f3_resultats/`) en
sont une copie.

## Machine des mesures (26/11/2026)

Machine Linux partagée (bac à sable) : « Intel(R) Xeon(R) Processor », 8 cœurs (1 fil par cœur),
15 Go de mémoire, Linux 6.12, Python 3.13.5, onnxruntime 1.32.0, onnx 1.23.2, numpy 2.5.5,
FFmpeg 7.1.5. Conversion : torch 2.15.0+cpu, spandrel 0.4.2. ONNX Runtime : 8 fils.

**Charge** : d'autres essais tournaient en même temps. Pendant l'essai complet, charge moyenne
1 min de 11 à 20 (pour 8 cœurs) : les temps de `f3_temps.csv` sont gonflés (jusqu'à 84 s/image).
Le chronométrage `--chrono 3` a été lancé machine plus calme (charge 0,7 au départ, 5 à 8 pendant
la mesure, à cause d'autres agents) : ce sont les chiffres retenus ci-dessous, probablement encore
un peu pessimistes.

## Résultats mesurés

### Écart à l'origine, banc F4 (5 images, moyenne ; image entière)

Plus haut = mieux pour PSNR et SSIM ; plus bas = mieux pour ΔE2000. `hf_rapport` proche de 1 = autant de fins détails que l'original.

| Variante | PSNR (dB) | SSIM | ΔE2000 | hf_rapport |
|---|---|---|---|---|
| dégradée (repère) | 19,99 | 0,447 | 13,82 | 1,13 |
| sans IA, « Bien nettoyé, naturel » | 19,33 | 0,683 | 14,03 | 0,98 |
| 1x VHS Sharpen | 12,88 | 0,569 | 19,58 | 0,79 |
| 1x BaldrickVHSFix | 19,46 | 0,620 | 14,48 | 0,55 |
| 2x VHS upscale and denoise Film | 17,99 | 0,535 | 15,24 | 1,47 |
| Real-ESRGAN x4plus seul (ONNX) | 20,68 | 0,723 | 11,65 | 0,35 |
| rendu « Nettoyage au plus fort » (pré-filtres + Real-ESRGAN) | 19,49 | 0,722 | 13,90 | 0,42 |

Détail par image : `f3_resultats/f3_resultats.csv`. Contrôle : `reference.py` de F4 relancé sur
cette machine donne exactement nos chiffres « dégradée » et « sans IA » ; le
`resultats-reference.csv` poussé par F4 en diffère légèrement (ex. intérieur, dégradée :
19,27 dB contre 19,02 dB), sans doute une autre machine ou version de FFmpeg : à vérifier par F4.

### Détails inventés : zones visage (2 zones) et texte (3 bandes de la mire F3), moyennes

| Variante | Visage PSNR | Visage SSIM | Visage hf_rapport | Visage hf_ecart | Texte PSNR | Texte SSIM | Texte hf_rapport | Texte hf_ecart |
|---|---|---|---|---|---|---|---|---|
| dégradée | 21,58 | 0,475 | 2,47 | 16,22 | 18,96 | 0,467 | 0,96 | 30,70 |
| sans IA | 20,45 | 0,795 | 2,37 | 15,48 | 19,03 | 0,806 | 0,80 | 26,86 |
| 1x VHS Sharpen | 13,21 | 0,722 | 1,49 | 10,95 | 11,31 | 0,683 | 0,72 | 28,58 |
| 1x BaldrickVHSFix | 21,79 | 0,775 | 1,25 | 9,75 | 18,72 | 0,772 | 0,48 | 22,88 |
| 2x VHS Film | 19,03 | 0,581 | 3,93 | 25,10 | 16,94 | 0,609 | 1,35 | 33,31 |
| Real-ESRGAN x4plus | 23,03 | 0,915 | 0,36 | 5,86 | 22,87 | 0,973 | 1,12 | 10,64 |
| rendu « Nettoyage au plus fort » | 21,14 | 0,904 | 0,50 | 6,03 | 21,20 | 0,968 | 1,13 | 11,41 |

Sur le visage dégradé, le bruit fait déjà monter `hf_rapport` (2,47) : une valeur élevée mêle bruit
restant et détails ajoutés. Seul « 2x VHS Film » dépasse l'image dégradée sur les visages
(hf_rapport 3,93, hf_ecart 25,10) : ce sont des fins détails absents de l'original. Les planches
hors dépôt montrent à l'œil une trame régulière sur la peau pour ce modèle, un assombrissement
et une teinte chaude pour VHS Sharpen, des taches de couleur pour Baldrick, une peau lisse pour
Real-ESRGAN (observation visuelle, pas une mesure).

### Temps par image, processeur, ONNX Runtime 8 fils, 720 × 576 (`--chrono 3`, médiane de 3 passes)

| Variante | s / image (médiane ; min – max) | Film de 2 h (180 000 images) |
|---|---|---|
| sans IA (FFmpeg, démarrage inclus) | 0,014 (0,014 – 0,015) | 0,7 h |
| 1x VHS Sharpen | 16,96 (16,23 – 17,19) | 848 h |
| 1x BaldrickVHSFix | 16,63 (15,79 – 19,05) | 831 h |
| 2x VHS upscale and denoise Film | 17,99 (17,85 – 19,79) | 900 h |
| Real-ESRGAN x4plus (ONNX) | 18,84 (18,24 – 21,69) | 942 h |
| rendu « Nettoyage au plus fort » (pré-filtres + Real-ESRGAN) | 17,17 (16,35 – 18,56) | 858 h |

Formule : heures = s/image × 180 000 / 3 600. Exemple : 16,96 × 50 = 848 h. Le « rendu maximum »
mesuré plus vite que Real-ESRGAN seul vient de la variation entre passes sur une machine partagée,
pas d'un vrai gain. Tous les modèles ont la même architecture : des temps proches sont attendus.

## Non mesuré

- Vrais extraits de cassettes (`--extraits`) : aucun fourni ; non mesuré.
- Temps de l'IA telle que le logiciel l'appelle (realesrgan-ncnn-vulkan, carte graphique ou
  processeur, PC du père) : non mesuré.
- Temps sans tuiles (`--tuile 0`), autre nombre de fils, ou machine au repos complet : non mesuré.
- BaldrickVHSFix sur source entrelacée : non mesuré (le banc est progressif ; l'auteur le réserve
  aux sources désentrelacées).
- Notes des juges de qualité (F2) sur ces sorties : non mesuré.
- Taille mémoire utilisée par chaque modèle : non mesurée.

Aucune recommandation n'est tirée ici : la synthèse revient à F4.
