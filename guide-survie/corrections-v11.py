"""Corrections v1.1 (rapport consolidé, 45 points). Chaque motif doit être trouvé exactement une fois."""
import re
import sys

p = sys.argv[1]
s = open(p, encoding="utf-8").read()
errors = []


def rep(old, new):
    global s
    n = s.count(old)
    if n != 1:
        errors.append(f"{n}x : {old[:90]!r}")
        return
    s = s.replace(old, new)


# P2 — fiche 3 (fusion Éditeur + Médecin)
rep("<li>Oui : position latérale de sécurité (PLS).</li>",
    "<li>Oui : PLS si aucun traumatisme ; après une chute, un choc ou si la cause est inconnue, je le laisse sur le dos, voies aériennes libres. J'alerte (112).</li>")
rep("<li>Non : 112 en haut-parleur, défibrillateur, compressions 100–120/min, 5–6 cm ; défibrillateur dès qu'il arrive.</li>",
    "<li>Non : 112 en haut-parleur, je fais apporter un défibrillateur ; adulte : compressions 100–120/min, 5–6 cm ; je l'utilise dès qu'il arrive. Enfant ou nourrisson : fiche 3 bis.</li>")

# P3 — ch. 21, ébullition (Éditeur)
rep("Dès que possible, faites bouillir : gros bouillons 1 minute, 3 minutes au-dessus d'environ 2 000 m (canette, bouteille : voir chapitre 13).",
    "Dès que possible, faites bouillir dans un récipient prévu pour la cuisson : gros bouillons 1 minute, 3 minutes au-dessus d'environ 2 000 m. Ne chauffez ni bouteille plastique ni canette ; sans récipient adapté, utilisez un autre traitement (voir chapitre 13).")

# P4 — pin, sapin, épicéa
rep("<td>Aiguilles. Ne pas confondre avec l'<b>if</b> (aiguilles plates, souples, baies rouges) : mortel.</td><td>Aiguilles fraîches en infusion (vitamine C). Écorce interne blanche comestible en dernier recours.</td>",
    "<td>Aiguilles. Attention : le sapin a, comme l'if, des aiguilles plates et souples, et l'if ne porte ses « baies » rouges que sur certains arbres et à certaines saisons. Aucun de ces caractères ne permet d'écarter l'<b>if</b>, mortel (voir « Les sosies mortels à connaître »).</td><td>Ne faites pas d'infusion d'aiguilles et ne consommez ni pousses ni écorce d'un conifère que vous n'avez pas identifié avec certitude, de préférence appris sur le terrain avec un connaisseur. Au moindre doute, abstenez-vous.</td>")

# P5 — myrtille (texte Botaniste final ; encadré conservé et complété)
rep("<td>Petit arbrisseau des sous-bois. Ses baies, bleu-noir à reflet bleuté, poussent une par une sur la tige (ni en grappe, ni soudées par deux).</td><td>Fruits crus, seulement après identification certaine. Sosies toxiques : voir l'encadré « Myrtille : les sosies toxiques » ci-dessous.</td>",
    "<td>Petit arbrisseau des sous-bois ; baies bleu-noir à reflet bleuté, isolées sur la tige (ni en grappe, ni soudées par deux). Ces indices ne suffisent pas à l'identifier.</td><td>Uniquement si vous la connaissez déjà avec certitude. Sosies toxiques : voir l'encadré « Myrtille : les sosies toxiques » ci-dessous.</td>")
rep("      <li><b>troène, nerprun, bourdaine</b> : arbustes à baies noires ou bleu-noir.</li>\n    </ul>",
    "      <li><b>troène, nerprun, bourdaine</b> : arbustes à baies noires ou bleu-noir.</li>\n    </ul>\n    La belladone a, elle aussi, des baies isolées.")

# P6 — alambic
rep("L'alambic permet aussi d'obtenir de l'eau douce à partir d'eau de mer ou d'eau très sale versée dans le trou (pas dans le récipient !). Creuser coûte",
    "L'alambic peut aussi servir avec de l'eau de mer ou une eau boueuse versée dans le trou (pas dans le récipient !). N'y versez jamais une eau suspecte de pollution chimique (carburant, solvant, pesticide, eau d'inondation) : la distillation n'élimine pas certains composés volatils. Gardez le récipient propre et couvert. Creuser coûte")

# P7 — bougie de tranchée (fusion Abri Feu + Bushcraft) ; tissu charbonné (Bushcraft)
rep("imprégnées de cire de bougie fondue. Chauffe, éclaire, allume.</li>",
    "imprégnées de cire de bougie fondue. Allume-feu d'appoint, à utiliser uniquement dehors, sous surveillance, loin de toute matière inflammable, et à éteindre avant de dormir. Ce n'est pas un moyen de chauffage ni d'éclairage : jamais dans une tente, un abri de neige, un véhicule ou tout espace clos, même aéré (monoxyde de carbone, chapitre 15).</li>")
rep("<li>Fabriquer du coton-vaseline et du tissu charbonné.</li>",
    "<li>Fabriquer du coton-vaseline ; tissu charbonné seulement avec une personne qui maîtrise la technique, dehors, là où un feu est autorisé.</li>")

# P8 — noyade : harmonisation avec le choix RTN pour l'enfant
rep("Si vous savez les réaliser, commencez par <b>5 insufflations initiales</b>, puis poursuivez",
    "Si vous savez les réaliser, commencez par <b>5 insufflations initiales</b> (consigne des recommandations européennes ERC 2025 ; le référentiel français PSC ne prévoit pas d'insufflations initiales spécifiques), puis poursuivez")

# P9 — sphaigne (fusion)
rep("<li><b>Sphaigne</b> (mousse des tourbières) : très absorbante, utilisée autrefois comme pansement d'appoint.</li>",
    "<li><b>Sphaigne</b> (mousse des tourbières) : très absorbante. Ne l'utilisez pas comme pansement : aucune mousse sauvage ne doit être posée sur une plaie (chapitre 8, « Petites plaies »). Portez des gants pour la manipuler si vous avez des coupures aux mains.</li>")

# P10 — if
rep("<td>Plante très toxique. Au moindre doute, s'abstenir. <i>(Formulation spécialisée non transmise.)</i></td>",
    "<td>Très toxique. Le feuillage (aiguilles, rameaux) et la graine contenue dans la « baie » rouge sont toxiques ; les aiguilles sont les plus chargées en poison, et le séchage ou la cuisson ne le détruisent pas. Seule la chair rouge qui entoure la graine est décrite comme non toxique, mais ne la mangez pas : la graine peut être avalée ou croquée avec. Symptômes, en général dans les premières heures : vomissements, diarrhée, douleurs au ventre, vertiges ; dans les cas graves : pouls irrégulier, troubles du rythme cardiaque, chute de tension, convulsions, jusqu'à l'arrêt cardiaque. Après ingestion d'aiguilles, de graines ou d'une tisane d'aiguilles : centre antipoison immédiatement, même sans symptôme ; 15 ou 112 (114 pour les personnes sourdes ou malentendantes) en cas de détresse ; ne faites pas vomir. Des rameaux d'if peuvent être pris pour des pousses de sapin : ne consommez aucune partie et ne faites aucune infusion d'un conifère non identifié avec certitude.</td>")

# P11 — myrtilles, ch. 9
rep("Myrtilles : seulement après identification certaine ; sosies toxiques (dont la belladone) au chapitre 10.",
    "Myrtilles : uniquement si vous les connaissez déjà avec certitude ; plusieurs baies noires ou bleu-noir toxiques poussent dans les mêmes milieux (voir chapitre 10, ligne « Myrtille »).")

# P12 — lianes : titre du chapitre 5
rep("Cherchez une autre source d'eau et traitez-la comme indiqué au chapitre 5.</li>",
    "Cherchez une autre source d'eau et traitez-la comme indiqué au chapitre 5, « Trouver et purifier l'eau ».</li>")

# P13 — sac sur branche
rep("se condense sur le plastique et coule vers le point bas. Rendement faible",
    "se condense sur le plastique et coule vers le point bas. Pour le sac sur branche, choisissez une plante non toxique que vous connaissez avec certitude. Rendement faible")

# P14 — pluie
rep("<td>Bâche ou poncho tendu en pente, un caillou au point bas, un récipient dessous. Les arbres : un tissu enroulé autour du tronc guide l'eau qui ruisselle.</td>",
    "<td>Bâche ou poncho propre tendu en pente, un caillou au point bas, un récipient propre dessous. Évitez l'eau qui a ruisselé sur un tronc ou sur le sol. Traitez l'eau recueillie avant de la boire (chapitre 5).</td>")

# P15 — bambous
rep("<li>Bambous : de l'eau s'accumule parfois dans les segments (secouez pour entendre).</li>",
    "<li>Bambous : de l'eau s'accumule parfois dans les segments (secouez pour entendre). Traitez-la comme une eau naturelle avant de la boire (chapitre 5).</li>")

# P16 — rationnement
rep("En cas de pénurie : rationnez l'effort, pas l'eau. Buvez",
    "En cas de pénurie : réduisez d'abord les pertes (effort, chaleur, soleil) et ne vous privez pas d'eau tant que vous en avez de sûre ; en mer, voir le chapitre 16. Buvez")

# P17 — encadré Danger, ch. 4
rep("Jamais de feu dans un abri fermé ou une tente (monoxyde de carbone, incendie).",
    "Jamais de feu, de braises ni d'appareil à combustion dans une tente, un abri de neige ou un abri couvert, même muni d'une aération (monoxyde de carbone, incendie). Le feu se fait à l'extérieur, à distance des parois.")

# P18 + P38 — étoile et renvoi du tipi
rep("<figcaption>Le tipi (page précédente) démarre vite. La cabane fait de belles braises pour cuire. L'étoile économise le bois toute la nuit.",
    "<figcaption>Le tipi (voir « Monter un feu en tipi », chapitre 4) démarre vite. La cabane fait de belles braises pour cuire. L'étoile permet d'avancer les bûches peu à peu et d'économiser le bois pendant la veillée ; comme tous les feux, elle reste sous la surveillance d'une personne éveillée et doit être complètement éteinte avant de dormir.")
rep("<li>Entretenir un feu toute une soirée avec un feu en étoile.</li>",
    "<li>Entretenir un feu toute une soirée avec un feu en étoile, sous surveillance continue, éteint complètement à la fin.</li>")

# P19 — réflecteur (fusion)
rep("<td>Un petit mur de bûches empilées ou de pierres derrière le feu renvoie la chaleur vers vous (et vers l'abri).</td>",
    "<td>Un petit mur de bûches ou de pierres sèches (pas de pierres de rivière) derrière le feu renvoie une partie de la chaleur vers vous. Gardez l'abri, le couchage, le lit de feuilles et la réserve de bois hors de portée des flammes, du rayonnement et des projections (chapitre 4).</td>")

# P20 — encoches (Bushcraft)
rep("Elles servent à accrocher une cordelette, faire tenir un piquet, suspendre une gourde au-dessus du feu.</li>",
    "Elles servent à accrocher une cordelette, faire tenir un piquet ou suspendre une popote prévue pour la cuisson au-dessus du feu (gourde : seulement si sa notice autorise la chauffe, bouchon retiré, voir plus bas). Vérifiez que la suspension et la branche supportent le poids et ne peuvent pas brûler.</li>")

# P21 — hutte de débris (fusion)
rep("<p>Comptez 2 à 3 heures de travail : commencez <b>bien avant la nuit</b>. Travaillez sans transpirer",
    "<p>La construction peut prendre plusieurs heures, souvent davantage sans outil : installez d'abord une protection minimale, commencez dès qu'une nuit dehors devient probable, avec une large marge, et réduisez le projet si le temps manque. Calez la perche pour qu'elle ne puisse ni glisser ni basculer de la souche et vérifiez la stabilité depuis l'extérieur avant de vous glisser dessous, puis après avoir ajouté les débris. Travaillez sans transpirer")
rep("Bouchez l'entrée avec un tas de feuilles une fois à l'intérieur.</figcaption>",
    "Une fois à l'intérieur, fermez l'entrée avec des feuilles sans vous empêcher de ressortir facilement.</figcaption>")

# P22 — blizzard (Abri Feu)
rep("Abritez-vous derrière un rocher, des arbres, dans la neige (trou à neige, chapitre 15).",
    "Abritez-vous derrière un rocher ou des arbres, ou utilisez le matériel de bivouac emporté. Un abri creusé dans la neige ne s'envisage que si vous l'avez appris et dans les conditions du chapitre 15 (neige adaptée, compagnon dehors pendant le creusement, jamais dans une pente avalancheuse).")

# P23 — check-list « Si je suis perdu » (Bushcraft)
rep("    <li>Je prépare un feu et des signaux.</li>\n    <li>Je m'occupe de l'eau.</li>",
    "    <li>Je prépare des signaux.</li>\n    <li>Je m'occupe de l'eau.</li>\n    <li>Feu seulement si l'abri est prêt, si c'est autorisé et sûr, et si je peux le surveiller et l'éteindre.</li>")

# P24 — couteau à lame fixe
rep("<td>Fendre au bâton, tailler, creuser. Choisissez une lame de 9–12 cm, épaisse (3–4 mm), avec un <b>dos à angle vif</b> pour frotter la pierre à feu.</td>",
    "<td>Tailler, préparer l'amadou ; fendre au bâton seulement si le fabricant autorise cet usage et après apprentissage encadré (voir plus haut). Une lame de 9–12 cm, avec un <b>dos à angle vif</b> pour frotter la pierre à feu, est un choix courant ; l'épaisseur seule ne garantit pas la résistance aux chocs. Ne vous en servez pas comme levier ni comme pelle.</td>")

# P25 — schéma sécurité couteau
rep('<text x="0" y="142" class="txts">• personne à portée de bras</text>',
    '<text x="0" y="142" class="txts">• aucune personne à portée de la lame</text>')

# P26 — fiche 1 et check-list (Militaire)
rep("<li>J'appelle le 112 depuis ma position sûre ; SMS au 114 ou à un proche ; après l'alerte je reste joignable (pas de mode avion).</li>",
    "<li>J'appelle le 112 depuis ma position sûre. Si je ne peux pas parler ou entendre : 114 (SMS ou appli). Sinon, SMS à un proche qui alerte les secours et me le confirme. Après l'alerte, je reste joignable (pas de mode avion).</li>")
rep("<li>J'essaie le <b>112</b> depuis ma position sûre (SMS : 114 ou un proche ; point proche seulement si le trajet est sûr). Après l'alerte, je reste joignable.</li>",
    "<li>J'essaie le <b>112</b> depuis ma position sûre (point proche seulement si le trajet est sûr). Si je ne peux pas parler ou entendre : 114 ; sinon SMS à un proche chargé d'alerter. Après l'alerte, je reste joignable.</li>")

# P27 — signaux
rep("La réponse est 3 signaux par minute. Le chiffre 3 (3 feux, 3 coups) est aussi compris partout comme un appel à l'aide.</li>",
    "La réponse est 3 signaux par minute, puis une minute de pause : elle signifie que l'appel a été reçu. Pour demander de l'aide, utilisez toujours la série de 6 signaux par minute. Si vous percevez ce signal de détresse, alertez le 112 en précisant où et quand vous l'avez entendu ou vu.</li>")

# P28 — menace
rep("si partir n'est pas sûr, mettez-vous à l'abri, limitez les bruits et alertez dès que possible, puis suivez les instructions des forces de sécurité.",
    "si partir n'est pas sûr, mettez-vous à l'abri, éloignez-vous des fenêtres, passez votre téléphone en silencieux et limitez les bruits. Une fois à l'abri, alertez le 17 ou le 112. Si vous ne pouvez pas parler, utilisez le 114 par SMS. Suivez ensuite les instructions des forces de sécurité. Dans cette situation, rester joignable ne signifie pas garder la sonnerie active.")

# P29 — chaleur, ch. 21
rep("<li>Par forte chaleur : c'est l'inverse. Restez à l'ombre, couvrez la tête, bougez le matin et le soir seulement.</li>",
    "<li>Par forte chaleur : c'est l'inverse. Restez à l'ombre, couvrez la tête et réservez les efforts indispensables au matin et au soir. Cela ne justifie pas de quitter l'endroit où l'on peut vous trouver (voir chapitre 17).</li>")

# P30 — sortie hivernale (fusion)
rep("<li>Faire une sortie en hiver ou par mauvais temps (encadrée ou à plusieurs).</li>",
    "<li>Faire une première sortie en hiver ou par mauvais temps avec un encadrant compétent (professionnel qualifié, club ou fédération), sur un itinéraire adapté à votre niveau, après consultation de la météo et, sur terrain enneigé, du bulletin d'avalanche ; un groupe de débutants ne remplace pas l'encadrement. Ensuite, à plusieurs, sur un itinéraire maîtrisé, avec heure de demi-tour et replis (chapitre 15).</li>")

# P31 — rester ou partir
rep("Ne bougez que si l'endroit est dangereux, ou si personne ne viendra et que vous connaissez le chemin.",
    "Ne bougez que pour échapper à un danger immédiat, ou pour rejoindre une destination identifiée par un trajet connu et praticable ; sinon, restez localisable dans un endroit sûr (voir chapitre 21).")

# P32 — pentes
rep("<li>Suivez les pentes vers le bas : l'eau s'accumule au fond des vallées.</li>",
    "<li>L'eau s'accumule souvent dans les creux et les fonds de vallon. Ne descendez la chercher que par un terrain visible et praticable, dont le retour est sûr ; si vous êtes perdu, ne quittez pas un endroit sûr et localisable pour une recherche hasardeuse (voir chapitres 6 et 21).</li>")

# P33 — figure contournement
rep('<text x="236" y="150" class="txts">+90°, N pas</text>', '<text x="236" y="150" class="txts">+90°, distance d</text>')
rep('<text x="236" y="45" class="txts">−90°, N pas</text>', '<text x="236" y="45" class="txts">−90°, même distance d</text>')

# P34 — canopée
rep("<li>La canopée cache le soleil et le GPS capte mal : faites des pauses dans les clairières pour relever votre position.</li>",
    "<li>La canopée masque le soleil et peut dégrader la position GPS : en progression sur un itinéraire connu, profitez des zones dégagées rencontrées pour relever votre position et son incertitude. Si vous êtes perdu, ne quittez pas un endroit sûr pour chercher une clairière ; ne vous y rendez que si l'aller et le retour sont manifestement sûrs (voir chapitre 7).</li>")

# P35 — première heure
rep("S.T.O.P. Inventaire. Appel 112 / SMS. Marquer sa position.",
    "S.T.O.P. Inventaire. Appel au 112 ; à défaut, SMS au 114 ou à un proche chargé d'alerter (chapitre 7). Marquer sa position.")

# P36 — mer, panique
rep("bien avant la soif ou la faim. Le deuxième est la panique.</p>",
    "bien avant la soif ou la faim. Dans la première minute, le choc thermique peut aussi faire perdre le contrôle de la respiration et des mouvements : c'est une réaction du corps, pas une faiblesse.</p>")
rep("<td><b>Choc thermique</b> : halètement incontrôlable. Ne paniquez pas, gardez la tête hors de l'eau, flottez et calmez votre respiration.</td>",
    "<td><b>Choc thermique</b> : halètement réflexe, qui passe généralement en moins d'une minute. Ne cherchez pas à nager tout de suite : gardez la tête hors de l'eau, flottez, laissez votre respiration se calmer, puis agissez.</td>")

# P37 — sommaire
rep('<li><a href="#feu">Faire du feu</a> et <a href="#feu-techniques">l\'allumer</a></li>',
    '<li><a href="#feu">Faire du feu</a> (et <a href="#feu-techniques">4 bis — Les techniques d\'allumage</a>)</li>')
rep('<li><a href="#fabrications">Fabrications simples</a></li>', '<li><a href="#fabrications">Fabrications simples et efficaces</a></li>')
rep('<li><a href="#mer">Survie en mer</a></li>', '<li><a href="#mer">Survie en mer et dans l\'eau</a></li>')

# P39 — sosies
rep("<b>sosies toxiques</b> (page suivante) en même temps",
    "<b>sosies toxiques</b> (voir « Les sosies mortels à connaître », plus loin dans ce chapitre) en même temps")

# P40 — mal des montagnes
rep("<li>Prévention : monter progressivement, bien boire, « monter haut, dormir bas ».</li>",
    "<li>Prévention : monter progressivement, boire selon la soif et l'effort, sans excès (chapitre 11), « monter haut, dormir bas ».</li>")

# P41 — séisme
rep("<li>Après : sortez par l'escalier (jamais l'ascenseur), méfiez-vous des répliques,",
    "<li>Après : méfiez-vous des répliques,")

# P42 — SMS
rep("au cas où les réseaux locaux seraient saturés. Préférez les SMS aux appels.</li>",
    "au cas où les réseaux locaux seraient saturés. Pour joindre vos proches, préférez les SMS aux appels ; pour les secours, appelez le 112 (alerte écrite : 114, chapitre 7).</li>")
rep("<li>SMS plutôt qu'appels, point de rendez-vous familial.</li>",
    "<li>SMS aux proches plutôt qu'appels, point de rendez-vous familial ; secours : 112.</li>")

# P43 — fiche 6
rep("<li>Je calme ma respiration (1 minute).</li>",
    "<li>Je garde la tête hors de l'eau et je calme ma respiration (choc des premières minutes).</li>")
rep("<li>Au chaud, vêtements secs, 112.</li>", "<li>Une fois sorti : à l'abri, vêtements secs, 112.</li>")

# P44 — fiche 8
rep("<li>Je reste dans la voiture, j'appelle le 112.</li>", "<li>Je reste avec la voiture tant qu'elle est sûre, j'appelle le 112.</li>")

# P45 — centre antipoison
rep("<tr><th>196</th><td>Secours en mer (France)</td></tr>",
    "<tr><th>196</th><td>Secours en mer (France)</td></tr>\n    <tr><th>Centre antipoison</th><td>Numéro du centre antipoison de votre région, à relever avant le départ (annuaire officiel des centres antipoison) ; détresse vitale : 15 ou 112 (France)</td></tr>")

# Couverture
rep("Version 1.0 — 9 novembre 2026 ·", "Version 1.1 — 9 novembre 2026 ·")

if errors:
    print("ÉCHECS :", *errors, sep="\n - ")
    sys.exit(1)
open(p, "w", encoding="utf-8").write(s)
print("OK")
