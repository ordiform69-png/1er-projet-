"""Version 1.7 — relecture spécialisée faite par l'auteur (premiers secours : ch. 8 et fiches, comparés au RTN PSC
de juillet 2026 ; plantes : ch. 9, 10 et 19). Ne remplace pas la relecture par un formateur PSC ou un médecin,
ni par un botaniste.
Usage : python3 corrections-v17.py source/livret-corps.html
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


# ===== PREMIERS SECOURS (RTN PSC, juillet 2026) =====
# M1 — Convulsions : des mouvements saccadés peuvent survenir au début d'un arrêt cardiaque (RTN, fiche Arrêt cardiaque)
rep("M1-CONVULSIONS", "Dès que les secousses s'arrêtent, mettez-la sur le côté (PLS), restez avec elle et surveillez sa respiration.",
    "Dès que les secousses s'arrêtent, vérifiez qu'elle respire normalement : si oui, mettez-la sur le côté (PLS), restez avec elle et surveillez sa respiration ; si elle ne respire pas ou respire anormalement, c'est un arrêt cardiaque (encadré ci-dessus, fiche 3). De brefs mouvements saccadés peuvent en effet survenir au début d'un arrêt cardiaque.")
# M2 — Saignement : couvrir, surveiller, pansement compressif, précautions vis-à-vis du sang (RTN, Hémorragies)
rep("M2-SAIGNEMENT", "<li>Allongez la victime, alertez les secours.</li>",
    "<li>Allongez la victime, alertez les secours. Couvrez-la (le froid aggrave son état), parlez-lui et surveillez l'apparition de sueurs, d'une pâleur, d'une sensation de froid ou d'une perte de connaissance : alertez de nouveau si son état s'aggrave. Si le saignement est arrêté et que vous avez besoin de vos mains, remplacez la main par un pansement serré (tissu propre plié, maintenu par un bandage). Protégez votre main si possible (gants, sac plastique), sans retarder la compression ; après coup, lavez-vous les mains et ne portez rien à la bouche, au nez ou aux yeux.</li>")
rep("M2-FICHE4", "<li>J'allonge la victime.</li>", "<li>J'allonge la victime et je la couvre.</li>")
# M3 — Brûlure : critère de gravité du RTN
rep("M3-BRULURE", "Pour une brûlure profonde, étendue, circulaire, située au visage, au cou, aux mains ou sur une articulation,",
    "Pour une brûlure grave — cloque plus grande que la moitié de la paume de la main de la victime, brûlure profonde (blanchâtre ou noirâtre), circulaire, située au visage, au cou, aux mains, sur une articulation ou près des orifices naturels, rougeur étendue chez un enfant —")
# M4 — Entorse, fracture : le RTN demande de ne pas mobiliser ; l'attelle n'est qu'un recours sans secours possible
rep("M4-FRACTURE", "<li>Ne pas bouger la zone. Immobiliser dans la position trouvée avec une attelle improvisée (bâtons, carton, sac de couchage roulé) attachée au-dessus et en dessous de la blessure.</li>\n    <li>Vérifier que les doigts / orteils restent chauds et colorés : ne pas serrer trop.</li>",
    "<li>Demandez fermement à la personne de ne pas bouger la partie blessée ; ne la déplacez pas. Membre déformé : ne tentez jamais de le remettre droit. Couvrez-la, alertez le 15 ou le 112 et surveillez-la.</li>\n    <li>Seulement si aucun secours ne peut venir et qu'un déplacement est inévitable : immobilisez dans la position trouvée avec une attelle improvisée (bâtons, carton, sac de couchage roulé) attachée au-dessus et en dessous de la blessure, sans serrer ; vérifiez que les doigts ou orteils restent chauds et colorés.</li>")
# M5 — Partie du corps arrachée : pansement compressif même sans saignement (RTN, Plaies)
rep("M5-ARRACHEMENT", "<b>Doigt ou autre partie du corps arrachée</b> : arrêtez d'abord le saignement.",
    "<b>Doigt ou autre partie du corps arrachée</b> : arrêtez d'abord le saignement, puis posez un pansement serré sur la plaie, même si elle ne saigne plus.")
# M6 — Arrêt cardiaque de l'adulte : sur le dos ; applications citoyennes citées par le RTN
rep("M6-ARRET", "Commencez les compressions au centre du thorax :",
    "Allongez-la sur le dos, sur un sol dur, et commencez les compressions au centre du thorax :")
rep("M6-APPLI", "Dès que le défibrillateur est disponible, allumez-le et suivez ses instructions, en limitant les interruptions.",
    "Dès que le défibrillateur est disponible, allumez-le et suivez ses instructions, en limitant les interruptions. Le régulateur peut vous guider au téléphone. Une application de « bon Samaritain » (par exemple Staying Alive ou SAUV Life) permet d'être alerté quand quelqu'un fait un arrêt cardiaque près de vous.")

# ===== PLANTES (ch. 9, 10) =====
rep("B1-CHATAIGNE", "<td>Mûres, framboises, noisettes, châtaignes.", "<td>Mûres, framboises, noisettes, châtaignes (à ne pas confondre avec le marron d'Inde, toxique : voir chapitre 10).")
rep("B2-SOSIES", "<tr><td><b>Muguet, colchique, arum</b></td><td>Confondus avec l'ail des ours. Toxiques pour le cœur ou mortels.</td></tr>",
    "<tr><td><b>Muguet, colchique, arum</b></td><td>Confondus avec l'ail des ours. Le muguet est toxique pour le cœur, le colchique peut être mortel, l'arum brûle la bouche et la gorge.</td></tr>")
rep("B3-AIL", "<td>Feuilles cuites : il pousse en milieu humide (règle 3). <b>Voir sosies mortels !</b></td>",
    "<td>Feuilles cuites : il pousse en milieu humide (règle 3). Cueillez feuille par feuille en vérifiant l'odeur de chacune (l'odeur reste sur les mains). <b>Voir sosies mortels !</b></td>")
rep("B4-LAURIER", "    <tr><td><b>Champignons</b></td>",
    "    <tr><td><b>Laurier-rose</b></td><td>Arbuste de jardin très courant dans le Midi, toxique pour le cœur dans toutes ses parties. N'en taillez jamais de brochette ni d'ustensile : pour cuire, utilisez seulement un bois que vous connaissez avec certitude.</td></tr>\n    <tr><td><b>Champignons</b></td>")

# Couverture et mentions
rep("COUV", "Version 1.6 — 10 novembre 2026", "Version 1.7 — 10 novembre 2026")
rep("MENTIONS", "<b>Petit guide de survie</b> — version 1.6, 10 novembre 2026.", "<b>Petit guide de survie</b> — version 1.7, 10 novembre 2026.")

open(path, "w", encoding="utf-8").write(h)
print(len(log), "opérations :", ", ".join(log))
