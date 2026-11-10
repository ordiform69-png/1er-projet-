// Produit un PDF A5 numéroté à partir d'un HTML du livret.
// Usage : node outils/livret-pdf.js <entrée.html> <sortie.pdf>   (Playwright requis)
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');
const [entree, sortie] = process.argv.slice(2);
const html = fs.readFileSync(entree, 'utf8');
const v = html.match(/Version (\d+\.\d+) — ([^·<]+?)\s*·/) || [, '?', ''];
const pied = `Petit guide de survie — version ${v[1]} (${v[2]}) — `;
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + path.resolve(entree));
  await p.emulateMedia({ media: 'print' });
  await p.pdf({
    path: sortie, format: 'A5', printBackground: true,
    margin: { top: '14mm', bottom: '15mm', left: '12mm', right: '12mm' },
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: `<div style="font-size:8.5px;width:100%;padding:0 12mm;display:flex;justify-content:space-between;color:#666;font-family:sans-serif"><span>${pied.replace(/ — $/, '')}</span><span class="pageNumber" style="font-weight:bold;font-size:10px"></span></div>`,
  });
  await b.close();
})();
