"""Intégration des 72 manques (v1.2). Chaque ancre doit exister exactement une fois."""
import re
import sys

p = sys.argv[1]
s = open(p, encoding="utf-8").read()
errors = []
ADDED = []  # (manque, texte ajouté) pour le contrôle


def _pos(anchor):
    n = s.count(anchor)
    if n != 1:
        errors.append(f"{n}x ancre : {anchor[:80]!r}")
        return None
    return s.index(anchor)


def ins(tag, anchor, mode, html):
    """Insère html après (ou avant) l'élément contenant l'ancre."""
    global s
    pos = _pos(anchor)
    if pos is None:
        return
    if mode == "before":
        at = pos
    elif mode == "li":
        at = s.index("</li>", pos) + 5
    elif mode == "tr":
        at = s.index("</tr>", pos) + 5
    elif mode == "list":
        at = re.compile(r"</(ul|ol)>").search(s, pos).end()
    elif mode == "figure":
        at = s.index("</figure>", pos) + 9
    elif mode == "block":
        at = re.compile(r"</(p|table|div)>").search(s, pos).end()
    else:
        raise ValueError(mode)
    s = s[:at] + "\n" + html + s[at:]
    ADDED.append((tag, html))


def rep(tag, old, new):
    global s
    if _pos(old) is None:
        return
    s = s.replace(old, new)
    ADDED.append((tag, new))


def box(title, body, warn=False):
    return f'  <div class="box{" warn" if warn else ""}">\n    <strong>{title}</strong>\n    {body}\n  </div>'


# ======================= CHAPITRE 1 =======================
ins("M21", "(Voir aussi la respiration, chapitre 11.)", "block", box(
    "Quand le corps flanche, le jugement aussi",
    "Le froid peut empêcher de penser clairement, et la personne touchée ne s'en aperçoit pas toujours. La chaleur et l'altitude peuvent aussi rendre confus (chapitres 8 et 15). Avant une décision importante (partir, se séparer, renoncer à l'abri), demandez l'avis d'un autre membre du groupe. Surveillez-vous mutuellement : maladresse, paroles confuses, somnolence ou idée inhabituelle. Si vous êtes seul et avez froid, mettez-vous d'abord à l'abri et au chaud avant de décider quoi que ce soit."))

ins("M5", "Les efforts déjà fournis ne justifient pas", "block", box(
    "Ne jamais se disperser",
    "Évitez de partir seul. En groupe, restez ensemble et marchez à deux (chacun veille sur un partenaire) ; donnez un sifflet à chacun. Ne laissez jamais le groupe s'étirer hors de vue : une personne ouvre la marche et personne ne la dépasse ; une autre ferme la marche (« serre-file ») et vérifie que personne ne reste derrière. Prévenez la tête ou le serre-file avant de vous arrêter ou de vous écarter. Si quelqu'un veut faire demi-tour ou explorer, il ne part jamais seul. Si vous êtes séparé du groupe, restez où vous êtes, sauf danger immédiat. <b>Si quelqu'un manque à l'appel</b> : arrêtez-vous et regroupez tout le monde ; revenez ensemble au dernier endroit où il a été vu et attendez-le là tant que c'est sûr ; alertez le 112 en donnant ce dernier point, l'heure, la couleur de ses vêtements, ce qu'il porte et son état de santé. Ne partez pas le chercher seul hors du sentier."))

ins("M4", "Ne bougez que pour échapper à un danger immédiat", "block", box(
    "Si un enfant se perd",
    "Avant chaque sortie, apprenez aux enfants à toujours dire à un adulte où ils vont, et cette phrase simple : « Si tu te perds, serre un arbre et ne bouge plus. » Son « arbre » peut aussi être un gros rocher ou un banc : l'essentiel est de rester au même endroit. Expliquez-lui qu'il doit se couvrir, fermer sa veste et s'asseoir sur des feuilles plutôt que sur le sol. Dites-lui que les personnes qui crient son nom viennent l'aider, qu'il doit leur répondre, siffler ou agiter les bras, ne jamais se cacher, et que personne ne sera fâché contre lui. Donnez à chaque enfant un sifflet et un vêtement de couleur vive.", warn=True))

rep("M2", "<li>Laissez votre itinéraire et votre heure de retour à un proche.</li>",
    "<li><b>Plan de sortie écrit</b>, laissé à un proche : participants (et leur numéro), itinéraire et variantes, lieu de stationnement (modèle et plaque de la voiture), matériel, heure de retour prévue et <b>heure limite d'alerte</b>. Convenez avec lui : « Sans nouvelles de moi à telle heure, appelle le 112 et donne ce plan » ; dites-lui qu'il ne dérange personne en le faisant. Ajoutez une description des vêtements ou une photo du groupe prise au départ. Tenez-vous à ce plan ; si vous en changez, prévenez-le ; au retour, confirmez-lui que vous êtes rentré. Choisissez une sortie adaptée à la personne la moins entraînée.</li>")

ins("M45-M56", "<li>Partez avec un téléphone chargé et une batterie externe", "li",
    "    <li>Consultez la carte de <b>vigilance de Météo-France</b> (vigilance.meteofrance.fr, mise à jour deux fois par jour) et, près d'un cours d'eau, <b>Vigicrues</b> (vigicrues.gouv.fr) ; activez au besoin les notifications de vigilance dans l'application Météo-France. Vigilance orange : soyez très vigilant et suivez les conseils des pouvoirs publics. Vigilance rouge : respectez impérativement leurs consignes. Au besoin, reportez ou modifiez votre sortie.</li>\n"
    "    <li>En été, dans les départements exposés aux feux de forêt, l'accès aux massifs peut être limité ou interdit selon le risque du jour : consultez la veille la carte d'accès publiée par la préfecture et respectez-la (exemple : dans les Bouches-du-Rhône, du 1er juin au 30 septembre, elle est mise à jour vers 18 h pour le lendemain).</li>")

# ======================= CHAPITRE 2 =======================
rep("M25", "<li><b>Soins :</b> pansements, compresses, bande, désinfectant, médicaments personnels.</li>",
    "<li><b>Soins :</b> gants jetables ; pansements de plusieurs tailles et pansements anti-ampoules ; compresses stériles ; bande et pansement compressif ; sparadrap ; désinfectant cutané incolore ; solution hydroalcoolique ; sérum physiologique en unidoses ; petits ciseaux, pince à écharde, tire-tique ; 2 sachets de sels de réhydratation orale ; sucre en emballage individuel ; tous vos médicaments personnels en quantité suffisante, y compris ceux prévus en cas d'urgence (auto-injecteur d'adrénaline, inhalateur prescrits) ; une fiche d'urgence plastifiée (identité, traitements, allergies, antécédents importants, personne à prévenir). Autres médicaments : seulement sur avis médical. Vérifiez les dates et complétez la trousse après chaque sortie.</li>")
rep("Arb7", "cordelette (10 m)", "cordelette (10 à 15 m)")
rep("M59", "Mesurez le volume d'eau et respectez exactement la dose, la température d'emploi et le temps de contact indiqués.</li>",
    "Mesurez le volume d'eau et respectez exactement la dose, la température d'emploi et le temps de contact indiqués. Évitez l'eau traitée à l'iode si vous êtes enceinte, si vous avez un problème de thyroïde ou une allergie à l'iode ; personne ne doit en boire plus de quelques semaines d'affilée.</li>")
ins("M44k", "cordelette (10 à 15 m)", "li",
    "    <li><b>Zone sans réseau fiable :</b> balise personnelle de détresse (PLB), voir chapitre 7.</li>")
ins("M41", "<li><b>Zone sans réseau fiable :</b>", "list",
    "  <p><b>Garder le kit au sec et le vérifier.</b> Rangez le kit, les vêtements de rechange et le sac de couchage dans un sac étanche ou un sac poubelle épais, à l'intérieur du sac à dos, même si celui-ci a une housse de pluie. Avant chaque sortie, faites un contrôle rapide : le briquet s'allume, la lampe fonctionne et les piles de rechange sont là, le téléphone et la batterie sont chargés, le couteau coupe et se ferme bien. Vérifiez les dates de péremption des pansements, des médicaments et des pastilles. Remplacez tout de suite ce que vous avez utilisé.</p>")

# ======================= CHAPITRE 4 =======================
rep("M36", "N'utilisez ni essence, ni alcool, ni solvant pour allumer ou raviver.",
    "N'utilisez ni essence, ni alcool, ni solvant pour allumer ou raviver. <b>En France</b>, seul le propriétaire du terrain (ou son occupant) peut porter ou allumer du feu dans les bois et forêts et jusqu'à 200 m de ceux-ci : un randonneur n'y fait pas de feu, sauf urgence vitale. En période de risque, le préfet peut interdire tout emploi du feu, voire l'accès aux massifs. Avant de partir, consultez la « Météo des forêts » de Météo-France et les consignes de la préfecture. Le non-respect est sanctionné.")
ins("M37", "<li>Pour éteindre : noyez, remuez, noyez encore.", "li",
    "    <li><b>Si votre feu s'échappe ou si vous voyez un départ de feu</b> : alertez immédiatement (112, 18, ou 114 par SMS si vous ne pouvez pas parler). Localisez le feu sans vous mettre en danger, éloignez-vous de la fumée et ne traversez jamais un front de flammes ou de fumée. Une voiture n'est pas un abri sûr : rejoignez si possible une habitation débroussaillée et suivez les consignes des secours.</li>")
ins("M8", "Évitez les pierres de rivière autour du foyer", "block", box(
    "Vêtements en feu : s'arrêter, se laisser tomber, se rouler",
    "Si vos vêtements prennent feu : arrêtez-vous, laissez-vous tomber au sol en couvrant votre visage avec les mains, et roulez-vous jusqu'à ce que les flammes s'éteignent. Ne courez pas. Si la personne ne peut pas le faire, étouffez les flammes avec une couverture épaisse ou une veste, pas avec une couverture de survie. Refroidissez ensuite la brûlure à l'eau (chapitre 8) et alertez si elle est étendue.", warn=True))

# ======================= CHAPITRE 5 =======================
ins("M13", "Signes de déshydratation : soif, urines foncées et rares", "block",
    "  <p><b>Signes graves :</b> bouche et langue très sèches, yeux creux, peau qui reste plissée quand on la pince, très peu d'urines, désorientation, malaise ou comportement inhabituel. Appelez le 15 (ou le 112) si la personne a des troubles de la conscience, refuse ou ne peut pas boire, ou si sa peau change de couleur ; ne faites boire qu'une personne bien consciente qui avale sans difficulté (chapitre 8). Les personnes âgées ont souvent une soif tardive et faible : proposez-leur à boire régulièrement, sans attendre qu'elles le demandent. Les nourrissons et les jeunes enfants se déshydratent vite par la chaleur : proposez souvent à boire et appelez un médecin en cas de fièvre ou de changement de comportement.</p>")
ins("M31", "Écartez les eaux suspectes de pollution. Une eau claire peut être contaminée.</p>", "block", box(
    "Eaux à ne pas boire, même traitées",
    "Une eau calme colorée de façon inhabituelle (verte, bleue, rouge), avec une écume ou des amas en surface, ou qui sent mauvais ; une eau près de poissons morts ; une eau qui sent le carburant ou un produit chimique, ou qui coule en aval d'un rejet de produits chimiques ou de carburant. Certaines toxines d'algues (cyanobactéries) résistent à l'ébullition. Cherchez une autre source. Tenez enfants et chiens éloignés de ces eaux.", warn=True))
ins("M14-M35", "<b>Filtres et pastilles :</b>", "block",
    box("Eau de Javel : à valider",
        "En crise à la maison, l'eau de Javel peut servir à désinfecter une eau claire, mais le dosage dépend de sa concentration et doit être exact. Le protocole transmis (Javel à 2,6 %) n'a pas pu être validé et diffère fortement des recommandations étrangères : ce livret ne donne donc pas de dosage. Suivez les consignes des autorités sanitaires (ARS, mairie) ou de la notice d'un produit de traitement de l'eau ; n'utilisez jamais une Javel parfumée ou avec additif. Faute de consigne fiable, faites bouillir. La Javel ne retire aucun produit chimique.", warn=True) + "\n"
    "  <p><b>Hygiène autour de l'eau :</b> lavez-vous les mains au savon avant de manipuler l'eau ou la nourriture et après être allé aux toilettes ; à défaut, utilisez un gel hydroalcoolique à au moins 60 % d'alcool. Sans toilettes, enterrez vos selles à au moins 20 cm de profondeur et à au moins 60 m de tout cours d'eau, lac ou source, en aval du point où vous puisez l'eau. Ne faites jamais vos besoins dans l'eau. Lavez-vous, et lavez la vaisselle et les vêtements, à au moins 30 m de l'eau que vous buvez.</p>")

# ======================= CHAPITRE 6 =======================
ins("M48-M50-M20", "Boussole à plaque posée sur une carte", "figure",
    "  <h3>Lire la carte</h3>\n"
    "  <p>Pour marcher, prenez une carte topographique au 1:25 000 (en France, IGN TOP 25 ou série bleue) : 1 cm sur la carte = 250 m sur le terrain, donc 4 cm = 1 km. Les courbes de niveau, complétées de cotes d'altitude, montrent le relief. La légende indique la déclinaison magnétique, valable pour une année donnée. Avant de partir, mesurez les distances de chaque étape et notez-les sur votre fiche d'itinéraire.</p>\n"
    "  <h3>Suivre sa progression</h3>\n"
    "  <p>Orientez la carte : tournez-la pour que son nord coïncide avec le nord de la boussole, ou alignez-la sur une route ou une lisière. En marchant, « cochez » chaque repère passé (carrefour, ruisseau, col) et retournez-vous de temps en temps pour mémoriser le retour. Quand c'est possible, suivez une ligne évidente (chemin, lisière, crête large et sûre). Pour un objectif discret, visez d'abord un repère proche et facile à trouver. Repérez aussi à l'avance une « ligne d'arrêt » au-delà de l'objectif (route, rivière, début de descente) : si vous l'atteignez, vous êtes allé trop loin.</p>\n"
    "  <h3>Le balisage des sentiers</h3>\n"
    "  <p>Sur les sentiers balisés de la FFRandonnée, la couleur indique le type de sentier : blanc-rouge pour un GR, jaune-rouge pour un GR de Pays, jaune pour une promenade (PR). La forme donne la consigne : un trait (deux pour un GR) = bonne direction ; un trait fléché = changement de direction ; une croix = mauvaise direction. Méfiez-vous des marques orange (itinéraires équestres) et des marques forestières ou communales. Plus de balise depuis longtemps ? Revenez à la dernière balise vue.</p>\n"
    + box("Au premier doute, arrêtez-vous",
          "Au premier doute (plus de balise depuis un moment, terrain qui ne correspond pas à la carte, trajet plus long que prévu), arrêtez-vous tout de suite. Notez l'heure et cherchez ce qui ne colle pas. Si le chemin parcouru est clair et sûr, revenez sur vos pas jusqu'au dernier point certain : dernière balise vue, carrefour identifié, repère reconnu. Ne continuez jamais « pour voir ». Si le retour n'est pas évident, appliquez S.T.O.P. et restez sur place (chapitre 1).", warn=True))
ins("M69", "n'est pas utilisable dans l'hémisphère sud.</figcaption>", "figure",
    "  <p><b>Hémisphère sud : la Croix du Sud.</b> Prolongez son grand axe, du haut vers le bas de la croix, d'environ 4,5 fois sa longueur. Le point obtenu est proche du pôle sud céleste ; à la verticale de ce point, sur l'horizon, se trouve approximativement le sud. Ce repère est approximatif : contrôlez-le avec une autre méthode et ne l'utilisez pas seul pour suivre un cap.</p>")

# ======================= CHAPITRE 7 =======================
ins("M3", "<li>Essayez d'abord le <b>112</b> par appel, depuis votre emplacement sûr.", "li",
    "    <li><b>Que dire au téléphone (112, 15 ou 18) :</b> restez calme. Donnez votre nom et le numéro d'où vous appelez, puis le lieu le plus précis possible : massif, commune, lieu-dit, nom du sommet ou du sentier, altitude, repères, coordonnées GPS (voir ci-dessous). Dites ce qui s'est passé et à quelle heure, combien de personnes sont concernées et dans quel état, les gestes déjà faits, la météo et les dangers sur place. Répondez aux questions, appliquez les consignes et ne raccrochez qu'avec l'accord de l'opérateur. Si vous chargez quelqu'un d'alerter, vérifiez avant qu'il a toutes les informations, puis qu'il a bien appelé. Si possible, envoyez une personne accueillir et guider les secours. Si l'état de la victime s'aggrave, rappelez.</li>\n"
    "    <li><b>Localisation automatique :</b> en France, lors d'un appel au 112 depuis un smartphone, votre position est en général transmise automatiquement aux secours (système AML), sans application ni action de votre part, parfois même avec une faible couverture. Laissez la localisation activée. Cette transmission n'est pas garantie : donnez quand même votre position à voix haute et décrivez le lieu.</li>")
ins("M44", "<li><b>SMS :</b> en France, n'envoyez pas par défaut un SMS au 112.", "li",
    "    <li><b>Balise personnelle de détresse (PLB, 406 MHz) :</b> en zone isolée sans réseau fiable, elle envoie une alerte et votre position par satellite. Enregistrez-la avant le départ ; en France, auprès du registre des balises 406 MHz (registre406.cnes.fr), en y indiquant votre sortie. Apprenez à l'utiliser, gardez-la sur vous, pas au fond du sac, et ne la déclenchez qu'en détresse réelle. Elle complète le téléphone et le plan laissé à un proche ; elle ne les remplace pas.</li>")

# ======================= CHAPITRE 8 =======================
ins("M53", "→ <b>Alerter</b> (112) → <b>Secourir</b>.</p>", "block",
    "  <p class=\"small\">Pour l'alerte, voir « Que dire au téléphone », chapitre 7.</p>\n" + box(
        "Le blessé n'a pas besoin que de gestes",
        "Restez près de lui si c'est sûr, dites-lui votre prénom et ce que vous faites, et dites-lui que les secours sont prévenus. Écoutez-le sans le juger et ne lui promettez pas ce que vous ne savez pas. Si quelqu'un meurt, occupez-vous d'abord de la sécurité des vivants et laissez chacun réagir à sa façon. Après coup, la culpabilité est fréquente : parlez-en. Demandez de l'aide auprès de la cellule d'urgence médico-psychologique (via le 15) ou de votre médecin."))
ins("M57", "Formation à la pose d'un garrot tourniquet", "figure",
    "  <h3>Saignement de nez</h3>\n"
    "  <p>Asseyez la personne, tête penchée en avant ; ne l'allongez pas. Demandez-lui de se moucher fort, puis de serrer les deux narines avec les doigts pendant 10 minutes sans relâcher. Demandez un avis médical si le saignement ne s'arrête pas ou revient, s'il fait suite à une chute ou à un coup, ou si la personne prend un médicament qui fait saigner davantage. Alertez le 15 ou le 112 en cas de sueurs abondantes, de sensation de froid, de pâleur intense ou de malaise.</p>")
ins("M23", "<h3>Étouffement (adulte)</h3>", "before",
    "  <h3>Convulsions</h3>\n"
    "  <p>Ne retenez pas les mouvements et ne mettez rien dans la bouche. Écartez ce qui peut blesser, protégez la tête avec un vêtement plié, desserrez col et ceinture, retirez les lunettes. Ne déplacez la personne qu'en cas de danger immédiat. Notez l'heure de début. Dès que les secousses s'arrêtent, mettez-la sur le côté (PLS), restez avec elle et surveillez sa respiration. Ne lui donnez rien à boire. Appelez le 15 ou le 112 si la crise dure plus de cinq minutes, si elle se répète sans retour à la normale, si la personne reste inconsciente ou ne reprend pas vite une respiration normale, si elle est blessée, si la crise est survenue dans l'eau, ou s'il s'agit d'une première crise.</p>\n\n")
ins("M1-M22", "Les antihistaminiques ne remplacent pas l'adrénaline.", "block",
    "\n  <h3>Malaise, douleur dans la poitrine</h3>\n"
    "  <p>Une personne consciente qui « ne se sent pas bien » peut faire une urgence grave. Mettez-la tout de suite au repos : allongée, assise si elle respire mal, sinon dans la position où elle se sent le mieux. Appelez sans attendre le 15 ou le 112 si elle présente notamment : une douleur dans la poitrine qui serre, dure plus de cinq minutes ou s'étend aux bras, à la mâchoire ou au dos ; un essoufflement ; des sueurs abondantes ou une pâleur intense ; une difficulté à parler ; un mal de tête sévère et inhabituel. Au moindre doute, appelez aussi. Notez son âge, depuis quand elle a ces signes, si c'est déjà arrivé et quels médicaments elle prend : le médecin du 15 vous le demandera. Ne lui donnez aucun médicament de votre propre initiative. Aidez-la seulement à prendre son traitement prescrit (par exemple son inhalateur si elle est asthmatique), à sa demande ou sur consigne du 15. Protégez-la du froid, de la chaleur et des intempéries, surveillez-la sans arrêt et parlez-lui. Si elle perd connaissance et ne respire plus normalement, c'est un arrêt cardiaque (encadré ci-dessus).</p>\n"
    "  <h3>Signes d'AVC : pensez VITE</h3>\n"
    "  <p><b>V</b> : Visage paralysé (bouche de travers, sourire impossible). <b>I</b> : Impossible de bouger un bras ou une jambe, ou faiblesse d'un membre. <b>T</b> : Trouble de la parole (mots qui ne sortent pas ou incompréhensibles). <b>E</b> : Éviter le pire en appelant le 15 ou le 112. Un seul de ces signes, apparu brutalement, suffit pour appeler, même s'il disparaît en quelques minutes. Appelez aussi en cas de perte brutale de la vue d'un œil ou de vision double, de perte soudaine de l'équilibre, ou de mal de tête brutal, intense et inhabituel. Notez l'heure du début des signes. Aidez la personne à s'asseoir ou à s'allonger. Ne lui donnez ni à boire, ni à manger, ni aucun médicament, même son traitement habituel. Si elle ne répond plus mais respire normalement, mettez-la en PLS et surveillez sa respiration.</p>\n"
    "  <h3>Personne diabétique confuse ou somnolente</h3>\n"
    "  <p>Chez une personne diabétique, un changement brutal de comportement, une confusion ou une somnolence doivent faire penser à un manque de sucre (hypoglycémie). Si elle est bien réveillée et avale bien : donnez-lui du sucre tout de suite (morceaux de sucre, bonbons sucrés, 50 à 100 mL de jus de fruits ou une boisson sucrée, ou ses propres comprimés de glucose). Si les signes persistent au bout de 15 minutes, redonnez du sucre. Une fois remise, faites-lui manger une collation. Appelez le 15 ou le 112 si elle ne s'améliore pas ou si son état se dégrade. Si elle ne répond pas : rien par la bouche, appelez le 15 ou le 112 et, si elle respire normalement, mettez-la en PLS.</p>")
ins("M7", "même si elle frissonne encore.</p>", "block",
    "  <p>L'hypothermie ne survient pas seulement dans la neige : être mouillé par la pluie ou le brouillard, puis exposé au vent, peut refroidir rapidement, même en été. Des frissons persistants ou violents sont un signal d'alarme sérieux. Une personne qui se refroidit dit souvent que « ça va » : surveillez vos compagnons et protégez-vous avant d'être trempé (vêtement de pluie, abri du vent, bonnet).</p>")
ins("M38", "Évitez les sources brûlantes et les bains ou douches chauds.", "list",
    "  <p><b>Réchauffer sans danger :</b> mettez la personne au sec dans un sac de couchage ou des couvertures sèches, avec un bonnet, sur un isolant. Vous pouvez placer des bouillottes tièdes ou des chaufferettes bien enveloppées (jamais au contact direct de la peau) au cou, aux aisselles et à l'aine, et contrôler régulièrement la peau. Boissons chaudes seulement si elle est consciente et avale bien, jamais d'alcool. Alertez si elle devient confuse ou somnolente.</p>")
ins("M39", "Une transpiration abondante n'exclut pas un coup de chaleur.</li>", "list",
    "  <p><b>Avant le coup de chaleur : l'épuisement.</b> La chaleur peut d'abord provoquer une grande fatigue, une faiblesse, des vertiges, des maux de tête, des nausées, des crampes, des sueurs abondantes, une peau pâle et moite. Arrêtez l'effort, allongez la personne à l'ombre ou au frais, desserrez ses vêtements, mouillez sa peau et éventez-la. Faites-la boire par petites gorgées seulement si elle est bien consciente, avale sans difficulté et n'a pas de nausées. Si elle vomit, si son état s'aggrave ou ne s'améliore pas rapidement, ou en cas de confusion : 15 ou 112.</p>")
ins("M15", "Vérifier que les doigts / orteils restent chauds et colorés", "list",
    "\n  <h3>Chute ou choc violent : tête, cou, dos</h3>\n"
    "  <p>Après une chute de hauteur, un choc violent ou en cas de douleur du cou ou du dos, ne déplacez pas la personne, sauf danger immédiat. Si elle est consciente, demandez-lui fermement de ne pas bouger, surtout la tête. Ne la forcez jamais dans une position. Couvrez-la contre le froid sans la mobiliser, appelez le 15 ou le 112, surveillez-la et parlez-lui. Après un choc à la tête, même si elle semble aller bien, demandez un avis médical et alertez de nouveau si une perte de connaissance, même brève, des maux de tête qui persistent, des vomissements, une agitation, une somnolence, une confusion ou un trouble de la vue apparaissent. Elle doit alors cesser tout effort. Membre déformé : ne tentez pas de le remettre droit.</p>")
ins("M55-M24", "Un tire-tique (crochet) : glissé sous la tique", "figure",
    "  <p><b>Prévenir les tiques :</b> en forêt, dans les hautes herbes ou les broussailles, portez des vêtements longs et clairs, serrés aux poignets et aux chevilles, et emportez un tire-tique. Au retour, puis le lendemain, examinez tout le corps (aisselles, plis des genoux, organes génitaux, nombril, oreilles, cou, cuir chevelu), et celui des enfants avec soin. Surveillez la zone de la piqûre pendant un mois : une plaque rouge qui s'étend entre 3 et 30 jours après peut signaler la maladie de Lyme et impose de consulter.</p>\n"
    "  <h3>Piqûre de guêpe, d'abeille ou de frelon</h3>\n"
    "  <p>Le plus souvent : douleur, rougeur et gonflement au point de piqûre. Piqûre à la main : retirez les bagues. Abeille : retirez vite le dard en grattant avec l'ongle ou le bord d'une carte, sans le pincer. Lavez à l'eau et au savon, appliquez du froid enveloppé dans un tissu, et cessez tout effort pendant 30 minutes. Vérifiez la vaccination antitétanique. Appelez immédiatement le 15 ou le 112 en cas de piqûre dans la bouche ou la gorge, de difficulté à respirer ou à avaler, de gonflement de la langue, des lèvres ou du visage, de malaise ou d'urticaire généralisée (voir Anaphylaxie), de piqûres multiples (plus de 20 chez l'adulte, dès 4 ou 5 chez l'enfant), ou d'allergie connue au venin : aidez alors la personne à utiliser son auto-injecteur d'adrénaline. Consultez si la zone reste très rouge, gonflée et douloureuse au-delà de 24 heures.</p>")
ins("M16", "Rougeur qui s'étend, douleur croissante, pus ou fièvre nécessitent un avis médical", "list",
    "\n  <h3>Plaie grave</h3>\n"
    "  <p><b>Objet planté</b> (bâton, éclat, couteau) : ne le retirez jamais. <b>Plaie de la poitrine</b> : laissez la personne assise, sans couvrir la plaie avec un pansement étanche. <b>Plaie du ventre</b> : allongez-la, jambes pliées. <b>Plaie de l'œil</b> : allongée, yeux fermés, en lui demandant de ne pas bouger la tête. Dans tous les cas : en cas de saignement abondant, appliquez la rubrique « Saignement abondant » sans retirer l'objet ; protégez la personne du froid, appelez le 15 ou le 112 et surveillez-la. <b>Doigt ou autre partie du corps arrachée</b> : arrêtez d'abord le saignement. Enveloppez la partie dans un tissu propre humidifié, mettez-la dans un sac fermé et étanche, puis posez ce sac dans un autre sac contenant de la glace ou de l'eau glacée, sans contact direct avec la glace. Notez le nom et l'heure, et remettez-la aux secours.</p>")

# ======================= CHAPITRE 9 =======================
ins("M11", "<td>La cuisson réduit de nombreux risques infectieux, mais ne rend pas comestible", "block",
    "  <p><b>La cuisson ne rend pas comestible une plante ou un champignon toxique :</b> elle tue des parasites, mais le poison de l'if ou de l'amanite phalloïde résiste à la cuisson et au séchage. On ne cuit que ce qui est déjà identifié avec certitude comme comestible.</p>")
ins("M29-M30", "<strong>Règle absolue</strong>", "block",
    "  <ul>\n    <li>Ne vous fiez pas à ce que mangent les animaux : un oiseau peut manger sans danger les « baies » de l'if, dont la graine est très toxique pour l'homme.</li>\n"
    "    <li>Le « test universel de comestibilité » décrit dans certains manuels de survie n'est pas une méthode pour débutant : il oblige à goûter puis avaler une plante inconnue, alors que quelques baies ou une petite quantité de certaines plantes peuvent suffire à tuer. Ce livret ne le recommande pas.</li>\n  </ul>")

# ======================= CHAPITRE 10 =======================
rep("M28", "Un doute = on ne mange pas.</li>",
    "Un doute = on ne mange pas. Une application de reconnaissance ne suffit jamais pour décider de manger une plante, et ne mangez jamais un champignon identifié par une application.</li>")
rep("M27", "<li>Ne cueillez pas au bord des routes, des champs traités, ni près des déjections animales (douve du foie : lavez et cuisez les plantes des prés humides).</li>",
    "<li>Ne cueillez pas au bord des routes, des champs traités, ni près des déjections animales. Ne mangez jamais de cresson sauvage cru, ni de plantes crues cueillies en milieu humide (pissenlit, menthe…) : elles peuvent porter la douve du foie, et le lavage, même au vinaigre, ne l'élimine pas ; seule la cuisson la tue. Les baies et plantes cueillies près du sol peuvent être souillées par les renards : dans le quart nord-est de la France et le Massif central notamment, cuisez systématiquement les fruits sauvages (la congélation ne suffit pas).</li>")
ins("M58", "<tr><td><b>Noisetier, châtaignier, hêtre</b></td>", "tr",
    "    <tr><td><b>Glands (chêne)</b></td><td>Fruits du chêne.</td><td>Ne les mangez pas : leurs tanins provoquent des troubles digestifs (constipation, douleurs, parfois diarrhée sanglante).</td></tr>")
rep("M9a", "indiquez l'heure, la partie consommée et la quantité estimée.",
    "indiquez l'heure, la partie consommée et la quantité estimée (numéros des centres antipoison : chapitre 25).")
ins("M10-M26", "<strong>Intoxication suspectée</strong>", "block",
    box("Champignon sauvage déjà mangé ?",
        "Appelez un centre antipoison sans attendre, même si tout va bien : les intoxications les plus graves commencent par plusieurs heures sans aucun symptôme, et les premiers signes peuvent n'apparaître que 12 heures après le repas, ou plus tard. Des troubles qui apparaissent vite ne rassurent pas non plus : plusieurs espèces ont pu être mangées. La cuisson ne détruit pas ces toxines. Notez l'heure du repas et des premiers signes et gardez les restes. Détresse : 15 ou 112.", warn=True) + "\n"
    + box("Plantes qui brûlent la peau au soleil",
          "Certaines plantes de la famille de la carotte (berce du Caucase, très grande, à tige creuse tachée de pourpre ; berce commune ; angélique) contiennent une sève qui brûle la peau au soleil. Les cloques peuvent apparaître un à trois jours après le contact. Ne les utilisez ni pour l'abri ni pour le feu ; portez des manches longues et des gants. En cas de contact : lavez à l'eau froide et au savon, protégez la zone du soleil pendant plusieurs jours, et consultez si la zone est étendue, si les yeux sont touchés ou s'il s'agit d'un enfant.", warn=True))

# ======================= CHAPITRE 12 =======================
ins("M42-M40-M65", "<p class=\"small\">Les étapes du nœud de chaise et du nœud tendeur sont illustrées", "block",
    "  <h3>Abouter deux cordes</h3>\n"
    "  <p>Le nœud plat (deux demi-nœuds croisés dans le même sens) sert à fermer un sac ou un bandage. Ne l'utilisez pas pour joindre deux cordes qui vont tirer : il peut glisser et se défaire. Pour abouter deux cordelettes de même diamètre, faites un double nœud de pêcheur : superposez les deux bouts, faites deux tours avec le premier bout autour des deux cordes, puis repassez-le dans ces tours et serrez ; faites la même chose avec l'autre bout, dans l'autre sens. Tirez sur les deux cordes pour que les deux nœuds se collent, et laissez des bouts libres assez longs. Ce nœud peut devenir très difficile à défaire. Comme les autres nœuds du livret, il ne sert pas à porter une personne.</p>\n"
    "  <h3>Monter une bâche sur une ligne de faîtage</h3>\n"
    "  <p>Choisissez deux arbres sains, à 3 à 4,5 m l'un de l'autre, sans branche morte au-dessus (chapitre 3). Tendez une cordelette entre eux à hauteur de taille. Attachez un bout avec un nœud de chaise ou un cabestan sécurisé, et l'autre avec un nœud qui se règle, comme le nœud tendeur. Posez la bâche à cheval sur la corde, centrée, puis fixez les quatre coins au sol avec des piquets ou des pierres, le côté bas face au vent. Retendez avant la nuit. Comptez environ 15 m de cordelette et une bâche d'environ 2 × 2,5 m pour une personne. Une couverture de survie se déchire facilement et ne fait pas une bonne toile d'abri.</p>\n"
    "  <h3>Assembler deux perches : le brêlage carré</h3>\n"
    "  <p>Pour fixer deux perches en croix, commencez par un nœud de cabestan sur l'une d'elles. Enroulez ensuite la corde autour des deux perches, en passant alternativement dessus et dessous, sur 3 ou 4 tours bien serrés. Faites ensuite 3 ou 4 tours de serrage entre les deux perches, autour des tours précédents. Terminez par deux ou trois demi-clés serrées. Testez l'assemblage en le chargeant à la main avant de vous en servir. Il convient à une structure de camp (cadre d'abri, étagère), pas à porter une personne sans formation (chapitre 13).</p>")

# ======================= CHAPITRE 14 =======================
ins("M19", "<li><b>Rivières</b> : privilégiez un pont sûr", "li",
    "    <li><b>Barrages et centrales :</b> même par beau temps, des lâchers d'eau peuvent faire monter brusquement le niveau et le courant d'une rivière, y compris loin de l'ouvrage. Respectez les panneaux jaunes, restez sur les berges, ne vous installez jamais sur un îlot, prenez un repère visuel du niveau de l'eau et évitez les endroits sans repli rapide. L'accès est interdit dans les 50 m en amont et en aval d'un barrage ou d'une centrale.</li>")
ins("M46-M47", "<li><b>Animaux</b> : faites du bruit en marchant", "li",
    "    <li><b>Période de chasse</b> (en général de début septembre à fin février, avec des extensions possibles) : renseignez-vous sur les jours et les lieux de chasse (mairie, fédération départementale, ONF en forêt domaniale). Restez sur les sentiers fréquentés, évitez l'aube et le crépuscule, portez des couleurs vives et faites-vous entendre. Un panneau « chasse en cours » signale une battue : il n'interdit pas le passage mais impose la vigilance ; contournez si possible et signalez-vous à un chasseur. Si des chiens de battue arrivent, arrêtez-vous et attendez qu'ils s'éloignent.</li>\n"
    "    <li><b>Munition ou objet suspect</b> : ne touchez jamais un objet ressemblant à une munition (obus, grenade), même rouillé. Prenez une photo si possible, marquez l'endroit, recouvrez-le délicatement d'herbe ou de terre sans le déplacer, puis éloignez-vous. Appelez le 17 en indiquant le lieu précis, sa description et votre numéro de téléphone.</li>")

# ======================= CHAPITRE 15 =======================
rep("M6", "Ne creusez jamais dans une pente qui peut avalancher.",
    "Ne creusez jamais dans une pente qui peut avalancher. <b>Reconnaître une intoxication au monoxyde de carbone</b> : maux de tête, vertiges, nausées, fatigue ou confusion près d'un feu, d'un réchaud, d'un moteur ou d'un appareil de chauffage. Ces signes ressemblent à une grippe sans fièvre et touchent souvent plusieurs personnes en même temps ; une personne qui dort peut mourir sans avoir ressenti de symptôme. Faites sortir immédiatement tout le monde à l'air libre, sans chercher la source, appelez le 112 (ou le 15 ou le 18), et ne revenez pas sans l'accord des secours.")
ins("M51", "Fixez une <b>heure limite de demi-tour</b>", "list", box(
    "Quatre pensées qui doivent vous alerter",
    "« On l'a déjà fait cent fois. » « On a dit qu'on irait au sommet. » « Il est expérimenté, il sait ce qu'il fait. » « D'autres y vont, donc ça passe. » Ces pensées sont normales, mais des études d'accidents montrent qu'elles poussent les groupes à prendre plus de risques. Quand vous en entendez une, arrêtez-vous et regardez les faits du jour : météo, horaire, état de chacun. Le plus inquiet du groupe a le droit de demander le demi-tour."))

# ======================= CHAPITRE 16 =======================
ins("M18", "<h3>Homme à la mer (depuis un bateau)</h3>", "before",
    "  <h3>Marées et pêche à pied</h3>\n"
    "  <p>Avant de vous avancer sur l'estran, renseignez-vous sur les heures de marée du port le plus proche, sur le coefficient (100 ou plus = danger), sur la météo et sur les dangers locaux. Ne partez pas seul, prévenez quelqu'un de votre heure de retour, emportez un téléphone et une montre. La mer remonte très vite et peut arriver de tous côtés, même derrière vous, encercler un banc de sable et vous isoler. Commencez à revenir dès l'heure de la basse mer : le retour est toujours plus long que l'aller. Urgence : 196 ou 112.</p>\n\n")

# ======================= CHAPITRE 17 =======================
ins("M61", "<li><b>Restez près du véhicule</b> en panne", "list",
    "  <p><b>Crème solaire :</b> sur la peau non couverte, appliquez généreusement une crème solaire « large spectre » (UVA et UVB), indice 15 au minimum. Renouvelez au moins toutes les 2 heures, et plus souvent si vous transpirez ou vous baignez. Les nuages laissent passer une grande partie des UV, et aucune crème ne bloque tout : gardez chapeau, vêtements et ombre. Les crèmes en aérosol peuvent s'enflammer : tenez-les loin du feu.</p>")

# ======================= CHAPITRE 18 =======================
ins("M60", "<li>Mangez gras et sucré, buvez chaud", "li",
    "    <li>Au froid aussi, continuez à boire régulièrement, de préférence des boissons tièdes ou chaudes, sans alcool : l'alcool ne réchauffe pas.</li>")

# ======================= CHAPITRE 20 =======================
ins("M68", "<li>En France, l'alerte <b>FR-Alert</b>", "li",
    "    <li><b>Au signal d'alerte</b>, rejoignez le bâtiment le plus proche : ne restez ni dehors ni dans votre voiture. Fermez portes, fenêtres et volets ; si vous le pouvez, arrêtez la ventilation et le chauffage. N'évacuez que sur consigne des autorités. La fin de l'alerte est annoncée par un son continu de 30 secondes : restez à l'abri jusque-là.</li>")
ins("M70", "<li>Radio à piles : les stations locales du service public", "li",
    "    <li>Fiez-vous aux sources officielles et méfiez-vous des rumeurs. Écoutez les consignes à heures fixes plutôt qu'en continu : voir et revoir les mêmes images entretient la peur. Éloignez les enfants des reportages et des vidéos de l'événement. Entre deux points d'information, occupez-vous avec des tâches utiles ou une activité qui vous fait du bien.</li>")
ins("M32-M33-M34", "Adaptez les réserves aux enfants, aux personnes dépendantes et aux animaux.", "block",
    "  <p><b>Constituer et renouveler la réserve d'eau.</b> Le plus simple et le plus sûr : de l'eau en bouteille du commerce, non ouverte, renouvelée avant sa date limite. Si vous remplissez vous-même des contenants : utilisez des récipients alimentaires propres, solides et bien fermés, jamais un bidon ayant contenu Javel, carburant ou pesticide. Lavez-les au savon et rincez avant de les remplir. Notez « eau de boisson » et la date, rangez-les au frais, à l'abri de la lumière et loin des produits toxiques, et renouvelez l'eau tous les 6 mois. Pour vous servir, utilisez un ustensile propre, jamais les mains.</p>\n"
    "  <p><b>Réserves d'eau cachées.</b> Sans réserve, il reste souvent de l'eau utilisable à la maison : le ballon d'eau chaude sanitaire (celui qui alimente robinets et douche, pas le circuit des radiateurs ; pour le vider sans danger, suivez sa notice) ; les glaçons faits avec une eau saine ; le réservoir de la chasse d'eau (pas la cuvette), seulement si l'eau est claire et sans produit colorant ou désinfectant ; le jus des conserves de fruits et légumes. Ne buvez pas l'eau des radiateurs ni du circuit de chauffage. L'eau de piscine ou de spa sert à l'hygiène et au ménage, pas à boire. Suivez les consignes des autorités, qui peuvent demander de fermer le robinet général.</p>\n"
    "  <p><b>Nourrisson.</b> Le lait infantile liquide prêt à l'emploi est le plus sûr en crise, car il ne demande pas d'eau ; gardez-en dans le kit. Sinon, préparez le lait en poudre avec de l'eau en bouteille tant que les autorités n'ont pas déclaré l'eau du robinet potable (à défaut, une eau bouillie puis refroidie). Respectez exactement les doses de la boîte. Sans moyen de bien laver les biberons, donnez le lait dans un gobelet jetable propre. Ne fabriquez jamais de lait « maison ». L'allaitement se poursuit normalement.</p>")
ins("M63", "<li><b>Jamais</b> de groupe électrogène", "li",
    "    <li>Un <b>détecteur de monoxyde de carbone</b> à piles, installé près des chambres, peut donner l'alerte avant que vous ne ressentiez des symptômes. Il complète l'entretien des appareils et l'aération, il ne les remplace pas. S'il sonne : sortez tout le monde à l'air libre, appelez les secours et ne rentrez pas sans leur accord. Remplacez-le selon la notice. Signes d'intoxication : voir chapitre 15.</li>")
ins("M12", "<li>N'allez pas chercher les enfants à l'école", "li",
    "    <li><b>Eau du robinet :</b> après une inondation, ne la buvez pas tant que la mairie ou le distributeur d'eau n'a pas confirmé qu'elle est potable. En attendant, buvez de l'eau en bouteille dont le bouchon est resté scellé, aussi pour préparer les repas et vous brosser les dents. Ne consommez pas une bouteille ou une conserve restée dans l'eau de crue. L'eau d'un puits inondé n'est pas potable : demandez conseil à la mairie avant de la réutiliser. Lavez-vous les mains au savon après tout contact avec l'eau de crue.</li>\n"
    "    <li>Ne descendez pas dans les sous-sols ni les parkings souterrains inondés. Faites vérifier l'électricité et le chauffage par un professionnel avant de les remettre en marche. N'utilisez pas de nettoyeur ou de pompe à moteur thermique dans la maison (monoxyde de carbone).</li>")
ins("M62", "<h3>Séisme</h3>", "before",
    "  <h3>Canicule</h3>\n"
    "  <p>Fermez volets et fenêtres côté soleil pendant la journée, et ouvrez en grand la nuit dès que l'air extérieur est plus frais. Mouillez-vous le corps, buvez régulièrement, évitez l'alcool et les efforts, et passez quelques heures dans un lieu frais si votre logement chauffe trop. Prenez des nouvelles des personnes fragiles. En cas de malaise, appelez le 15.</p>\n\n")

# ======================= CHAPITRE 21 =======================
ins("M71", "Concentrez-vous sur ce que vous pouvez faire maintenant", "block",
    "  <p class=\"small\">La nuit, l'obscurité et les bruits peuvent faire peur : c'est fréquent. Installez-vous avant la nuit et posez à portée de main la lampe, le sifflet et le téléphone. Ne vous déplacez pas dans l'obscurité : attendez le jour pour réévaluer. Si vous vous réveillez inquiet, reprenez un point d'appui simple (sentir le sol, nommer ce qui vous entoure, voir chapitre 1). Gardez la lampe pour signaler et pour les vrais besoins.</p>")

# ======================= CHAPITRE 22 =======================
ins("M17", "Le « triangle de sang » : l'intérieur des cuisses", "figure",
    "  <p><b>Règles de base.</b> Avant d'ouvrir la lame, tendez le bras et tournez sur vous-même : personne ni rien ne doit se trouver à portée de la lame. Si quelqu'un s'approche, arrêtez-vous. Asseyez-vous sur un appui stable, les coudes sur les genoux, et travaillez devant vous ou sur le côté, loin des cuisses. Coupez toujours en éloignant la lame de vous, et gardez la main qui tient le bois derrière le tranchant. Ne travaillez pas fatigué ni dans la pénombre, et gardez la trousse de secours à portée. Après chaque usage, refermez ou rengainez la lame ; pour la passer à quelqu'un, fermez-la ou rengainez-la d'abord, puis tendez le manche. En cas de coupure, appuyez sur la plaie et voyez le chapitre 8.</p>")
ins("M64", "tranchant à la traîne, afin de ne pas couper le cuir.</figcaption>", "figure",
    "  <p><b>Entretenir ses outils.</b> Après usage, et surtout après la pluie, la sève ou des aliments, nettoyez la lame. Pour un couteau suisse, ouvrez et fermez les outils dans de l'eau tiède jusqu'à ce qu'ils bougent librement. Séchez tout complètement, puis mettez une petite goutte d'huile prévue pour couteaux et compatible avec les aliments sur les articulations. Pas de lave-vaisselle, et pas de trempage prolongé pour un manche en bois. Une tache sombre sur l'acier est un début de rouille : nettoyez et huilez. Rangez l'outil sec et fermé.</p>")
ins("M66", "<tr><td><b>Hachette</b></td>", "block",
    "  <p><b>Scier sans se blesser :</b> posez la pièce contre un appui dur et gardez la main qui la tient bien loin de la lame, surtout au début de la coupe, quand la lame peut sauter. Un gant de travail sur cette main protège des échardes et des petites entailles. Si vous bloquez le bois avec le pied, portez des chaussures fermées qui couvrent les orteils. Un gant ne remplace pas la bonne position : il réduit les petites blessures, il n'empêche pas une coupure grave.</p>")
rep("M43", "vérifiez les règles du lieu, des transports et du pays avant le départ.",
    "vérifiez les règles du lieu, des transports et du pays avant le départ. Transportez un couteau pliant fermé et un couteau à lame fixe toujours dans son étui, dans une pochette au milieu du sac, pas dans une poche où vous mettez la main sans regarder. À la ceinture, dans son étui, la lame pointe vers le bas. Faites de même pour la scie (lame repliée) et la hachette (protège-lame). À la maison, rangez les lames propres, sèches, fermées et hors de portée des jeunes enfants.")

# ======================= CHAPITRE 23 (fiche 10) =======================
ins("M12f", "<li>SMS aux proches plutôt qu'appels, point de rendez-vous familial ; secours : 112.</li>", "li",
    "        <li>Je ne bois l'eau du robinet que si la mairie la déclare potable ; sinon, eau en bouteille scellée.</li>")

# ======================= CHAPITRE 24 =======================
ins("M67a", "<li>Fabriquer du coton-vaseline ; tissu charbonné", "li",
    "    <li>Faire vérifier par une personne compétente le cercle de sécurité, la position assise et le passage d'une lame fermée ou rengainée (chapitre 22).</li>\n    <li>Nettoyer, sécher et huiler son couteau.</li>")
ins("M67b", "<li>Construire un appentis stable, fixations montrées", "li",
    "    <li>Monter une bâche sur une ligne de faîtage et la retendre (chapitre 12).</li>\n    <li>Réaliser un brêlage carré et le tester à la main.</li>")

# ======================= CHAPITRE 25 =======================
rep("M2c", "<li>Itinéraire + heure de retour laissés à un proche</li>",
    "<li>Plan de sortie écrit laissé à un proche, avec heure limite d'alerte convenue</li>")
ins("M45c", "<li>Météo et heure de coucher du soleil vérifiées</li>", "li",
    "    <li>Vigilance Météo-France et Vigicrues vérifiées ; accès aux massifs autorisé (été)</li>\n"
    "    <li>Enfants : consigne « serre un arbre » apprise, sifflet et vêtement voyant</li>")
ins("M61c", "<li>Kit de survie + mini-trousse de secours</li>", "li",
    "    <li>Crème solaire, lunettes de soleil, chapeau</li>\n    <li>Zone sans réseau : balise PLB enregistrée</li>")
rep("M9", "<tr><th>Centre antipoison</th><td>Numéro du centre antipoison de votre région, à relever avant le départ (annuaire officiel des centres antipoison) ; détresse vitale : 15 ou 112 (France)</td></tr>",
    "<tr><th>Centres antipoison</th><td>France, 24 h/24, 7 j/7 : Angers 02 41 48 21 21 · Bordeaux 05 56 96 40 80 · Lille 0 800 59 59 59 · Lyon 04 72 11 69 11 · Marseille 04 91 75 25 25 · Nancy 03 83 22 50 50 · Paris 01 40 05 48 48 · Toulouse 05 61 77 74 47. N'attendez pas les symptômes pour appeler. Personne inconsciente ou qui respire mal : 15 ou 112.</td></tr>")
rep("M54", "N'attendez pas un mois pour demander de l'aide si vous allez mal.",
    "N'attendez pas un mois pour demander de l'aide si vous allez mal. <b>Vers qui se tourner :</b> votre médecin traitant, qui peut vous orienter. Après une catastrophe, une cellule d'urgence médico-psychologique (CUMP) est souvent mise en place : en cas d'urgence, appelez le 15. Si les difficultés durent plus d'un mois, le centre régional du psychotraumatisme de votre région peut vous accompagner. Il n'est jamais trop tard pour demander de l'aide, même des années après.")
ins("M52", "<b>Vers qui se tourner :</b> votre médecin traitant", "block", box(
    "Après le retour, pour les enfants",
    "Un enfant peut redevenir « plus petit » (pipi au lit, besoin d'être porté), avoir peur d'être séparé de vous, faire des colères ou des cauchemars. Ces réactions disparaissent souvent avec le temps. Répondez à ses questions simplement et avec des mots vrais, laissez-le en parler ou dessiner s'il le souhaite, sans l'y obliger. Reprenez vite les habitudes (repas, coucher, école) et évitez-lui les images de l'événement. Parlez-en au médecin si la peur, la tristesse ou la colère durent plus de deux à quatre semaines, s'aggravent ou gênent sa vie à l'école ou en famille."))

# Glossaire (M72) : section avant les crédits
ins("M72", '<section class="page credits" id="credits">', "before",
    '<section class="page" id="glossaire">\n  <h2>Petit glossaire</h2>\n  <table>\n'
    '    <tr><th>AML</th><td>Localisation automatique d\'un smartphone lors d\'un appel d\'urgence (ch. 7)</td></tr>\n'
    '    <tr><th>BERA</th><td>Bulletin d\'estimation du risque d\'avalanche (ch. 15)</td></tr>\n'
    '    <tr><th>CROSS</th><td>Centres de secours en mer, joignables au 196 (ch. 16)</td></tr>\n'
    '    <tr><th>CUMP</th><td>Cellule d\'urgence médico-psychologique (ch. 8 et 25)</td></tr>\n'
    '    <tr><th>DAE</th><td>Défibrillateur automatisé externe (ch. 8)</td></tr>\n'
    '    <tr><th>DVA</th><td>Détecteur de victimes d\'avalanche, à utiliser avec pelle et sonde (ch. 15)</td></tr>\n'
    '    <tr><th>FR-Alert</th><td>Alerte officielle diffusée sur les téléphones (ch. 20)</td></tr>\n'
    '    <tr><th>PLB</th><td>Balise personnelle de détresse, 406 MHz (ch. 7)</td></tr>\n'
    '    <tr><th>PLS</th><td>Position latérale de sécurité (ch. 8)</td></tr>\n'
    '    <tr><th>PSC1</th><td>Formation de base aux premiers secours (ch. 8)</td></tr>\n'
    '    <tr><th>RTN PSC</th><td>Référentiel technique national des premiers secours citoyens (ch. 8)</td></tr>\n'
    '    <tr><th>SRO</th><td>Solution de réhydratation orale (ch. 8)</td></tr>\n'
    '  </table>\n</section>\n\n')
rep("M72s", '<p style="margin:.2em 0 0"><a href="#credits">Crédits photographiques</a></p>',
    '<p style="margin:.2em 0 0"><a href="#glossaire">Petit glossaire</a> · <a href="#credits">Crédits photographiques</a></p>')

# Couverture
rep("ver", "Version 1.1 — 9 novembre 2026 ·", "Version 1.2 — 9 novembre 2026 ·")

if errors:
    print("ÉCHECS :", *errors, sep="\n - ")
    sys.exit(1)
open(p, "w", encoding="utf-8").write(s)
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(f"{t}\t{len(h)}" for t, h in ADDED))
print(f"OK : {len(ADDED)} opérations")
