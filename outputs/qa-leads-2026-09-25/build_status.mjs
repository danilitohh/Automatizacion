import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

// Conserva el reporte previo y registra cada intento sin atribuirle enlaces no confirmados.
const root = path.resolve('../../');
const reportDir = path.join(root, 'storage', 'reports', 'bot');
const firstPath = path.join(reportDir, 'e45deb25afa44a7695001cb4ad083a5b_leadsQA_sin_URL_LEAD.xlsx');
const secondPath = path.join(reportDir, '0bfcc2ab82a94aafbdbb6eb95878ae89_leadsQA_sin_URL_LEAD.xlsx');
const vietnamPreviewPath = path.join(reportDir, 'c574646637bb46dcab349ce05b480702_leadsQA_sin_URL_LEAD.xlsx');
const outputPath = path.join(process.cwd(), 'leadsQA_estado_verificacion_2026-09-25.xlsx');
const first = await SpreadsheetFile.importXlsx(await FileBlob.load(firstPath));
const second = await SpreadsheetFile.importXlsx(await FileBlob.load(secondPath));
const vietnamPreview = await SpreadsheetFile.importXlsx(await FileBlob.load(vietnamPreviewPath));
console.log((await first.inspect({ kind: 'sheet', include: 'id,name', maxChars: 1200 })).ndjson);
const main = first.worksheets.getItemAt(0);
const secondMain = second.worksheets.getItemAt(0);
const source = main.getRange('A2:AS105').values;
const secondSource = secondMain.getRange('A2:AS105').values;
const vietnamSource = vietnamPreview.worksheets.getItemAt(0).getRange('A2:AS105').values;
const audit = first.worksheets.add('Estado verificación 25-09');
audit.showGridLines = false;
audit.getRange('A1:I1').values = [[
  'Estado del envío real y verificación CRM — 25/09/2026', null, null, null, null, null, null, null, null,
]];
audit.getRange('A2:I2').values = [[
  'No se reenvían filas con URL LEADS previa ni casos con envío incierto. Un enlace previo no equivale a una verificación nueva.',
  null, null, null, null, null, null, null, null,
]];
audit.getRange('A4:I4').values = [[
  'Fila Excel', 'País', 'Landing', 'Estado', 'Detalle', 'Nombre', 'Correo', 'Teléfono', 'URL LEADS previa',
]];

// Separa enlaces heredados, rechazos del formulario, fallos del origen y casos no ejecutados.
const origin520 = new Set([51, 52, 53, 54]);
const uncertain = new Set([48, 56]);
const outOfScope = new Set([104, 105]);
const descriptions = {
  4: ['Rechazado por UTEL', 'POST /api/forms devolvió HTTP 500 en tres intentos; no se confirmó lead. La URL es de licenciaturas híbridas aunque el Excel dice maestrías.'],
  8: ['Enviado; CRM no confirmado', 'UTEL mostró confirmación, pero el formulario seleccionó programa Bachelor para una fila Master. Una búsqueda manual posterior por el correo no mostró resultados en Balancer. InConcert requiere iniciar sesión para verificar. No reenviar.'],
  9: ['Rellenado sin envío', 'Tras corregir el generador de Vietnam, el formulario se llenó y validó con nivel Bachelor, programa y teléfono válidos. No se pulsó Enviar ni se consultó CRM.'],
};
const rows = source.map((values, index) => {
  const rowNumber = index + 2;
  const later = secondSource[index] || [];
  const priorLink = values[14] || '';
  let status = 'Pendiente: no enviado';
  let detail = 'No se intentó el envío real en esta sesión.';
  if (priorLink) {
    status = 'URL LEADS previa';
    detail = 'Enlace presente en un reporte anterior; no se reenviaron ni reconfirmaron estas filas hoy.';
  } else if (descriptions[rowNumber]) {
    [status, detail] = descriptions[rowNumber];
  } else if (uncertain.has(rowNumber)) {
    status = 'Estado incierto: no reenviar';
    detail = 'El lote se canceló mientras esta fila figuraba activa. No apareció por correo en una búsqueda manual posterior de Balancer, pero falta verificar InConcert antes de reintentar.';
  } else if (origin520.has(rowNumber)) {
    status = 'No enviado: error 520';
    detail = 'La landing mostró Cloudflare 520 Host Error y no presentó formulario utilizable; el bot no hizo POST.';
  } else if (outOfScope.has(rowNumber)) {
    status = 'Fuera de dominios permitidos';
    detail = 'La URL no pertenece a los dominios UTEL habilitados en este flujo; no se intentó.';
  }
  // Nombre, correo y teléfono se toman del checkpoint correspondiente, sin inventarlos.
  const evidence = rowNumber === 9 ? vietnamSource[index] : (origin520.has(rowNumber) || rowNumber === 56 ? later : values);
  const name = evidence[32] || '';
  const email = evidence[33] || '';
  const phone = evidence[34] || '';
  return [rowNumber, values[1] || '', values[3] || '', status, detail, name, email, phone, priorLink];
});
audit.getRange('A5:I108').values = rows;

// Da a la hoja de auditoría una estructura legible sin cambiar datos del libro original.
audit.freezePanes.freezeRows(4);
audit.getRange('A1:I1').format.fill = '#173B25';
audit.getRange('A1:I1').format.font.color = '#FFFFFF';
audit.getRange('A1:I1').format.font.bold = true;
audit.getRange('A4:I4').format.fill = '#DCEED9';
audit.getRange('A4:I4').format.font.bold = true;
audit.getRange('A:A').format.columnWidth = 12;
audit.getRange('B:B').format.columnWidth = 18;
audit.getRange('C:C').format.columnWidth = 55;
audit.getRange('D:D').format.columnWidth = 28;
audit.getRange('E:E').format.columnWidth = 76;
audit.getRange('F:F').format.columnWidth = 24;
audit.getRange('G:G').format.columnWidth = 39;
audit.getRange('H:H').format.columnWidth = 20;
audit.getRange('I:I').format.columnWidth = 62;
audit.getRange('A5:I108').format.wrapText = true;
await first.recalculate();
console.log((await first.inspect({ kind: 'region', sheetId: 'Estado verificación 25-09', range: 'A4:E9', maxChars: 1800 })).ndjson);
await fs.mkdir(path.dirname(outputPath), { recursive: true });
await (await SpreadsheetFile.exportXlsx(first)).save(outputPath);
console.log(JSON.stringify({ outputPath, rows: rows.length, priorLinks: rows.filter((row) => row[8]).length }));
