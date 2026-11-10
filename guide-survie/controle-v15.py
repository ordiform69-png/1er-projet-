"""Contrôle v1.5 : chaque opération de corrections-v15.py est en place (les textes sont générés en boucle).
Usage : python3 controle-v15.py source/livret-corps.html [guide-survie.html]"""
import ast, re, sys
src = open(sys.argv[1], encoding="utf-8").read()
ok = bad = 0
def chk(nom, cond):
    global ok, bad
    ok += cond; bad += not cond
    if not cond: print("À REVOIR :", nom)
code = open(__file__.replace("controle-v15.py", "corrections-v15.py"), encoding="utf-8").read()
F = ast.literal_eval(code[code.index("F = [") + 4: code.index("]\nfor k, (o, n) in enumerate(F, 1)") + 1])
for k, (o, n) in enumerate(F, 1):
    chk(f"fiche {k} : nouveau texte", n in src); chk(f"fiche {k} : ancien texte retiré", o not in src)
chk("6 bandeaux de parties", src.count('class="partie-bandeau"') == 6)
chk("page À propos", 'id="mentions"' in src); chk("page Sources et limites", 'id="sources"' in src)
chk("sommaire : 31 entrées avec numéro", src.count('<span class="pg" data-for=') == 31)
chk("ancien sommaire retiré", "<nav class=\"toc\" style=" not in src)
chk("couverture v1.5", "Version 1.5 — 10 novembre 2026" in src)
if len(sys.argv) > 2:
    pub = open(sys.argv[2], encoding="utf-8").read()
    chk("édition publique : numéros de page remplis", len(re.findall(r'<span class="pg" data-for="[\w-]+">\d+</span>', pub)) == 31)
    chk("édition publique : index présent", 'id="index"' in pub and pub.count('class="lettre"') >= 15)
    chk("édition publique : pas d'annexes", 'id="annexe-' not in pub)
print(f"{ok} contrôles conformes, {bad} à revoir")
