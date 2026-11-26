# Corrections avant fusion : n°19 (reprise) et copie de lecture (pour le chef des bots)

Vérifié par Claude. Rappel : `[skip ci]` à la fin du titre de TOUS les commits.

## 1. n°19, agent R2 (`grok/reprise`, `99dd9bf`) : deux tests de `test_ergonomie.py` échouent

Suite complète de Claude (n°17 + n°19 assemblées) : 429 réussis, 2 échecs, les deux dans
`test_ergonomie.py`, un fichier modifié par R2 mais jamais lancé. Ils échouent AUSSI sur
`grok/reprise` seul (vérifié) :

- `test_lecture_reprise_tolerante` : `lire_reprise` rend `None`.
- `test_reprise_annoncee_a_l_ecran` : la ligne d'état ne dit jamais « …arrêtée à 45 %… ».

Cause : `ergonomie.lire_reprise` devine les fonctions de `reprise.py` (`_appelable`,
`_invoquer`, noms de secours `etat`, `situation`, `eligible`…), écrit avant que R1 fixe son
interface. Cette devinette ne passe pas avec les signatures des tests.

À faire (R2) :
- Appeler directement l'interface de R1, désormais fixe : `reprise.applicable(info, reglages,
  passages=None, start=None, duration=None)`, `reprise.dossier(...)` (mêmes paramètres),
  `reprise.parties_faites(dossier)`, `reprise.decouper(passages, ...)`. Supprimer la devinette.
- Les deux tests utilisent ces vraies signatures (faux module ou vrai `reprise.py` avec un dossier
  temporaire), et vérifient toujours : 5 parties sur 11, « 45 % », « Reprise : 5 parties sur 11 déjà
  faites. », le message d'ouverture, celui d'arrêt et celui d'erreur.
- Lancer `test_ergonomie.py` ET `test_reprise.py` (et `test_assistant.py`).

## 2. Copie de lecture, Navigation (`grok/lecteur-copie`, `d7f64bd`)

Vérifié : 15 tests passent chez Claude, stries 17 → 0, priorité basse, place vérifiée, moteur
intact. Un point : la copie est encodée en CRF 18, environ 3 à 4 Go de fichier temporaire pour
une cassette de 2 heures, pour une image vue dans un cadre d'environ 500 px.
- Passer à `-crf 27` (même `veryfast`), et ajuster `besoin_octets` en conséquence.
- Mesurer la taille obtenue pour une heure de film (720 × 576 entrelacé), à mettre au rapport.
- L'enchaînement « après l'analyse des scènes » (n°17, absente de la branche de départ) sera fait
  par Claude à l'assemblage : rien à faire ici.

## Règles

Chaque commit poussé tout de suite, avec `[skip ci]`. Seulement les fichiers de tests cités.
Aucun test affaibli. Ni fusion dans `ccr-5856e8d6-8xt8uh`, ni pull request. Rapports :
`RAPPORT-N19-POUR-CLAUDE.md` et `RAPPORT-N13-ETAPE2-POUR-CLAUDE.md`, partie « Corrections ».
