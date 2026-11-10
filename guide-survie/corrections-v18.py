"""Version 1.8 — page « Apprendre en vidéo » : chaînes et vidéos d'organismes officiels, vérifiées le 10 novembre 2026
(liens relevés sur leurs sites officiels, noms des chaînes contrôlés), avec QR codes pour l'édition imprimée.
Usage : python3 corrections-v18.py source/livret-corps.html   (module Python qrcode requis)
"""
import html as H
import sys

import qrcode
import qrcode.image.svg

path = sys.argv[1]
h = open(path, encoding="utf-8").read()
log = []


def rep(pt, old, new, n=1):
    global h
    c = h.count(old)
    assert c == n, f"{pt}: {c} occurrence(s) au lieu de {n} : {old[:80]}"
    h = h.replace(old, new)
    log.append(pt)


def qr(url):
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    svg = img.to_string(encoding="unicode")
    svg = svg.replace("<svg ", f'<svg class="qr" role="img" aria-label="QR code vers {H.escape(url)}" ', 1)
    return svg


# (organisme, ce qu'on y apprend, URL de la chaîne ou de la vidéo, site officiel, où le lien a été vérifié)
SOURCES = [
    ("Croix-Rouge française", "Premiers secours et gestes qui sauvent ; inscriptions aux formations PSC1.",
     "https://www.youtube.com/@CroixRougeFR", "croix-rouge.fr"),
    ("Protection Civile (FNPC)", "Premiers secours, défibrillateur, formations près de chez vous.",
     "https://www.youtube.com/@ProtectionCivileFR", "protection-civile.org"),
    ("AP-HP (hôpitaux de Paris)", "Santé et urgences, expliquées par des soignants.",
     "https://www.youtube.com/@APHPhopitauxdeParis", "aphp.fr"),
    ("FFME — test du DVA", "Ski de randonnée et avalanche : contrôle des DVA au départ (série de 4 vidéos : préparation, test DVA, pendant la sortie, alerte).",
     "https://youtu.be/h0dGRfWVg8A", "ffme.fr"),
    ("Sauveteurs en Mer (SNSM)", "Sécurité en mer et sur le littoral : préparer sa sortie, réagir en cas de problème.",
     "https://www.youtube.com/@SauveteursenMer-SNSM", "snsm.org"),
]

cartes = []
for nom, quoi, url, site in SOURCES:
    court = url.replace("https://www.", "").replace("https://", "")
    cartes.append(
        f'    <div class="video-carte">\n      {qr(url)}\n      <div><p class="video-nom">{H.escape(nom)}</p>'
        f'<p>{H.escape(quoi)}</p><p class="video-lien">{H.escape(court)} · site : {H.escape(site)}</p></div>\n    </div>')

section = f"""<section class="page" id="videos">
  <h2>Apprendre en vidéo</h2>
  <p>Voir un geste aide à le comprendre ; seul l'entraînement encadré permet de le maîtriser. Les chaînes ci-dessous appartiennent à des organismes officiels ou reconnus : leurs liens ont été relevés sur les sites officiels de ces organismes et vérifiés le 10 novembre 2026. Les adresses peuvent changer : en cas de doute, passez par le site officiel. Scannez le QR code avec l'appareil photo de votre téléphone (connexion nécessaire).</p>
  <div class="videos">
{chr(10).join(cartes)}
  </div>
  <p class="small">Avalanches : l'ANENA (anena.org) publie conseils et vidéos sur son site. Arrêt cardiaque : les applications Staying Alive ou SAUV Life (chapitre 8).</p>
  <h3>Choisir un bon tutoriel</h3>
  <ul>
    <li>Pour les urgences (étouffement, saignement, arrêt cardiaque, AVC, crise d'épilepsie), YouTube affiche en France, en tête des résultats, une sélection de vidéos de sources de santé reconnues, dont la Croix-Rouge française : commencez par celles-là.</li>
    <li>Vérifiez qui parle : organisme de secours, hôpital, fédération sportive. Le nombre de vues ne garantit rien.</li>
    <li>Préférez les vidéos françaises récentes : les gestes évoluent (recommandations européennes de 2021 et 2025, référentiel français de 2026) et les numéros d'urgence changent d'un pays à l'autre.</li>
    <li>Méfiez-vous d'une vidéo qui contredit ce livret. Signaux d'alarme : sucer ou inciser une morsure, garrot fait d'une ficelle, « test de comestibilité » d'une plante inconnue, boire l'eau d'une liane, frotter une gelure, feu ou réchaud dans une tente, traverser une eau en mouvement.</li>
  </ul>
</section>

"""

css = """  .videos { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: .6em 0; }
  @media (max-width: 640px) { .videos { grid-template-columns: 1fr; } }
  .video-carte { display: flex; gap: .6em; align-items: flex-start; border: 1px solid var(--line); border-radius: 8px; padding: .5em; break-inside: avoid; }
  .video-carte .qr { width: 2.3cm; height: 2.3cm; flex: none; background: #fff; border-radius: 4px; }
  .video-carte .qr path { fill: #000; }
  .video-carte p { margin: 0 0 .2em; font-size: .9em; }
  .video-nom { font: 700 .95em "Trebuchet MS", system-ui, sans-serif !important; color: var(--accent); }
  .video-lien { font-size: .78em !important; color: var(--muted); word-break: break-all; }
"""
rep("CSS", "  /* Illustrations", css + "  /* Illustrations")
rep("SECTION", '<section class="page" id="sources">', section + '<section class="page" id="sources">')
rep("SOMMAIRE", '      <li><a href="#sources"><span class="t">Sources et limites</span></a><span class="pg" data-for="sources"></span></li>',
    '      <li><a href="#videos"><span class="t">Apprendre en vidéo</span></a><span class="pg" data-for="videos"></span></li>\n'
    '      <li><a href="#sources"><span class="t">Sources et limites</span></a><span class="pg" data-for="sources"></span></li>')
rep("COUV", "Version 1.7 — 10 novembre 2026", "Version 1.8 — 10 novembre 2026")
rep("MENTIONS", "<b>Petit guide de survie</b> — version 1.7, 10 novembre 2026.", "<b>Petit guide de survie</b> — version 1.8, 10 novembre 2026.")

open(path, "w", encoding="utf-8").write(h)
print(len(log), "opérations :", ", ".join(log))
