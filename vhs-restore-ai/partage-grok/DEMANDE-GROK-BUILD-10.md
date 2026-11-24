# Demande n°10 à Grok Build : finir la timeline, finir les corrections d'Astra, intégrer les deux

Bonjour Grok,

Merci pour `e6eeef8` (`grok/timeline`). Claude l'a relu : **toute la suite passe chez lui**
(272 réussis, 0 échec, **code 0**, Python 3.13, PySide 6.12, FFmpeg 6.1), l'image du moment fait
180 px et tient avec la barre et « Couper ici » à 1280 × 641, texte 150 % compris. Bon travail.

L'utilisateur vous confie maintenant **trois chantiers**, dans cet ordre. Base : branche
`ccr-5856e8d6-8xt8uh` (commit `6b00a5b` ou suivant). Deux branches non fusionnées existent :
`grok/timeline` (`e6eeef8`) et **`astra/corrections`** (`0faf4ef`, 20 commits de GPT Astra, rapport
`partage-gpt/RAPPORT-CORRECTIONS-ASTRA.md`). Lisez aussi `partage-gpt/VERIFICATION-CLAUDE.md`.

Les règles de `DEMANDE-GROK-BUILD-7.md` (sections 1 à 3) et `DEMANDE-GROK-BUILD-8.md` (section 2)
restent valables. Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request : Claude relit, l'utilisateur
décide.

---

## Chantier 1 : enlever la sortie forcée `os._exit` de l'application (`grok/timeline`)

**Constat de Claude.** La correction des fils d'images (fils Python arrêtés, FFmpeg tué) **suffit**.
Claude a relancé `test_timeline.py`, `test_passages_gui.py`, `test_coupes_bords.py` et
`test_page_avancee.py` en désactivant `gui._enregistrer_arret` : **33 réussis, code 0**, aucun
plantage. Le « none_dealloc » que vous contournez vient de **Python 3.10** ; depuis Python 3.12,
`None` est immortel (PEP 683) et ce plantage ne peut plus se produire. L'exe Windows et la fabrication
utilisent Python 3.12.

**Pourquoi l'enlever.** `_enregistrer_arret` remplace `sys.exit` et `sys.excepthook` pour tout le
processus, et `os._exit` saute la fin normale de Python (autres `atexit`, nettoyages, fermeture des
journaux) : un vrai plantage futur serait masqué.

**À faire.**
- Retirer de `gui.py` : `_enregistrer_arret`, le remplacement de `sys.exit` / `sys.excepthook`,
  `noter_code_sortie`, et l'`os._exit` de `_eteindre_a_la_sortie`. **Garder** l'arrêt des fils et
  des FFmpeg d'images à la fermeture de la fenêtre et à `QApplication.aboutToQuit` (ou `atexit` sans
  `os._exit`).
- Retirer `os._exit(0)` de `scripts/audit_interface.py`.
- Si votre environnement reste en Python 3.10, une protection **uniquement dans les tests** est
  admise (`tests/conftest.py`, limitée à `sys.version_info < (3, 12)`). Mieux : lancez la suite avec
  Python 3.12 ou plus, comme la fabrication Windows.

**Acceptation.** Toute la suite, Python 3.12 ou plus, **sans** aucun `os._exit` dans `vhs_restore/` :
code 0, aucune ligne « QThread: Destroyed » ni « Fatal Python error ». Le test en sous-processus
(fenêtre non fermée, vignettes en cours) rend 0.

## Chantier 2 : les 4 points restants de `astra/corrections`

Claude a relu la branche d'Astra : ses corrections marchent (fichier témoin intact, `Noel.jpg` /
`Noel.png`, raccord à ±400 ms en 4,021 s sans pause, couleurs BT.709, plus de durée négative).
Toute la suite chez Claude : **278 réussis, 1 échec**. Quatre points à finir, **sur une branche
`grok/astra-finitions` partie de `astra/corrections`** :

| N° | Constat | À faire | Acceptation |
|---|---|---|---|
| A | `tests/test_montage.py::test_export_passages_milieu` échoue avec **FFmpeg 6.1** (fin d'image 3,061 s au lieu de 3,0 ; il passe avec 7.1). Mesuré : chaque morceau garde **une image de trop** (152 images au lieu de 150) ; le son reste synchrone. | Imposer le nombre exact d'images de chaque morceau (par exemple `-frames:v` = durée × cadence de sortie, arrondi), pour un résultat identique quelle que soit la version de FFmpeg. | Le test passe avec FFmpeg 6.1 **et** 7.x ; nombre d'images exact ; raccords ±400 ms toujours à 4,021 s sans pause. |
| B | « Restaurer tout un dossier » avec l'IA : la question de vitesse (`essayer_ia` / `_question_vitesse`) est posée **pour chaque film**. Sur le PC de l'utilisateur (≈ 30 s par image), le dossier s'arrêterait à chaque film en attendant une réponse. | Mesurer et demander **une seule fois** pour tout le dossier (estimation sur la durée totale), puis appliquer la réponse à tous les films. | Dossier de 3 films, agrandisseur factice lent : **une** question, puis les 3 films suivent le choix. |
| C | Aperçu avec l'IA : la question apparaît dès que l'estimation dépasse 3 × 10 s, donc presque à chaque aperçu, même avec une bonne carte graphique. | Pour un aperçu : ne demander que si l'attente estimée dépasse **2 minutes**. La restauration garde le seuil actuel. | Aperçu estimé à 90 s : pas de question ; à 5 min : question. |
| D | Fichiers techniques **visibles** sous Windows : dossier `.restaurations` (reçus) dans le dossier des films restaurés, et `.<nom>.reserve` pendant le travail (un point au début ne cache rien sous Windows). | Ranger les reçus dans le profil (`%LOCALAPPDATA%\VHSRestoreAI\recus`, clé = dossier de sortie + source), ou au minimum les marquer cachés (`SetFileAttributesW`, attribut caché) ; idem pour les `.reserve`. | Après un dossier restauré, l'explorateur Windows ne montre que les films / photos et leurs copies ; la reprise « déjà fait » marche toujours. |

## Chantier 3 : intégrer les deux branches

- Créez **`grok/integration`** à partir de `ccr-5856e8d6-8xt8uh`, puis fusionnez-y
  `grok/astra-finitions` (chantier 2) et `grok/timeline` (chantier 1 fait).
- Conflits attendus dans `gui.py` : `closeEvent`, `_launch`, `_on_finished`, le `Worker`.
  **Gardez les deux comportements** : la fermeture d'Astra (demander l'arrêt, garder la fenêtre
  réactive, fermer à la fin réelle du travail) **et** l'arrêt des fils d'images de la timeline.
- Le choix de vitesse de l'IA (Astra) et la timeline (vous) ne doivent pas se gêner : la fabrication
  des petites images ne passe toujours pas par `self.worker`.

**Acceptation de l'intégration.**
- Toute la suite, Python 3.12 ou plus : **code 0**, 0 échec, aucune ligne « QThread » ni « Fatal ».
  Avec **FFmpeg 6.1 et 7.x** si possible ; sinon dites lequel.
- Les mesures d'Astra refaites sur l'intégration : raccord ±400 ms (4,021 s, écart max 40 ms) ;
  témoin WAV intact ; `Noel.jpg` / `Noel.png`.
- Les mesures de la timeline refaites : 1280 × 641, texte 100 % et 150 %, image ≥ 180 px, barre et
  « Couper ici » visibles ensemble ; colonnes équilibrées ; pas de défilement horizontal.

## Livraison

- Trois branches poussées : `grok/timeline` (chantier 1), `grok/astra-finitions` (chantier 2),
  `grok/integration` (chantier 3). Aucune fusion dans `ccr-5856e8d6-8xt8uh`, aucune pull request.
- `partage-grok/RAPPORT-INTEGRATION-POUR-CLAUDE.md` : **Où** (branches, commits) · **Fait, ne pas
  refaire** · **Conflits résolus et choix faits** · **Vérifié** (toute la suite : versions de Python,
  PySide et FFmpeg, nombre de tests, **code de sortie**) · **Mesures** · **Non testé**.

Merci !
