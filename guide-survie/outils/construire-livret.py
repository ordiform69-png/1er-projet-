"""Construit les deux éditions du livret.

- Édition publique : guide-survie.html, guide-survie.pdf, guide-survie-corrige.md
  (guide, glossaire, index, sources et limites, crédits ; sommaire et index avec numéros de page).
- Dossier éditorial : dossier-editorial.html, dossier-editorial.pdf, dossier-editorial.md
  (édition publique + annexes A note de version, B journal des corrections, C contrôles).

Sources (dossier guide-survie/) : source/livret-corps.html, source/note-de-version.md,
JOURNAL-CORRECTIONS.md, CONTROLE-PERSISTANCE.md, outils/index-termes.txt.
Usage : python3 outils/construire-livret.py   (Playwright et poppler-utils requis)
"""
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

import markdown
from bs4 import BeautifulSoup, NavigableString

O = os.path.dirname(os.path.abspath(__file__))
G = os.path.dirname(O)
read = lambda p: open(os.path.join(G, p), encoding="utf-8").read()
NBSP, NNBSP = " ", " "

ANNEXES = [
    ("annexe-note", "Annexe A — Note de version", "source/note-de-version.md"),
    ("annexe-journal", "Annexe B — Journal des corrections", "JOURNAL-CORRECTIONS.md"),
    ("annexe-controle", "Annexe C — Contrôles", "CONTROLE-PERSISTANCE.md"),
]


# ---------- typographie française (texte visible seulement) ----------
def typographie(html):
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.find_all(string=True):
        if s.parent.name in ("style", "script", "title") or s.find_parent("svg") or "://" in s:
            continue
        t = str(s)
        t2 = re.sub(r" ([;!?])", NNBSP + r"\1", t)
        t2 = re.sub(r" :", NBSP + ":", t2)
        t2 = re.sub(r"« ", "«" + NBSP, t2)
        t2 = re.sub(r" »", NBSP + "»", t2)
        t2 = re.sub(r"(\d) (h|min|s|m|cm|km|mm|L|mL|kg|g|°C|%|MHz)\b", r"\1" + NBSP + r"\2", t2)
        if t2 != t:
            s.replace_with(NavigableString(t2))
    return str(soup)


def pdf(html_path, pdf_path):
    subprocess.run(["node", os.path.join(O, "livret-pdf.js"), html_path, pdf_path], check=True)


def pages_texte(pdf_path):
    n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True).stdout).group(1))
    out = subprocess.run(["pdftotext", "-layout", pdf_path, "-"], capture_output=True, text=True).stdout
    pages = out.split("\f")[:n]
    return pages


def norm(t):
    t = unicodedata.normalize("NFC", t).replace(NBSP, " ").replace(NNBSP, " ")
    return re.sub(r"\s+", "", t).lower()


def titres(html):
    soup = BeautifulSoup(html, "html.parser")
    res = []
    for sec in soup.body.find_all("section", recursive=False):
        ident = sec.get("id")
        if not ident:
            continue
        h = sec.find(["h2", "h3"])
        if h is None:
            continue
        for svg in h.find_all("svg"):
            svg.decompose()
        res.append((ident, h.get_text("", strip=True)))
    return res


def localiser(pages, titres_):
    """Page de début de chaque section : le titre doit occuper seul une ligne (ou commencer une ligne s'il est coupé)."""
    lignes = [[norm(l) for l in p.splitlines() if l.strip()] for p in pages]
    res, debut = {}, 1
    for ident, t in titres_:
        cle = norm(t)
        for k in range(debut, len(pages)):
            if any(l == cle or (len(l) >= 12 and cle.startswith(l)) for l in lignes[k]):
                res[ident] = k + 1
                debut = k
                break
    return res


def index_html(pages, deb, fin):
    termes = []
    for l in read("outils/index-termes.txt").splitlines():
        if not l.strip() or l.startswith("#"):
            continue
        terme, formes = [x.strip() for x in l.split("|")]
        termes.append((terme, [f.strip() for f in formes.split(";")]))
    lignes, lettre = [], ""
    for terme, formes in sorted(termes, key=lambda x: unicodedata.normalize("NFD", x[0].lower()).encode("ascii", "ignore")):
        compte = {}
        for k in range(deb - 1, fin - 1):
            txt = pages[k].replace(NBSP, " ").replace(NNBSP, " ")
            c = 0
            for f in formes:
                motif = re.escape(f).replace("\\ ", r"\s+")  # un terme peut être coupé en fin de ligne
                flags = 0 if (f.isupper() or f[:1].isdigit() or f in ("If",)) else re.I
                c += len(re.findall(r"(?<![\w])" + motif + r"(?![\w])", txt, flags))
            if c:
                compte[k + 1] = c
        if not compte:
            continue
        meilleures = sorted(sorted(compte, key=lambda p: -compte[p])[:5])
        l0 = unicodedata.normalize("NFD", terme[0]).encode("ascii", "ignore").decode().upper() or terme[0]
        if l0.isdigit():
            l0 = "0–9"
        if l0 != lettre:
            lettre = l0
            lignes.append(f'<p class="lettre">{lettre}</p>')
        lignes.append(f"<p>{terme}{NBSP}: {', '.join(map(str, meilleures))}</p>")
    return "\n    ".join(lignes)


def section_index(contenu):
    return ('<section class="page" id="index">\n  <h2>Index</h2>\n'
            '  <p class="small">Pages principales où le sujet est traité (5 au plus par entrée).</p>\n'
            f'  <div class="index-cols">\n    {contenu}\n  </div>\n</section>\n\n')


def remplir_numeros(html, pos):
    def r(m):
        ident = m.group(2)
        return f'{m.group(1)}{pos.get(ident, "")}{m.group(3)}'
    html = re.sub(r'(<span class="pg" data-for="([\w-]+)">)[^<]*(</span>)', r, html)
    html = re.sub(r'(<span class="pg-inline" data-for="([\w-]+)">)[^<]*(</span>)',
                  lambda m: f'{m.group(1)}{", page " + str(pos[m.group(2)]) if m.group(2) in pos else ""}{m.group(3)}', html)
    return html


# ---------- édition publique ----------
corps = read("source/livret-corps.html")
assert '<section class="page credits" id="credits">' in corps
# l'index suit le glossaire
_g = corps.index('<section class="page" id="glossaire">')
_f = corps.index("</section>", _g) + len("</section>")
base = corps[:_f] + "\n\n<!--INDEX-->" + corps[_f:]
assert "<!--INDEX-->" in base

tmp = tempfile.mkdtemp()
h_pub = os.path.join(G, "guide-survie.html")
p_pub = os.path.join(G, "guide-survie.pdf")

# passe 1 : index provisoire (mêmes termes, numéros fictifs de même largeur)
pos, idx = {}, section_index("<p>…</p>")
for passe in range(4):
    html = remplir_numeros(base.replace("<!--INDEX-->", idx), pos)
    html = typographie(html)
    open(h_pub, "w", encoding="utf-8").write(html)
    pdf(h_pub, p_pub)
    pages = pages_texte(p_pub)
    nouv = localiser(pages, titres(html))
    deb, fin = nouv.get("avant-propos", 1), nouv.get("glossaire", len(pages))
    nouv_idx = section_index(index_html(pages, deb, fin))
    if nouv == pos and nouv_idx == idx:
        break
    pos, idx = nouv, nouv_idx
else:
    sys.exit("les numéros de page ne se stabilisent pas")
manquants = [i for i, _ in titres(html) if i not in pos]
print(f"édition publique : {len(pages)} pages ; sommaire stable après {passe + 1} passes ; sections non localisées : {manquants or 'aucune'}")

# Markdown public (sans numéros de page)
md_tmp = os.path.join(tmp, "corps.md")
subprocess.run([sys.executable, os.path.join(O, "html-vers-markdown.py"), os.path.join(G, "source/livret-corps.html"), md_tmp],
               check=True, capture_output=True)
md_pub = open(md_tmp, encoding="utf-8").read().rstrip("\n")
open(os.path.join(G, "guide-survie-corrige.md"), "w", encoding="utf-8").write(md_pub + "\n")

# ---------- dossier éditorial = édition publique + annexes ----------
css = """
  .annexe { font-size: .86em; }
  .annexe table { font-size: .82em; }
  .annexe td, .annexe th { padding: .3em .4em; }
  .annexe h3 { font-size: 1.05em; }
  .annexe code { font-size: .9em; }
  @media print { .annexe table { break-inside: auto; } .annexe tr { break-inside: avoid; } }
"""
dos = html.replace("  /* Illustrations", css + "  /* Illustrations", 1)
sections, md_dos = "", md_pub
for ident, titre, src in ANNEXES:
    body = markdown.markdown(read(src), extensions=["tables", "fenced_code"])
    body = re.sub(r"<h1>(.*?)</h1>", f"<h2>{titre}</h2>", body, count=1)
    sections += f'\n<section class="page annexe" id="{ident}">\n{body}\n</section>\n'
    t = re.sub(r"^# .*$", f"# {titre}", read(src), count=1, flags=re.M)
    md_dos += "\n\n---\n\n" + t.strip("\n")
dos = dos.replace("\n</body>", sections + "\n</body>", 1)
liens = "".join(f'      <li><a href="#{i}"><span class="t">{t}</span></a><span class="pg"></span></li>\n' for i, t, _ in ANNEXES)
dos, nb = re.subn(r"</ul>\s*</nav>", lambda m: '<li class="partie">Dossier éditorial</li>\n' + liens + "</ul>\n</nav>", dos, count=1)
assert nb == 1, "fin du sommaire introuvable"
dos = dos.replace("<title>Petit guide de survie</title>", "<title>Petit guide de survie — dossier éditorial</title>", 1)
h_dos, p_dos = os.path.join(G, "dossier-editorial.html"), os.path.join(G, "dossier-editorial.pdf")
open(h_dos, "w", encoding="utf-8").write(dos)
pdf(h_dos, p_dos)
pg_dos = pages_texte(p_dos)
pos_dos = localiser(pg_dos, titres(dos))
dos = re.sub(r'(<a href="#(annexe-[\w-]+)"><span class="t">[^<]*</span></a><span class="pg">)(</span>)',
             lambda m: m.group(1) + str(pos_dos.get(m.group(2), "")) + m.group(3), dos)
open(h_dos, "w", encoding="utf-8").write(dos)
pdf(h_dos, p_dos)
open(os.path.join(G, "dossier-editorial.md"), "w", encoding="utf-8").write(md_dos + "\n")
print(f"dossier éditorial : {len(pages_texte(p_dos))} pages (annexes p. {', '.join(str(pos_dos.get(i)) for i, _, _ in ANNEXES)})")
