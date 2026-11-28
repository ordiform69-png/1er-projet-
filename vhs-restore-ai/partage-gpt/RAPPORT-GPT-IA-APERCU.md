# Avant / après et export — vérification Astra n°3

Base `b34e1f8`. Mesures sous Linux sur fichiers synthétiques, avec FFmpeg. Les secondes sont comptées depuis le début du fichier source, sauf les fenêtres du tableau de voix qui sont relatives à l’extrait.

## P0.1 — Calage DeepFilterNet

DeepFilterNet Linux x86-64 musl 0.5.6, fourni par `VHSRA_DEEPFILTER`. Film à éclairs et bips de 60 s à 25 i/s et 48 kHz, profil Maximum, sans dérive. Extrait de 4 à 10 s. Début audible par silencedetect à −30 dB, éclair par luminance, comparaison des repères communs (7,1 et 9,1 s). Valeurs en ms arrondies à 0,1 ms ; résolution sonore 1 échantillon.

| Traitement | Bip − éclair, aperçu | Bip − éclair, export |
|---|---:|---:|
| Nettoyage habituel | −20,0 | −20,0 |
| DeepFilterNet avec l’ancien appel `-D` | −50,0 | −50,0 |
| DeepFilterNet après retrait de `-D` | −20,0 | −20,0 |

Contrôle sur WAV seul : le bip à 3,060021 s ressort à 3,030021 s avec `-D`, et à 3,060021 s sans cette option. Certains premiers bips sont atténués sous le seuil de détection. Le test de régression mesure plusieurs repères communs. Sur la base : `assert 30.00000000000025 <= 5` ; sur la correction : `1 passed`.

## P0.2 — Voix et souffle

Voix synthétique Flite SLT, phrase répétée toutes les 4 s, souffle blanc ajouté (amplitude 0,025, graine 83). Source de 12 s ; extrait de 4 à 10 s ; profil Maximum, vrai DeepFilterNet, sans dérive. Décodage mono à 48 kHz. RMS en dBFS (arrondi au dixième), corrélation normalisée au pic de corrélation croisée, alignement à l’échantillon (16 échantillons, 0,33 ms).

| Fenêtre dans l’extrait | Son | Aperçu dBFS | Export dBFS | Corrélation |
|---|---|---:|---:|---:|
| 0–0,1 s | Démarrage | −57,1 | −45,6 | 0,793 |
| 0,25–0,5 s | Voix | −19,0 | −9,3 | 0,999 |
| 1–2 s | Voix | −17,8 | −12,4 | 0,982 |
| 2,5–3,5 s | Souffle seul | −45,8 | −45,6 | 0,967 |
| 4,25–5,5 s | Voix suivante | −13,9 | −9,9 | 0,985 |

La forme d’onde de la voix est déjà très proche à 0,25 s. Le niveau ne converge pas durablement pendant les 6 s observées : l’export reste environ 4 dB plus fort sur la dernière fenêtre de voix. Le souffle seul diffère de 0,25 dB. Ces valeurs décrivent le profil complet, qui comprend aussi un gain dynamique. Elles ne permettent pas d’attribuer au seul modèle une durée universelle de démarrage.

## P0.3 — Repli du son

Essai depuis la fenêtre, film PAL de 4 s avec son, profil Maximum, agrandissement IA désactivé.

| Outil | Après aperçu | Dans le bilan du film |
|---|---|---|
| DeepFilterNet absent | « DeepFilterNet indisponible. Le nettoyage habituel a été utilisé. » | Même avertissement |
| Exécutable qui quitte en erreur | Même avertissement | Même avertissement |

Sur la base, les deux cas échouent dès la première assertion : `assert 'DeepFilterNet indisponible. Le nettoyage habituel a été utilisé.' in "Aperçu prêt (extrait de 0 s à 4 s)…"`. La correction conserve l’information de repli pendant le travail en cours, y compris lorsque plusieurs morceaux sont traités.

## P1.1 — Image restaurée en pleine taille

Vrai Real-ESRGAN ncnn-vulkan 20220424 Ubuntu, modèle realesrgan-x4plus, Vulkan logiciel Mesa lavapipe 25.0.7 (LLVM 19). Pièce et jardin de test_couleur_film, réduits à 64 × 48, cinq images/s, une seconde chacun. Profil Équilibré avec IA ; même instant dans apercu_restaure.mp4 et dans l’export (1440 × 1080). Décodage RGB24 avec FFmpeg, PSNR calculé sur les trois canaux ; différences signées aperçu moins export en niveaux sur 255.

| Scène / instant | PSNR aperçu-export | ΔR moyen | ΔG moyen | ΔB moyen |
|---|---:|---:|---:|---:|
| Pièce, 0,4 s | 46,99 dB | +0,056 | −0,045 | +0,039 |
| Jardin, 1,4 s | 46,81 dB | −0,018 | −0,001 | −0,021 |

Sur ces deux images, rendu très proche, avec de petites différences d’encodage. La comparaison côte à côte reste limitée à 540 lignes.

## P1.2 — L’utilisateur choisit un aperçu sans IA

| Réglage de départ | Décision dans le dialogue (> 2 min) | Étiquette et ligne d’état | Réglage du film |
|---|---|---|---|
| Amélioration IA cochée | Continuer sans l’IA | « APRÈS (sans IA) » et « Aperçu prêt sans agrandissement IA. L’IA reste cochée pour la restauration. » | Case toujours cochée |

Le test pilote la fenêtre, simule un agrandisseur lent et remplace demander_ia pour répondre « sans ». Sortie sur la base : `assert 'APRÈS' == 'APRÈS (sans IA)'`. Après correction : `1 passed`. Les indications de repli son et image peuvent apparaître ensemble.

## P1.3 — La voie image IA peut décaler le film d’une image

Film de 8 s, 25 i/s, éclairs et bips du même jeu de repères, réduit à 32 × 24 en FFV1/PCM. Première image source à 40 ms, son à zéro (ffprobe). Profil Équilibré, sortie 1080, DeepFilterNet désactivé. Extrait 4–6 s, repère vers 5,1 s. Agrandisseur de contrôle donné par VHSRA_REALESRGAN : script qui lit les PNG par ordre, agrandit ×4 avec FFmpeg et conserve les noms. L’extraction, les horodatages, l’encodage et le multiplexage sont ceux du logiciel. Écart bip − éclair en ms, arrondi à 0,1 ms, même détection que P0.1.

| Dérive (ms/min) | Chemin | Aperçu | Export | Différence export IA − normal |
|---:|---|---:|---:|---:|
| 0 | Normal | −19,8 | −20,0 | |
| 0 | IA | −19,8 | −60,0 | −40,0 ms |
| +400 | Normal | −62,8 | −66,7 | |
| +400 | IA | −62,8 | −106,7 | −40,0 ms |
| −400 | Normal | +2,6 | −3,1 | |
| −400 | IA | Échec avant production | −43,1 | −40,0 ms |

**Seuil de 5 ms dépassé sur les exports IA.** Sans dérive, le premier éclair est à 1,08 s dans la source et dans l’export normal, à 1,12 s dans l’export IA. Les deux exports déclarent une première image à 0,04 s. Le décalage porte donc bien sur le contenu et se distingue de l’avance connue du filtre atempo. Pour l’aperçu à −400, FFmpeg refuse l’horodatage transmis par le moteur : `Invalid duration for option itsoffset: 192153584101141.156250`. Le chemin fautif se situe dans le traitement d’export IA ; la demande exclut les modifications à `_export_ai`. Corriger seulement l’aperçu laisserait le défaut dans le film.

### Contrôle distinct du démarrage de DeepFilterNet

Sur la même piste Flite avec souffle, passage par le binaire seul (WAV, aucune normalisation de volume ni compression AAC). En fenêtres successives de 100 ms, l’écart de niveau reste sous 0,5 dB et la corrélation au-dessus de 0,99 **à partir de 2,3 s** et jusqu’à la fin de l’extrait ; sur cet intervalle, maximum 0,32 dB et minimum 0,992. Il s’agit d’un temps de stabilisation mesuré sur cette voix. Le profil complet conserve ses différences de volume au-delà de cette durée.

### Contre-épreuve avec le véritable Real-ESRGAN

Même source réduite aux deux premières secondes, 32 × 24 à 25 i/s, même moteur Vulkan logiciel que pour les couleurs. L’aperçu commence ici au début du film. Repère à environ 1,1 s ; écart bip − éclair en ms.

| Dérive (ms/min) | Chemin | Aperçu | Export |
|---:|---|---:|---:|
| 0 | Normal | −20,0 | −20,0 |
| 0 | Real-ESRGAN | −60,0 | −60,0 |
| +400 | Normal | −39,3 | −39,3 |
| +400 | Real-ESRGAN | −79,3 | −79,3 |

Le vrai modèle confirme l’écart de 40 ms par rapport au chemin normal, avec et sans dérive. Un extrait qui commence au début peut donc reproduire fidèlement le décalage de l’export. Sur le film de 8 s, un extrait pris au milieu peut au contraire le masquer.

## Bilan pour Claude

- **Image** : la pleine définition représente bien les deux scènes testées si le même traitement IA est appliqué. Un aperçu réalisé après avoir choisi « sans » est signalé.
- **Son** : avec DeepFilterNet 0.5.6, le calage des bips correspond au nettoyage habituel après correction. Le souffle et la voix restent reconnaissables dans l’aperçu ; le niveau de voix du profil Maximum peut différer sensiblement du film. En cas de repli, l’utilisateur est averti.
- **Avant de valider le calage de l’export IA**, reprendre les horodatages dans `_export_ai`, avec une première image source à +40 ms et une première piste son à zéro. Vérifier aussi le cas de dérive négative avec extrait pris au milieu. Aucune correction à cette fonction dans cette branche.
- **Tests** : les cinq fichiers demandés ensemble, avec DeepFilterNet activé pour son test, donnent `34 passed` en 302 s. Le contrôle d’écran distinct demandé pour les changements d’interface donne `9 passed` (1280 × 641, 100/125/150 %). FFmpeg 7.1.5, Linux ; les deux outils IA réels ont tourné. Suite complète et Windows : non lancés ; la demande réserve la suite complète à Claude avant fusion, et l’environnement de mesure est Linux.

## n°4 — Calage, avertissements et volume

### Extraction des images

Le mode passthrough de la sortie PNG conserve une image par trame décodée. L’horodatage initial reste appliqué une seule fois par l’encodeur. Un contrôle arrête le traitement si le nombre extrait diffère du nombre attendu. Sur une source AVI MPEG-2 dont chaque image porte son numéro en binaire, les trois paquets contiennent 60, 60 et 11 PNG. L’export conserve les 131 numéros de l’intermédiaire dans l’ordre. Sur f9cc499 le test échoue dès le deuxième numéro (« At index 1 diff: 0 != 1 »).
