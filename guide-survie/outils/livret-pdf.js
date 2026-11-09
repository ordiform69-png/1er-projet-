// Produit guide-survie.pdf (A5, numéros de page) à partir de guide-survie.html.
// Usage : node outils/livret-pdf.js   (depuis le dossier guide-survie ; Playwright requis)
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');
const G = path.dirname(__dirname);
const html = fs.readFileSync(path.join(G, 'source/livret-corps.html'), 'utf8');
const version = (html.match(/Version (\d+\.\d+) — ([^·<]+?)\s*·/) || [, '?', ''])
const pied = `Petit guide de survie — version ${version[1]} (${version[2]}) — `;
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + path.join(G, 'guide-survie.html'));
  await p.emulateMedia({ media: 'print' });
  await p.pdf({
    path: path.join(G, 'guide-survie.pdf'), format: 'A5', printBackground: true,
    margin: { top: '14mm', bottom: '14mm', left: '12mm', right: '12mm' },
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: `<div style="font-size:7px;width:100%;text-align:center;color:#888">${pied}<span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
  });
  await b.close();
})();
