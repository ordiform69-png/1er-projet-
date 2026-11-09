"""Vérifie que chaque remplacement v1.1 est présent et que l'ancien texte a disparu (sauf s'il est inclus dans le nouveau)."""
import ast
import sys

src = open(sys.argv[1], encoding="utf-8").read()
html = open(sys.argv[2], encoding="utf-8").read()
tree = ast.parse(src)
ok = bad = 0
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "rep":
        old, new = (ast.literal_eval(a) for a in node.args)
        present = new in html
        gone = (old in new) or (old not in html)
        if present and gone:
            ok += 1
        else:
            bad += 1
            print("À REVOIR :", "nouveau absent" if not present else "ancien encore présent", "|", old[:80])
print(f"{ok} remplacements conformes, {bad} à revoir")
