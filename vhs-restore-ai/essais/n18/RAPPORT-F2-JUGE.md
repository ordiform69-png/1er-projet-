# Demande n°18, agent F2 : un juge de qualité choisit la force du débruitage et de la netteté

Branche `grok/ia-juge`, partie de `38554ea`. Le banc F4 a été repris de `grok/ia-essai` @ `d9d88e4` (copie des fichiers dans un commit normal, sans fusion).
Rien n'a été touché dans `vhs_restore/`, dans `requirements*.txt` ni dans le paquet. Le dépôt ne contient aucun poids, aucune image et aucune vidéo.
Toutes les valeurs ci-dessous ont été **mesurées sur la box** le 26/11/2026 (heure de Paris), sauf mention contraire. Conditions : Intel Xeon, 8 cœurs, onnxruntime 1.32.0, numpy 2.5.5, FFmpeg 7.1.5.
**Attention :** la box était partagée avec d'autres agents. La charge moyenne allait de 11 à 15 pendant les mesures (elle est notée dans `resultats-juge-chrono.csv`). Les temps sont donc pessimistes et bruités.

## Relancer (une commande, depuis `vhs-restore-ai/`)

```
python essais/n18/essai_juge.py                     # télécharge les poids (SHA-256), banc F4 complet, CSV
python essais/n18/essai_juge.py --extraits <dossier> # en plus : vrais extraits → notes, temps, PNG avant/après (hors dépôt)
python essais/n18/juges_iqa.py --chrono              # temps par image 720×576 → resultats-juge-chrono.csv
python essais/n18/essai_juge.py --resumer-seulement  # recalcule le résumé depuis le détail
```

Les poids vont dans `~/vhs-n18-juge/poids` (variable `VHS_N18_JUGE` pour changer de dossier). Les images du banc vont dans `essais/n18/cache/` et les PNG dans `essais/n18/sorties/juge/`, deux dossiers ignorés par git.
Dépendances : onnxruntime, numpy et FFmpeg. Les juges tournent en ONNX sur le processeur (`CPUExecutionProvider`).

## Protocole

1. **Images** : les 5 références CC0 du banc F4 (`references.csv` : intérieur sombre, extérieur, visages, peau, ciel), recadrées en 720 × 576.
2. **Dégradation** : `banc.degrader`, sans changer `images` (9) ni `graine` (1). On mesure trois niveaux de bruit, et rien d'autre ne varie : `defaut` (luma 12 / chroma 24, réglage F4), `leger` (6 / 12) et `fort` (20 / 36). Cela donne **15 cas**.
3. **Réglages sûrs (9)** : la chaîne du logiciel `banc.chaine_naturelle()` (profil « Bien nettoyé, naturel »), dont on remplace seulement :
   - le débruitage des trois profils de `profiles.py` : fidèle `hqdn3d=1.5:3:2:4` ; équilibré `removegrain` + `hqdn3d=3:5:4.5:7` ; maximum `removegrain` + `hqdn3d=4:7:6:10` ;
   - la netteté `cas` des trois rendus : 0 / 0,30 / 0,45.

   Le script vérifie que ces valeurs sont bien celles de `profiles.py`. Le réglage `equilibre+n030` est exactement la chaîne actuelle.
4. **Variantes hors grille** (pour mesurer les biais) : `aucun` (image dégradée brute), `biais_trop_net` (équilibré + cas 0,45 + `unsharp=5:5:1.2`) et `biais_trop_colore` (équilibré + cas 0,3 avec saturation 1,45 au lieu de 1,08). `cas=strength=1` n'a pas été retenu : mesuré dégénéré sur FFmpeg 7.1 (PSNR d'environ 10 dB).
5. **Mesures** : PSNR, SSIM et ΔE2000 de `banc.mesurer`, sur l'image du milieu. Le « meilleur » réglage est le meilleur rang moyen PSNR + SSIM + ΔE (le **consensus**). On compte aussi le meilleur selon chaque mesure prise seule.
6. **Juges** : chaque juge note les 12 images, et son choix est la meilleure note parmi les 9 réglages sûrs. On calcule ensuite :
   - le taux de bon choix ;
   - le top 3 ;
   - la perte par rapport au meilleur (dB de PSNR, SSIM, ΔE) ;
   - le ρ de Spearman entre la note et chaque mesure (moyenne sur les 15 cas) ;
   - le biais : part des cas où le juge note la variante trop nette, trop colorée ou brute au-dessus du meilleur réglage.
7. **Témoins sans IA** : on fait la même chose avec un réglage fixe, pour chacun des 9 réglages.
8. **Deux façons de nourrir les juges** (les exports ONNX ont une entrée fixe de 224 × 224) :
   - `tuiles` : moyenne de 6 tuiles 224 × 224 prises à la définition d'origine ;
   - `redim` : l'image entière réduite à 224 × 224.

   LIQE garde son découpage d'origine (`natif`, 15 tuiles au pas de 32, comme dans `pyiqa`).

## Licences (vérifiées à la source le 26/11/2026)

Les ONNX viennent tous de [`86Cao/IQA-ONNX-Models`](https://huggingface.co/86Cao/IQA-ONNX-Models), révision figée `2e32ab1ad40c592da9d199f4c7fb8a2383bbae94`.
Sa fiche annonce « apache-2.0 », mais précise : « Original model weights are subject to their respective licenses ». Ces fichiers sont des exports des poids de [IQA-PyTorch](https://github.com/chaofengc/IQA-PyTorch). Un ré-hébergeur ne peut pas lever les conditions d'origine. **Il faut donc retenir les licences d'origine, toutes non commerciales.**

| Juge | Code / architecture | Poids | Données d'entraînement |
|---|---|---|---|
| **CLIP-IQA+** | [CLIP-IQA officiel : S-Lab License 1.0](https://github.com/IceClear/CLIP-IQA/blob/v2-3.8/LICENSE) (redistribution « for non-commercial purpose ») ; ré-implémentation [IQA-PyTorch : PolyForm Noncommercial 1.0.0](https://github.com/chaofengc/IQA-PyTorch/blob/main/LICENSE) ; dorsale [CLIP RN50 d'OpenAI : MIT](https://github.com/openai/CLIP/blob/main/LICENSE) | `CLIP-IQA+_learned_prompts-603f3273.pth` sur [chaofengc/IQA-PyTorch-Weights : CC-BY-NC-SA-4.0](https://huggingface.co/chaofengc/IQA-PyTorch-Weights) | KonIQ-10k ([page officielle](https://database.mmsp-kn.de/koniq-10k-database.html) : « freely available to the research community », sans licence commerciale écrite) ; données de CLIP non publiées |
| **LIQE** | [LIQE officiel : MIT](https://github.com/zwx8981/LIQE/blob/main/LICENSE) ; IQA-PyTorch : PolyForm NC 1.0.0 | **`liqe_mix.pt`** (voir plus bas), même dépôt de poids : CC-BY-NC-SA-4.0 | Six bases d'après l'[article LIQE, §4](https://arxiv.org/abs/2303.14968) : LIVE, CSIQ, KADID-10k, LIVE Challenge, BID et KonIQ-10k. La licence de chaque base n'a pas été vérifiée une à une (**non vérifié**). |
| **MUSIQ** | [google-research : Apache-2.0](https://github.com/google-research/google-research/blob/master/LICENSE) ; IQA-PyTorch : PolyForm NC 1.0.0 | Point de contrôle KonIQ officiel de Google ([README MUSIQ](https://github.com/google-research/google-research/tree/master/musiq)), converti par IQA-PyTorch (`musiq_koniq_ckpt-e95806b9.pth`) : CC-BY-NC-SA-4.0 | KonIQ-10k (même remarque) |
| DOVER-Mobile (option) | [teowu/DOVER → DOVER-Dev : MIT](https://github.com/teowu/DOVER-Dev/blob/master/LICENSE) | `DOVER-Mobile.pth`, release GitHub v0.5.0. La licence propre des poids n'est pas indiquée à part. | LSVQ (licence **non vérifiée**) |

À trancher par Claude :
- **Non commercial.** Tous les poids sont en CC-BY-NC-SA-4.0, et le code d'IQA-PyTorch est en PolyForm NC. C'est acceptable selon la demande, puisque le logiciel est gratuit, mais **il faut le signaler**.
- **KonIQ-10k.** La base est offerte « à la communauté de recherche » sans licence écrite. Ce n'est pas un « recherche seulement » explicite comme MIT-Adobe FiveK, mais c'est une **zone grise**.
- **Fiche Hugging Face inexacte.** Elle dit « Pretrained on KonIQ-10k (all models) » et cite pour LIQE l'arXiv 2304.00451, qui est en fait Re-IQA.

## Contrôles des exports ONNX (sur la box, PyTorch servant SEULEMENT à comparer, hors dépôt)

- **SHA-256 des 6 fichiers** (`.onnx` et `.onnx.data`) : identiques aux empreintes LFS de Hugging Face. Ils sont figés dans `juges_iqa.py`.
- **CLIP-IQA+** : l'ONNX donne exactement la note de `pyiqa` 0.1.16 (`clipiqa+`) sur la même image 224 × 224, sur 6 images (écart < 1e-4).
- **LIQE** :
  - Le graphe normalise lui-même l'entrée : il attend des valeurs dans [0, 1].
  - Il prend `logit_scale` en logarithme et fait exp() lui-même. La valeur 4.6051702 a été lue dans le point de contrôle.
  - Il contient 495 textes (5 qualités × 9 scènes × 11 défauts), donc le mode multitâche.
  - Résultat mesuré : l'ONNX donne **exactement `pyiqa liqe_mix`** sur 6 images (écart < 1e-4), et pas `liqe` (KonIQ), qui s'écarte jusqu'à 2,2 points. **L'ONNX est donc LIQE « mix »**, entraîné sur six bases, et pas sur KonIQ seule.
- **MUSIQ** : l'export ne garde qu'une seule échelle de 224 × 224, alors que l'original est multi-échelle. Contre `pyiqa musiq` (multi-échelle) sur la même image 224, l'écart mesuré va de 0,1 à 18,3 points selon l'image. La comparaison à une seule échelle a été interrompue : **non vérifié**.
- **DOVER-Mobile** : **non mesuré**. Aucun ONNX n'est publié, et il aurait fallu faire l'export avec le `convert_to_onnx.py` officiel. C'est en plus un modèle **vidéo** (il note des extraits, pas des images), ce qui ne colle pas avec « l'image du milieu » du banc. Il n'a pas été fait faute de temps.

## Résultats mesurés (15 cas : 5 images × 3 niveaux de bruit ; `resultats-juge-resume.csv`)

| Juge (mode) | ONNX CPU | Taille | Temps / image 720×576 (méd., 8 fils) | ρ PSNR | ρ SSIM | ρ ΔE | Bon choix (consensus) | Top 3 | Perte PSNR (dB) | Préfère trop net | Préfère trop coloré | Préfère brut |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **CLIP-IQA+ (tuiles)** | oui | 153,2 Mo | 313 ms | **0,71** | **0,73** | 0,49 | 53,3 % (8/15) | 80 % | 0,064 | **0 %** | 6,7 % | 0 % |
| CLIP-IQA+ (redim) | oui | 153,2 Mo | 247 ms | −0,04 | 0,18 | −0,10 | 20 % | 33 % | 0,248 | 73 % | 47 % | 27 % |
| MUSIQ (tuiles) | oui | 109,7 Mo | 397 ms | 0,17 | 0,22 | 0,05 | 20 % | 53 % | 0,320 | 67 % | 20 % | 40 % |
| MUSIQ (redim) | oui | 109,7 Mo | 196 ms | −0,35 | −0,31 | −0,27 | 6,7 % | 13 % | 0,461 | 80 % | 53 % | 60 % |
| LIQE (natif, = liqe_mix) | oui | 353,9 Mo | 767 ms | −0,21 | −0,11 | −0,19 | 13,3 % | 13 % | 0,398 | 100 % | 73 % | 100 % |
| DOVER-Mobile | non mesuré (pas d'ONNX publié) | non mesuré | non mesuré | — | — | — | — | — | — | — | — | — |
| *Témoin fixe `maximum+n0`* | — | — | — | — | — | — | **60 % (9/15)** | 93 % | **0,0035** | — | — | — |
| *Témoin fixe `equilibre+n0`* | — | — | — | — | — | — | 26,7 % | 100 % | 0,031 | — | — | — |
| *Témoin fixe `equilibre+n030` (chaîne actuelle)* | — | — | — | — | — | — | 0 % | 0 % | 0,361 | — | — | — |

Temps avec 1 seul fil (`resultats-juge-chrono.csv`) :

| Juge (mode) | Temps / image |
|---|---|
| CLIP-IQA+ (tuiles) | 583 ms |
| CLIP-IQA+ (redim) | 214 ms |
| MUSIQ (tuiles) | 199 ms |
| MUSIQ (redim) | 138 ms |
| LIQE | 875 ms |

Avec une charge de 11 à 15 sur 8 cœurs, le gain apporté par les fils n'est pas mesurable proprement. Appliquer un réglage FFmpeg prend 22 ms par image (médiane sur 180 passages, démarrage de FFmpeg inclus).

Autres constats mesurés :
- **Meilleur réglage selon le consensus** :
  - bruit léger : `equilibre+n0` 3 fois, `fidele+n0` 2 fois ;
  - bruit par défaut : `maximum+n0` 4 fois, `equilibre+n0` 1 fois ;
  - bruit fort : `maximum+n0` 5 fois.

  Sur ce banc, la netteté `cas` n'améliore **jamais** PSNR, SSIM ou ΔE : le meilleur réglage est toujours à cas 0. Le bon débruitage suit le niveau de bruit.
- **CLIP-IQA+ (tuiles)** :
  - bruit fort : 5 bons choix sur 5 ;
  - bruit par défaut : 3 sur 5 ;
  - bruit léger : **0 sur 5**. Il choisit alors le réglage voisin, souvent un débruitage plus fort.
- **LIQE** reste collé à son plancher : il note de 1,01 à 2,45 sur 5 les images de la grille (moyenne 1,48), et il note toujours l'image brute au-dessus. La dégradation de lumière et de couleur du banc (gamma, saturation, dominante, noirs relevés) l'écrase.
- **Le mode compte beaucoup** : réduire l'image à 224 × 224 efface le bruit et la netteté que l'on cherche à juger. Le mode `redim` ne sert à rien pour ce choix.

## Temps pour un film de 2 heures (ESTIMÉ, pas mesuré)

C'est un calcul fait à partir des temps mesurés, avec deux hypothèses : une scène toutes les 10 s, soit 720 scènes, et un seul point d'échantillonnage par scène.
- Par scène : 9 réglages × 9 images FFmpeg × 22 ms ≈ 1,8 s, plus 9 notes CLIP-IQA+ (tuiles) × 313 ms ≈ 2,8 s, soit ≈ 4,6 s.
- Pour le film : ≈ 56 min en plus.
- Avec 3 points par scène, il faudrait environ 3 fois plus.

## Verdict et recommandation

- **CLIP-IQA+ en mode tuiles** est le seul juge qui suit vraiment les mesures (ρ 0,71 pour PSNR, 0,73 pour SSIM). Il ne préfère pas la variante trop nette (0 cas sur 15) et presque jamais la trop colorée (1 sur 15). **Mais il ne bat pas un simple réglage fixe** : 53 % de bons choix contre 60 % pour `maximum+n0`, avec une perte moyenne de 0,064 dB contre 0,0035 dB. Il se trompe aussi sur tous les cas à bruit léger.
- **MUSIQ et LIQE sont à écarter** pour ce rôle : corrélation nulle ou négative, et nette préférence pour l'image trop nette (67 à 100 %) ou brute. LIQE est en plus le plus lourd (354 Mo) et le plus lent.
- **Recommandation** : ne pas mettre de juge sans référence dans le logiciel pour choisir la force du débruitage et de la netteté. Sur ce banc, aucun juge ne fait mieux qu'un réglage fixe, alors qu'un juge ajoute plus de 110 Mo de poids sous licence non commerciale, avec un doute sur KonIQ.
  - Si l'on veut garder une piste, CLIP-IQA+ (tuiles) pourrait servir de **garde-fou contre l'excès de netteté**, et non de sélecteur. Il faudrait d'abord le re-tester sur de vrais extraits (`--extraits`).
  - Les chiffres suggèrent plutôt que **le niveau de bruit** décide du bon débruitage : un estimateur de bruit simple, sans IA, pourrait suffire. Ce n'est pas testé ici.
  - Ils indiquent aussi que `cas` n'améliore pas les trois mesures sur ce banc. Cela ne veut pas dire qu'il est inutile pour l'œil : la netteté perçue n'a pas été évaluée.

## Limites

- 15 cas seulement : 5 images × 3 niveaux de bruit, avec un bruit de synthèse et une seule graine.
- La « qualité perçue » est approchée par PSNR, SSIM et ΔE : aucun jugement humain.
- La box était partagée : les temps sont bruités.
- DOVER-Mobile n'a pas été mesuré.
- MUSIQ à une seule échelle n'a pas été vérifié contre l'original.
- Les licences des données de LIQE mix n'ont pas été vérifiées base par base.
