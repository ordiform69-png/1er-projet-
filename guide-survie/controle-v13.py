"""Contrôle v1.3 : chaque remplacement de corrections-v13.py est présent et l'ancien texte a disparu.

Usage : python3 controle-v13.py corrections-v13.py guide-survie.html
Les remplacements dont le texte est calculé (encadré Javel, paragraphe Nourrisson, fiche 3 ter) sont contrôlés
par leurs marqueurs : nouveau titre présent, ancien titre ou ancienne phrase absents.
"""
import ast
import sys

src = open(sys.argv[1], encoding="utf-8").read()
html = open(sys.argv[2], encoding="utf-8").read()
ok = bad = 0
for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "rep":
        pt = ast.literal_eval(node.args[0])
        try:
            old = ast.literal_eval(node.args[1])
        except ValueError:
            old = None
        try:
            new = ast.literal_eval(node.args[2])
        except ValueError:
            continue  # texte calculé : contrôlé par marqueurs ci-dessous
        present = new in html
        gone = old is None or old in new or old not in html
        if present and gone:
            ok += 1
        else:
            bad += 1
            print("À REVOIR :", pt, "nouveau absent" if not present else "ancien encore présent")
# marqueurs des remplacements calculés (script v1.3 seulement)
for pt, must, never in [] if '"P06"' not in src else [
    ("P06", "Eau de Javel : seulement sur consigne des autorités", "Le protocole transmis (Javel à 2,6 %)"),
    ("P20", "<h4>3 ter · Malaise, douleur dans la poitrine, signes d'AVC</h4>", "<h4>3 ter · Malaise ou signes d'AVC</h4>"),
    ("P10", "convient pour la préparation des aliments des nourrissons", "(à défaut, une eau bouillie puis refroidie)"),
]:
    if must in html and never not in html:
        ok += 1
    else:
        bad += 1
        print("À REVOIR :", pt, "(marqueurs)")
print(f"{ok} contrôles conformes, {bad} à revoir")
print("Mentions « à valider » restantes :", html.count("à valider"))
