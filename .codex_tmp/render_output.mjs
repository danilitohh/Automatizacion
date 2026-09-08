import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = process.argv[2];
const outputPath = process.argv[3];
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const blob = await workbook.render({ sheetName: "Bloque 1 Prod", range: "A1:Q47", scale: 1 });
await blob.save(outputPath);
console.log(outputPath);
