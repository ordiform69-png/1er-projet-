"""Mesure le remplissage de chaque page du PDF : hauteur occupée entre la marge haute et le pied de page.

Usage : python3 outils/controle-mise-en-page.py guide-survie.pdf [seuil]
Liste les pages remplies à moins du seuil (défaut 40 %), sauf la dernière page d'une partie forcée.
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image

pdf = sys.argv[1]
seuil = float(sys.argv[2]) if len(sys.argv) > 2 else 0.40
with tempfile.TemporaryDirectory() as d:
    subprocess.run(["pdftoppm", "-r", "24", "-gray", pdf, os.path.join(d, "p")], check=True)
    pages = sorted(os.listdir(d))
    faibles = []
    for k, f in enumerate(pages, 1):
        im = Image.open(os.path.join(d, f))
        w, h = im.size
        top, bottom = int(h * 0.06), int(h * 0.92)  # marges haute et pied de page exclus
        px = im.load()
        last = top
        for y in range(top, bottom):
            if any(px[x, y] < 200 for x in range(int(w * 0.08), int(w * 0.92), 2)):
                last = y
        fill = (last - top) / (bottom - top)
        if fill < seuil:
            faibles.append((k, fill))
print(f"{len(pages)} pages ; {len(faibles)} remplies à moins de {seuil:.0%} :")
print("  " + "  ".join(f"p{k}:{f:.0%}" for k, f in faibles))
