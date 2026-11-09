"""Pictogrammes des fiches réflexes et des check-lists (SVG en ligne, couleurs du thème, mode sombre compris)."""

S = 'fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"'
P = {
    # 1 · perdu : boussole
    "perdu": f'<circle cx="24" cy="24" r="18" {S}/><path d="M24 10 L29 24 L24 38 L19 24 Z" {S}/><circle cx="24" cy="24" r="2.5" fill="currentColor"/>',
    # 2 · nuit dehors : lune et abri
    "nuit": f'<path d="M30 6a10 10 0 1 0 10 13a8 8 0 0 1-10-13z" {S}/><path d="M6 42 L20 22 L34 42 Z M20 22 V42" {S}/>',
    # 3 · adulte inconscient : personne allongée et cœur
    "inconscient": f'<circle cx="9" cy="34" r="4" {S}/><path d="M14 35 H42 M20 35 L24 42 M32 35 L36 42" {S}/><path d="M30 20c-3-5-11-2-7 4l7 6 7-6c4-6-4-9-7-4z" {S}/>',
    # 3 bis · enfant : petit personnage et cœur
    "enfant": f'<circle cx="16" cy="13" r="5" {S}/><path d="M16 18 V32 M10 24 H22 M16 32 L11 42 M16 32 L21 42" {S}/><path d="M35 22c-3-5-11-2-7 4l7 6 7-6c4-6-4-9-7-4z" {S}/>',
    # 3 ter · malaise : cœur et tracé
    "malaise": f'<path d="M24 14c-5-8-19-4-12 7l12 11 12-11c7-11-7-15-12-7z" {S}/><path d="M4 42 H16 L20 34 L25 46 L29 38 H44" {S}/>',
    # 4 · saignement : goutte et main qui appuie
    "saignement": f'<path d="M24 5 C18 15 12 21 12 28 a12 12 0 0 0 24 0 C36 21 30 15 24 5 z" {S}/><path d="M18 30 H30" {S}/>',
    # 5 · eau froide : tête hors de l'eau, vagues
    "eau-froide": f'<circle cx="24" cy="16" r="7" {S}/><path d="M4 30 q5 -5 10 0 t10 0 t10 0 t10 0 M4 40 q5 -5 10 0 t10 0 t10 0 t10 0" {S}/>',
    # 6 · glace : surface fissurée
    "glace": f'<path d="M4 18 H44 M10 18 L18 28 L14 36 M18 28 L28 30 L34 40 M28 30 L36 22" {S}/><path d="M22 6 l2 4 l2-4 M24 10 V14" {S}/>',
    # 7 · orage : nuage et éclair
    "orage": f'<path d="M12 26 a8 8 0 0 1 2-15 a10 10 0 0 1 19 2 a7 7 0 0 1 3 13 z" {S}/><path d="M24 26 L18 36 H26 L21 46" {S}/>',
    # 8 · voiture dans la neige
    "voiture": f'<path d="M6 34 V26 L12 18 H34 L40 26 V34 Z M6 26 H40" {S}/><circle cx="14" cy="36" r="3.5" {S}/><circle cx="32" cy="36" r="3.5" {S}/><path d="M24 4 V14 M19 6.5 L29 11.5 M29 6.5 L19 11.5" {S}/>',
    # 9 · coup de chaleur : soleil et thermomètre
    "chaleur": f'<circle cx="16" cy="16" r="6" {S}/><path d="M16 3 V6 M16 26 V29 M3 16 H6 M26 16 H29 M7 7 L9 9 M23 23 L25 25 M7 25 L9 23 M23 9 L25 7" {S}/><path d="M36 10 V32 a5 5 0 1 0 4 0 V10 a2 2 0 0 0 -4 0 z" {S}/>',
    # 10 · catastrophe à la maison : maison fissurée
    "maison": f'<path d="M6 22 L24 6 L42 22 M10 19 V42 H38 V19" {S}/><path d="M26 10 L22 20 L28 26 L23 34 L26 42" {S}/>',
    # check-lists : sac à dos
    "sac": f'<path d="M14 14 a10 10 0 0 1 20 0 V42 H14 Z M18 10 a6 6 0 0 1 12 0 M14 26 H34 M20 26 V32 H28 V26" {S}/>',
    # check-lists : liste cochée
    "liste": f'<path d="M8 10 l3 3 l5-6 M8 24 l3 3 l5-6 M8 38 l3 3 l5-6 M22 10 H42 M22 24 H42 M22 38 H42" {S}/>',
}


def svg(name, label, cls="picto"):
    return (f'<svg class="{cls}" viewBox="0 0 48 48" role="img" aria-label="{label}">'
            f'<title>{label}</title>{P[name]}</svg>')
