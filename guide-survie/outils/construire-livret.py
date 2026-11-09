"""Construit le livret complet (HTML et Markdown) : le guide suivi de ses annexes.

Sources (dossier guide-survie/) :
  source/livret-corps.html   le guide (avant-propos, 25 chapitres, glossaire, crédits)
  source/note-de-version.md  annexe A
  JOURNAL-CORRECTIONS.md     annexe B
  CONTROLE-PERSISTANCE.md    annexe C
Sorties : guide-survie.html, guide-survie-corrige.md (le PDF est produit ensuite par outils/livret-pdf.js).

Usage : python3 outils/construire-livret.py   (depuis le dossier guide-survie)
"""
import os
import re
import subprocess
import sys

import markdown

G = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
read = lambda p: open(os.path.join(G, p), encoding="utf-8").read()

ANNEXES = [
    ("annexe-note", "Annexe A — Note de version", "source/note-de-version.md"),
    ("annexe-journal", "Annexe B — Journal des corrections", "JOURNAL-CORRECTIONS.md"),
    ("annexe-controle", "Annexe C — Contrôles", "CONTROLE-PERSISTANCE.md"),
]

# ---------- HTML ----------
html = read("source/livret-corps.html")
css = """
  .annexe { font-size: .86em; }
  .annexe table { font-size: .82em; }
  .annexe td, .annexe th { padding: .3em .4em; }
  .annexe h3 { font-size: 1.05em; }
  .annexe code { font-size: .9em; }
  @media print { .annexe table { break-inside: auto; } .annexe tr { break-inside: avoid; } }
"""
assert html.count("  /* Illustrations") == 1
html = html.replace("  /* Illustrations", css + "  /* Illustrations", 1)

sections = ""
for ident, titre, src in ANNEXES:
    body = markdown.markdown(read(src), extensions=["tables", "fenced_code"])
    body = re.sub(r"<h1>(.*?)</h1>", f"<h2>{titre}</h2>", body, count=1)
    sections += f'\n<section class="page annexe" id="{ident}">\n{body}\n</section>\n'
assert html.count("\n</body>") == 1
html = html.replace("\n</body>", sections + "\n</body>", 1)

old = '<a href="#glossaire">Petit glossaire</a> · <a href="#credits">Crédits photographiques</a></p>'
assert html.count(old) == 1, "sommaire"
liens = " · ".join(f'<a href="#{i}">{t}</a>' for i, t, _ in ANNEXES)
html = html.replace(old, old + f'\n    <p style="margin:.2em 0 0">{liens}</p>', 1)
open(os.path.join(G, "guide-survie.html"), "w", encoding="utf-8").write(html)

# ---------- Markdown ----------
tmp = os.path.join(G, ".corps.md")
subprocess.run([sys.executable, os.path.join(G, "outils/html-vers-markdown.py"),
                os.path.join(G, "source/livret-corps.html"), tmp], check=True, capture_output=True)
md = open(tmp, encoding="utf-8").read().rstrip("\n")
os.remove(tmp)
for _, titre, src in ANNEXES:
    t = read(src)
    t = re.sub(r"^# .*$", f"# {titre}", t, count=1, flags=re.M)
    md += "\n\n---\n\n" + t.strip("\n")
open(os.path.join(G, "guide-survie-corrige.md"), "w", encoding="utf-8").write(md + "\n")
print("livret construit :", len(html) // 1024, "Ko HTML ;", md.count("\n"), "lignes Markdown")
