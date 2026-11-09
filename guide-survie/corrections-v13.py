"""Applique les 42 points de la vérification consolidée v1.2 -> v1.3 (arbitrages de l'éditeur)."""
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


# ---- POINT 1 + POINT 39 : malaise / AVC, renvoi arrêt cardiaque (Médecin)
rep("P01", "Aidez-la seulement à prendre son traitement prescrit (par exemple son inhalateur si elle est asthmatique), à sa demande ou sur consigne du 15.",
    "Aidez-la seulement à prendre son traitement prescrit (par exemple son inhalateur si elle est asthmatique), à sa demande ou sur consigne du 15, sauf en cas de signe d'AVC (rubrique suivante) : dans ce cas, aucun médicament, ni à boire ni à manger.")
rep("P39", "c'est un arrêt cardiaque (encadré ci-dessus).",
    "c'est un arrêt cardiaque : voir l'encadré « Ne respire pas normalement ? Arrêt cardiaque » plus haut dans ce chapitre (enfant ou nourrisson : encadré « Arrêt cardiaque de l'enfant et du nourrisson ») et la fiche 3.")

# ---- POINT 2 : RCP enfant (Médecin, deux référentiels) + RTN PSC cité (POINT 42)
rep("P02", "<li>Faites 100 à 120 compressions par minute en enfonçant d'au moins un tiers du thorax : une main pour l'enfant (deux si nécessaire), les deux pouces pour le nourrisson. Si vous ne savez pas insuffler, faites des compressions seules, en continu.</li>",
    "<li>Faites 100 à 120 compressions par minute en enfonçant d'un tiers de l'épaisseur du thorax (environ 5 cm chez l'enfant, environ 4 cm chez le nourrisson) : une main pour l'enfant (deux si nécessaire), les deux pouces pour le nourrisson. Chez l'enfant, les insufflations sont importantes : faites-les si vous le pouvez. Si vous ne pouvez pas ou ne savez pas insuffler, faites au moins les compressions, en continu (recommandations européennes ERC 2025 ; le référentiel français ne le précise que pour l'adulte).</li>", n=2)
rep("P02b", "Un tiers du thorax correspond à environ 4 cm chez le nourrisson et environ 5 cm chez l'enfant. Seul et sans téléphone",
    "Seul et sans téléphone")
rep("P42a", "Référence suivie : référentiel technique national PSC (France), celui qu'enseigne la formation PSC1.",
    "Référence suivie : Références techniques nationales – Premiers secours citoyen (RTN PSC, DGSCGC, France), celles qu'enseigne la formation PSC1.")

# ---- POINT 3 : monoxyde de carbone (Abri Feu)
rep("P03", "<li><b>Jamais</b> de groupe électrogène, barbecue, brasero ou chauffage d'appoint à combustion dans un espace fermé : le monoxyde de carbone tue sans odeur.</li>",
    "<li><b>Jamais</b> de groupe électrogène, barbecue, brasero, réchaud de camping ou chauffage d'appoint non prévu pour l'intérieur dans un logement, un garage, une cave ou une tente, même portes et fenêtres ouvertes : le monoxyde de carbone tue sans odeur. Un groupe électrogène s'utilise uniquement dehors, loin des portes, fenêtres et aérations.</li>")
rep("P03b", "N'utilisez pas de nettoyeur ou de pompe à moteur thermique dans la maison (monoxyde de carbone).",
    "N'utilisez pas de nettoyeur ou de pompe à moteur thermique dans la maison, le garage ou la cave, même ouverts (monoxyde de carbone).")

# ---- POINT 4 : voiture et feu de forêt (Militaire)
rep("P04", "Une voiture n'est pas un abri sûr : rejoignez si possible une habitation débroussaillée et suivez les consignes des secours.",
    "Une voiture n'est pas un abri sûr : rejoignez si possible une habitation débroussaillée et suivez les consignes des secours. Mais si vous êtes déjà en voiture à proximité directe du feu, n'en sortez pas : garez-vous dans une zone dégagée.")

# ---- POINT 5 : bougie de tranchée (Bushcraft)
rep("P05", "<li><b>« Bougie de tranchée » :</b> bandes de carton enroulées serré dans une boîte de conserve, imprégnées de cire de bougie fondue. Allume-feu d'appoint, à utiliser uniquement dehors, sous surveillance, loin de toute matière inflammable, et à éteindre avant de dormir. Ce n'est pas un moyen de chauffage ni d'éclairage : jamais dans une tente, un abri de neige, un véhicule ou tout espace clos, même aéré (monoxyde de carbone, chapitre 15).</li>",
    "<li><b>« Bougie de tranchée » :</b> bandes de carton enroulées serré dans une boîte de conserve, imprégnées de cire. Faites fondre la cire au bain-marie, jamais directement sur une flamme ou une plaque, et ne la quittez pas des yeux. Allume-feu d'appoint, à utiliser uniquement dehors, posé sur un sol stable et dégagé, sous surveillance, loin de toute matière inflammable. Ne la déplacez pas tant que la cire est liquide. Pour l'éteindre, étouffez-la avec un couvercle ou une plaque métallique : jamais d'eau sur de la cire qui brûle. Éteignez-la avant de dormir. Ce n'est pas un moyen de chauffage ni d'éclairage : jamais dans une tente, un abri de neige, un véhicule ou tout espace clos, même aéré (monoxyde de carbone, chapitres 4 et 15).</li>")
rep("P05b", "trempées dans de la cire de bougie).", "trempées dans de la cire de bougie fondue au bain-marie).")

# ---- POINT 6 : eau de Javel (Expert Eau, sans dosage)
i = h.index("<strong>Eau de Javel : à valider</strong>")
j = h.index("</div>", i)
old_box = h[i:j]
assert h.count(old_box) == 1
rep("P06", old_box,
    "<strong>Eau de Javel : seulement sur consigne des autorités</strong>\n"
    "    À la maison, préférez d'abord l'eau en bouteille, puis l'ébullition. La désinfection à l'eau de Javel est réservée à l'extrême urgence, quand l'ébullition est impossible, et seulement si l'ARS ou la mairie la conseille : ce sont elles qui fixent la dose et le temps d'attente, car ils dépendent de l'eau à traiter. Ce livret ne donne donc pas de dosage. Si cette consigne vous est donnée : utilisez uniquement une eau de Javel à 2,6 % de chlore actif, sans parfum ni additif, dosée avec un compte-gouttes, dans une eau claire (laissez décanter ou filtrez au linge une eau trouble), et respectez exactement la dose et le temps indiqués. Ne mélangez jamais la Javel à un autre produit. La Javel agit mal contre certains parasites (<i>Cryptosporidium</i>) et ne retire aucun produit chimique. Gardez l'eau traitée dans un récipient propre et fermé, au frais, 72 heures au maximum. Sans consigne, faites bouillir.\n  ")

# ---- POINT 7 + POINT 34 : tableau des plantes et règle 3 (Botaniste)
rep("P07a", "<td>Feuilles crues (amères) ou cuites, fleurs, racine grillée.</td>",
    "<td>Feuilles cuites (crues seulement si elles ne viennent ni d'un milieu humide ni d'une zone pâturée : voir règle 3), fleurs, racine grillée.</td>")
rep("P07b+P34", "<tr><td><b>Ronce, framboisier</b></td><td>Bien connus ; baies en grappe de petites boules.</td><td>Fruits crus. En cas de diarrhée : réhydratation d'abord (chapitre 8).</td></tr>",
    "<tr><td><b>Ronce, framboisier</b></td><td>Bien connus ; arbustes à tiges épineuses, chaque fruit est formé de nombreuses petites boules serrées.</td><td>Fruits crus, sauf dans les régions où la règle 3 impose la cuisson des fruits sauvages cueillis près du sol (quart nord-est de la France, Massif central notamment) : alors cuits (compote, confiture). En cas de diarrhée : réhydratation d'abord (chapitre 8).</td></tr>")
rep("P07c", "(voir chapitre 10, ligne « Myrtille »). En cas de doute, abstenez-vous.",
    "(voir chapitre 10, ligne « Myrtille »). Dans certaines régions, les fruits sauvages cueillis près du sol doivent être cuits (chapitre 10, règle 3). En cas de doute, abstenez-vous.")

# ---- POINT 8 : 114 (fusion Militaire + Éditeur)
rep("P08a", "Un SMS s'adresse à un proche capable d'alerter ou au 114 (voir chapitre 7).",
    "Un SMS s'adresse à un proche capable d'alerter ; le 114 est réservé aux personnes qui ne peuvent pas parler ou entendre (voir chapitre 7).")
rep("P08b", "Appel au 112 ; à défaut, SMS au 114 ou à un proche chargé d'alerter (chapitre 7).",
    "Appel au 112 ; si vous ne pouvez pas parler ou entendre : 114 ; si l'appel ne passe pas, SMS à un proche chargé d'alerter (chapitre 7).")
rep("P08c", "Si je ne peux pas parler ou entendre : 114 (SMS ou appli). Sinon, SMS à un proche qui alerte les secours et me le confirme.",
    "Si je ne peux pas parler ou entendre : 114 (SMS ou appli). Si l'appel ne passe pas : SMS à un proche qui alerte les secours et me le confirme.")
rep("P08d", "Si je ne peux pas parler ou entendre : 114 ; sinon SMS à un proche chargé d'alerter.",
    "Si je ne peux pas parler ou entendre : 114 ; si l'appel ne passe pas, SMS à un proche chargé d'alerter.")

# ---- POINT 9 : eau douce en mer (Médecin, sans chiffre)
rep("P09", "Rationnez l'eau douce, récoltez la pluie (rincez d'abord la bâche du sel), utilisez un dessalinisateur manuel si vous en avez un.",
    "Faites tout de suite l'inventaire de l'eau douce et fixez une ration quotidienne par personne, selon la réserve, le nombre de personnes, le délai probable avant les secours, les chances de pluie et l'état de chacun. Buvez votre ration en petites prises réparties dans la journée. Réduisez d'abord les pertes : ombre, repos, vêtements mouillés à l'eau de mer (sans en boire), traitement du mal de mer avant qu'il commence (voir plus haut). Récoltez la pluie (rincez d'abord la bâche du sel) et utilisez un dessalinisateur manuel si vous en avez un.")

# ---- POINT 10 : nourrisson (Expert Eau, paragraphe entier)
i = h.index("<p><b>Nourrisson.</b>")
j = h.index("</p>", i) + 4
rep("P10", h[i:j],
    "<p><b>Nourrisson.</b> Le lait infantile liquide prêt à l'emploi, stérile, est le plus sûr en crise car il ne demande pas d'eau ; gardez-en dans le kit. Pour le lait en poudre, tant que les autorités n'ont pas déclaré l'eau du robinet potable, utilisez une eau en bouteille non gazeuse portant la mention « convient pour la préparation des aliments des nourrissons » ; une bouteille entamée se garde au réfrigérateur et se boit dans les 24 heures. À défaut, utilisez une eau bouillie puis bien refroidie. Lavez-vous les mains au savon, respectez exactement les doses de la boîte, préparez le biberon juste avant de le donner et jetez le lait non bu (au plus tard une heure après la préparation à température ambiante). Lavez biberon et tétine à l'eau chaude potable avec du liquide vaisselle et un goupillon, rincez et laissez sécher à l'air : la stérilisation n'est pas nécessaire. Sans eau potable pour les laver, donnez le lait dans un gobelet jetable propre. Ne fabriquez jamais de lait « maison ». L'allaitement se poursuit normalement.</p>")

# ---- POINT 11 : ébullition
rep("P11", "<p><b>Faire bouillir :</b> portez l'eau claire à gros bouillons pendant 1 minute, ou 3 minutes au-dessus d'environ 2 000 m. Laissez refroidir dans un récipient propre et fermé.</p>",
    "<p><b>Faire bouillir :</b> portez l'eau claire à gros bouillons pendant au moins 1 minute, ou 3 minutes au-dessus d'environ 2 000 m. Si l'ARS ou la mairie donne une autre durée (en France, souvent 5 minutes pour l'eau du robinet), suivez-la. Laissez refroidir dans un récipient propre et fermé, et consommez cette eau dans les 72 heures, de préférence gardée au frais.</p>")

# ---- POINT 12 : check-list « Si je suis perdu » (Psychologue, étape 3 insérée ; la liste <ol> se renumérote)
rep("P12", "<li>Je me mets à l'abri du vent, de la pluie et du sol froid.</li>\n    <li>Je prépare des signaux.</li>",
    "<li>Je reste sur place si quelqu'un connaît mon itinéraire, sauf danger immédiat.</li>\n    <li>Je me mets à l'abri du vent, de la pluie et du sol froid.</li>\n    <li>Je prépare des signaux.</li>")

# ---- POINT 13 : consignes pendant l'alerte
rep("P13", "<li>Fiez-vous aux sources officielles et méfiez-vous des rumeurs. Écoutez les consignes à heures fixes plutôt qu'en continu : voir et revoir les mêmes images entretient la peur.",
    "<li>Fiez-vous aux sources officielles et méfiez-vous des rumeurs. Pendant l'alerte, gardez la radio ou les notifications allumées pour recevoir les consignes. Une fois à l'abri et la situation stabilisée, évitez de regarder les mêmes images en boucle : elles entretiennent la peur.")

# ---- POINT 14 : la nuit (sans « c'est fréquent »)
rep("P14", "La nuit, l'obscurité et les bruits peuvent faire peur : c'est fréquent. Installez-vous avant la nuit et posez à portée de main la lampe, le sifflet et le téléphone. Ne vous déplacez pas dans l'obscurité : attendez le jour pour réévaluer.",
    "La nuit, l'obscurité et les bruits peuvent faire peur. Installez-vous avant la nuit et posez à portée de main la lampe, le sifflet et le téléphone. Sauf danger immédiat (eau qui monte, feu, chute de pierres), ne vous déplacez pas dans l'obscurité, même avec une lampe : attendez le jour pour réévaluer.")

# ---- POINT 15 : soutien psychologique
rep("P15", "Restez près de lui si c'est sûr, dites-lui votre prénom et ce que vous faites, et dites-lui que les secours sont prévenus. Écoutez-le sans le juger et ne lui promettez pas ce que vous ne savez pas. Si quelqu'un meurt, occupez-vous d'abord de la sécurité des vivants et laissez chacun réagir à sa façon. Après coup, la culpabilité est fréquente : parlez-en. Demandez de l'aide auprès de la cellule d'urgence médico-psychologique (via le 15) ou de votre médecin.",
    "Restez près de lui si c'est sûr, dites-lui votre prénom et ce que vous faites ; dites-lui que les secours sont prévenus seulement quand c'est vrai. Écoutez-le sans le juger et ne lui promettez pas ce que vous ne savez pas. Si quelqu'un meurt, occupez-vous d'abord de la sécurité des vivants et laissez chacun réagir à sa façon. Après coup, on peut se sentir coupable : ne restez pas seul, parlez-en. Demandez de l'aide à votre médecin ; après un événement grave, une cellule d'urgence médico-psychologique (CUMP) peut être mise en place ; en cas d'urgence, appelez le 15.")

# ---- POINT 16 : belladone (la phrase était dans le HTML et le PDF ; absente du .md à cause du convertisseur, corrigé)
rep("P16", "    La belladone a, elle aussi, des baies isolées.\n    Ces indices aident",
    "    Attention : la belladone a, elle aussi, des baies isolées.\n    Ces indices aident")

# ---- POINT 17 : quelqu'un manque à l'appel (fusion Militaire + Navigateur + Éditeur)
rep("P17", "<b>Si quelqu'un manque à l'appel</b> : arrêtez-vous et regroupez tout le monde ; revenez ensemble au dernier endroit où il a été vu et attendez-le là tant que c'est sûr ; alertez le 112 en donnant ce dernier point, l'heure, la couleur de ses vêtements, ce qu'il porte et son état de santé. Ne partez pas le chercher seul hors du sentier.",
    "<b>Si quelqu'un manque à l'appel</b> : arrêtez-vous et regroupez tout le monde ; appelez-le et sifflez par séries de 6, puis écoutez sa réponse. S'il ne répond pas, alertez aussitôt le 112 en donnant le dernier endroit où il a été vu, l'heure, la couleur de ses vêtements, ce qu'il porte et son état de santé. Ensuite, revenez ensemble, sans vous séparer, à ce dernier point et restez-y tant que c'est sûr. Ne partez jamais le chercher seul hors du sentier.")

# ---- POINT 18 : balise PLB (Navigateur + Militaire)
rep("P18", "Enregistrez-la avant le départ ; en France, auprès du registre des balises 406 MHz (registre406.cnes.fr), en y indiquant votre sortie. Apprenez à l'utiliser, gardez-la sur vous, pas au fond du sac, et ne la déclenchez qu'en détresse réelle.",
    "Enregistrez-la avant le départ ; en France, auprès du registre des balises 406 MHz (registre406.cnes.fr), et tenez à jour vos coordonnées et vos contacts d'urgence. Apprenez à l'utiliser, gardez-la sur vous, pas au fond du sac, et ne la déclenchez qu'en détresse réelle. Une fois déclenchée, suivez sa notice : antenne déployée vers le haut, vue dégagée sur le ciel. Si vous la déclenchez par erreur, éteignez-la et prévenez aussitôt les secours pour faire annuler l'alerte (112 ; en mer : VHF canal 16 ou 196).")

# ---- POINT 19 : vigilance
rep("P19", "<li>Consultez la carte de <b>vigilance de Météo-France</b> (vigilance.meteofrance.fr, mise à jour deux fois par jour) et, près d'un cours d'eau, <b>Vigicrues</b> (vigicrues.gouv.fr) ; activez au besoin les notifications de vigilance dans l'application Météo-France. Vigilance orange : soyez très vigilant et suivez les conseils des pouvoirs publics. Vigilance rouge : respectez impérativement leurs consignes. Au besoin, reportez ou modifiez votre sortie.</li>",
    "<li>Consultez la carte de <b>vigilance de Météo-France</b> (vigilance.meteofrance.fr, actualisée au moins deux fois par jour, à 6 h et 16 h) et, près d'un cours d'eau, <b>Vigicrues</b> (vigicrues.gouv.fr, au moins à 10 h et 16 h). Activez les notifications de vigilance (orange et rouge) dans l'application Météo-France. Vigilance jaune : soyez attentif, surtout pour une activité de plein air ou près d'un cours d'eau ; en crues jaune, évitez les activités nautiques. Vigilance orange : soyez très vigilant, suivez les conseils des pouvoirs publics et reportez ou adaptez votre sortie. Vigilance rouge : ne partez pas, restez à l'abri et respectez impérativement les consignes des autorités.</li>")

# ---- POINT 20 + POINT 28 : fiche 3 ter (texte du Médecin), décompte des fiches
anchor = '    <div class="fiche">\n      <h4>4 · Saignement abondant</h4>'
rep("P20", anchor,
    '    <div class="fiche">\n      <h4>3 ter · Malaise, douleur dans la poitrine, signes d\'AVC</h4>\n      <ol>\n'
    '        <li>Je la mets au repos : allongée, ou assise si elle respire mal.</li>\n'
    '        <li>Douleur dans la poitrine qui serre ou dure plus de 5 minutes, essoufflement, sueurs, pâleur : 15 ou 112 tout de suite.</li>\n'
    '        <li>VITE : visage paralysé, impossible de bouger un membre, trouble de la parole : 15 ou 112, même si ça passe. Je note l\'heure.</li>\n'
    '        <li>Aucun médicament de ma propre initiative. Signe d\'AVC : ni à boire, ni à manger, ni médicament.</li>\n'
    '        <li>Je la protège du froid et je la surveille sans arrêt. Ne répond plus et respire normalement : PLS. Ne respire pas normalement : fiche 3.</li>\n'
    '      </ol>\n      <p class="ref">→ chapitre 8</p>\n    </div>\n' + anchor)
rep("P28", "<p>Onze fiches, cinq gestes chacune, dans l'ordre.", "<p>Douze fiches de cinq gestes (six pour la fiche 10), dans l'ordre.")

# ---- POINT 21 : nœud plat
rep("P21", "Le nœud plat (deux demi-nœuds croisés dans le même sens) sert à fermer un sac ou un bandage.",
    "Le nœud plat (un demi-nœud droite sur gauche, puis un second gauche sur droite) sert à fermer un sac ou un bandage. Si vous faites les deux demi-nœuds dans le même sens, vous obtenez un nœud de vache, qui glisse : refaites-le.")

# ---- POINT 22 : kit
rep("P22a", "<li><b>Divers :</b> cordelette (10 à 15 m),", "<li><b>Divers :</b> cordelette (environ 15 m si vous comptez monter une bâche, chapitre 12),")
rep("P22b", "<li><b>Protection :</b> couverture de survie, sac poubelle épais (poncho, abri, bâche).</li>",
    "<li><b>Protection :</b> couverture de survie, sac poubelle épais (poncho, abri de secours) ; si possible, une bâche légère d'environ 2 × 2,5 m (chapitre 12).</li>")

# ---- POINT 23 : couteau (encadré juridique + rubrique séparée)
rep("P23", "Transportez un couteau pliant fermé et un couteau à lame fixe toujours dans son étui, dans une pochette au milieu du sac, pas dans une poche où vous mettez la main sans regarder. À la ceinture, dans son étui, la lame pointe vers le bas. Faites de même pour la scie (lame repliée) et la hachette (protège-lame). À la maison, rangez les lames propres, sèches, fermées et hors de portée des jeunes enfants.\n  </div>\n</section>",
    "En dehors de l'activité, transportez l'outil fermé ou dans son étui, rangé dans le sac, pas sur vous ; dans les transports publics, rien de visible.\n  </div>\n"
    "  <h3>Ranger et transporter une lame</h3>\n"
    "  <p>Couteau pliant fermé ; couteau à lame fixe toujours dans son étui, dans une pochette au milieu du sac, pas dans une poche où vous mettez la main sans regarder. Pendant l'activité seulement, si vous le portez à la ceinture, gardez-le dans son étui, lame vers le bas. Même règle pour la scie (lame repliée) et la hachette (protège-lame). À la maison, rangez les lames propres, sèches, fermées et hors de portée des jeunes enfants.</p>\n</section>")

# ---- POINT 24 : avant de dormir (Abri Feu)
rep("P24", "Avant de dormir : mangez, urinez (le corps ne chauffe plus la vessie), mettez des vêtements secs.",
    "Avant de dormir : mangez, allez aux toilettes pour éviter de devoir sortir du couchage au froid pendant la nuit (un récipient fermable réservé à cet usage peut servir), et mettez des vêtements secs.")

# ---- POINT 25 : feu en forêt (Abri Feu)
rep("P25", "un randonneur n'y fait pas de feu, sauf urgence vitale.",
    "un randonneur n'y fait pas de feu. En situation de détresse, privilégiez l'abri, l'isolation et l'alerte (chapitre 21).")

# ---- POINT 26 : bâche (Bushcraft)
rep("P26", "fixez les quatre coins au sol avec des piquets ou des pierres, le côté bas face au vent.",
    "fixez les quatre coins au sol avec des piquets ou des pierres. Orientez la ligne de faîtage pour que le vent frappe un pan de la bâche ou une extrémité étroite, pas l'ouverture ; si le vent tourne, fermez le côté exposé avec votre sac ou des branches.")

# ---- POINT 27 : renvoi kit eau (Expert Eau)
rep("P27", "<li><b>Eau :</b> récipient permettant de faire bouillir (voir chapitre 22),",
    "<li><b>Eau :</b> récipient permettant de faire bouillir (voir chapitre 13, « Faire bouillir : un vrai récipient », et chapitre 22),")

# ---- POINT 29 : balisage
rep("P29", "La forme donne la consigne : un trait (deux pour un GR) = bonne direction ; un trait fléché = changement de direction ; une croix = mauvaise direction. Méfiez-vous des marques orange (itinéraires équestres) et des marques forestières ou communales. Plus de balise depuis longtemps ? Revenez à la dernière balise vue.",
    "La forme donne la consigne : un trait pour un PR, deux traits pour un GR ou un GR de Pays = bonne direction ; un trait fléché = changement de direction ; une croix = mauvaise direction. Méfiez-vous des marques orange (itinéraires équestres) et des marques forestières ou communales. Plus de balise depuis un moment : voir l'encadré ci-dessous.")

# ---- POINT 30 : Croix du Sud
rep("P30", "d'environ 4,5 fois sa longueur. Le point obtenu",
    "d'environ 4,5 fois sa longueur. Repérez-la grâce aux deux étoiles brillantes voisines, les « Pointeurs » : la perpendiculaire tracée au milieu de leur segment croise le prolongement du grand axe de la croix près du pôle sud céleste. Le point obtenu")

# ---- POINT 31 : accord enfants
rep("P31", "apprenez aux enfants à toujours dire à un adulte où ils vont,", "apprenez à chaque enfant à toujours dire à un adulte où il va,")

# ---- POINT 32 : F.A.C.E.T.S.
rep("P32", "des études d'accidents montrent", "des études d'accidents d'avalanche montrent")

# ---- POINT 33 : fiche 6
rep("P33", "<li>Je garde la tête hors de l'eau et je calme ma respiration (choc des premières minutes).</li>",
    "<li>Je garde la tête hors de l'eau et je laisse ma respiration se calmer (le choc passe en général en moins d'une minute).</li>")

# ---- POINT 35 : « Nœuds utiles »
rep("P35a", '<a href="#noeuds">Trois nœuds utiles</a>', '<a href="#noeuds">Nœuds utiles</a>')
rep("P35b", '<span class="num">12</span>Trois nœuds utiles</h2>', '<span class="num">12</span>Nœuds utiles</h2>')
rep("P35c", "<li>Faire les 3 nœuds les yeux fermés (chapitre 12).</li>",
    "<li>Faire les yeux fermés le nœud de chaise, le cabestan et le nœud tendeur (chapitre 12).</li>")

# ---- POINT 36, 37 : entraînement
rep("P36", "<li>Réussir un feu après la pluie : bois fendu, copeaux en plumes.</li>",
    "<li>Réussir un feu après la pluie : bois mort abrité, copeaux en plumes ; bois fendu à la scie ou par bâtonnage seulement après apprentissage encadré (chapitre 22).</li>")
rep("P37", "le cercle de sécurité, la position assise", "le cercle de sécurité (bras tendu, tour sur soi-même), la position assise")

# ---- POINT 38 : 3 L/pers./jour
rep("P38", "au moins 6 litres par personne selon les recommandations françaises, à adapter aux besoins ;",
    "au moins 6 litres par personne selon les recommandations françaises, à adapter aux besoins ; en situation de crise, les autorités distribuent en général 3 litres par personne et par jour pour boire et préparer les repas ;")

# ---- POINT 40 : fiche 3
rep("P40", "5–6 cm ; je l'utilise dès qu'il arrive.", "5–6 cm ; j'utilise le défibrillateur dès qu'il arrive.")

# ---- POINT 41, 42 : glossaire
rep("P41a", "    <tr><th>FR-Alert</th>",
    "    <tr><th>EPIRB</th><td>Balise de détresse d'un bateau ; alerte par satellite avec sa position (ch. 16)</td></tr>\n    <tr><th>FR-Alert</th>")
rep("P41b", "    <tr><th>PLB</th>",
    "    <tr><th>MOB</th><td>« Homme à la mer » : touche du GPS qui enregistre la position de la chute (ch. 16)</td></tr>\n    <tr><th>PLB</th>")
rep("P41c", "    <tr><th>SRO</th><td>Solution de réhydratation orale (ch. 8)</td></tr>",
    "    <tr><th>SRO</th><td>Solution de réhydratation orale (ch. 8)</td></tr>\n    <tr><th>VHF</th><td>Radio marine ; le canal 16 sert à l'appel de détresse (ch. 16)</td></tr>")
rep("P42b", "<td>Référentiel technique national des premiers secours citoyens (ch. 8)</td>",
    "<td>Références techniques nationales – Premiers secours citoyen (DGSCGC), référence suivie pour l'arrêt cardiaque de l'enfant (ch. 8)</td>")

# ---- Couverture
rep("COUV", "Version 1.2 — 9 novembre 2026", "Version 1.3 — 9 novembre 2026")

open(path, "w", encoding="utf-8").write(h)
print(len(log), "opérations appliquées :", ", ".join(log))
