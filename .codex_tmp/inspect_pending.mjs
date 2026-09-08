import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = process.argv[2];
if (!inputPath) {
  throw new Error("Falta la ruta del archivo XLSX.");
}

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 20000,
  tableMaxRows: 80,
  tableMaxCols: 20,
  tableMaxCellChars: 200,
});

process.stdout.write(overview.ndjson);
