import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

// Preserve the complete matrix; only verified links and the user-confirmed level change.
const root = new URL('.', import.meta.url);
const input = 'C:/Users/danil/Downloads/leadsQA_209_URL_LEADS_completados.xlsx';
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const main = wb.worksheets.getItem('Hoja 1');
const before = main.getRange('A1:Z210').values;
if (process.argv.includes('--preview')) {
  const png = await wb.render({sheetName:'Hoja 1', range:'N86:O91', scale:1, format:'png'});
  await fs.writeFile(new URL('revision60_antes.png', root), new Uint8Array(await png.arrayBuffer()));
  console.log((await wb.inspect({kind:'region',sheetId:'Hoja 1',range:'B159:E163',maxChars:2000,tableMaxRows:5,tableMaxCols:4})).ndjson);
  process.exit(0);
}

// Every originally pending row gets a current diagnosis, without repeating a lead submission.
const pending = JSON.parse(await fs.readFile(new URL('pending_60.json', root), 'utf8'));
const results = JSON.parse(await fs.readFile(new URL('revision_60_results.json', root), 'utf8'));
assert.equal(pending.length, 60);
assert.equal(new Set(results.map(r=>r.row)).size, 60);
assert.equal(results.length, 60);
const verified = results.filter(r=>r.link);
assert.equal(new Set(verified.map(r=>r.link)).size, verified.length);
for (const result of verified) {
  assert.ok(!before[result.row-1][14], `Do not replace existing link: ${result.row}`);
  assert.ok(/^https:\/\//.test(result.link));
  main.getRange(`O${result.row}`).values = [[result.link]];
}
main.getRange('C161').values = [['Licenciatura']];

// A separate diagnostic view keeps the original matrix and its historical notes intact.
const report = wb.worksheets.add('Revisión 60 pendientes');
report.showGridLines = false;
report.getRange('A2').values = [['Revisión de los 60 pendientes']];
report.getRange('A3').values = [['Resultados de esta revisión. Se conservaron los 149 enlaces existentes.']];
report.getRange('A4:C6').values = [
  ['Enlaces recuperados', null, verified.length],
  ['Pendientes, sin Vietnam', null, results.filter(r=>!r.link && r.status!=='EXCLUIDO POR USUARIO').length],
  ['Vietnam excluido por el usuario', null, 2],
];
report.getRange('A4:B6').merge(true);
const headers = ['Fila original','País matriz','URL formulario','Estado actual','Diagnóstico actual','Nombre QA','Correo QA','Teléfono QA','Envío en esta revisión','Link confirmado','Sistema','Hora de revisión UTC','Ray ID','Estado histórico','Error histórico'];
const rows = pending.map(rec=>{
  const result = results.find(r=>r.row===rec.row);
  const identity = result.identity || (rec.email ? rec : rec.identities.length===1 ? rec.identities[0] : null);
  const ray = (result.evidence || '').match(/Cloudflare Ray ID:[\s\S]*?- strong: ([a-f0-9]+)/i)?.[1] || '';
  return [rec.row,rec.country,rec.url,result.status,result.detail,identity?.name||'',identity?.email||result.email||'',identity?.phone||'',
    result.submitted?'Sí':'No',result.link||'',result.source||'',result.time||'',ray,rec.prior_status||identity?.status||'',rec.prior_error||identity?.error||''];
});
report.getRange(`A8:O${8+rows.length}`).values = [headers,...rows];
report.tables.add(`A8:O${8+rows.length}`,true,'RevisionPendientes');
report.getRange(`A1:O${8+rows.length}`).format.font = {name:'Arial',size:11,color:'#243328'};
report.getRange('A2').format.font = {name:'Arial',size:16,bold:true,color:'#243328'};
report.getRange('A8:O8').format = {fill:'#203923',font:{name:'Arial',size:11,bold:true,color:'#FFFFFF'},rowHeight:30};
report.getRange(`A9:O${8+rows.length}`).format.rowHeight = 92;
report.getRange(`A8:O${8+rows.length}`).format.wrapText = true;
report.getRange(`A8:O${8+rows.length}`).format.verticalAlignment = 'center';
for (const [column,width] of Object.entries({A:15,B:19,C:58,D:28,E:76,F:25,G:43,H:20,I:23,J:64,K:17,L:28,M:24,N:20,O:72})) {
  report.getRange(`${column}8:${column}${8+rows.length}`).format.columnWidth = width;
}
report.freezePanes.freezeRows(8);
report.freezePanes.freezeColumns(2);

// Assert scope preservation and reconcile the final total before export.
const after = main.getRange('A1:Z210').values;
for(let r=0;r<before.length;r++)for(let c=0;c<26;c++) {
  if(c===14 && verified.some(v=>v.row===r+1) || r===160 && c===2)continue;
  assert.deepEqual(after[r][c],before[r][c],`Unrequested change: row ${r+1}, column ${c+1}`);
}
assert.equal(after.slice(1).filter(r=>r[14]).length,149+verified.length);
wb.recalculate();
console.log((await wb.inspect({kind:'region',sheetId:report.name,range:'A4:C6',maxChars:1500,tableMaxRows:3,tableMaxCols:3})).ndjson);
for(const [name,sheet,range] of [['revision60_despues.png',report.name,'A2:E13'],['revision60_enlaces.png','Hoja 1','N86:O91']]) {
  const png = await wb.render({sheetName:sheet,range,scale:1,format:'png'});
  await fs.writeFile(new URL(name,root),new Uint8Array(await png.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(new URL('leadsQA_209_revision_60.xlsx',root).pathname.replace(/^\//,''));
console.log(JSON.stringify({verified:verified.length,totalWithLinks:149+verified.length,remaining:60-verified.length}));
