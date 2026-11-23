"""Aides d'ergonomie : phrases simples, sans changer les traitements.

L'utilisateur visé a 76 ans. Il ne lit pas les infobulles, il a peur de casser
un film, et un message technique l'arrête. Chaque erreur dit ce qui s'est passé
et quoi faire ; le détail technique reste disponible, jamais en premier.
"""
from __future__ import annotations

PHRASE_PATIENCE = "Vous pouvez utiliser l'ordinateur ou le laisser travailler."


def expliquer(message: str) -> tuple[str, str]:
    """(phrase pour la personne, détail technique inchangé)."""
    brut = (message or "").strip()
    bas = brut.lower()
    if ("ffmpeg" in bas or "ffprobe" in bas) and ("introuvable" in bas or "filtres manquants" in bas
                                                  or "trop ancien" in bas):
        clair = ("Le logiciel est incomplet (un de ses outils manque). "
                 "Réinstallez-le à partir du fichier téléchargé, puis recommencez.")
    elif "espace disque" in bas or "insuffisant" in bas:
        clair = ("Il n'y a plus assez de place sur le disque. "
                 "Libérez de la place, ou choisissez un autre dossier, puis recommencez.")
    elif any(mot in bas for mot in ("introuvable", "n'est plus", "no such file", "errno 2",
                                    "device or resource", "i/o error", "permission denied")):
        clair = ("Le fichier ou le dossier n'est plus là. "
                 "Vérifiez qu'il n'a pas été déplacé, et que la clé USB est bien branchée.")
    elif any(mot in bas for mot in ("non reconnu", "n'a pas pu être lue", "illisible",
                                    "abîm", "corrupt", "invalid data", "moov atom",
                                    "pas de piste vidéo", "ffprobe ne répond pas")):
        clair = ("Ce fichier semble abîmé, ou ce n'est pas une vidéo ni une photo. "
                 "Essayez une autre copie du fichier.")
    elif "fin doit être après" in bas or "début choisi" in bas:
        clair = "Le début et la fin ne vont pas ensemble. La fin doit être après le début."
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


def resume_dossier(reussis: int, deja: int, erreurs: list[tuple[str, str]]) -> str:
    """Résumé final d'un dossier, en mots simples."""
    lignes = [
        "C'est prêt.",
        f"Réussis : {reussis}.",
        f"Déjà faits, laissés tels quels : {deja}.",
        f"En échec : {len(erreurs)}.",
    ]
    for nom, msg in erreurs:
        clair, _ = expliquer(msg)
        lignes.append(f"• {nom} : {clair}")
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


def montrer_erreur(parent, message: str) -> None:
    """Boîte lisible : quoi faire, puis le détail technique derrière un bouton."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    clair, detail = expliquer(message)
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
