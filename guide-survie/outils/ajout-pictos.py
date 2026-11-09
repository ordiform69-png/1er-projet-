"""Ajoute les pictogrammes aux fiches réflexes et aux check-lists de source/livret-corps.html (une seule fois)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pictos import svg  # noqa: E402

G = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = os.path.join(G, "source/livret-corps.html")
h = open(p, encoding="utf-8").read()
assert 'class="picto"' not in h, "pictogrammes déjà présents"

FICHES = [
    ("1 · Je suis perdu", "perdu", "Boussole"),
    ("2 · Nuit imprévue dehors", "nuit", "Lune et abri"),
    ("3 · Un adulte est inconscient", "inconscient", "Personne allongée et cœur"),
    ("3 bis · Enfant ou nourrisson qui ne respire pas", "enfant", "Enfant et cœur"),
    ("3 ter · Malaise, douleur dans la poitrine, signes d'AVC", "malaise", "Cœur et tracé cardiaque"),
    ("4 · Saignement abondant", "saignement", "Goutte de sang"),
    ("5 · Tombé dans l'eau froide", "eau-froide", "Tête hors de l'eau"),
    ("6 · Passé à travers la glace", "glace", "Glace fissurée"),
    ("7 · Orage en pleine nature", "orage", "Nuage d'orage et éclair"),
    ("8 · Voiture bloquée dans la neige", "voiture", "Voiture et flocon"),
    ("9 · Coup de chaleur", "chaleur", "Soleil et thermomètre"),
    ("10 · Catastrophe à la maison", "maison", "Maison fissurée"),
]
for titre, nom, label in FICHES:
    old = f"<h4>{titre}</h4>"
    assert h.count(old) == 1, titre
    h = h.replace(old, f'<h4>{svg(nom, label)}<span>{titre}</span></h4>')

# check-lists (chapitre 25) seulement
i = h.index('<section class="page" id="checklist">')
avant, cl = h[:i], h[i:]
for titre, nom, label in [("Avant de partir", "sac", "Sac à dos"), ("Si je suis perdu", "perdu", "Boussole")]:
    old = f"  <h3>{titre}</h3>"
    assert cl.count(old) == 1, titre
    cl = cl.replace(old, f'  <h3 class="avec-picto">{svg(nom, label)}<span>{titre}</span></h3>')
h = avant + cl

css = """  .picto { width: 2.1em; height: 2.1em; flex: none; color: var(--accent); }
  .fiche h4, h3.avec-picto { display: flex; align-items: center; gap: .5em; }
  h3.avec-picto .picto { width: 1.8em; height: 1.8em; }
"""
assert h.count("  /* Illustrations") == 1
h = h.replace("  /* Illustrations", css + "  /* Illustrations", 1)
open(p, "w", encoding="utf-8").write(h)
print("pictogrammes ajoutés :", len(FICHES) + 2)
