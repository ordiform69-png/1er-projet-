"""Version 1.5 — édition publique : sommaire par parties avec numéros de page, mentions, bandeaux de parties,
fiches réflexes resserrées (une ligne par geste), page « Sources et limites ».
Usage : python3 corrections-v15.py source/livret-corps.html
"""
import re
import sys

path = sys.argv[1]
h = open(path, encoding="utf-8").read()
log = []


def rep(pt, old, new, n=1):
    global h
    c = h.count(old)
    assert c == n, f"{pt}: {c} occurrence(s) au lieu de {n} : {old[:80]}"
    h = h.replace(old, new)
    log.append(pt)


# ---------- Couverture, mentions, sommaire ----------
rep("COUV", "Version 1.4 — 9 novembre 2026 · hors ligne — à enregistrer sur votre téléphone ou à imprimer (format A5).",
    "Version 1.5 — 10 novembre 2026 · hors ligne — à enregistrer sur votre téléphone ou à imprimer (format A5).")

i = h.index('  <nav class="toc" style="text-align:left">')
j = h.index("  </nav>", i) + len("  </nav>")
old_nav = h[i:j]

PARTIES = [
    ("I", "Les fondamentaux", [("priorites", "1", "Les priorités"), ("kit", "2", "Le kit de survie"), ("abri", "3", "S'abriter"),
                               ("feu", "4", "Faire du feu"), ("feu-techniques", "4 bis", "Les techniques d'allumage"),
                               ("eau", "5", "Trouver et purifier l'eau"), ("orientation", "6", "S'orienter"), ("signaux", "7", "Se faire repérer")]),
    ("II", "Soigner et se nourrir", [("secours", "8", "Premiers secours"), ("nourriture", "9", "Se nourrir"), ("plantes", "10", "Plantes utiles")]),
    ("III", "Savoir-faire", [("militaire", "11", "Techniques issues de l'armée"), ("noeuds", "12", "Nœuds utiles"),
                             ("fabrications", "13", "Fabrications simples et efficaces")]),
    ("IV", "Milieux et dangers", [("meteo", "14", "Météo et dangers"), ("montagne", "15", "Survie en montagne"), ("mer", "16", "Survie en mer et dans l'eau"),
                                  ("desert", "17", "Désert et chaleur extrême"), ("froid", "18", "Grand froid, neige et glace"),
                                  ("jungle", "19", "Forêt tropicale et jungle"), ("ville", "20", "En ville et en cas de catastrophe")]),
    ("V", "Selon ce que vous avez sur vous", [("rien", "21", "Avec rien sur soi"), ("outils", "22", "Avec un couteau ou un outil")]),
    ("VI", "Aide-mémoire", [("fiches", "23", "Fiches réflexes"), ("entrainement", "24", "Programme d'entraînement"), ("checklist", "25", "Check-lists")]),
]


def ligne(ident, num, titre, cls=""):
    n = f'<span class="n">{num}</span>' if num else ""
    return f'      <li{cls}><a href="#{ident}">{n}<span class="t">{titre}</span></a><span class="pg" data-for="{ident}"></span></li>'


lignes = [ligne("avant-propos", "", "Avant-propos : à quoi sert ce livret", ' class="hors"')]
for num, titre, chap in PARTIES:
    lignes.append(f'      <li class="partie">Partie {num} · {titre}</li>')
    lignes += [ligne(*c) for c in chap]
lignes.append('      <li class="partie">Pour aller plus loin</li>')
lignes += [ligne("glossaire", "", "Petit glossaire"), ligne("index", "", "Index"),
           ligne("sources", "", "Sources et limites"), ligne("credits", "", "Crédits photographiques")]
nav = ('<section class="page" id="sommaire">\n  <nav class="toc">\n    <h2>Sommaire</h2>\n'
       '    <p class="urgence"><b>Urgence ?</b> Appelez le <b>112</b> (ou le 15), puis ouvrez les '
       '<a href="#fiches">fiches réflexes</a><span class="pg-inline" data-for="fiches"></span>.</p>\n'
       '    <ul class="toc-list">\n' + "\n".join(lignes) + "\n    </ul>\n  </nav>\n</section>")

mentions = """<section class="page" id="mentions">
  <h2>À propos de cette édition</h2>
  <p><b>Petit guide de survie</b> — version 1.5, 10 novembre 2026. Édition grand public, lisible hors ligne et imprimable (A5).</p>
  <p><b>Informations vérifiées au 10 novembre 2026</b> : numéros d'urgence, règles françaises (feu en forêt, couteaux, balises de détresse), recommandations de secourisme et de santé. Les règles et les recommandations évoluent : vérifiez-les avant de partir.</p>
  <p><b>Responsabilité.</b> Ce livret donne des repères généraux. Il ne remplace ni une formation aux premiers secours, ni un stage encadré, ni les consignes des secours et des autorités. En cas d'urgence : <b>112</b> ou <b>15</b>.</p>
  <p><b>Relecture.</b> Chaque consigne a fait l'objet d'une vérification documentaire à partir de sources officielles (voir « Sources et limites »). Une relecture des premiers secours par un formateur PSC ou un médecin, et des plantes par un botaniste, est prévue avant toute diffusion.</p>
  <p><b>Illustrations.</b> Dessins et pictogrammes réalisés pour ce livret. Photographies sous licences libres ; auteurs et licences dans les « Crédits photographiques ».</p>
</section>"""

rep("SOMMAIRE", old_nav, "")
# fin de la section couverture : on ajoute mentions et sommaire juste après
k = h.index("</section>", h.index('<section class="page cover">')) + len("</section>")
h = h[:k] + "\n\n" + mentions + "\n\n" + nav + h[k:]
log.append("MENTIONS")

css = """  .toc h2 { margin-bottom: .4em; }
  .toc .urgence { border: 2px solid var(--accent); border-radius: 6px; padding: .4em .6em; margin: 0 0 .8em; }
  .toc-list { list-style: none; padding: 0; margin: 0; }
  .toc-list li { display: flex; align-items: baseline; gap: .3em; margin: .12em 0; }
  .toc-list li a { flex: 1 1 auto; display: flex; align-items: baseline; gap: .3em; color: inherit; text-decoration: none; }
  .toc-list li a::after { content: ""; flex: 1 1 auto; border-bottom: 1px dotted var(--muted); margin: 0 .2em; transform: translateY(-.25em); }
  .toc-list .n { min-width: 2.6em; color: var(--accent); font-weight: 600; }
  .toc-list li.partie { display: block; margin: .7em 0 .15em; font: 700 .9em "Trebuchet MS", system-ui, sans-serif; color: var(--accent); text-transform: uppercase; letter-spacing: .04em; }
  .toc-list li.hors { margin-bottom: .3em; }
  .pg { min-width: 1.6em; text-align: right; font-variant-numeric: tabular-nums; }
  .partie-bandeau { margin: 0 0 .3em; font: 700 .85em "Trebuchet MS", system-ui, sans-serif; color: var(--accent); text-transform: uppercase; letter-spacing: .06em; }
  .index-cols { columns: 2; column-gap: 1.6em; font-size: .9em; }
  .index-cols p { margin: 0 0 .15em; break-inside: avoid; }
  .index-cols .lettre { font: 700 1.05em "Trebuchet MS", system-ui, sans-serif; color: var(--accent); margin-top: .5em; }
"""
rep("CSS-TOC", "  .toc ol { columns: 2; column-gap: 2em; }\n  @media (max-width: 640px) { .toc ol { columns: 1; } }\n", css)
rep("CSS-PRINT", "    #avant-propos, #annexe-note { break-before: page;", "    #mentions, #sommaire, #avant-propos, #index, #annexe-note { break-before: page;")

# ---------- Bandeaux de parties ----------
for num, titre, chap in PARTIES:
    ident = chap[0][0]
    a = f'<section class="page" id="{ident}">\n'
    rep(f"PARTIE-{num}", a, a + f'  <p class="partie-bandeau">Partie {num} · {titre}</p>\n')

# ---------- Fiches réflexes : une ligne par geste (même contenu ; détails au chapitre indiqué) ----------
F = [
    ("<li>J'appelle le 112 depuis ma position sûre. Si je ne peux pas parler ou entendre&nbsp;: 114 (SMS ou appli). Si l'appel ne passe pas&nbsp;: SMS à un proche qui alerte les secours et me le confirme. Après l'alerte, je reste joignable (pas de mode avion).</li>",
     "<li>J'appelle le 112. Je ne peux pas parler ou entendre&nbsp;: 114 (SMS, appli). L'appel ne passe pas&nbsp;: SMS à un proche qui alerte et me le confirme. Puis je reste joignable (pas de mode avion).</li>"),
    ("<li>Oui : PLS si aucun traumatisme ; après une chute, un choc ou si la cause est inconnue, je le laisse sur le dos, voies aériennes libres. J'alerte (112).</li>",
     "<li>Oui : PLS. Après une chute, un choc ou si la cause est inconnue : sur le dos, voies aériennes libres. J'alerte (112).</li>"),
    ("<li>Il ne répond pas et ne respire pas, ou respire anormalement (vérifiez pendant 10 s au plus, après avoir libéré les voies aériennes) : c'est un arrêt, commencez.</li>\n        <li>Appelez le 15 ou le 112 en haut-parleur (ou faites appeler et apporter un DAE), puis suivez les consignes du régulateur.</li>\n        <li>Insufflations par bouche-à-bouche (bouche-à-bouche-et-nez pour le nourrisson) : cycles de 15 compressions et 2 insufflations.</li>\n        <li>Faites 100 à 120 compressions par minute en enfonçant d'un tiers de l'épaisseur du thorax (environ 5 cm chez l'enfant, environ 4 cm chez le nourrisson) : une main pour l'enfant (deux si nécessaire), les deux pouces pour le nourrisson. Chez l'enfant, les insufflations sont importantes : faites-les si vous le pouvez. Si vous ne pouvez pas ou ne savez pas insuffler, faites au moins les compressions, en continu (recommandations européennes ERC 2025 ; le référentiel français ne le précise que pour l'adulte).</li>\n        <li>Utilisez le DAE dès que possible, avec les électrodes ou le mode enfant. À défaut, utilisez les électrodes adultes, l'une devant au milieu de la poitrine et l'autre dans le dos.</li>",
     "<li>Ne répond pas, ne respire pas ou respire anormalement (10 s au plus, voies aériennes libérées) : c'est un arrêt, je commence.</li>\n        <li>15 ou 112 en haut-parleur, DAE demandé ; je suis les consignes du régulateur.</li>\n        <li>Cycles de 15 compressions et 2 insufflations (bouche-à-bouche ; bouche-à-bouche-et-nez chez le nourrisson).</li>\n        <li>100 à 120 compressions/min, un tiers du thorax (environ 5 cm enfant, 4 cm nourrisson) ; une main (deux si besoin), deux pouces chez le nourrisson. Je ne peux pas insuffler : compressions seules, en continu.</li>\n        <li>DAE dès que possible : électrodes ou mode enfant ; sinon électrodes adultes, une devant au milieu de la poitrine, une dans le dos.</li>"),
    ("<li>Je la protège du froid et je la surveille sans arrêt. Ne répond plus et respire normalement : PLS. Ne respire pas normalement : fiche 3.</li>",
     "<li>Je la protège du froid, je la surveille. Ne répond plus mais respire : PLS. Ne respire pas normalement : fiche 3.</li>"),
    ("<li>Membre, compression inefficace : garrot conçu à cet effet (ou lien large 3–5 cm non élastique + serrage), entre la plaie et la racine du membre, jamais sur une articulation.</li>",
     "<li>Membre, compression inefficace : garrot (ou lien large 3–5 cm non élastique, serré) entre la plaie et la racine du membre, jamais sur une articulation.</li>"),
    ("<li>Je garde la tête hors de l'eau et je laisse ma respiration se calmer (le choc passe en général en moins d'une minute).</li>",
     "<li>Tête hors de l'eau, je laisse ma respiration se calmer (moins d'une minute en général).</li>"),
    ("<li>Tonnerre audible : je rejoins tout de suite un bâtiment fermé ou un véhicule fermé à toit rigide, si c'est possible sans danger.</li>",
     "<li>Tonnerre audible : je rejoins un bâtiment ou un véhicule fermé à toit rigide, si c'est sans danger.</li>"),
]
for k, (o, n) in enumerate(F, 1):
    rep(f"FICHE-{k}", o, n)

# ---------- Sources et limites (avant les crédits) ----------
sources = """<section class="page" id="sources">
  <h2>Sources et limites</h2>
  <p>Les consignes de ce livret s'appuient d'abord sur des sources officielles françaises, complétées par des références européennes ou internationales quand aucune source française n'existe. Principales références :</p>
  <ul>
    <li><b>Premiers secours</b> : Références techniques nationales – Premiers secours citoyen (DGSCGC, juillet 2026) ; recommandations européennes de réanimation (ERC 2025) ; Assurance maladie (ameli.fr) pour le malaise, l'AVC et la douleur thoracique.</li>
    <li><b>Eau et alimentation</b> : ministère de la Santé (guide ORSEC eau potable), Anses (eau, douve, échinococcose, biberons), CDC (eau en situation d'urgence), Eawag (désinfection solaire SODIS), centres antipoison.</li>
    <li><b>Alerte et secours</b> : service-public.fr (112, 114), Urgence 114, ministère de la Mer (balises de détresse, fausses alertes, 196), Cospas-Sarsat, sécurité civile (signal national d'alerte, FR-Alert).</li>
    <li><b>Météo et milieux</b> : Météo-France (vigilance, météo des forêts), Vigicrues, bulletins d'avalanche (BERA), EDF (lâchers d'eau), RNLI (eau froide, courants).</li>
    <li><b>Règles françaises</b> : Code forestier (art. L131-1, feu en forêt), réglementation sur le port et le transport des couteaux, FFRandonnée (balisage).</li>
  </ul>
  <h3>Limites</h3>
  <ul>
    <li>Ce livret ne remplace ni une formation pratique (PSC1, stage de survie, alpinisme, mer), ni les consignes des secours et des autorités, qui priment toujours.</li>
    <li>Aucune photo ni description ne suffit à identifier une plante ou un champignon : en cas de doute, ne mangez pas.</li>
    <li>Les règles citées sont celles de la France au 10 novembre 2026 ; à l'étranger, renseignez-vous sur les règles et les numéros locaux.</li>
    <li>Quand les sources ne s'accordent pas, ce livret retient la consigne la plus prudente. Le détail des corrections et des sources figure dans le dossier éditorial qui accompagne cette édition.</li>
  </ul>
</section>

"""
rep("SOURCES", '<section class="page credits" id="credits">', sources + '<section class="page credits" id="credits">')

open(path, "w", encoding="utf-8").write(h)
print(len(log), "opérations :", ", ".join(log))
