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
