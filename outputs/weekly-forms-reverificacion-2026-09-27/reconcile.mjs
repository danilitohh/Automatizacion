import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

// Coincidencias verificadas en las interfaces CRM por correo exacto e identidad.
const recovered = [
  [16, 'Danilo Prueba BKK', 'balancer', 'https://lead-balancer.scalahed.com/leads/detail/3229190'],
  [19, 'Danilo Prueba BKN', 'balancer', 'https://lead-balancer.scalahed.com/leads/detail/3229193'],
  [21, 'Danilo Prueba BKP', 'inconcert', 'https://mas-utel-singapur.infunnel.inconcert.cloud/mas/contact/people/view/159600'],
  [22, 'Danilo Prueba BKQ', 'inconcert', 'https://mas-utel-singapur.infunnel.inconcert.cloud/mas/contact/people/view/159601'],
  [23, 'Danilo Prueba BKR', 'inconcert', 'https://mas-utel-singapur.infunnel.inconcert.cloud/mas/contact/people/view/159602'],
  [26, 'Danilo Prueba BKU', 'inconcert', 'https://mas-utel-singapur.infunnel.inconcert.cloud/mas/contact/people/view/159603'],
  [27, 'Danilo Prueba BKV', 'inconcert', 'https://mas-utel-singapur.infunnel.inconcert.cloud/mas/contact/people/view/159604'],
].map(([n, name, source, url]) => ({email: `Testing2026-09-25N${n}@testingUtel.com`, name, source, url}));
const root = new URL('.', import.meta.url);
// Incorporar únicamente fichas verificadas por correo en la continuación.
const continuation = JSON.parse(await fs.readFile(new URL('continuacion.json', root), 'utf8'));
recovered.push(...continuation.recovered.map(lead => ({...lead,
  email: `Testing2026-09-25N${lead.n}@testingUtel.com`, source:'inconcert',
})));
const input = 'C:/Users/danil/Downloads/300bf37145c44a2c871dc6d9950071b1_leadsQA_sin_URL_LEAD (1).xlsx';
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const main = wb.worksheets.getItem('Hoja 1');
const report = wb.worksheets.getItem('Form Validation resultados');

// Revisar el formato original antes de modificar; nunca sobrescribir el archivo fuente.
if (process.argv.includes('--preview')) {
  console.log((await wb.inspect({kind:'sheet', include:'id,name', maxChars:2000})).ndjson);
  const png = await wb.render({sheetName:'Hoja 1', range:'O1:O11', scale:1, format:'png'});
  await fs.writeFile(new URL('antes.png', root), new Uint8Array(await png.arrayBuffer()));
  process.exit(0);
}

// Vincular por correo, no por fila histórica: el usuario eliminó filas del origen.
const mainValues = main.getRange('A1:AS95').values;
const reportValues = report.getRange('A1:O105').values;
const changes = [];
function put(sheet, address, value) {
  sheet.getRange(address).values = [[value]];
  changes.push({sheet:sheet.name, address, value});
}
for (const lead of recovered) {
  const matches = mainValues.flatMap((r, i) => r[33] === lead.email ? [i] : []);
  const resultMatches = reportValues.flatMap((r, i) => r[3] === lead.email ? [i] : []);
  assert.equal(matches.length, 1, `Identidad ambigua en Hoja 1: ${lead.email}`);
  assert.equal(resultMatches.length, 1, `Identidad ambigua en resultados: ${lead.email}`);
  const row = matches[0] + 1;
  const resultRow = resultMatches[0] + 1;
  assert.equal(mainValues[row - 1][32], lead.name);
  assert.equal(reportValues[resultRow - 1][2], lead.name);
  const action = lead.submitted
    ? `Envío corregido con los mismos nombre, correo y teléfono. Graduación: SI. Privacidad: Sí.${lead.document ? ` Documento sintético QA: ${lead.document}. Consentimiento multicanal opcional: No.` : ''}`
    : 'Lead existente. Sin reenviar ni generar datos nuevos.';
  const detail = `Reverificado 27/09/2026: encontrado en ${lead.source === 'balancer' ? 'Balancer' : 'inConcert'} con el mismo correo e identidad. ${action} Diagnóstico anterior: ${mainValues[row - 1][27] ?? ''}`;
  put(main, `O${row}`, lead.url);
  // Hacer legible el enlace recuperado sin alterar las columnas de datos originales.
  main.getRange(`O${row}`).format.font = {name:'Arial', size:11, color:'#0563C1'};
  main.getRange(`O${row}`).format.wrapText = true;
  main.getRange(`O${row}`).format.rowHeight = 45;
  put(main, `AA${row}`, 'VERIFICADO');
  put(main, `AB${row}`, detail);
  // Conservar el estado histórico del envío; actualizar únicamente su verificación CRM.
  put(main, `${lead.source === 'balancer' ? 'AO' : 'AM'}${row}`, 'Sí');
  put(main, `${lead.source === 'balancer' ? 'AP' : 'AN'}${row}`, lead.url);
  put(main, `AQ${row}`, lead.source);
  put(main, `AS${row}`, '');
  put(report, `${lead.source === 'balancer' ? 'K' : 'I'}${resultRow}`, 'Sí');
  put(report, `${lead.source === 'balancer' ? 'L' : 'J'}${resultRow}`, lead.url);
  put(report, `M${resultRow}`, lead.source);
  put(report, `O${resultRow}`, '');
  if (lead.submitted) {
    put(main, `AL${row}`, 'success');
    put(report, `H${resultRow}`, 'success');
  }
  // Mantener el programa realmente elegido y ambos enlaces cuando se verificaron.
  if (lead.program) {
    put(main, `AD${row}`, lead.program);
    put(main, `AK${row}`, lead.program);
    put(report, `G${resultRow}`, lead.program);
  }
  if (lead.balancer) {
    put(main, `AO${row}`, 'Sí');
    put(main, `AP${row}`, lead.balancer);
    put(report, `K${resultRow}`, 'Sí');
    put(report, `L${resultRow}`, lead.balancer);
  }
}

// Registrar los envíos con redirección de confirmación, sin inventar enlaces CRM.
for (const lead of continuation.submitted_pending_crm) {
  const email = `Testing2026-09-25N${lead.n}@testingUtel.com`;
  const row = mainValues.findIndex(r => r[33] === email) + 1;
  const resultRow = reportValues.findIndex(r => r[3] === email) + 1;
  assert.equal(row, lead.row);
  assert.ok(resultRow > 1);
  const detail = `27/09/2026: formulario completado con la misma identidad. Redirección posterior al envío: ${lead.confirmation}. Falta verificar en inConcert Perú (sesión pendiente). No reenviar. Programa: ${lead.program}.`;
  put(main, `AA${row}`, 'PENDIENTE CRM');
  put(main, `AB${row}`, `${detail} Diagnóstico anterior: ${mainValues[row - 1][27] ?? ''}`);
  put(main, `AD${row}`, lead.program);
  put(main, `AK${row}`, lead.program);
  put(main, `AL${row}`, 'pending');
  put(main, `AS${row}`, detail);
  put(report, `G${resultRow}`, lead.program);
  put(report, `H${resultRow}`, 'pending');
  put(report, `O${resultRow}`, detail);
}
// Marcar lo pendiente sin atribuir un 520 individual a URLs no revisitadas.
const confirmedEmails = new Set(recovered.map(lead => lead.email));
let pendingOrigin = 0;
for (let index = 1; index < mainValues.length; index++) {
  const data = mainValues[index];
  if (confirmedEmails.has(data[33]) || !String(data[3]).startsWith('https://universidad.utel.edu.mx/')) continue;
  const row = index + 1;
  const detail = '27/09/2026: pendiente de revisión actual. Varias landings de este dominio devuelven HTTP 520 del origen. Esta URL no se volvió a probar individualmente en esta continuación. No se realizó un nuevo envío. Se conserva el diagnóstico histórico.';
  put(main, `AA${row}`, 'PENDIENTE REVISIÓN');
  put(main, `AB${row}`, `${detail} Diagnóstico anterior: ${data[27] ?? ''}`);
  pendingOrigin++;
}
assert.equal(pendingOrigin, 45);
// Diferenciar las URLs efectivamente visitadas con 520 de las aún no revisadas.
for (const issue of continuation.origin_errors) {
  const detail = `27/09/2026: HTTP 520 del servidor de origen. Formulario inaccesible; no se realizó un nuevo envío.${issue.ray ? ` Ray ID: ${issue.ray}.` : ''}`;
  put(main, `AA${issue.row}`, 'ERROR EXTERNO 520');
  put(main, `AB${issue.row}`, `${detail} Diagnóstico anterior: ${mainValues[issue.row - 1][27] ?? ''}`);
}
// Registrar bloqueos observados fuera del dominio afectado sin alterar el historial.
for (const issue of continuation.reviewed_issues) {
  const data = mainValues[issue.row - 1];
  const resultRow = reportValues.findIndex(r => r[3] === data[33]) + 1;
  assert.ok(resultRow > 1);
  put(main, `AA${issue.row}`, issue.status);
  put(main, `AB${issue.row}`, `27/09/2026: ${issue.detail} Diagnóstico anterior: ${data[27] ?? ''}`);
  put(main, `AS${issue.row}`, issue.detail);
  put(report, `O${resultRow}`, issue.detail);
}

// Comprobar todos los enlaces confirmados y preservar las tres identidades originales.
assert.equal(recovered.length, 44);
assert.equal(new Set(recovered.map(lead => lead.email)).size, 44);
for (const lead of recovered) {
  const row = mainValues.findIndex(r => r[33] === lead.email) + 1;
  assert.equal(main.getRange(`O${row}`).values[0][0], lead.url);
  assert.deepEqual(main.getRange(`AG${row}:AI${row}`).values[0], mainValues[row - 1].slice(32, 35));
}
main.getRange('O1:O95').format.columnWidth = 60;
wb.recalculate();
console.log((await wb.inspect({kind:'region', sheetId:'Hoja 1', range:'AM3:AQ11', maxChars:2000, tableMaxRows:9, tableMaxCols:5})).ndjson);
const png = await wb.render({sheetName:'Hoja 1', range:'O36:O42', scale:1, format:'png'});
await fs.writeFile(new URL('despues.png', root), new Uint8Array(await png.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(new URL('leadsQA_avance_44_confirmados.xlsx', root).pathname.replace(/^\//, ''));
await fs.writeFile(new URL('verificaciones_continuacion.json', root), JSON.stringify({input, recovered, changes}, null, 2));
console.log('44 confirmados acumulados, incluidos ambos Perú en los dos CRM. 50 pendientes. Se conservan identidades e historial original.');
