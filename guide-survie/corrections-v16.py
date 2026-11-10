"""Version 1.6 — relecture de la v1.5 (faite par l'auteur, faute de relecture par les agents) :
légendes alignées sur le texte du livret, numéro 196 précisé (France), pêche, crédit de la planche de myrtille.
Usage : python3 corrections-v16.py source/livret-corps.html
"""
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


# Légendes : ne rien affirmer qui ne soit pas dans le texte du livret
rep("L-ORAGE", "Un nuage qui monte très haut en forme de chou-fleur ou d'enclume (cumulonimbus) annonce l'orage : quittez crêtes, sommets et eau avant que la foudre ne tombe.",
    "Les nuages à fort développement vertical (cumulonimbus) annoncent souvent l'orage. Dès que le tonnerre est audible, rejoignez un bâtiment fermé ou un véhicule fermé à toit rigide, si c'est possible sans danger.")
rep("L-INONDATION", "Ne traversez jamais une rue inondée, à pied ou en voiture : l'eau cache le courant, les trous et les plaques d'égout soulevées.",
    "Ne marchez et ne roulez jamais dans l'eau en mouvement : 15 cm d'eau courante peuvent faire tomber un adulte, 30 cm emporter une voiture.")
rep("L-GLACE", "La glace d'un lac peut être fine même par grand froid : une fissure, de la neige qui cache l'eau ou un courant suffisent. Pour la nuit, une tente adaptée, un bon couchage et un sol isolé.",
    "L'épaisseur seule ne garantit jamais la sécurité de la glace : glace blanche ou grise, près des berges, des roseaux ou des courants, elle est beaucoup plus fragile. Pour la nuit dans la neige : un couchage adapté et un sol isolé.")
rep("L-BIVOUAC", "Bivouac d&#x27;hiver encadré", "Bivouac d&#x27;hiver", n=2)
rep("L-DAE", "Défibrillateur automatisé externe (DAE) en accès public, avec son logo vert : repérez-les sur vos trajets habituels. Il guide l'utilisateur à la voix.",
    "Défibrillateur automatisé externe (DAE) en accès public : repérez-les sur vos trajets habituels. Faites-le apporter dès qu'une personne ne respire pas normalement.")
rep("L-EAU", "Les deux moyens les plus sûrs pour une eau claire : l'ébullition à gros bouillons, ou un filtre dont la notice précise ce qu'il retient (bactéries, protozoaires, virus).",
    "Faire bouillir à gros bouillons reste la méthode de référence. Un filtre ne retient que ce que précise sa notice : vérifiez s'il arrête les bactéries, les protozoaires et les virus.")
rep("L-JUNGLE", "rivières en crue rapide, humidité permanente et moustiques. Dormir surélevé sous une moustiquaire limite les piqûres et le contact avec le sol.",
    "crues soudaines, humidité permanente et moustiques. Un hamac sous une moustiquaire limite le contact avec le sol et les piqûres, sans protéger de tout.")

# Crédit de la planche de myrtille : illustrateur nommé (Redouté), numérisation rawpixel
rep("CREDIT-39", "© Free Public Domain Illustrations by rawpixel — CC BY 2.0 (crédit n° 39)",
    "© Pierre-Joseph Redouté, numérisation rawpixel — CC BY 2.0 (crédit n° 39)")
rep("CREDIT-39b", "<td>39</td><td>Myrtille (planche)</td><td>Free Public Domain Illustrations by rawpixel</td>",
    "<td>39</td><td>Myrtille (planche)</td><td>Pierre-Joseph Redouté (planche), numérisation rawpixel</td>")

# Balise : le 196 est un numéro français
rep("PLB-196", "par téléphone, le 196, même à terre ; en mer, VHF canal 16.",
    "par téléphone, le 196 en France, même à terre (à l'étranger : le numéro d'urgence local) ; en mer, VHF canal 16.")

# Pêche : aucune exception « urgence vitale » n'est prévue par la réglementation
rep("PECHE", "(pêche soumise à la réglementation hors urgence vitale)", "(la pêche reste soumise à la réglementation : permis, périodes, tailles)")

# Fiche 7 : « fermé » vaut pour le bâtiment comme pour le véhicule
rep("FICHE-7", "<li>Tonnerre audible : je rejoins un bâtiment ou un véhicule fermé à toit rigide, si c'est sans danger.</li>",
    "<li>Tonnerre audible : je rejoins un bâtiment fermé ou un véhicule fermé à toit rigide, si c'est sans danger.</li>")
# Légendes plantes : reprendre la description du livret
rep("L-BELLADONE", "la belladone porte de grosses baies noires luisantes, isolées elles aussi, parmi de grandes feuilles.",
    "la belladone porte des baies noires luisantes, comme de petites cerises, isolées elles aussi.")
rep("L-MURES", "Mûres : seules les noires sont mûres", "Mûres (ronce)", n=2)

# Couverture
rep("COUV", "Version 1.5 — 10 novembre 2026", "Version 1.6 — 10 novembre 2026")
rep("MENTIONS", "<b>Petit guide de survie</b> — version 1.5, 10 novembre 2026.", "<b>Petit guide de survie</b> — version 1.6, 10 novembre 2026.")

open(path, "w", encoding="utf-8").write(h)
print(len(log), "opérations :", ", ".join(log))
