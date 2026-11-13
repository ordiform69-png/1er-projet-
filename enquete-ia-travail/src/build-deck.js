// Génère le PowerPoint « IA et robotique : la France est-elle prête… »
// Usage : NODE_PATH=<node_modules contenant pptxgenjs> node build-deck.js <sortie.pptx>
const pptxgen = require("pptxgenjs");
const path = require("path");

const OUT = process.argv[2] || path.join(__dirname, "..", "IA-robotique-travail-France.pptx");
const SKILL = process.env.PPTX_SKILL_DIR;

const THEME = {
  name: "Enquete IA Travail",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B1F24", lt1: "FFFFFF", dk2: "2B3440", lt2: "EEF1F4",
    accent1: "D9482B", // signal : risques, annonces
    accent2: "1F7A72", // vérifié / opportunités
    accent3: "B8860B", // projection
    accent4: "5B6B7F", // neutre
    accent5: "8E3B46", // bordeaux
    accent6: "9AA5B1",
    hlink: "1F7A72", folHlink: "5B6B7F",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13,333 x 7,5 in
pres.title = "IA et robotique : la France est-elle prête à la fin du travail tel que nous le connaissons ?";
pres.subject = "Enquête prospective — novembre 2026";
pres.author = "Cellule de recherche prospective (dossier citoyen)";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const W = 13.333, M = 0.6, CW = W - 2 * M;

// ---------- Layouts ----------
pres.defineSlideMaster({
  title: "COUVERTURE",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 1.7, w: 11.6, h: 2.4, fontFace: "Cambria", fontSize: 40, bold: true, color: C.background1, valign: "top", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.25, w: 10.5, h: 1.2, fontFace: "Calibri", fontSize: 20, color: "C9D1D9", valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENU",
  background: { color: C.background1 },
  margin: [0.5, 0.6, 0.9, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.35, w: CW, h: 1.05, fontFace: "Cambria", fontSize: 28, bold: true, color: C.text1, valign: "middle", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "source", type: "body", x: M, y: 6.82, w: 11.2, h: 0.5, fontFace: "Calibri", fontSize: 9, color: C.accent4, valign: "top", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 12.25, y: 6.9, w: 0.5, h: 0.3, fontFace: "Calibri", fontSize: 10, color: C.accent4, align: "right" },
});
pres.defineSlideMaster({
  title: "SOMBRE",
  background: { color: C.text1 },
  margin: [0.5, 0.6, 0.9, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.35, w: CW, h: 1.05, fontFace: "Cambria", fontSize: 28, bold: true, color: C.background1, valign: "middle", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "source", type: "body", x: M, y: 6.82, w: 11.2, h: 0.5, fontFace: "Calibri", fontSize: 9, color: "AEB7C2", valign: "top", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 12.25, y: 6.9, w: 0.5, h: 0.3, fontFace: "Calibri", fontSize: 10, color: "AEB7C2", align: "right" },
});

// ---------- Helpers ----------
let section = "";
function sec(t) { section = t; pres.addSection({ title: t }); }
function slide(title, source, opts = {}) {
  const s = pres.addSlide({ masterName: opts.dark ? "SOMBRE" : "CONTENU", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  if (source) s.addText(source, { placeholder: "source" });
  return s;
}
const BADGES = {
  fait: { t: "FAIT VÉRIFIÉ", c: C.accent2 },
  mesure: { t: "MESURE", c: C.accent2 },
  proj: { t: "PROJECTION", c: C.accent3 },
  annonce: { t: "ANNONCE", c: C.accent1 },
  incertain: { t: "INCERTAIN", c: C.accent4 },
  interne: { t: "DOC. INTERNE", c: C.accent5 },
  illus: { t: "ILLUSTRATIF", c: C.accent4 },
};
function badge(s, kind, x, y, w = 1.35) {
  const b = BADGES[kind];
  s.addText(b.t, { x, y, w, h: 0.26, shape: pres.ShapeType.roundRect, rectRadius: 0.13, fill: { color: b.c }, color: C.background1, fontSize: 9, bold: true, align: "center", valign: "middle", margin: 0, charSpacing: 1, isTextBox: true, objectName: "badge-" + kind });
}
function card(s, x, y, w, h, fill = C.background2) {
  s.addShape(pres.ShapeType.rect, { x, y, w, h, fill: { color: fill }, line: { color: fill, width: 0 } });
}
function txt(s, text, o) {
  s.addText(text, Object.assign({ isTextBox: true, margin: 0, fontSize: 14, color: C.text1, valign: "top", paraSpaceAfter: 4 }, o));
}
function bullets(arr) {
  return arr.map((t, i) => {
    const runs = typeof t === "string" ? { text: t } : t;
    return Object.assign({}, runs, { options: Object.assign({ bullet: { indent: 14 }, breakLine: i < arr.length - 1 }, runs.options || {}) });
  });
}
function bigStat(s, x, y, w, num, label, color = C.accent1, numSize = 36, b) {
  if (b) badge(s, b, x, y);
  txt(s, num, { x, y: y + 0.28, w, h: 0.62, fontSize: numSize, bold: true, color, fontFace: "Cambria", valign: "bottom" });
  txt(s, label, { x, y: y + 0.95, w, h: 0.72, fontSize: 13, color: C.text2 });
}
const chartBase = (extra) => Object.assign({
  catAxisLabelColor: "2B3440", valAxisLabelColor: "5B6B7F", catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
  catAxisLabelFontSize: 12, valAxisLabelFontSize: 11, dataLabelFontFace: "+mn-lt", dataLabelFontSize: 13, dataLabelColor: "1B1F24",
  valGridLine: { color: "D9DEE3", size: 0.5 }, catGridLine: { style: "none" }, showLegend: false,
  titleFontFace: "+mn-lt", titleFontSize: 13, titleColor: "2B3440", showTitle: true,
}, extra);
function arrow(s, x1, y1, x2, y2, color = C.accent4) {
  s.addShape(pres.ShapeType.line, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001, flipH: x2 < x1, flipV: y2 < y1, line: { color, width: 1.75, endArrowType: "triangle" } });
}

// =========================================================
// 1. COUVERTURE
sec("Ouverture");
{
  const s = pres.addSlide({ masterName: "COUVERTURE", sectionTitle: section });
  txt(s, "ENQUÊTE PROSPECTIVE · DOSSIER DOCUMENTÉ · 13 NOVEMBRE 2026", { x: M, y: 0.8, w: 11, h: 0.4, fontSize: 13, bold: true, color: C.accent1, charSpacing: 2 });
  s.addText("IA et robotique : la France est-elle prête à la fin du travail tel que nous le connaissons ?", { placeholder: "title" });
  s.addText("Enquête sur l'accélération technologique, ses conséquences économiques et les réponses politiques à préparer avant et après 2027", { placeholder: "body" });
  txt(s, "La question centrale", { x: M, y: 5.55, w: 5, h: 0.35, fontSize: 13, bold: true, color: "C9D1D9" });
  txt(s, "« Nous investissons massivement pour construire des machines capables de remplacer une partie croissante du travail humain. Préparons-nous avec la même ambition une société capable de fonctionner lorsque ce travail ne sera plus nécessaire dans les mêmes proportions ? »", { x: M, y: 5.9, w: 11.6, h: 0.9, fontSize: 15, italic: true, color: C.background1 });
  s.addNotes("Dossier non partisan destiné aux journalistes, parlementaires, élus, décideurs et chercheurs. Chaque affirmation chiffrée est reliée à une source datée (pied de page et annexes A1 à A4). Code couleur des étiquettes : vert = fait ou mesure vérifiée ; ocre = projection d'institution ou de chercheurs ; rouge = annonce d'entreprise ou de responsable politique non réalisée ; bordeaux = document interne rapporté par la presse ; gris = incertain ou illustratif.");
}

// 2. SYNTHÈSE
{
  const s = slide("Cinq conclusions : la transformation est réelle et rapide, mais sa forme française reste à décider",
    "Sources détaillées dans les diapositives suivantes et en annexe. Étiquettes : FAIT VÉRIFIÉ = source primaire consultée ; PROJECTION = estimation d'institution ; INCERTAIN = données insuffisantes.");
  const items = [
    ["1", "Les capacités des IA progressent plus vite que toute technologie récente", "Autonomie mesurée sur tâches logicielles : doublement tous les ~4 à 7 mois (METR). Coût d'usage ÷ 280 en 18 mois (Stanford AI Index).", "fait"],
    ["2", "En France, le premier effet visible est un gel des embauches de jeunes, pas des licenciements massifs", "Embauches en CDI des 21-29 ans : −28 % dans les métiers les plus exposés vs −8 % dans les moins exposés (nov. 2022 → mars 2026, Banque de France).", "mesure"],
    ["3", "La robotique physique avance beaucoup plus lentement que le logiciel", "Humanoïdes : quelques milliers à dizaines de milliers d'unités par an ; robots industriels classiques : 5 millions en service fin 2025 (IFR).", "fait"],
    ["4", "L'impact macroéconomique reste profondément incertain", "Les estimations vont de +0,66 % de productivité en 10 ans (Acemoglu) à un doublement de la croissance (Commission IA) : aucun consensus.", "incertain"],
    ["5", "Le débat de 2027 aborde l'IA, mais presque pas le financement de la protection sociale", "Propositions sur l'investissement, la formation et l'administration ; aucune proposition chiffrée trouvée sur l'assiette des cotisations face à l'automatisation.", "mesure"],
  ];
  items.forEach((it, i) => {
    const y = 1.6 + i * 1.02;
    s.addText(it[0], { x: M, y, w: 0.62, h: 0.62, shape: pres.ShapeType.ellipse, fill: { color: C.text1 }, color: C.background1, fontFace: "Cambria", fontSize: 20, bold: true, align: "center", valign: "middle", margin: 0, isTextBox: true });
    txt(s, it[1], { x: 1.45, y: y - 0.04, w: 9.6, h: 0.4, fontSize: 16, bold: true });
    txt(s, it[2], { x: 1.45, y: y + 0.36, w: 9.6, h: 0.55, fontSize: 13, color: C.text2 });
    badge(s, it[3], 11.35, y + 0.05);
  });
  s.addNotes("Synthèse. 1) METR Time Horizon 1.1 (29/01/2026) : doublement ~7 mois sur 2019-2025, ~4,3 mois après 2023 ; Claude Mythos Preview ≥ 16 h (IC 95 % 8,5-55 h), mesure à la limite de la suite de tests. Stanford HAI AI Index 2025 : 20 $ → 0,07 $ par million de jetons à niveau GPT-3.5 (nov. 2022 → oct. 2024). 2) Banque de France, Bloc-notes Éco n° 463, 8 oct. 2026 (Palladino, Bergeaud, Bertheau, Bunel, Degos) : les auteurs ne concluent pas à une causalité établie. 3) IFR World Robotics 2025 ; Omdia (via presse) ≈13 300 humanoïdes livrés en 2025. 4) Acemoglu, Economic Policy 2025 ; Commission de l'IA, mars 2024. 5) Revue de presse et programmes au 13/11/2026 (Maddyness 05/10/2026, Next.ink 02/10/2026, franceinfo, IFRAP).");
}

// 3. POURQUOI UNE TRANSFORMATION MAJEURE
sec("Technologie");
{
  const s = slide("L'IA a les traits d'une technologie générale — mais l'histoire montre que ses effets économiques prennent du temps",
    "Bresnahan & Trajtenberg (1995), « General purpose technologies », J. of Econometrics ; P. David (1990), « The Dynamo and the Computer », AER P&P ; Eloundou et al. (2024), « GPTs are GPTs », Science ; OIT Working Paper 140 (mai 2025).");
  const cols = [
    ["Machine à vapeur, électricité", "Technologies générales : elles se diffusent dans tous les secteurs et appellent des innovations complémentaires.", "Ce qu'elles ont automatisé : surtout l'énergie et le geste physique.", C.accent4],
    ["Informatique, internet", "Automatisent le calcul et la transmission d'information ; transforment les tâches routinières de bureau.", "Effet productivité visible avec plusieurs décennies de décalage (« paradoxe de Solow »).", C.accent4],
    ["IA générative et agents", "Première technologie générale qui produit du texte, du code, de l'analyse : des tâches cognitives non routinières.", "Associée à la robotique, elle touche à la fois le travail intellectuel et, plus lentement, physique.", C.accent1],
  ];
  cols.forEach((c, i) => {
    const x = M + i * 4.1;
    card(s, x, 1.65, 3.85, 3.55, i === 2 ? "FBE9E4" : C.background2);
    txt(s, c[0], { x: x + 0.25, y: 1.85, w: 3.35, h: 0.5, fontSize: 18, bold: true, fontFace: "Cambria", color: c[3] });
    txt(s, c[1], { x: x + 0.25, y: 2.45, w: 3.35, h: 1.4, fontSize: 14 });
    txt(s, c[2], { x: x + 0.25, y: 3.95, w: 3.35, h: 1.1, fontSize: 13, color: C.text2, italic: true });
  });
  txt(s, [
    { text: "Ce qui est établi : ", options: { bold: true } },
    { text: "selon l'OIT (2025), 1 emploi sur 4 dans le monde comporte des tâches exposées à l'IA générative (34 % dans les pays à revenu élevé), mais seuls 3,3 % sont dans la catégorie d'exposition la plus forte. " },
    { text: "Ce qui ne l'est pas : ", options: { bold: true } },
    { text: "« exposé » ne veut pas dire « remplacé ». La vitesse de diffusion dépend des organisations, du droit et des coûts — pas seulement des capacités." },
  ], { x: M, y: 5.45, w: 10.6, h: 1.2, fontSize: 14 });
  badge(s, "fait", 11.35, 5.5);
  s.addNotes("L'analogie avec l'électricité est utile mais doit être maniée avec prudence : Paul David a montré que l'électrification des usines n'a produit ses gains de productivité qu'après une réorganisation complète, plusieurs décennies après l'invention de la dynamo. La singularité de l'IA est d'automatiser des tâches cognitives (rédaction, code, analyse). L'indice OIT-NASK (Working Paper 140, 20 mai 2025) insiste : la transformation des emplois est l'effet le plus probable, plutôt que leur disparition. Ne pas présenter l'IA comme 'comparable à la roue' : c'est une hypothèse, pas un constat.");
}

// 4. CAPACITÉS
{
  const s = slide("Les capacités mesurées des IA ont progressé d'un facteur considérable depuis 2022, à coût fortement décroissant",
    "METR, « Measuring AI Ability to Complete Long Tasks » (19/03/2025) et « Time Horizon 1.1 » (29/01/2026), metr.org ; Stanford HAI, AI Index 2025, chap. Économie (prix par million de jetons pour un modèle atteignant 64,8 % au MMLU).");
  txt(s, "Durée des tâches logicielles qu'un agent réussit une fois sur deux (« horizon temporel », METR)", { x: M, y: 1.55, w: 7.2, h: 0.5, fontSize: 14, bold: true });
  const pts = [
    ["2023", "GPT-4", "≈ 3,5 minutes"],
    ["début 2025", "Claude 3.7 Sonnet", "≈ 1 heure"],
    ["mars 2026", "Claude Mythos Preview", "≥ 16 heures*"],
  ];
  const tx = M + 1.2, tw = 4.8, ty = 3.05;
  s.addShape(pres.ShapeType.line, { x: tx, y: ty, w: tw, h: 0, line: { color: C.text2, width: 2 } });
  pts.forEach((p, i) => {
    const x = tx + i * (tw / 2);
    s.addShape(pres.ShapeType.ellipse, { x: x - 0.11, y: ty - 0.11, w: 0.22, h: 0.22, fill: { color: i === 2 ? C.accent1 : C.text2 }, line: { color: C.background1, width: 1 } });
    const bx = Math.min(Math.max(x - 0.85, M), M + 7.2 - 1.7);
    txt(s, p[0], { x: bx, y: ty - 0.75, w: 1.7, h: 0.3, fontSize: 12, color: C.accent4, align: "center" });
    txt(s, p[2], { x: bx, y: ty + 0.25, w: 1.7, h: 0.4, fontSize: 15, bold: true, align: "center", color: i === 2 ? C.accent1 : C.text1 });
    txt(s, p[1], { x: bx, y: ty + 0.62, w: 1.7, h: 0.45, fontSize: 11, align: "center", color: C.text2 });
  });
  card(s, M, 4.4, 7.2, 2.2);
  txt(s, bullets([
    "Doublement tous les ~7 mois sur 2019-2025 ; ~4 mois depuis 2023 (révision TH 1.1).",
    "* Estimation METR rapportée par la presse (IC 95 % : 8,5 à 55 h) ; METR juge peu fiables les mesures au-delà de 16 h.",
    "Un horizon de 16 h ne signifie pas 16 h de travail autonome, ni l'automatisation de 16 h d'un emploi.",
  ]), { x: M + 0.2, y: 4.55, w: 6.8, h: 1.95, fontSize: 13 });
  badge(s, "mesure", M + 5.65, 6.25);
  card(s, 8.15, 1.55, 4.58, 4.0, C.background2);
  txt(s, "Prix d'une IA de niveau GPT-3.5 (dollars par million de jetons)", { x: 8.35, y: 1.7, w: 4.2, h: 0.6, fontSize: 13, bold: true, color: C.text2 });
  txt(s, "20 $", { x: 8.35, y: 2.4, w: 4.2, h: 0.8, fontSize: 44, bold: true, fontFace: "Cambria", color: C.text1 });
  txt(s, "novembre 2022", { x: 8.35, y: 3.2, w: 4.2, h: 0.35, fontSize: 13, color: C.text2 });
  txt(s, "0,07 $", { x: 8.35, y: 3.85, w: 4.2, h: 0.8, fontSize: 44, bold: true, fontFace: "Cambria", color: C.accent1 });
  txt(s, "octobre 2024", { x: 8.35, y: 4.65, w: 4.2, h: 0.35, fontSize: 13, color: C.text2 });
  badge(s, "fait", 8.35, 5.1);
  txt(s, "÷ 280 en 18 mois", { x: 8.15, y: 5.6, w: 4.6, h: 0.5, fontSize: 22, bold: true, color: C.accent1, fontFace: "Cambria", align: "center" });
  txt(s, "Selon les tâches, la baisse annuelle varie de ×9 à ×900 (AI Index).", { x: 8.15, y: 6.1, w: 4.6, h: 0.5, fontSize: 12, color: C.text2, align: "center" });
  s.addNotes("Points de la frise vérifiés le 13/11/2026 : GPT-4 (2023) 3,5 min [IC 1,6-6,9] et Claude 3.7 Sonnet 59 min [27-114] selon le tableau du billet TH1.1 de METR (29/01/2026). Mythos Preview : ajouté à la page de suivi METR le 08/05/2026 ; la valeur (≥16 h) figure dans un graphique, et le chiffre texte provient de comptes rendus de presse citant METR. Claude Mythos Preview : évaluation d'un instantané pré-déploiement en mars 2026 publiée le 8 mai 2026 ; ≥16 h, IC 95 % 8,5-55 h. Mises en garde METR (note du 22/01/2026) : tâches logicielles bien spécifiées, notées automatiquement ; ne mesure pas la fiabilité en conditions réelles. Prix : Stanford HAI AI Index 2025 (avril 2025), 20 $ (nov. 2022) → 0,07 $ (oct. 2024, Gemini-1.5-Flash-8B). Distinction : progrès démontrés (benchmarks publics), annonces commerciales (communiqués), performances hypothétiques (extrapolations) — seuls les premiers figurent ici.");
}

// 5. LIMITES
{
  const s = slide("Fiabilité, énergie et organisation freinent encore la conversion de ces capacités en automatisation réelle",
    "AIE, « Energy and AI » (avr. 2025), scénario de base ; METR, note « Clarifying limitations of time horizon » (22/01/2026) ; Klarna : déclarations du PDG (fév. 2024, mai 2025) rapportées par Bloomberg/Entrepreneur ; Insee Première n° 2120 (juil. 2026).");
  s.addChart(pres.ChartType.bar, [{ name: "TWh", labels: ["2024", "2030 (proj.)", "2035 (proj.)"], values: [415, 945, 1200] }], chartBase({
    x: M, y: 1.5, w: 5.4, h: 4.3, barDir: "col", chartColors: ["2B3440", "B8860B", "B8860B"], varyColors: true,
    title: "Consommation électrique mondiale des centres de données (TWh)", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0", valAxisMaxVal: 1400, valAxisLabelFormatCode: "0",
  }));
  txt(s, "2035 : fourchette 700 à 1 700 TWh selon les scénarios AIE. 2024 ≈ 1,5 % de l'électricité mondiale.", { x: M, y: 5.85, w: 5.4, h: 0.6, fontSize: 12, color: C.text2 });
  badge(s, "proj", M + 4.05, 6.35);
  const lim = [
    ["Fiabilité", "Un taux de réussite de 50 % ou 80 % sur des tests ne suffit pas pour des processus où l'erreur coûte cher (droit, santé, finance)."],
    ["Retours en arrière", "Klarna annonçait en 2024 que son assistant faisait le travail de 700 agents ; en 2025, son PDG a reconnu être « allé trop loin » et réembauche des humains."],
    ["Compétences et organisation", "Plus de la moitié des entreprises françaises utilisatrices d'IA disent être limitées par le manque d'expertise (Insee, 2025)."],
    ["Sécurité et droit", "Données sensibles, cybersécurité, responsabilité juridique : autant de verrous qui ralentissent les déploiements."],
  ];
  lim.forEach((l, i) => {
    const y = 1.6 + i * 1.22;
    card(s, 6.45, y, 6.28, 1.08);
    txt(s, l[0], { x: 6.65, y: y + 0.1, w: 5.9, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
    txt(s, l[1], { x: 6.65, y: y + 0.45, w: 5.9, h: 0.6, fontSize: 13 });
  });
  s.addNotes("L'AIE estime 415 TWh en 2024 (≈1,5 % de l'électricité mondiale) et ≈945 TWh en 2030 dans le scénario de base ; ≈1 200 TWh en 2035 avec une fourchette 700-1 700 TWh. États-Unis et Chine ≈80 % de la croissance. Pour la France, l'enjeu est moins la quantité d'électricité (parc nucléaire) que les raccordements et les délais. Klarna : l'entreprise n'a pas abandonné l'IA ; elle revendique un modèle hybride. Ce cas montre que les annonces de substitution peuvent être révisées — il ne prouve pas que la substitution échoue en général.");
}

// 6. ROBOTIQUE
{
  const s = slide("Robotique : les robots industriels classiques comptent davantage aujourd'hui que les humanoïdes",
    "IFR, World Robotics 2025 (25/09/2025) et World Robotics 2026 (24/09/2026) ; Omdia via presse spécialisée (2026) ; Figure AI, « F.02 contributed to the production of 30,000 cars at BMW » ; BMW Group (25/06/2026) ; GXO/Agility (2025-2026) ; Tesla, appel résultats T3 2026 (22/10/2026).");
  bigStat(s, M, 1.5, 3.1, "5 M", "robots industriels en service dans le monde fin 2025 (+9 %) ; plus de 600 000 installés en 2025", C.text1, 36, "fait");
  bigStat(s, M, 3.2, 3.1, "4 500", "robots industriels installés en France en 2025 (−8 % ; 4 900 en 2024)", C.text1, 36, "fait");
  bigStat(s, M, 4.9, 3.1, "≈ 13 000", "humanoïdes livrés dans le monde en 2025, surtout par des fabricants chinois (estimation Omdia)", C.accent3, 36, "proj");
  const rows = [
    [{ text: "Acteur", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }, { text: "Démontré / déployé", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }, { text: "Annoncé (non réalisé)", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }],
    ["Figure AI (États-Unis)", "Figure 02 : 11 mois chez BMW Spartanburg, 90 000 pièces chargées (chiffres de l'entreprise) ; Figure 03 en logistique depuis l'été 2026", "Nombre de robots, cadence et contrats non publiés"],
    ["Agility Robotics", "Digit chez GXO (Géorgie) : 100 000 bacs manipulés (nov. 2025, selon l'entreprise)", "Extension à 2 sites en 2027 ; ≈ 150 unités livrées en 2025"],
    ["Unitree (Chine)", "> 5 500 humanoïdes livrés en 2025 (presse, non audité) ; introduction en bourse à Shanghai", "Usage surtout recherche, éducation, démonstration"],
    ["Tesla Optimus", "« Production initiale » à Fremont annoncée en oct. 2026 ; nombre de robots produits non communiqué", "20 000 / semaine « dans au moins un an » ; livraisons externes fin 2027"],
    ["Boston Dynamics", "Atlas électrique en essais chez Hyundai", "Pas de volumes commerciaux publiés"],
  ];
  s.addTable(rows, { x: 4.0, y: 1.55, w: 8.73, colW: [1.9, 3.85, 2.98], fontSize: 11.5, color: HEX.dk1, fontFace: "Calibri", border: { type: "solid", pt: 0.5, color: "D9DEE3" }, fill: { color: "FFFFFF" }, valign: "middle", margin: 0.06, rowH: [0.38, 0.85, 0.7, 0.7, 0.7, 0.55] });
  txt(s, "Lecture : un bras robotisé ou un convoyeur spécialisé est souvent plus rentable qu'un humanoïde polyvalent. Les volumes d'humanoïdes restent inférieurs de plusieurs ordres de grandeur au parc industriel.", { x: 4.0, y: 5.75, w: 8.73, h: 0.8, fontSize: 13, italic: true, color: C.text2 });
  s.addNotes("Vérifié le 13/11/2026 sur les communiqués IFR : 2024 : 542 000 installations, 4 664 000 en service (+9 %), France 4 900 (−24 %) ; 2025 (World Robotics 2026, 24/09/2026) : plus de 600 000 installations (+11 %), 5 millions en service (+9 %), France près de 4 500 (−8 %), UE-27 : 712 000 en service. Humanoïdes : estimation Omdia (≈13 318 unités en 2025) reprise par la presse spécialisée, non vérifiée à la source ; Unitree > 5 500 (presse). Figure : chiffres auto-déclarés (1 250 h de fonctionnement, 90 000 pièces, 30 000 X3) ; BMW présente l'usage comme un allègement ergonomique, sans réduction d'effectifs annoncée. Boston Dynamics : déploiement commercial non documenté à grande échelle — formulation prudente. Productivité et coût comparés au travail humain : aucune donnée indépendante publiée ; aucun prix de marché d'humanoïde n'a été vérifié.");
}

// 7. MUSK
{
  const s = slide("L'écosystème Musk vise une boucle IA → calcul → robots ; la plupart de ses maillons restent des projets",
    "Tesla, appel résultats T3 2026 (22/10/2026) et vote AG du 06/11/2025 ; SpaceX, document S-1 cité par Electrek (20/05/2026) ; Fortune (22/03/2026) et Automotive World sur Terafab ; presse sur la fusion SpaceX-xAI (fév. 2026).");
  const nodes = [
    { k: "IA (Grok, xAI → SpaceX)", d: "xAI absorbée par SpaceX (fusion, fév. 2026)", b: "fait", x: 0.9, y: 1.65 },
    { k: "Agents « Macrohard »", d: "« Stade très précoce », sans engagement ferme (S-1)", b: "annonce", x: 4.95, y: 1.65 },
    { k: "Puces « Terafab »", d: "Annoncé le 21/03/2026 ; 20-25 Md$ estimés ; pas de calendrier de construction", b: "annonce", x: 9.0, y: 1.65 },
    { k: "Robots Optimus", d: "Production initiale à Fremont ; 20 000/semaine visés « dans au moins un an »", b: "annonce", x: 9.0, y: 4.25 },
    { k: "Productivité, revenus", d: "Aucun gain mesurable publié à ce stade", b: "incertain", x: 4.95, y: 4.25 },
    { k: "Capital, valorisations", d: "Plan de rémunération : objectif 1 million d'Optimus déployés", b: "fait", x: 0.9, y: 4.25 },
  ];
  nodes.forEach((n) => {
    card(s, n.x, n.y, 3.45, 1.75, C.background2);
    txt(s, n.k, { x: n.x + 0.2, y: n.y + 0.15, w: 3.05, h: 0.4, fontSize: 15, bold: true });
    txt(s, n.d, { x: n.x + 0.2, y: n.y + 0.6, w: 3.05, h: 0.75, fontSize: 12, color: C.text2 });
    badge(s, n.b, n.x + 0.2, n.y + 1.38);
  });
  arrow(s, 4.4, 2.5, 4.9, 2.5); arrow(s, 8.45, 2.5, 8.95, 2.5);
  arrow(s, 10.7, 3.45, 10.7, 4.2); arrow(s, 8.95, 5.1, 8.45, 5.1);
  arrow(s, 4.9, 5.1, 4.4, 5.1); arrow(s, 2.6, 4.2, 2.6, 3.45);
  txt(s, [{ text: "Accélérateurs : ", options: { bold: true, color: C.accent2 } }, { text: "capital abondant, intégration verticale, données de flotte.  " }, { text: "Freins : ", options: { bold: true, color: C.accent1 } }, { text: "fabrication de puces (années), fiabilité des robots, conception encore changeante, historique de délais non tenus (ex. conduite autonome)." }],
    { x: M, y: 6.15, w: CW, h: 0.6, fontSize: 13 });
  s.addNotes("Ne pas présenter les objectifs comme acquis. Statut vérifié au 13/11/2026 : (1) xAI absorbée par SpaceX en février 2026 (fusion en actions, montants divergents selon les sources). (2) Macrohard et Terafab décrits par le S-1 de SpaceX comme 'very early stages', sans termes financiers ni engagement contraignant (Electrek, 20/05/2026). (3) Terafab annoncé le 21/03/2026 comme coentreprise Tesla-SpaceX-xAI ; partenariat Intel annoncé le 07/04/2026 selon la presse. (4) Optimus : Tesla déclare une production initiale sur une ligne conçue pour ~1 million d'unités/an ; Musk : 'au moins un an' pour atteindre 20 000/semaine ; puce AI5 vers avril 2027 ; livraisons externes vers fin 2027. Aucun total de robots produits n'est donné dans les passages consultés de la transcription (appel du 21/10/2026). Un article d'Electrek du 12/11/2026 évoque un possible projet de fusion Tesla-SpaceX annoncé en décembre : rapport de presse non vérifié. (5) Plan de rémunération de Musk approuvé par ~75 % des voix exprimées le 06/11/2025, avec parmi les objectifs 1 million d'Optimus déployés. Une affirmation de location de Terafab à un tiers, issue d'un seul message sur X, a été écartée faute de confirmation.");
}

// 8. AMAZON
sec("Études de cas");
{
  const s = slide("Amazon : l'automatisation permet de croître en recrutant moins, sans licenciements massifs en entrepôt",
    "Amazon (30/06/2025) ; New York Times (21/10/2025) et réponse d'Amazon ; AP/Reuters (28/01/2026) ; Amazon France (avr. 2025, mai-juin 2026) ; Amazon (2018-2019) et Phonandroid sur Brétigny-sur-Orge.");
  bigStat(s, M, 1.5, 3.5, "> 1 million", "robots dans les entrepôts Amazon (juil. 2025), pour ≈ 1,5 million de salariés dans le monde", C.text1, 36, "fait");
  bigStat(s, M, 3.2, 3.5, "≈ 30 000", "postes de bureau supprimés (oct. 2025 et janv. 2026)", C.text1, 36, "fait");
  bigStat(s, M, 4.9, 3.5, "600 000", "embauches américaines « évitées » d'ici 2033 selon des documents internes (NYT) ; Amazon conteste", C.accent5, 36, "interne");
  // France box
  card(s, 4.4, 1.55, 8.33, 2.55, C.background2);
  txt(s, "En France", { x: 4.6, y: 1.65, w: 4, h: 0.4, fontSize: 16, bold: true, fontFace: "Cambria" });
  txt(s, bullets([
    "Brétigny-sur-Orge (oct. 2019, 152 000 m²) : 1er site français équipé d'Amazon Robotics ; « plus de 1 000 » CDI annoncés sur trois ans.",
    "Effectifs : plus de 25 000 CDI en France selon Amazon (avril 2025) ; plan de 15 Md€ sur 2026-2028 annoncé en mai 2026.",
    "Aides publiques : aucune subvention spécifique documentée dans les sources consultées — point à instruire, pas à affirmer.",
  ]), { x: 4.6, y: 2.05, w: 7.9, h: 2.0, fontSize: 13 });
  card(s, 4.4, 4.3, 8.33, 2.3, "FBE9E4");
  txt(s, "Ce que montre le cas — et ce qu'il ne montre pas", { x: 4.6, y: 4.4, w: 7.9, h: 0.4, fontSize: 16, bold: true, fontFace: "Cambria", color: C.accent1 });
  txt(s, bullets([
    "Le mécanisme principal est la baisse des besoins d'embauche par unité vendue, pas le licenciement des salariés d'entrepôt.",
    "Amazon a pourtant déclaré vouloir utiliser l'IA générative pour réduire ses effectifs de bureau (A. Jassy, juin 2025), tout en justifiant les 30 000 suppressions par la « bureaucratie ».",
    "Les 600 000 embauches évitées sont une projection d'équipe interne, non un plan officiel ni une observation.",
  ]), { x: 4.6, y: 4.8, w: 7.9, h: 1.75, fontSize: 13 });
  s.addNotes("Robots : communiqué Amazon du 30/06/2025 (vérifié) (1 millionième robot, modèle DeepFleet annoncé comme réduisant de 10 % le temps de trajet de la flotte). Chiffre écarté après vérification : '670 salariés par entrepôt' (WSJ via TechSpot), source inaccessible. NYT (21/10/2025) : documents internes évoquant 160 000 embauches évitées d'ici 2027 et plus de 600 000 d'ici 2033, avec un objectif d'automatiser 75 % des opérations ; Amazon répond que ces documents reflètent le point de vue d'une seule équipe. Suppressions : ≈14 000 postes de bureau (oct. 2025) + ≈16 000 (janv. 2026) ; Andy Jassy avait déclaré en juin 2025 que l'IA générative réduirait les effectifs de bureau 'dans les prochaines années'. France : communiqué Amazon du 22/10/2019 vérifié (152 000 m², « plus de 1 000 » CDI sur trois ans). Le nombre de robots (≈4 000) et l'effectif à l'ouverture, cités par la presse, ne figurent pas dans le communiqué et ont été retirés. 15 Md€ : critiqué par Le Journal des Entreprises comme incluant des dépenses de fonctionnement. Nous n'avons trouvé aucune preuve de détournement d'aides publiques et n'en affirmons aucun.");
}

// 9. COMPARAISONS
{
  const s = slide("Trois autres terrains confirment le schéma : moins d'embauches, plus de productivité, des reculs possibles",
    "Insee, Note de conjoncture, éclairage du 24/03/2026 ; Brynjolfsson, Li & Raymond, « Generative AI at Work » (NBER w31161 ; QJE 2025) ; Klarna (2024-2025) ; BMW Group / Figure AI (2025-2026).");
  const cases = [
    ["Services informatiques en France", "L'emploi de l'information-communication recule de 3,0 % entre fin 2023 et fin 2025, baisse « entièrement portée » par les 15-29 ans, tandis que la valeur ajoutée reste orientée à la hausse.", "Insee, mars 2026", "mesure"],
    ["Service client (États-Unis)", "5 179 téléconseillers : l'assistant IA augmente de 14 % les dossiers résolus par heure, surtout pour les débutants. Klarna, qui avait remplacé 700 agents, a partiellement fait machine arrière.", "NBER / Klarna", "fait"],
    ["Industrie automobile", "Chez BMW (États-Unis), l'humanoïde Figure est présenté comme un allègement des tâches pénibles, sans réduction d'effectifs annoncée. Les données de productivité restent celles du fabricant.", "BMW / Figure", "annonce"],
  ];
  cases.forEach((c, i) => {
    const x = M + i * 4.1;
    card(s, x, 1.6, 3.85, 4.2);
    txt(s, c[0], { x: x + 0.25, y: 1.8, w: 3.35, h: 0.75, fontSize: 17, bold: true, fontFace: "Cambria" });
    txt(s, c[1], { x: x + 0.25, y: 2.6, w: 3.35, h: 2.6, fontSize: 14 });
    txt(s, c[2], { x: x + 0.25, y: 5.35, w: 2.0, h: 0.3, fontSize: 11, color: C.accent4 });
    badge(s, c[3], x + 2.25, 5.35);
  });
  txt(s, "Point commun : l'ajustement passe d'abord par les flux (embauches) plutôt que par les stocks (licenciements). C'est moins visible — et donc plus facile à sous-estimer politiquement.", { x: M, y: 6.0, w: CW, h: 0.7, fontSize: 15, bold: true, color: C.accent1 });
  s.addNotes("Insee (Adjerad, Vermersch, 24/03/2026) : les auteurs soulignent qu'il est impossible d'attribuer directement l'évolution à la seule IA générative. États-Unis : 'computer systems design' −1,2 % en 2024 et −1,6 % en 2025 selon la même note. Brynjolfsson, Li, Raymond : +14 % en moyenne, +34 % pour les moins expérimentés, effet faible pour les plus expérimentés ; amélioration du sentiment client et de la rétention. Klarna : chiffres de 700 agents et 2,3 millions de conversations par mois annoncés par l'entreprise en février 2024.");
}

// 10. TRAVAIL INTELLECTUEL
sec("Travail et économie");
{
  const s = slide("Travail intellectuel : distinguer assistance, transformation, moindres embauches et suppressions",
    "Lecture des auteurs à partir de : OIT WP 140 (2025) ; FMI SDN/2024/001 (janv. 2024) ; Brynjolfsson, Chandar, Chen (Stanford, août 2025) ; Banque de France (oct. 2026) ; OpenAI GDPval (sept. 2025) ; Anthropic Economic Index (mars 2026). Intensités indicatives, non mesurées.");
  const head = ["Fonction", "Assistance", "Transformation", "Moins d'embauches", "Suppressions"];
  const lvl = { F: ["Fort", "F4D2C9"], M: ["Moyen", "F3E6C4"], f: ["Faible", "E3E8EC"], O: ["Observé", "F4D2C9"], S: ["Signaux", "F3E6C4"], N: ["Non établi", "E3E8EC"] };
  const data = [
    ["Développement logiciel", "F", "F", "O", "S"],
    ["Service client", "F", "F", "S", "S"],
    ["Administratif, secrétariat, comptabilité", "F", "M", "S", "N"],
    ["Banque, assurance, finance", "F", "M", "S", "N"],
    ["Droit, analyse documentaire", "F", "M", "N", "N"],
    ["Recrutement, RH", "M", "M", "N", "N"],
    ["Conseil, ingénierie, contenus", "F", "M", "S", "N"],
  ];
  const rows = [head.map((h) => ({ text: h, options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 }, align: "center" } }))];
  data.forEach((r) => rows.push([{ text: r[0], options: { bold: true } }].concat(r.slice(1).map((k) => ({ text: lvl[k][0], options: { fill: { color: lvl[k][1] }, align: "center" } })))));
  s.addTable(rows, { x: M, y: 1.55, w: 8.0, colW: [2.8, 1.3, 1.3, 1.3, 1.3], fontSize: 12.5, color: HEX.dk1, fontFace: "Calibri", border: { type: "solid", pt: 1, color: "FFFFFF" }, valign: "middle", margin: 0.05, rowH: 0.52 });
  txt(s, "Colonnes 1-2 : intensité potentielle (Fort / Moyen / Faible). Colonnes 3-4 : état des preuves (Observé / Signaux / Non établi).", { x: M, y: 5.8, w: 8.0, h: 0.5, fontSize: 11, color: C.accent4 });
  badge(s, "illus", M + 6.6, 6.25);
  card(s, 9.0, 1.55, 3.73, 5.0, C.background2);
  txt(s, "Qui est le plus exposé ?", { x: 9.2, y: 1.7, w: 3.35, h: 0.4, fontSize: 16, bold: true, fontFace: "Cambria" });
  txt(s, [{ text: "Jeunes diplômés : ", options: { bold: true } }, { text: "les tâches d'entrée de carrière sont les plus faciles à confier à l'IA (−13 % d'emploi relatif des 22-25 ans exposés aux États-Unis)." }], { x: 9.2, y: 2.15, w: 3.35, h: 1.4, fontSize: 13 });
  txt(s, [{ text: "Salariés expérimentés : ", options: { bold: true } }, { text: "plutôt protégés à court terme ; leur expertise sert à superviser l'IA." }], { x: 9.2, y: 3.6, w: 3.35, h: 1.1, fontSize: 13 });
  txt(s, [{ text: "Qualifications intermédiaires : ", options: { bold: true } }, { text: "les gains d'assistance sont les plus forts pour les moins expérimentés — un levier de rattrapage, ou de dévalorisation." }], { x: 9.2, y: 4.7, w: 3.35, h: 1.6, fontSize: 13 });
  s.addNotes("Ce tableau est une synthèse qualitative des auteurs, pas une mesure. 'Observé' = baisse d'embauches documentée par une étude (Banque de France pour les métiers exposés ; Insee et Stanford pour le logiciel). 'Signaux' = cas d'entreprises ou études partielles. FMI (janv. 2024) : ≈40 % des emplois mondiaux et ≈60 % dans les économies avancées exposés, dont environ la moitié pourraient bénéficier de l'IA. GDPval (OpenAI, sept. 2025) : sur 1 320 tâches de 44 métiers, le meilleur modèle d'alors était jugé égal ou meilleur que l'expert dans 47,6 % des comparaisons ; ce test porte sur des livrables isolés, pas sur des emplois entiers. Stanford 'Canaries in the Coal Mine' (26/08/2025, données de paie ADP) : −13 % d'emploi relatif pour les 22-25 ans dans les métiers les plus exposés après contrôles ; les auteurs mentionnent d'autres causes possibles. Anthropic Economic Index (mars 2026) : l'augmentation (collaboration) progresse légèrement dans l'usage grand public, l'automatisation domine dans les usages API.");
}

// 11. FRANCE
{
  const s = slide("En France, le premier signal mesuré est un recul des embauches de jeunes dans les métiers exposés",
    "Banque de France, Bloc-notes Éco n° 463 (08/10/2026), Palladino, Bergeaud, Bertheau, Bunel, Degos, données DMMO (Dares), indice d'exposition fondé sur le ROME ; Insee Première n° 2120 (juil. 2026), enquête TIC, entreprises ≥ 10 salariés ; Eurostat (déc. 2025).");
  s.addChart(pres.ChartType.bar, [{ name: "Évolution", labels: ["Métiers les plus exposés (Q5)", "Métiers les moins exposés (Q1)"], values: [-28, -8] }], chartBase({
    x: M, y: 1.5, w: 6.0, h: 4.2, barDir: "col", chartColors: ["D9482B", "5B6B7F"], varyColors: true,
    title: "Embauches en CDI des 21-29 ans, mars 2026 vs nov. 2022 (%)", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', valAxisMinVal: -35, valAxisMaxVal: 0, valAxisLabelFormatCode: '0"%"',
  }));
  badge(s, "mesure", M, 6.45);
  txt(s, "Causalité non établie (télétravail, cycle, taux d'intérêt). Résultats contrastés ailleurs : pas de recul en Norvège, pas d'effet moyen au Danemark.", { x: M, y: 5.75, w: 6.0, h: 0.7, fontSize: 13, italic: true, color: C.text2 });
  s.addChart(pres.ChartType.bar, [{ name: "Part", labels: ["France 2024", "France 2025", "UE 2025"], values: [10, 18, 20] }], chartBase({
    x: 7.0, y: 1.5, w: 5.73, h: 3.2, barDir: "col", chartColors: ["9AA5B1", "1F7A72", "2B3440"], varyColors: true,
    title: "Entreprises de 10 salariés ou plus utilisant l'IA (%)", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', valAxisMinVal: 0, valAxisMaxVal: 25, valAxisLabelFormatCode: '0"%"',
  }));
  card(s, 7.0, 4.85, 5.73, 1.75, C.background2);
  txt(s, bullets([
    "Adoption × 3 depuis 2023, mais 82 % des entreprises n'utilisent pas encore l'IA.",
    "Écart de 43 points entre PME (< 50 salariés) et grandes entreprises.",
    "Le gros de la diffusion — et de ses effets — est donc devant nous.",
  ]), { x: 7.2, y: 4.97, w: 5.35, h: 1.55, fontSize: 13 });
  s.addNotes("Banque de France : embauches en CDI des 21-29 ans, quintile le plus exposé ≈ −28 % entre novembre 2022 et mars 2026 contre ≈ −8 % pour le quintile le moins exposé ; Texte vérifié dans le PDF le 13/11/2026 : « environ 28 % sous leur niveau de novembre 2022, contre 8 % dans le quintile le moins exposé » (séries de tendance filtrées, DMMO). Les fins de contrat baissent aussi (≈ −23 % contre −6 %) : moindre rotation, pas de vague de licenciements. Le billet cite des résultats contrastés : Hernæs et Kostøl (Norvège, 2026) ne trouvent pas de recul relatif ; Humlum et Vestergaard (Danemark, 2026) n'observent pas d'effet moyen sur les heures ou les revenus. Les auteurs écrivent que leurs résultats ne permettent pas encore d'établir la causalité. Un chiffre de « 75 000 CDI en moins par an » et un « −42 % pour les jeunes développeurs » circulent dans la presse ; nous ne les avons pas retrouvés dans le billet et ne les reprenons pas. Insee : 18 % des entreprises (≥10 salariés) utilisent au moins une technologie d'IA en 2025 contre 10 % en 2024 ; UE 20 % (Eurostat, 19,95 %). OCDE (Perspectives de l'emploi 2026, juillet 2026) : les données disponibles ne permettent pas d'affirmer que l'IA est la cause de la dégradation de la situation des jeunes, tendance antérieure aux grands modèles de langage — désaccord à signaler.");
}

// 12. CASCADE
{
  const s = slide("L'enjeu macroéconomique : si les gains vont au capital plus vite qu'aux revenus, la protection sociale se fragilise",
    "Schéma de causalité original des auteurs (hypothèses à tester, non démontrées). Estimations : Acemoglu, « The Simple Macroeconomics of AI », Economic Policy 40(121), 2025 ; Commission de l'IA, « IA : notre ambition pour la France » (13/03/2024) ; Cette & Chaney, document COR (2025).");
  const box = (x, y, w, t, col) => { s.addText(t, { x, y, w, h: 0.62, shape: pres.ShapeType.roundRect, rectRadius: 0.08, fill: { color: col }, color: C.background1, fontSize: 13, bold: true, align: "center", valign: "middle", margin: 0.05, isTextBox: true }); };
  txt(s, "Boucle de risque", { x: M, y: 1.5, w: 6, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
  const r = ["Concurrence\net baisse des coûts", "Automatisation\ndes tâches", "Moins\nd'embauches", "Revenus du travail\nen retrait", "Cotisations et\nconsommation ↓"];
  r.forEach((t, i) => { box(M + i * 2.5, 1.95, 2.1, t, C.accent1); if (i < 4) arrow(s, M + i * 2.5 + 2.12, 2.26, M + (i + 1) * 2.5 - 0.02, 2.26, C.accent1); });
  txt(s, "Boucle de compensation", { x: M, y: 3.0, w: 6, h: 0.35, fontSize: 15, bold: true, color: C.accent2 });
  const g = ["Gains de\nproductivité", "Baisse\ndes prix", "Hausse de\nla demande", "Nouveaux métiers,\ncomplémentarité", "Réduction possible\ndu temps de travail"];
  g.forEach((t, i) => { box(M + i * 2.5, 3.45, 2.1, t, C.accent2); if (i < 4) arrow(s, M + i * 2.5 + 2.12, 3.76, M + (i + 1) * 2.5 - 0.02, 3.76, C.accent2); });
  card(s, M, 4.45, 6.0, 2.15, C.background2);
  txt(s, "Ce que disent les études", { x: M + 0.2, y: 4.55, w: 5.6, h: 0.35, fontSize: 15, bold: true });
  txt(s, bullets([
    "Acemoglu : ≤ +0,66 % de productivité globale en 10 ans (≈ +0,06 pt/an).",
    "Commission IA (2024) : l'IA pourrait doubler le taux de croissance.",
    "Écart d'un ordre de grandeur : aucune projection ne fait consensus.",
  ]), { x: M + 0.2, y: 4.95, w: 5.6, h: 1.6, fontSize: 13 });
  badge(s, "proj", M + 4.45, 4.58);
  card(s, 6.85, 4.45, 5.88, 2.15, "FBE9E4");
  txt(s, "Le point de vulnérabilité français", { x: 7.05, y: 4.55, w: 5.5, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
  txt(s, "La protection sociale est financée principalement par des prélèvements assis sur les revenus d'activité. Si la valeur ajoutée croît sans croissance équivalente de la masse salariale, la base de financement s'érode — même sans chômage de masse.", { x: 7.05, y: 4.95, w: 5.5, h: 1.6, fontSize: 13 });
  s.addNotes("Le schéma est une grille d'analyse, pas une démonstration : les deux boucles coexistent et leur résultat net est inconnu. Indicateurs pour trancher : part des rémunérations dans la valeur ajoutée (comptes nationaux Insee), masse salariale soumise à cotisations (Urssaf), productivité horaire, prix des services exposés. Acemoglu (NBER w32487, 2024 ; Economic Policy, 2025) : ≤0,66 % de PGF en 10 ans, <0,53 % en tenant compte des tâches plus difficiles ; effet PIB ≈0,9 à 1,1 %. Commission Aghion-Bouverot (mars 2024) : hypothèse d'un doublement du taux de croissance, calibrations jugées très incertaines par Cette et Chaney (document COR, avril 2025). Conclusion prudente : le risque principal pour les finances publiques n'est pas nécessairement le chômage, mais un découplage entre production et masse salariale.");
}

// 13. JUSTICE
sec("Services publics");
{
  const s = slide("Justice : l'IA peut réduire les tâches documentaires, à condition de ne jamais décider à la place du juge",
    "Cour de cassation, « Cour de cassation et intelligence artificielle : préparer la Cour de demain » (28/04/2025) ; ministère de la Justice, rapport « L'IA au service de la justice » (juin 2025) ; Règlement (UE) 2024/1689, annexe III (administration de la justice = haut risque).");
  const cols = [
    ["Existant", ["Pseudonymisation de décisions de justice par IA (projet cité par la Cour des comptes, nov. 2025)", "Inventaire des usages et méthode d'évaluation par la Cour de cassation (avril 2025)"], C.accent2, "fait"],
    ["En test, recommandé", ["Exploitation des écritures des parties (résumés, repérage des moyens)", "Recherche dans les bases jurisprudentielles", "Aide à la rédaction — l'aide à la décision n'est pas demandée par les magistrats"], C.accent3, "proj"],
    ["Gains mesurés", ["Aucune évaluation publique chiffrée des gains de délais ou de coûts n'a été trouvée", "Économies : non chiffrables sans évaluation préalable"], C.accent4, "incertain"],
  ];
  cols.forEach((c, i) => {
    const x = M + i * 4.1;
    txt(s, c[0], { x, y: 1.55, w: 2.6, h: 0.4, fontSize: 16, bold: true, color: c[2] });
    badge(s, c[3], x + 2.5, 1.62);
    txt(s, bullets(c[1]), { x, y: 2.05, w: 3.85, h: 2.4, fontSize: 14 });
  });
  card(s, M, 4.55, CW, 2.05, C.background2);
  txt(s, "Obstacles et risques", { x: M + 0.25, y: 4.65, w: 4, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
  txt(s, bullets(["Données judiciaires sensibles et hétérogènes ; systèmes informatiques anciens.", "Classement « haut risque » par l'AI Act : exigences de documentation et de supervision.", "Risque de biais, d'automatisation de fait des décisions, d'atteinte au droit au procès équitable."]), { x: M + 0.25, y: 5.05, w: 6.3, h: 1.5, fontSize: 13 });
  txt(s, "Supervision humaine", { x: 7.3, y: 4.65, w: 5, h: 0.35, fontSize: 15, bold: true, color: C.accent2 });
  txt(s, "Ce qui peut être fait sans attendre une IA générale : outils de recherche et de synthèse pour toutes les juridictions, avec évaluation indépendante des délais avant/après et traçabilité de chaque usage.", { x: 7.3, y: 5.05, w: 5.2, h: 1.5, fontSize: 13 });
  s.addNotes("Rapport de la Cour de cassation (groupe présidé par Sandrine Zientara, remis le 28/04/2025) : trois familles d'usages (exploitation des écritures, recherche documentaire, aide à la rédaction) ; l'aide à la décision ne figure pas parmi les besoins recensés ; recommandation d'étendre certains outils à toutes les juridictions ; méthode d'évaluation des cas d'usage. Rapport du ministère remis à Gérald Darmanin en juin 2025. Après vérification, seul le projet de pseudonymisation est confirmé par une source consultée (Cour des comptes, via Localtis 21/11/2025) ; les autres outils internes n'ont pas pu être vérifiés et ont été retirés. Aucune évaluation publique chiffrée des gains n'a été trouvée. Accès au droit : pistes d'assistants pour les justiciables, mais risque d'informations juridiques erronées — supervision nécessaire.");
}

// 14. SANTÉ
{
  const s = slide("Santé : les gains les plus rapides concernent le temps administratif des soignants, pas le diagnostic autonome",
    "FHF (2025) ; HAS & CNIL, guide de recommandations IA (fév.-mars 2026) ; CHU de Montpellier (France 2030, janv. 2026) ; CHU de Poitiers (12/06/2026) ; Hôpital Foch (2026) ; Le Quotidien du médecin (2026).");
  bigStat(s, M, 1.5, 3.6, "> 6 sur 10", "établissements de santé utilisant déjà des outils intégrant de l'IA en 2025 (FHF, déclaratif)", C.accent2, 36, "mesure");
  bigStat(s, M, 3.3, 3.6, "14,9 M€", "financement France 2030 obtenu par le CHU de Montpellier pour l'« Alliance Santé IA » (2026)", C.text1, 36, "fait");
  const rows = [
    [{ text: "Usage", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }, { text: "Statut en France", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }],
    ["Imagerie (détection d'anomalies)", "Dispositifs médicaux marqués CE déjà utilisés en radiologie"],
    ["Comptes rendus, courriers de sortie", "Déploiements locaux 2026 (Foch, Poitiers, Montpellier)"],
    ["Planification, gestion des lits", "Expérimentations locales ; peu d'évaluations publiées"],
    ["Aide au diagnostic", "Usage d'appui ; décision médicale humaine obligatoire"],
  ];
  s.addTable(rows, { x: 4.6, y: 1.55, w: 8.13, colW: [3.3, 4.83], fontSize: 13, color: HEX.dk1, fontFace: "Calibri", border: { type: "solid", pt: 0.5, color: "D9DEE3" }, valign: "middle", margin: 0.06, rowH: 0.52 });
  card(s, 4.6, 4.4, 8.13, 2.2, "FBE9E4");
  txt(s, "Risques et conditions", { x: 4.8, y: 4.5, w: 5, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
  txt(s, bullets(["Erreurs de transcription ou « hallucinations » dans le dossier patient ; le soignant doit avoir le temps de relire.", "Données de santé : hébergement certifié, souveraineté, RGPD.", "Gains de temps : à mesurer par des évaluations indépendantes avant généralisation — pas de chiffre national fiable à ce jour."]), { x: 4.8, y: 4.9, w: 7.7, h: 1.65, fontSize: 13 });
  txt(s, "Ce qui peut être fait maintenant : un protocole national d'évaluation (temps libéré, erreurs, satisfaction) pour les outils de compte rendu.", { x: M, y: 5.25, w: 3.6, h: 1.35, fontSize: 13, italic: true, color: C.accent2 });
  s.addNotes("FHF : plus de six établissements sur dix utilisent des outils intégrant de l'IA en 2025 (déclaratif, périmètre variable). HAS-CNIL : guide de recommandations publié début 2026, mentionnant l'aide à la rédaction des comptes rendus. CHU de Montpellier : 14,9 M€ de France 2030 (janvier 2026). CHU de Poitiers : déploiement de MedGPT annoncé le 12/06/2026. Hôpital Foch : équipement d'une solution de comptes rendus automatisés d'ici septembre 2026. Aucun gain chiffré national n'a été trouvé ; nous n'inventons pas d'économies. Un responsable cité par Acteurs publics pose la question centrale : l'IA générative travaille vite, mais les soignants ont-ils le temps de contrôler ?");
}

// 15. ADMINISTRATION
{
  const s = slide("Administration : des outils existent, mais la Cour des comptes juge le passage à l'échelle insuffisant",
    "Cour des comptes, rapport sur la stratégie nationale pour l'IA (nov. 2025) ; DINUM (Albert, Assistant IA) ; DGFiP « Foncier innovant » (2022-2024) ; Maddyness (05/10/2026) ; franceinfo, Acteurs publics (2026).");
  const items = [
    ["Albert / Assistant IA", "Socle interministériel d'IA générative de la DINUM ; assistant ouvert à 10 000 agents, puis élargi.", "fait"],
    ["Contrôle fiscal (DGFiP)", "Détection de piscines non déclarées par images aériennes : > 20 000 repérées et ≈ 10 M€ de recettes en 2022 (expérimentation, 9 départements). Chaque cas vérifié par un agent.", "fait"],
    ["Pilotage", "La Cour des comptes recommande un Secrétariat général à l'IA rattaché au Premier ministre ; formation des agents jugée dispersée.", "fait"],
  ];
  items.forEach((it, i) => {
    const y = 1.55 + i * 1.32;
    card(s, M, y, 7.4, 1.18);
    txt(s, it[0], { x: M + 0.2, y: y + 0.1, w: 5, h: 0.35, fontSize: 15, bold: true });
    badge(s, it[2], M + 5.85, y + 0.12);
    txt(s, it[1], { x: M + 0.2, y: y + 0.48, w: 7.0, h: 0.68, fontSize: 13 });
  });
  card(s, 8.25, 1.55, 4.48, 3.82, "FBE9E4");
  txt(s, "Le débat politique a commencé", { x: 8.45, y: 1.65, w: 4.1, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
  txt(s, "B. Retailleau (LR) propose de libérer l'équivalent de 250 000 emplois à temps plein d'ici 2032 grâce à l'automatisation et au redéploiement d'agents.", { x: 8.45, y: 2.05, w: 4.1, h: 1.4, fontSize: 13 });
  txt(s, "Aucune évaluation publique ne permet aujourd'hui de vérifier la faisabilité d'un tel chiffre : il dépend de gains de productivité non encore mesurés.", { x: 8.45, y: 3.5, w: 4.1, h: 1.3, fontSize: 13, italic: true });
  badge(s, "annonce", 8.45, 4.95);
  txt(s, [{ text: "Obstacles : ", options: { bold: true, color: C.accent1 } }, { text: "systèmes d'information anciens, données dispersées, compétences, achat public, dialogue social, droit des usagers à une décision explicable et à un interlocuteur humain." }], { x: M, y: 5.6, w: CW, h: 0.9, fontSize: 13 });
  s.addNotes("Cour des comptes (novembre 2025) : bilan contrasté de la stratégie nationale pour l'IA, recommandation d'un Secrétariat général à l'IA auprès du Premier ministre, formation des agents faite d'initiatives isolées. Assistant IA de l'État (DINUM) : lancement pour 10 000 agents puis annonce d'un assistant pour tous les agents (presse 2025-2026). DGFiP : chiffres 2022 du dossier de presse officiel ; des chiffres plus élevés (120 000-140 000 bassins, 40 M€) circulent sans confirmation officielle concordante — non repris. La Cour a jugé les résultats encore insuffisants et le déploiement incomplet. Retailleau : chiffre de 250 000 ETP d'ici 2032 rapporté par Maddyness (programme présenté en juillet 2026) ; d'autres chiffres (300 000 postes, 125 000 non-remplacements + 125 000 redéploiements) ont été rapportés dans des interventions différentes — signe d'un chiffrage évolutif.");
}

// 16. VITESSE
sec("Politique");
{
  const s = slide("Les institutions agissent, mais à un rythme de plusieurs années quand les capacités doublent en quelques mois",
    "Règlement (UE) 2024/1689 (AI Act) ; Règlement (UE) 2026/1744 « Omnibus numérique IA » (8/07/2026, JOUE 24/07/2026) ; Commission de l'IA (13/03/2024) ; Élysée (09/02/2025) ; Cour des comptes (nov. 2025) ; METR (2025-2026) ; Insee (2026).");
  const ev = [
    ["Nov. 2022", "ChatGPT", 0, "tech"],
    ["Mars 2024", "Rapport Commission IA", 1, "pol"],
    ["Août 2024", "AI Act en vigueur", 1, "pol"],
    ["Fév. 2025", "Sommet IA Paris ; 109 Md€ d'investissements privés annoncés", 1, "pol"],
    ["2025", "Agents de ~1 h d'autonomie", 0, "tech"],
    ["Nov. 2025", "Cour des comptes : « changer d'échelle »", 1, "pol"],
    ["Mars 2026", "Agents ≥ 16 h (METR)", 0, "tech"],
    ["Juil. 2026", "Règlement 2026/1744 : report des règles « haut risque »", 1, "pol"],
    ["Déc. 2027", "Règles haut risque (annexe III)", 1, "fut"],
  ];
  const x0 = M + 0.75, x1 = 12.0, ly = 3.55;
  s.addShape(pres.ShapeType.line, { x: x0, y: ly, w: x1 - x0, h: 0, line: { color: C.text2, width: 2 } });
  txt(s, "Technologie et entreprises", { x: M, y: 1.5, w: 5, h: 0.3, fontSize: 13, bold: true, color: C.accent1 });
  txt(s, "Décision publique", { x: M, y: 5.6, w: 5, h: 0.3, fontSize: 13, bold: true, color: C.accent2 });
  ev.forEach((e, i) => {
    const x = x0 + i * ((x1 - x0) / (ev.length - 1));
    const up = e[2] === 0;
    const col = e[3] === "tech" ? C.accent1 : e[3] === "fut" ? C.accent6 : C.accent2;
    s.addShape(pres.ShapeType.ellipse, { x: x - 0.1, y: ly - 0.1, w: 0.2, h: 0.2, fill: { color: col }, line: { color: C.background1, width: 1 } });
    const bx = Math.max(M, Math.min(x - 0.72, 12.73 - 1.44));
    txt(s, e[0], { x: bx, y: up ? 2.0 : 3.8, w: 1.44, h: 0.3, fontSize: 12, bold: true, align: "center", color: col });
    txt(s, e[1], { x: bx, y: up ? 2.32 : 4.12, w: 1.44, h: up ? 1.0 : 1.4, fontSize: 11.5, align: "center" });
  });
  txt(s, "Risque double : légiférer trop tard (effets déjà installés) ou trop vite (règles inapplicables, à reporter — comme l'AI Act en 2026). Ne pas confondre inaction et action insuffisante ou mal ciblée.", { x: M, y: 6.0, w: CW, h: 0.7, fontSize: 13, italic: true, color: C.text2 });
  s.addNotes("Lecture : les gouvernements ne sont pas inactifs (stratégie nationale depuis 2018, France 2030, AI Act, Commission IA, Albert, Sommet de Paris). Mais l'essentiel de l'effort porte sur l'offre (calcul, champions, régulation des risques) ; l'anticipation des effets sur l'emploi et les finances sociales est quasi absente des documents publics consultés. AI Act : entré en vigueur le 01/08/2024 ; obligations des modèles d'IA à usage général depuis le 02/08/2025 ; accord politique début mai 2026, puis Règlement (UE) 2026/1744 du 8 juillet 2026, publié au JOUE le 24/07/2026, en vigueur le 27/07/2026 : régime haut risque annexe III reporté au 02/12/2027 et annexe I au 02/08/2028 (vérifié sur EUR-Lex et Gibson Dunn). 109 Md€ : investissements privés annoncés, pas un budget public.");
}

// 17. PRÉSIDENTIELLE
{
  const s = slide("Présidentielle 2027 : l'IA est dans les programmes, la question du financement social presque absente",
    "État au 13/11/2026, programmes non définitifs. Maddyness (05/10/2026, vérifié) ; Next.ink (02/10/2026, débat de Marseille du 25/09/2026) ; Europe 1 ; franceinfo, Acteurs publics (juil. 2026). « — » = aucune proposition trouvée dans les sources consultées.");
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } });
  const rows = [
    [H("Candidat / formation"), H("IA, souveraineté, investissement"), H("Emploi, formation, temps de travail"), H("Protection sociale, fiscalité"), H("Services publics")],
    ["G. Attal (Renaissance)", "Plan « France 2040 » 200 Md€ public-privé", "IA dans les savoirs fondamentaux à l'école", "« Crédit d'impôt productivité » pour l'adoption de l'IA", "—"],
    ["É. Philippe (Horizons)", "Doubler les capacités de calcul en 5 ans", "« Droit à la reconversion » ; de 40 000 à 100 000 ingénieurs/an", "—", "—"],
    ["B. Retailleau (LR)", "25 Md€ sur 5 ans ; avantages fiscaux", "—", "—", "≈ 250 000 ETP libérés d'ici 2032"],
    ["Rassemblement national", "L'IA pour « faire des économies » (M. Le Pen, VivaTech)", "—", "—", "—"],
    ["LFI (J.-L. Mélenchon)", "Petits modèles ; maîtrise publique des infrastructures", "Salariés associés aux choix de déploiement de l'IA", "—", "—"],
    ["Les Écologistes", "Puce européenne ; sobriété des modèles ; étiquetage", "—", "—", "—"],
    ["R. Glucksmann (Place publique)", "Agence industrielle du numérique et de l'IA ; traité international", "—", "—", "—"],
    ["É. Zemmour (Reconquête)", "Financement privé ; allègement réglementaire", "Robotique pour remplacer une partie de la main-d'œuvre immigrée", "—", "—"],
    ["PS (O. Faure)", "Non documenté dans les sources accessibles", "—", "—", "—"],
  ];
  s.addTable(rows, { x: M, y: 1.5, w: CW, colW: [2.35, 2.85, 2.9, 2.0, 2.03], fontSize: 10.5, color: HEX.dk1, fontFace: "Calibri", border: { type: "solid", pt: 0.5, color: "D9DEE3" }, valign: "middle", margin: 0.05, rowH: [0.42, 0.5, 0.45, 0.45, 0.45, 0.5, 0.45, 0.45, 0.45, 0.4] });
  txt(s, "Non abordés dans les sources consultées : assiette des cotisations face à l'automatisation, dividende de productivité, transparence des entreprises sur les effets emploi de l'IA.", { x: M, y: 6.15, w: CW, h: 0.6, fontSize: 13, bold: true, color: C.accent1 });
  s.addNotes("Méthode : propositions relevées dans la presse et les comparateurs, sans accès systématique aux programmes officiels, encore non définitifs. Nature : Retailleau (programme présenté le 07/07/2026 à Station F selon Maddyness ; chiffres variables selon les interventions : 300 000, 250 000, 125 000+125 000). Attal : IA parmi ses 'quatre chantiers capitaux' ; Crédit impôt productivité jusqu'à 30 % des projets selon La Tribune citée par Maddyness. Corrections du 13/11/2026 : la formation de '20 millions de salariés' (IFRAP) n'a pas été retrouvée et a été retirée ; la réduction du temps de travail 'sans licenciement ni baisse de salaire' figure chez N. Arthaud (LO) dans le comparateur IFRAP, et non chez LFI : attribution corrigée. Philippe : propositions rapportées par Maddyness ; L. Marcangeli au débat du 25/09/2026 : la France n'a 'pas vocation à rivaliser avec OpenAI sur les grands modèles'. RN : aucune proposition programmatique trouvée ; déclaration de Marine Le Pen à VivaTech rapportée par Europe 1 ; Alexandre Loubet (conseiller de J. Bardella) : 'Soit nous la maîtrisons, soit nous la subirons'. LFI : propositions selon Maddyness. PS : position non accessible (article payant). Dates des scrutins : avril-mai 2027, à confirmer par décret. Ce tableau doit être mis à jour à la publication des programmes définitifs.");
}

// 18. SCÉNARIOS
sec("Prospective");
{
  const s = slide("Trois scénarios pour 2030-2035 : ce qui les distingue, c'est la vitesse relative de diffusion et d'adaptation",
    "Scénarios qualitatifs construits par les auteurs. Aucune probabilité ni chiffre de destruction d'emplois n'est attribué faute de modèle validé. Indicateurs : Banque de France, Insee, Urssaf, IFR, METR.");
  const sc = [
    ["1. Transition progressive", C.accent2, "Fiabilité des agents limitée ; adoption lente des PME ; formation efficace.", "Emplois transformés ; moindres embauches concentrées sur quelques métiers ; gains de productivité modestes.", "Peu de changement de l'assiette ; gains fiscaux modestes.", "Formation, évaluation, modernisation des services publics."],
    ["2. Automatisation accélérée", C.accent3, "Agents fiables sur processus complets ; coûts en baisse ; pression concurrentielle forte.", "Entrée sur le marché du travail très difficile pour les jeunes diplômés des métiers exposés ; polarisation.", "Masse salariale moins dynamique que la valeur ajoutée ; tension sur retraites et santé.", "Réforme de l'assiette ; garantie jeunes renforcée ; transparence emploi."],
    ["3. Rupture majeure", C.accent1, "Agents autonomes + robots bon marché et fiables ; diffusion rapide ; énergie et calcul abondants.", "Réorganisation d'une large part de l'économie ; chômage de transition durable possible.", "Érosion forte des cotisations ; besoin de nouvelles ressources.", "Garantie de revenu, fiscalité de la valeur ajoutée, temps de travail."],
  ];
  const H = ["", "Conditions nécessaires", "Emploi et niveau de vie", "Finances publiques", "Options d'adaptation"];
  H.forEach((h, j) => { if (j) txt(s, h, { x: M + 2.45 + (j - 1) * 2.47, y: 1.5, w: 2.37, h: 0.35, fontSize: 13, bold: true, color: C.accent4 }); });
  sc.forEach((r, i) => {
    const y = 1.9 + i * 1.42;
    s.addText(r[0], { x: M, y, w: 2.3, h: 1.3, shape: pres.ShapeType.rect, fill: { color: r[1] }, color: C.background1, fontSize: 14, bold: true, fontFace: "Cambria", valign: "middle", margin: 8, isTextBox: true });
    for (let j = 2; j < 6; j++) {
      card(s, M + 2.45 + (j - 2) * 2.47, y, 2.37, 1.3);
      txt(s, r[j], { x: M + 2.55 + (j - 2) * 2.47, y: y + 0.08, w: 2.17, h: 1.15, fontSize: 11.5 });
    }
  });
  txt(s, [{ text: "Indicateurs à surveiller : ", options: { bold: true } }, { text: "embauches CDI des jeunes dans les métiers exposés · part des salaires dans la valeur ajoutée · assiette des cotisations · taux d'adoption des PME · horizon d'autonomie des agents · prix de l'inférence · installations de robots · licenciements économiques motivés par l'automatisation." }], { x: M, y: 6.2, w: CW, h: 0.6, fontSize: 12 });
  badge(s, "illus", M, 1.55);
  s.addNotes("Aucune probabilité n'est attribuée : les études disponibles (Acemoglu 2025, Commission IA 2024, FMI 2024) divergent d'un ordre de grandeur. Le scénario 1 correspond aux observations actuelles (2023-2026). Le scénario 2 suppose que les tendances mesurées (baisse des embauches jeunes, progression des agents) se diffusent aux PME et aux métiers intermédiaires. Le scénario 3 suppose une fiabilité et un coût que ni les agents ni les humanoïdes n'ont démontrés en novembre 2026. Horizon 2030 : les scénarios 1 et 2 sont compatibles avec les données ; horizon 2035 : les trois restent ouverts.");
}

// 19-20. OPTIONS
function optionsSlide(title, opts, src) {
  const s = slide(title, src);
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } });
  const rows = [[H("Option"), H("Atouts"), H("Limites et risques"), H("Coût, faisabilité")]];
  opts.forEach((o) => rows.push([{ text: o[0], options: { bold: true } }, o[1], o[2], o[3]]));
  s.addTable(rows, { x: M, y: 1.5, w: CW, colW: [2.6, 3.2, 3.4, 2.93], fontSize: 11.5, color: HEX.dk1, fontFace: "Calibri", border: { type: "solid", pt: 0.5, color: "D9DEE3" }, valign: "middle", margin: 0.06, rowH: [0.4, 0.92, 0.92, 0.92, 0.92, 0.92] });
  badge(s, "illus", 11.38, 6.45);
  return s;
}
{
  const s = optionsSlide("Financer et redistribuer : cinq options, aucune sans contrepartie", [
    ["Élargir l'assiette de la protection sociale (valeur ajoutée, CSG)", "Moins dépendante de la masse salariale ; neutre entre travail et machine", "Effets sur la compétitivité et les prix ; complexité ; risque de double imposition", "Réforme lourde, plusieurs années ; chiffrage par le HCFiPS nécessaire"],
    ["« Taxe robot » ou sur l'automatisation", "Signal politique ; recettes ciblées", "Définition du « robot » impossible à stabiliser ; freine l'investissement productif", "Faible ; peu d'exemples étrangers concluants"],
    ["Dividende social / fonds de productivité", "Partage visible des gains ; lien avec l'acceptabilité", "Mesure des gains imputables à l'IA difficile ; gouvernance du fonds", "Expérimentable à partir de recettes existantes"],
    ["Revenu universel ou garantie de revenu ciblée", "Filet si l'emploi se contracte ; simplification", "Universel : coût très élevé ; ciblé : effets de seuil", "Expérimentations départementales possibles avant toute généralisation"],
    ["Participation des salariés aux gains", "S'appuie sur des outils existants (participation, intéressement)", "Ne couvre pas les non-salariés ni les emplois non créés", "Faible coût public ; négociation de branche"],
  ], "Options issues de la littérature et du débat public ; avantages et limites établis par les auteurs. Aucun chiffrage n'est proposé faute d'évaluation officielle (HCFiPS, COR, France Stratégie n'ont pas publié d'évaluation dédiée trouvée).");
  s.addNotes("Toutes les options sont présentées sans préférence. Coûts : ordres de grandeur volontairement non chiffrés ; un revenu universel inconditionnel versé à tous les adultes coûterait plusieurs centaines de milliards d'euros par an selon le montant — tout chiffre précis dépend des paramètres et doit venir d'une évaluation officielle. Recommandation de méthode : saisir le HCFiPS et le COR d'une évaluation 'assiette et automatisation' à horizon 2035 dans les trois scénarios.");
}
{
  const s = optionsSlide("Travail, compétences et État : cinq leviers à préparer dès maintenant", [
    ["Formation continue et reconversion", "Consensus politique large ; CPF et « droit à la reconversion » proposés", "Efficacité variable des formations ; peu de ciblage des métiers exposés", "Coût élevé si massif ; évaluation indispensable"],
    ["Réduction progressive du temps de travail", "Partage du travail si la demande baisse", "Effets sur coûts et compétitivité ; débat sur les 35 h non tranché", "Négociation par branche ; réversibilité limitée"],
    ["Transparence sur les effets emploi de l'IA", "Donne aux pouvoirs publics des données qui manquent aujourd'hui", "Charge déclarative ; difficulté d'attribuer un effet à l'IA", "Faible : intégration au bilan social / CSE"],
    ["Infrastructures publiques d'IA (calcul, modèles, données)", "Souveraineté ; services publics moins dépendants", "Concurrence de géants mondiaux ; énergie et talents", "Élevé ; s'appuie sur France 2030 et EuroHPC"],
    ["Stratégie d'automatisation des services publics", "Délais réduits, agents recentrés sur l'humain", "Droits des usagers ; erreurs ; dialogue social", "Gains à mesurer avant de fixer des objectifs d'effectifs"],
  ], "Sources de contexte : Cour des comptes (nov. 2025) ; programmes 2027 rapportés par la presse ; Règlement (UE) 2024/1689. Analyse des auteurs.");
  s.addNotes("Le levier le moins coûteux et le plus urgent est informationnel : aujourd'hui, ni l'État ni les partenaires sociaux ne disposent d'une mesure régulière des effets de l'IA sur les embauches par métier. Les données existent (DSN, enquêtes TIC) : il s'agit de les exploiter de façon régulière et publique, comme l'ont fait ponctuellement la Banque de France et l'Insee.");
}

// 21. DIX QUESTIONS
sec("Conclusion");
{
  const s = slide("Dix questions auxquelles tout responsable public devrait pouvoir répondre", "Questions formulées par les auteurs à partir des constats du dossier.");
  const q = [
    "Quel indicateur public suit chaque trimestre les embauches par métier exposé à l'IA ?",
    "Comment la protection sociale sera-t-elle financée si la masse salariale croît moins vite que la production ?",
    "Que proposez-vous aux jeunes diplômés dont les postes d'entrée disparaissent ?",
    "Les gains de productivité de l'IA doivent-ils être partagés, et par quel mécanisme ?",
    "Faut-il obliger les grandes entreprises à publier les effets de l'IA sur leurs effectifs ?",
    "Quels gains l'IA a-t-elle réellement produits dans les services publics, mesurés comment ?",
    "Quelle garantie d'un interlocuteur humain pour l'usager et le justiciable ?",
    "Quelle part du calcul et des modèles doit être souveraine, à quel coût ?",
    "Comment former les salariés des PME, où l'adoption est la plus faible ?",
    "Qu'est-ce qui déclencherait un changement de politique : quel seuil, quel indicateur ?",
  ];
  q.forEach((t, i) => {
    const col = i < 5 ? 0 : 1, row = i % 5;
    const x = M + col * 6.15, y = 1.55 + row * 1.0;
    s.addText(String(i + 1), { x, y, w: 0.55, h: 0.55, shape: pres.ShapeType.ellipse, fill: { color: i === 1 ? C.accent1 : C.text1 }, color: C.background1, fontSize: 15, bold: true, fontFace: "Cambria", align: "center", valign: "middle", margin: 0, isTextBox: true });
    txt(s, t, { x: x + 0.75, y: y - 0.02, w: 5.2, h: 0.9, fontSize: 14, valign: "middle" });
  });
  s.addNotes("Questions conçues pour une audition parlementaire ou une interview. Elles sont non partisanes : chacune peut recevoir des réponses très différentes selon les préférences politiques.");
}

// 22. CONCLUSION
{
  const s = slide("Ce qui ne devrait pas attendre : mesurer, anticiper le financement, protéger l'entrée dans l'emploi", "Synthèse des auteurs. Voir annexes pour les sources, les limites et le registre des preuves.", { dark: true });
  const d = [
    ["Mesurer", "Créer un tableau de bord public trimestriel IA-emploi (DSN, Insee, Banque de France, France Travail)."],
    ["Anticiper", "Saisir le HCFiPS et le COR d'une évaluation de l'assiette sociale dans trois scénarios d'automatisation à 2035."],
    ["Protéger l'entrée", "Préparer un dispositif pour les jeunes des métiers exposés : alternance, compagnonnage IA, garantie de premier emploi."],
    ["Évaluer l'État", "Mesurer les gains réels de l'IA publique avant d'en tirer des objectifs d'effectifs."],
    ["Débattre", "Inscrire le partage des gains de productivité au débat de 2027, quelles que soient les réponses."],
  ];
  d.forEach((it, i) => {
    const y = 1.55 + i * 0.86;
    txt(s, it[0], { x: M, y, w: 2.8, h: 0.6, fontSize: 20, bold: true, fontFace: "Cambria", color: i === 0 ? C.accent1 : "F2B8A8" });
    txt(s, it[1], { x: 3.6, y: y + 0.05, w: 9.1, h: 0.8, fontSize: 16, color: C.background1 });
  });
  txt(s, "Nous ne savons pas à quelle vitesse le travail se transformera. Nous savons que les premiers effets sont mesurables, que nos systèmes de financement reposent sur le travail, et que les décisions de 2027 engageront la décennie.", { x: M, y: 5.95, w: CW, h: 0.7, fontSize: 13, italic: true, color: "C9D1D9" });
  s.addNotes("Ces cinq décisions ont en commun d'être peu coûteuses, réversibles et utiles dans les trois scénarios : elles ne supposent pas de croire à une rupture, seulement de s'y préparer.");
}

// ANNEXES
sec("Annexes");
{
  const s = slide("Annexe A1 — Méthode, niveaux de confiance et limites", "Dossier établi le 13/11/2026 à partir de recherches en ligne (≈ 40 requêtes) et de lectures de sources primaires ; certaines sources ont été lues partiellement (accès payant).");
  txt(s, "Méthode", { x: M, y: 1.5, w: 6, h: 0.35, fontSize: 16, bold: true, fontFace: "Cambria" });
  txt(s, bullets([
    "Priorité aux sources primaires : Insee, Banque de France, Cour des comptes, OIT, FMI, OCDE, AIE, IFR, Eurostat, textes européens, documents d'entreprises.",
    "Chaque chiffre est daté, son périmètre et sa méthode indiqués en notes de l'orateur.",
    "Les chiffres repris seulement par la presse secondaire sont signalés ou écartés.",
    "Les scénarios sont qualitatifs : aucune probabilité n'est attribuée.",
  ]), { x: M, y: 1.9, w: 6.0, h: 3.2, fontSize: 13 });
  txt(s, "Niveaux de confiance", { x: 6.95, y: 1.5, w: 5, h: 0.35, fontSize: 16, bold: true, fontFace: "Cambria" });
  const b = [["fait", "Source primaire consultée, chiffre publié"], ["mesure", "Étude statistique ; corrélation, causalité non établie"], ["proj", "Estimation ou projection d'institution / chercheurs"], ["annonce", "Objectif d'entreprise ou de responsable politique"], ["interne", "Document interne rapporté par la presse"], ["incertain", "Source unique, données partielles ou divergentes"], ["illus", "Construction analytique des auteurs"]];
  b.forEach((x, i) => { badge(s, x[0], 6.95, 1.95 + i * 0.5); txt(s, x[1], { x: 8.45, y: 1.93 + i * 0.5, w: 4.3, h: 0.35, fontSize: 13 }); });
  card(s, M, 5.3, CW, 1.3, "FBE9E4");
  txt(s, [{ text: "Limites principales : ", options: { bold: true, color: C.accent1 } }, { text: "chiffres clés revérifiés à la source le 13/11/2026 (PDF Banque de France et Insee, IFR, METR, OIT, NBER, Amazon, Tesla, EUR-Lex) ; AIE non accessible (chiffres via presse concordante) ; programmes 2027 non définitifs ; données d'humanoïdes auto-déclarées ; aucune évaluation chiffrée des gains de l'IA en justice et santé." }], { x: M + 0.2, y: 5.4, w: CW - 0.4, h: 1.15, fontSize: 13 });
}
function registre(title, rows) {
  const s = slide(title, "Registre complet avec URL : fichier « registre-des-preuves.md » joint au dossier.");
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } });
  const data = [[H("Affirmation"), H("Source (date)"), H("Confiance")]].concat(rows);
  s.addTable(data, { x: M, y: 1.5, w: CW, colW: [6.2, 4.4, 1.53], fontSize: 11, color: HEX.dk1, fontFace: "Calibri", border: { type: "solid", pt: 0.5, color: "D9DEE3" }, valign: "middle", margin: 0.05, rowH: 0.45 });
}
registre("Annexe A2 — Registre des preuves (1/2) : technologie et entreprises", [
  ["Horizon METR ≥ 16 h (IC 8,5-55 h) pour Claude Mythos Preview", "METR (08/05/2026) via presse", "Moyenne"],
  ["Doublement de l'horizon ~7 mois (2019-25), ~4,3 mois post-2023", "METR, Time Horizon 1.1 (29/01/2026)", "Élevée"],
  ["Prix niveau GPT-3.5 : 20 $ → 0,07 $ / M jetons", "Stanford HAI, AI Index 2025 (avr. 2025)", "Élevée"],
  ["Centres de données : 415 TWh (2024), ≈ 945 TWh (2030)", "AIE, Energy and AI (avr. 2025)", "Projection"],
  ["5 M robots industriels en service fin 2025 ; France 4 900 (2024), ≈ 4 500 (2025)", "IFR (25/09/2025 ; 24/09/2026)", "Élevée"],
  ["≈ 13 300 humanoïdes livrés en 2025", "Omdia via presse spécialisée (2026)", "Moyenne"],
  ["Optimus : production initiale, 20 000/sem. « dans au moins un an »", "Tesla, appel T3 2026 (22/10/2026)", "Annonce"],
  ["Macrohard et Terafab « very early stages »", "SpaceX S-1 via Electrek (20/05/2026)", "Moyenne"],
  ["Amazon > 1 M robots", "Amazon (30/06/2025)", "Élevée"],
  ["600 000 embauches évitées d'ici 2033 (documents internes)", "New York Times (21/10/2025) ; démenti partiel Amazon", "Doc. interne"],
]);
registre("Annexe A3 — Registre des preuves (2/2) : emploi, économie, politique", [
  ["Embauches CDI 21-29 ans : −28 % (Q5) vs −8 % (Q1)", "Banque de France, billet 463 (08/10/2026)", "Élevée (PDF lu)"],
  ["Emploi information-communication −3,0 % fin 2023-fin 2025", "Insee, Note de conjoncture (24/03/2026)", "Élevée (PDF lu)"],
  ["18 % des entreprises ≥ 10 salariés utilisent l'IA (2025)", "Insee Première n° 2120 (juil. 2026)", "Élevée"],
  ["−13 % d'emploi relatif des 22-25 ans exposés (États-Unis)", "Brynjolfsson, Chandar, Chen (26/08/2025)", "Mesure"],
  ["1 emploi sur 4 exposé à l'IA générative ; 3,3 % très exposés", "OIT, WP 140 (20/05/2025)", "Élevée"],
  ["≤ +0,66 % de PGF en 10 ans", "Acemoglu, Economic Policy (2025)", "Projection"],
  ["+14 % de productivité en service client", "Brynjolfsson, Li, Raymond (NBER/QJE)", "Élevée"],
  ["Report haut risque AI Act : 02/12/2027 et 02/08/2028", "Règlement (UE) 2026/1744 (JOUE 24/07/2026)", "Élevée"],
  ["Retailleau : ≈ 250 000 ETP administratifs d'ici 2032", "Maddyness (05/10/2026)", "Annonce, chiffres variables"],
  ["OCDE : pas de preuve que l'IA cause la dégradation de l'emploi des jeunes", "OCDE, blog et Perspectives de l'emploi 2026", "Élevée (désaccord)"],
]);
{
  const s = slide("Annexe A4 — Ce que nous n'avons pas pu vérifier (et avons donc écarté)", "Ces éléments circulent dans le débat public ; ils ne figurent pas dans le dossier faute de source primaire concordante.");
  txt(s, bullets([
    "« 75 000 CDI de jeunes en moins par an » et « −42 % d'embauches de jeunes développeurs » : chiffres de presse non retrouvés dans le billet de la Banque de France.",
    "« Plus de 50 % de baisse des offres d'emploi dans les métiers exposés » : étude Andreescu-Maurin non consultée dans sa version primaire.",
    "Subventions publiques spécifiques à l'implantation d'Amazon à Brétigny-sur-Orge : aucune trouvée — question ouverte, pas de conclusion.",
    "Location de Terafab à un tiers (message unique sur X) ; valorisations de la fusion SpaceX-xAI (sources divergentes).",
    "Bilans DGFiP 2023-2025 des piscines détectées (120 000 à 140 000 ; 40 M€) : chiffres non concordants.",
    "Chiffres de productivité et de coût horaire des humanoïdes comparés au travail humain : aucune donnée indépendante publiée.",
    "Positions détaillées du PS et du RN sur l'IA et l'emploi : non accessibles dans les sources consultées.",
    "« 670 salariés par entrepôt Amazon » (WSJ via TechSpot) ; « 4 000 robots » et « 670 CDI » à Brétigny : absents du communiqué Amazon.",
    "« Former 20 millions de salariés » (Attal) : non retrouvé dans le comparateur IFRAP.",
    "Résultats GDPval 2026 des derniers modèles (chiffre de 74 % non attribuable).",
  ]), { x: M, y: 1.55, w: CW, h: 5.1, fontSize: 13, paraSpaceAfter: 5 });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  if (SKILL) {
    const { applyTheme } = require(path.join(SKILL, "scripts", "apply_theme.js"));
    await applyTheme(OUT, THEME);
  }
  console.log("Écrit :", OUT);
})();
