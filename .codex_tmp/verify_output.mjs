import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = process.argv[2];
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItemAt(0);
const values = sheet.getRange("A1:Q47").values;
const headerIndex = values.findIndex((row) => row.includes("URL_LEAD"));
if (headerIndex < 0) throw new Error("No se encontró URL_LEAD");
const headers = values[headerIndex];
const programIndex = headers.indexOf("Programa");
const leadIndex = headers.indexOf("URL_LEAD");
const pageIndex = headers.indexOf("URL PAGE");
const rows = values.slice(headerIndex + 1).map((row, offset) => ({
  excelRow: headerIndex + offset + 2,
  program: row[programIndex] ?? "",
  page: row[pageIndex] ?? "",
  lead: row[leadIndex] ?? "",
})).filter((row) => row.program && row.page);
const missing = rows.filter((row) => !String(row.lead ?? "").trim());
console.log(JSON.stringify({totalCases: rows.length, withLead: rows.length - missing.length, missing}, null, 2));
