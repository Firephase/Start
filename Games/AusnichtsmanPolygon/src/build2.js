const fs = require('fs');
const parts = ['p2.js','p2b.js','p3.js','p4.js','p4b.js','p7.js','p9.js','p10.js','p11.js','p12.js','p13.js','p5.js','p8.js','p6.js'].map(f => fs.readFileSync(f,'utf8').trim()).join('\n\n');
const html = fs.readFileSync('p1.html','utf8').trim();
const out = html + '\n\n<script>\n' + parts + '\n<\/script>\n';
fs.writeFileSync('polygon-mobius.html', out);
fs.writeFileSync('wrapped2.html', '<!doctype html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>' + out + '</body></html>');
console.log('bytes', out.length, '| skeleton tags:', /<(!doctype|html|head|body)\b/i.test(out));
