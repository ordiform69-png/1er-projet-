"""Applique les 17 points de la relecture finale consolidée v1.3 (arbitrages de l'auteur) -> v1.4."""
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


# POINT 1 : ne pas dissuader le témoin non formé de réanimer (Médecin)
rep("R01", "Ces gestes s'apprennent en formation pratique : ne les improvisez pas à partir de ce livret. Noyade d'un enfant",
    "Ces gestes s'apprennent en formation pratique ; si vous n'êtes pas formé, faites-les quand même, en suivant les instructions du régulateur au téléphone. Noyade d'un enfant")

# POINT 2 : tente = aucun appareil à combustion (Abri Feu)
rep("R02", "dans un logement, un garage, une cave ou une tente, même portes et fenêtres ouvertes : le monoxyde de carbone tue sans odeur.",
    "dans un logement, un garage ou une cave, même portes et fenêtres ouvertes : le monoxyde de carbone tue sans odeur. Dans une tente, aucun appareil à combustion, même aéré (chapitres 4 et 15).")

# POINT 3 : annulation d'une fausse alerte PLB (source DGAMPA : 196 par téléphone, VHF 16 en mer)
rep("R03", "prévenez aussitôt les secours pour faire annuler l'alerte (112 ; en mer : VHF canal 16 ou 196).",
    "prévenez aussitôt les secours pour faire annuler l'alerte : par téléphone, le 196, même à terre ; en mer, VHF canal 16. Signaler l'erreur tout de suite évite de lancer des recherches inutiles.")

# POINT 4 : règle 3 étendue aux feuilles (Botaniste, version la plus protectrice)
rep("R04a", "cuisez systématiquement les fruits sauvages (la congélation ne suffit pas).",
    "cuisez systématiquement les fruits et les feuilles sauvages cueillis près du sol (la congélation ne suffit pas).")
rep("R04b", "<td>Feuilles crues ou cuites. <b>Voir sosies mortels !</b></td>",
    "<td>Feuilles cuites : il pousse en milieu humide (règle 3). <b>Voir sosies mortels !</b></td>")
rep("R04c", "<td>Feuilles cuites (crues seulement si elles ne viennent ni d'un milieu humide ni d'une zone pâturée : voir règle 3), fleurs, racine grillée.</td>",
    "<td>Feuilles cuites (crues seulement si elles ne viennent ni d'un milieu humide ni d'une zone pâturée, et hors des régions citées à la règle 3), fleurs, racine grillée.</td>")
rep("R04d", "Ortie (cuite), pissenlit (feuilles et fleurs), plantain.",
    "Ortie (cuite), pissenlit (feuilles cuites et fleurs : voir chapitre 10, règle 3), plantain (jeunes feuilles cuites).")

# POINT 5 : fiche 1, exception « danger immédiat » ; espace insécable devant « : 114 »
rep("R05", "<li>Je reste sur place si quelqu'un connaît mon itinéraire.</li>",
    "<li>Je reste sur place si quelqu'un connaît mon itinéraire, sauf danger immédiat.</li>")
rep("R05b", "<li>J'appelle le 112 depuis ma position sûre. Si je ne peux pas parler ou entendre : 114 (SMS ou appli). Si l'appel ne passe pas : SMS",
    "<li>J'appelle le 112 depuis ma position sûre. Si je ne peux pas parler ou entendre&nbsp;: 114 (SMS ou appli). Si l'appel ne passe pas&nbsp;: SMS")

# POINT 6 : reliquats du 114 (fusion Médecin + Militaire)
rep("R06a", "alertez immédiatement (112, 18, ou 114 par SMS si vous ne pouvez pas parler).",
    "alertez immédiatement (112 ou 18 ; personne sourde, malentendante ou aphasique : 114 par SMS).")
rep("R06b", "et dans certaines situations où parler est impossible.",
    "ainsi qu'aux victimes de violences intrafamiliales qui ne peuvent pas parler.")
rep("R06c", "(114 pour les personnes sourdes ou malentendantes)", "(114 pour les personnes sourdes, malentendantes ou aphasiques)", n=2)
rep("R06d", "appelez le 112 (alerte écrite : 114, chapitre 7).", "appelez le 112 (si vous ne pouvez pas parler ou entendre : 114, chapitre 7).")
rep("R06e", "<tr><th>114</th><td>Alerte écrite (SMS, appli) : personnes sourdes, malentendantes ou aphasiques, ou impossibilité de parler (France)</td></tr>",
    "<tr><th>114</th><td>Alerte écrite (SMS, appli, visio, tchat) : personnes sourdes, sourdaveugles, malentendantes ou aphasiques ; violences intrafamiliales si l'on ne peut pas parler (France)</td></tr>")

# POINT 7 : Croix du Sud (Navigateur)
rep("R07", "<p><b>Hémisphère sud : la Croix du Sud.</b> Prolongez son grand axe, du haut vers le bas de la croix, d'environ 4,5 fois sa longueur. Repérez-la grâce aux deux étoiles brillantes voisines, les « Pointeurs » : la perpendiculaire tracée au milieu de leur segment croise le prolongement du grand axe de la croix près du pôle sud céleste. Le point obtenu est proche du pôle sud céleste ; à la verticale de ce point, sur l'horizon, se trouve approximativement le sud.",
    "<p><b>Hémisphère sud : la Croix du Sud.</b> Repérez-la grâce aux deux étoiles brillantes voisines, les « Pointeurs ». Prolongez son grand axe, du haut vers le bas de la croix, d'environ 4,5 fois sa longueur : le point obtenu est proche du pôle sud céleste. Pour le contrôler, tracez la perpendiculaire au milieu du segment des Pointeurs : elle croise ce prolongement près du même point. À la verticale de ce point, sur l'horizon, se trouve approximativement le sud.")

# POINT 9 : bâche en A (Abri Feu : lève l'ambiguïté « extrémité étroite / ouverture »)
rep("R09", "Orientez la ligne de faîtage pour que le vent frappe un pan de la bâche ou une extrémité étroite, pas l'ouverture ; si le vent tourne, fermez le côté exposé avec votre sac ou des branches.",
    "Orientez la ligne de faîtage pour que le vent frappe un des grands pans de la bâche, pas une extrémité ouverte ; si le vent tourne, fermez l'extrémité exposée avec votre sac ou des branches.")

# POINT 10, 11 : réserve d'eau (Expert Eau)
rep("R10", "Si vous remplissez vous-même des contenants : utilisez",
    "Si vous remplissez vous-même des contenants, faites-le avec l'eau du robinet quand elle est potable (une eau bouillie ou traitée à la Javel se garde 72 heures au maximum, voir chapitre 5) : utilisez")
rep("R11", "pour couvrir aussi la préparation des aliments et une hygiène minimale,", "pour couvrir aussi une hygiène minimale,")

# POINT 12 : Javel, concentration de la consigne (Médecin)
rep("R12", "utilisez uniquement une eau de Javel à 2,6 % de chlore actif, sans parfum ni additif,",
    "utilisez exactement l'eau de Javel indiquée par la consigne (même concentration en chlore actif), sans parfum ni additif,")

# POINT 14 : extinction (Bushcraft)
rep("R14", "<li>Pour éteindre : noyez, remuez, noyez encore. Les cendres doivent être froides au toucher.</li>",
    "<li>Pour éteindre un feu de bois : noyez, remuez, noyez encore. Les cendres doivent être froides au toucher. Cire ou bougie de tranchée en feu : jamais d'eau, étouffez avec un couvercle (chapitre 13).</li>")

# POINT 15 : sirènes (Militaire, source sécurité civile)
rep("R15", "Les sirènes sont testées le premier mercredi du mois à midi : un son montant et descendant en dehors de ce test = mettez-vous à l'abri et écoutez la radio.",
    "Les sirènes sont testées le premier mercredi du mois, en général à midi : l'essai ne dure qu'un cycle d'1 minute 41 secondes. Le vrai signal d'alerte enchaîne trois cycles montants et descendants séparés de 5 secondes : mettez-vous à l'abri et écoutez la radio.")

# POINT 16 : corne de brume des grands barrages (Militaire)
rep("R16", "L'accès est interdit dans les 50 m en amont et en aval d'un barrage ou d'une centrale.</li>",
    "L'accès est interdit dans les 50 m en amont et en aval d'un barrage ou d'une centrale. Près d'un grand barrage, une sirène de type corne de brume (sons de 2 secondes répétés pendant au moins 2 minutes) annonce une rupture ou un lâcher d'eau important : quittez aussitôt le lit et les berges et montez sur les hauteurs, sans revenir en arrière.</li>")

# POINT 17 : glossaire ARS, DGSCGC, ERC
rep("R17a", "    <tr><th>BERA</th>",
    "    <tr><th>ARS</th><td>Agence régionale de santé : fixe les consignes sur l'eau en cas de crise (ch. 5)</td></tr>\n    <tr><th>BERA</th>")
rep("R17b", "    <tr><th>DVA</th>",
    "    <tr><th>DGSCGC</th><td>Direction générale de la sécurité civile et de la gestion des crises (ministère de l'Intérieur), autrice des RTN PSC (ch. 8)</td></tr>\n    <tr><th>DVA</th>")
rep("R17c", "    <tr><th>FR-Alert</th>",
    "    <tr><th>ERC</th><td>European Resuscitation Council : organisme qui publie les recommandations européennes de réanimation (ch. 8 et 16)</td></tr>\n    <tr><th>FR-Alert</th>")

rep("COUV", "Version 1.3 — 9 novembre 2026", "Version 1.4 — 9 novembre 2026")

open(path, "w", encoding="utf-8").write(h)
print(len(log), "opérations appliquées :", ", ".join(log))
