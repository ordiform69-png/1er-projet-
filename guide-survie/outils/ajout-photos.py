"""Insère des photos libres dans source/livret-corps.html et complète le tableau des crédits.

Usage : python3 outils/ajout-photos.py source/photos-ajout-v14.json <candidats.json> <dossier des vignettes>
- candidats.json : métadonnées Openverse (titre, page, licence, auteur) par sujet ; « n-sujet-3 » = 4e candidat du sujet.
- Modes d'ancrage : « after » (après l'élément p/li/ul/ol/table/div qui suit l'ancre) ;
  « after_box » (après l'encadré <div class="box"> qui contient l'ancre).
Les images sont réduites (900 × 700 px au plus) et intégrées au HTML, qui reste un fichier unique hors ligne.
"""
import base64
import html as H
import io
import json
import os
import re
import sys

from PIL import Image

G = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(G, "source/livret-corps.html")
sel = json.load(open(sys.argv[1], encoding="utf-8"))
cands = json.load(open(sys.argv[2], encoding="utf-8"))
thumbs = sys.argv[3]
s = open(src, encoding="utf-8").read()

nums = [int(n) for n in re.findall(r"<tr><td>(\d+)</td><td>", s[s.index('id="credits"'):])]
n = max(nums)
errors, rows = [], []


def embed(path):
    im = Image.open(path).convert("RGB")
    im.thumbnail((900, 700))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=72, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), im.size


def artist(a):
    a = re.sub(r"\s+", " ", a or "").strip()
    return (a[:80] + "…") if len(a) > 80 else (a or "auteur non indiqué")


for item in sel:
    a = item["anchor"]
    if s.count(a) != 1:
        errors.append(f"{s.count(a)} × ancre : {a[:70]}")
        continue
    if 'figure class="photo' in s[s.index(a):s.index(a) + 4000] and item["mode"] != "after_box":
        pass
    cells = []
    for im in item["images"]:
        key, idx = im["id"].rsplit("-", 1)
        c = cands[key][int(idx)]
        path = os.path.join(thumbs, f"{im['id']}.jpg")
        if not os.path.exists(path):
            errors.append(f"vignette absente : {im['id']}")
            continue
        n += 1
        uri, (w, h) = embed(path)
        lab = f'<span class="lab">{H.escape(im["label"])}</span>' if im.get("label") else ""
        alt = im.get("alt") or im.get("label") or im["subject"]
        cells.append(f'<div class="cell"><img src="{uri}" width="{w}" height="{h}" alt="{H.escape(alt)}">{lab}'
                     f'<span class="credit">© {H.escape(artist(c["artist"]))} — {H.escape(c["license"])} (crédit n° {n})</span></div>')
        rows.append(f'    <tr><td>{n}</td><td>{H.escape(im["subject"])}</td><td>{H.escape(artist(c["artist"]))}</td>'
                    f'<td>{H.escape(c["license"])}</td><td>{H.escape(c["page"])}</td></tr>')
    kind = "grid" if len(cells) > 1 else "single"
    fig = (f'\n  <figure class="photo {kind}">\n    <div class="cells">{"".join(cells)}</div>\n'
           f'    <figcaption>{item["caption"]}</figcaption>\n  </figure>')
    pos = s.index(a)
    if item["mode"] == "after_box":
        start = s.rfind('<div class="box', 0, pos)
        depth, i = 0, start
        while True:  # fin de l'encadré (divs imbriqués compris)
            m = re.compile(r"<div\b|</div>").search(s, i)
            depth += 1 if m.group(0) == "<div" else -1
            i = m.end()
            if depth == 0:
                break
        end = i
    else:
        m = re.compile(r"</(p|li|ul|ol|table|div)>").search(s, pos)
        end = m.end()
        if m.group(1) == "li":
            end = re.compile(r"</(ul|ol)>").search(s, pos).end()
    s = s[:end] + fig + s[end:]

if errors:
    sys.exit("ERREURS :\n - " + "\n - ".join(errors))

table_end = s.index("</table>", s.index('id="credits"'))
s = s[:table_end] + "\n".join(rows) + "\n  " + s[table_end:]
s = s.replace("Les photographies proviennent de Flickr et de Wikimedia Commons (recherche via Openverse)",
              "Les photographies proviennent de Flickr, de Wikimedia Commons et de Rawpixel (recherche via Openverse)", 1)
open(src, "w", encoding="utf-8").write(s)
print(f"{len(rows)} photos ajoutées ; crédits n° {n - len(rows) + 1} à {n}")
