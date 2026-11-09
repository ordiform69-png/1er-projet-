"""Contrôle v1.2 : couverture des 72 manques, présence des textes, validité HTML, liens."""
import re
import sys
from html.parser import HTMLParser

tags = [l.split("\t")[0] for l in open(sys.argv[1], encoding="utf-8").read().splitlines()]
html = open(sys.argv[2], encoding="utf-8").read()
covered = set()
for t in tags:
    for n in re.findall(r"M(\d+)", t):
        covered.add(int(n))
    for a, b in re.findall(r"M(\d+)-M(\d+)", t):
        pass
# M49 est intégré dans le bloc M48-M50-M20 (« Suivre sa progression »)
if "Suivre sa progression" in html:
    covered.add(49)
missing = sorted(set(range(1, 73)) - covered)
print("Manques couverts :", len(covered & set(range(1, 73))), "/ 72", "| non couverts :", missing)

ids = set(re.findall(r'id="([^"]+)"', html))
links = set(re.findall(r'href="#([^"]+)"', html))
print("Liens cassés :", links - ids)


class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.st = []; s.err = []

    def handle_starttag(s, t, a):
        if t not in ("meta", "br", "img", "circle", "rect", "path", "ellipse", "line", "input"):
            s.st.append(t)

    def handle_endtag(s, t):
        if t in ("meta", "br", "img", "circle", "rect", "path", "ellipse", "line"):
            return
        if s.st and s.st[-1] == t:
            s.st.pop()
        else:
            s.err.append((t, s.getpos()))


p = P(); p.feed(html)
print("Balises :", "OK" if not p.err and not p.st else (p.err[:3], p.st[-3:]))
for k in ["Malaise, douleur dans la poitrine", "pensez VITE", "Convulsions", "Plaie grave", "Chute ou choc violent",
          "Saignement de nez", "Champignon sauvage déjà mangé", "Marées et pêche à pied", "Si un enfant se perd",
          "Ne jamais se disperser", "Que dire au téléphone", "Balise personnelle de détresse", "Petit glossaire",
          "Eau de Javel : à valider", "Canicule", "Abouter deux cordes", "brêlage carré", "Vêtements en feu"]:
    print(f"  {'✓' if k in html else '✗'} {k}")
