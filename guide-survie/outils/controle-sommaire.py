"""Vérifie que chaque numéro de page du sommaire renvoie à la page où le titre apparaît réellement dans le PDF.
Usage : python3 outils/controle-sommaire.py guide-survie        (ou dossier-editorial)
"""
import re
import subprocess
import sys

from bs4 import BeautifulSoup

base = sys.argv[1]
h = open(base + ".html", encoding="utf-8").read()
pos = re.findall(r'<a href="#([\w-]+)">(?:<span class="n">[^<]*</span>)?<span class="t">[^<]*</span></a>'
                 r'<span class="pg"(?: data-for="[\w-]+")?>(\d+)</span>', h)
pages = subprocess.run(["pdftotext", "-layout", base + ".pdf", "-"], capture_output=True, text=True).stdout.split("\f")
soup = BeautifulSoup(h, "html.parser")
norm = lambda x: re.sub(r"\s+", "", x).replace(" ", "").replace(" ", "")
ecarts = []
for ident, p in pos:
    titre = soup.find("section", id=ident).find(["h2", "h3"])
    for v in titre.find_all("svg"):
        v.decompose()
    if norm(titre.get_text(""))[:20] not in norm(pages[int(p) - 1]):
        ecarts.append((ident, p))
print(f"{base} : {len(pos)} entrées du sommaire ; écarts : {ecarts or 'aucun'}")
sys.exit(1 if ecarts else 0)
