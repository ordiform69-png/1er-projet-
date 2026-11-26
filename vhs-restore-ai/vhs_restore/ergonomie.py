"""Aides d'ergonomie : phrases simples, sans changer les traitements.

L'utilisateur visé a 76 ans. Il ne lit pas les infobulles, il a peur de casser
un film, et un message technique l'arrête. Chaque erreur dit ce qui s'est passé
et quoi faire ; le détail technique reste disponible, jamais en premier.
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass

PHRASE_PATIENCE = ("Vous pouvez utiliser l'ordinateur ou le laisser travailler. "
                   "L'ordinateur ne se mettra pas en veille.")
PHRASE_COUPES_DOSSIER = ("Les coupes de ce film ne seront pas appliquées aux autres fichiers du dossier. "
                         "Chaque film part en entier.")

log = logging.getLogger("vhs_restore")

# Lecture du moteur `reprise.py` (autre agent). Sur cette branche le fichier n'existe pas encore :
# tout appel échoue en silence et l'écran se comporte comme aujourd'hui.
# Noms attendus (demande n°19, repris par les tests de la branche grok/reprise) :
#   applicable(info, reglages, passages=None) -> bool
#   dossier(info, reglages, passages=None) -> Path
#   parties_faites(dossier) -> séquence des parties déjà complètes
#   decouper(passages) -> liste des parties (la longueur est le total)
#   et, à défaut de ce qui précède : etat / situation / interrompue
# `passages` : intervalles gardés, ou None si le film part en entier.


def insecables(texte: str) -> str:
    """Espaces insécables dans « … », comme la ligne d'état."""
    return texte.replace("« ", "«\u00a0").replace(" »", "\u00a0»")


def message_ouverture(faites: int, total: int) -> str:
    """Annonce à l'ouverture. Le pourcentage est la part des parties déjà faites."""
    faites, total = int(faites), int(total)
    pct = round(faites / total * 100) if total else 0
    pct = max(0, min(100, pct))
    return (f"Une restauration de ce film s'était arrêtée à {pct} %. "
            "« Lancer la restauration » la reprendra.")


def message_progression(faites: int, total: int) -> str:
    """Ligne affichée pendant que la restauration reprend."""
    faites, total = int(faites), int(total)
    if faites == 1:
        return f"Reprise : 1 partie sur {total} déjà faite."
    return f"Reprise : {faites} parties sur {total} déjà faites."


def message_arret() -> str:
    return "Arrêté. Les parties déjà restaurées sont gardées : relancez pour reprendre."


@dataclass(frozen=True)
class Reprise:
    """Ce que l'écran a besoin de savoir. `en_parties` : un arrêt gardera le travail."""

    faites: int
    total: int
    en_parties: bool

    def phrase_ouverte(self) -> str:
        if self.faites <= 0 or self.total <= 0 or self.faites > self.total:
            return ""
        return message_ouverture(self.faites, self.total)

    def phrase_en_cours(self) -> str:
        if self.faites <= 0 or self.total <= 0 or self.faites > self.total:
            return ""
        return message_progression(self.faites, self.total)


def expliquer(message: str) -> tuple[str, str]:
    """(phrase pour la personne, détail technique inchangé)."""
    brut = (message or "").strip()
    bas = brut.lower()
    if ("ffmpeg" in bas or "ffprobe" in bas) and ("introuvable" in bas or "filtres manquants" in bas
                                                  or "trop ancien" in bas):
        clair = ("Le logiciel est incomplet (un de ses outils manque). "
                 "Réinstallez-le à partir du fichier téléchargé, puis recommencez.")
    elif ("renommez ce fichier" in bas or "chemin du fichier à créer est trop long" in bas
            or "chemin du film d'origine est trop long" in bas
            or "fermez-le, puis recommencez l'installation" in bas
            or "fat32" in bas):
        clair = brut                        # message déjà écrit pour la personne : il dit quoi faire
    elif any(mot in bas for mot in ("permission denied", "errno 13", "winerror 32", "winerror 5",
                                    "used by another process", "read-only file system", "lecture seule",
                                    "accès refusé", "access is denied")):
        clair = ("Le fichier est utilisé par un autre programme (un lecteur vidéo ?), ou le dossier est "
                 "protégé contre l'écriture. Fermez les autres programmes, ou choisissez un autre dossier, "
                 "puis recommencez.")
    elif "espace disque" in bas or "insuffisant" in bas:
        clair = ("Il n'y a plus assez de place sur le disque. "
                 "Libérez de la place, ou choisissez un autre dossier, puis recommencez.")
    elif any(mot in bas for mot in ("introuvable", "n'est plus", "no such file", "errno 2",
                                    "device or resource", "i/o error")):
        clair = ("Le fichier ou le dossier n'est plus là. "
                 "Vérifiez qu'il n'a pas été déplacé, et que la clé USB est bien branchée.")
    elif any(mot in bas for mot in ("non reconnu", "n'a pas pu être lue", "illisible",
                                    "abîm", "corrupt", "invalid data", "moov atom",
                                    "pas de piste vidéo", "ffprobe ne répond pas")):
        clair = ("Ce fichier semble abîmé, ou ce n'est pas une vidéo ni une photo. "
                 "Essayez une autre copie du fichier.")
    elif "fin doit être après" in bas or "début choisi" in bas:
        clair = "Le début et la fin ne vont pas ensemble. La fin doit être après le début."
    elif "ne resterait plus rien" in bas or "au moins un passage" in bas:
        clair = "Il ne resterait plus rien du film. Laissez au moins un passage."
    elif "passage au milieu" in bas:
        clair = ("Cette coupe au milieu ne va pas avec l'option cochée. Décochez "
                 "« Amélioration IA », « Enlever les poussières et rayures », « Bruit de bande », "
                 "« Couleur des décrochages » ou « Taches d'une seule image », ou remettez "
                 "« Cadence de tournage » sur « Celle du fichier ». "
                 "Sinon, n'enlevez que le début et la fin.")
    elif "ne peut pas être le fichier" in bas or "ne peut pas remplacer" in bas:
        clair = ("Le résultat ne peut pas remplacer le fichier d'origine. "
                 "Rien n'a été écrasé. Choisissez un autre dossier si besoin.")
    elif "aucune vidéo" in bas or "aucune photo" in bas:
        clair = ("Ce dossier ne contient pas de film ni de photo. "
                 "Choisissez le dossier où se trouvent les fichiers.")
    else:
        clair = ("Cette étape n'a pas abouti. Votre fichier d'origine n'a pas été modifié. "
                 "Vous pouvez réessayer. Si cela se reproduit, « Détails pour l'aide » "
                 "permet de copier l'explication technique.")
    return clair, brut


def resume_dossier(reussis: int, deja: int, erreurs: list[tuple[str, str]], remarque: str = "") -> str:
    """Résumé final d'un dossier, en mots simples. `remarque` : phrase ajoutée avant la dernière ligne
    (par exemple PHRASE_COUPES_DOSSIER, quand le film ouvert avait des coupes)."""
    lignes = [
        "C'est prêt." if reussis or deja else "Aucun fichier n'a pu être restauré.",
        f"Réussis : {reussis}.",
        f"Déjà faits, laissés tels quels : {deja}.",
        f"En échec : {len(erreurs)}.",
    ]
    for nom, msg in erreurs:
        clair, _ = expliquer(msg)
        lignes.append(f"• {nom} : {clair}")
    if remarque:
        lignes.append(remarque)
    lignes.append("Les fichiers d'origine n'ont pas été modifiés.")
    return "\n".join(lignes)


def memoriser_recent(liste: list[str], chemin: str, maxi: int = 5) -> list[str]:
    """Les derniers fichiers ouverts, le plus récent en premier, sans doublon."""
    out: list[str] = []
    for p in [str(chemin), *[str(x) for x in liste]]:
        if p and p not in out:
            out.append(p)
        if len(out) >= maxi:
            break
    return out


class _Echec:
    """L'appel au moteur a échoué : on n'invente pas un état."""


def _module_reprise():
    try:
        from . import reprise
    except ImportError:
        return None
    except Exception:
        log.warning("reprise : module illisible", exc_info=True)
        return None
    return reprise


def _appelable(mod, noms: tuple[str, ...]):
    for nom in noms:
        fn = getattr(mod, nom, None)
        if callable(fn) and not isinstance(fn, type):
            return fn
    return None


def _invoquer(fn, *args, **kwargs):
    """Appelle `fn` avec les arguments que sa signature accepte. None si l'appel casse."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = None
    if params is not None and not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        kwargs = {cle: val for cle, val in kwargs.items() if cle in params}
    try:
        return fn(*args, **kwargs)
    except TypeError:
        if not kwargs:
            log.warning("reprise : appel impossible", exc_info=True)
            return _Echec()
        try:
            return fn(*args)
        except Exception:
            log.warning("reprise : appel impossible", exc_info=True)
            return _Echec()
    except Exception:
        log.warning("reprise : appel impossible", exc_info=True)
        return _Echec()


def _entier(valeur, defaut: int | None = None) -> int | None:
    if isinstance(valeur, bool) or valeur is None:
        return defaut
    try:
        return int(round(float(valeur)))
    except (TypeError, ValueError):
        return defaut


def _compte(valeur) -> int | None:
    if isinstance(valeur, bool) or valeur is None or isinstance(valeur, _Echec):
        return None
    nombre = _entier(valeur)
    if nombre is not None:
        return nombre
    try:
        return len(list(valeur))
    except TypeError:
        return None


def _lire_attribut(objet, *noms):
    if isinstance(objet, dict):
        for nom in noms:
            if nom in objet:
                return objet[nom]
        return None
    for nom in noms:
        if hasattr(objet, nom):
            return getattr(objet, nom)
    return None


def _interpreter(brut) -> Reprise | None:
    """Accepte (faites, total), (faites, total, pourcent ignoré) ou un objet / dict nommé."""
    if brut is None or brut is False or isinstance(brut, _Echec):
        return None
    if brut is True:
        return Reprise(0, 0, True)
    faites = total = None
    en_parties = None
    if isinstance(brut, (tuple, list)):
        if len(brut) < 2:
            return None
        faites, total = _entier(brut[0], 0), _entier(brut[1], 0)
    else:
        faites = _entier(_lire_attribut(brut, "faites", "fait", "parties_faites", "deja"))
        total = _entier(_lire_attribut(brut, "total", "parties", "nombre"))
        drapeau = _lire_attribut(brut, "en_parties", "garde", "applicable")
        if isinstance(drapeau, bool):
            en_parties = drapeau
    if faites is None or total is None:
        return Reprise(0, 0, True) if en_parties else None
    faites, total = max(0, faites), max(0, total)
    if en_parties is None:
        en_parties = faites > 0 or total > 1
    if not en_parties and faites <= 0:
        return None
    return Reprise(faites, total, bool(en_parties) or faites > 0)


def lire_reprise(info, reglages, *, passages=None, gardes=None, start=None, duration=None) -> Reprise | None:
    """État d'une restauration interrompue, ou None si le moteur ne la reprendra pas.

    `passages` est celui de l'export (None si le film part en entier). `gardes` est la liste
    des intervalles gardés, utilisée seulement pour compter les parties.
    """
    mod = _module_reprise()
    if mod is None or info is None or reglages is None:
        return None
    applicable = _appelable(mod, ("applicable", "en_parties", "eligible"))
    if applicable is not None:
        return _lire_applicable(mod, applicable, info, reglages, passages, gardes, start, duration)
    fn = _appelable(mod, ("etat", "situation", "interrompue"))
    if fn is None:
        return None
    return _interpreter(_invoquer(fn, info, reglages, passages=passages, start=start, duration=duration))


def _lire_applicable(mod, applicable, info, reglages, passages, gardes, start, duration) -> Reprise | None:
    rep = _invoquer(applicable, info, reglages, passages=passages, start=start, duration=duration)
    if isinstance(rep, _Echec):
        return None
    if rep is False:
        return None
    concerne = True if rep is True else None
    gardes_liste = list(gardes or [])
    if not gardes_liste:
        duree = float(getattr(info, "duration", 0) or 0)
        if duree > 0:
            gardes_liste = [(0.0, duree)]
    total = 0
    decouper = _appelable(mod, ("decouper",))
    if decouper is not None and gardes_liste:
        total = _compte(_invoquer(decouper, gardes_liste)) or 0
    faites = 0
    dossier = _appelable(mod, ("dossier",))
    faits = _appelable(mod, ("parties_faites",))
    if dossier is not None and faits is not None:
        chemin = _invoquer(dossier, info, reglages, passages=passages, start=start, duration=duration)
        if not isinstance(chemin, _Echec) and chemin is not None:
            compte = _compte(_invoquer(faits, chemin))
            if compte is not None:
                faites = compte
    if concerne is None and faites <= 0 and total <= 1:
        return None
    return Reprise(max(0, faites), max(0, total), True)


def montrer_erreur(parent, message: str, *, complement: str = "") -> None:
    """Boîte lisible : quoi faire, puis le détail technique derrière un bouton.

    `complement` : phrase ajoutée devant (reprise gardée), sans remplacer l'explication.
    """
    from PySide6.QtWidgets import QApplication, QMessageBox

    clair, detail = expliquer(message)
    if complement:
        clair = complement + "\n\n" + clair
    box = QMessageBox(QMessageBox.Warning, "Une étape n'a pas abouti", clair, parent=parent)
    box.setStyleSheet("QLabel#qt_msgbox_label { min-width: 520px; font-size: 14pt; }")
    details = box.addButton("Détails pour l'aide", QMessageBox.ActionRole)
    fermer = box.addButton("Fermer", QMessageBox.AcceptRole)
    box.setDefaultButton(fermer)
    box.exec()
    if box.clickedButton() is not details:
        return
    suite = QMessageBox(QMessageBox.Information, "Détails pour l'aide", detail or "(aucun détail)",
                        parent=parent)
    copier = suite.addButton("Copier", QMessageBox.ActionRole)
    suite.addButton("Fermer", QMessageBox.AcceptRole)
    suite.exec()
    if suite.clickedButton() is copier:
        QApplication.clipboard().setText(detail)
