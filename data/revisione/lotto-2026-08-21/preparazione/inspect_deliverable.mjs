import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const requireRuntime = createRequire('C:/Users/alfio/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json');
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(requireRuntime.resolve('@oai/artifact-tool')).href);
const output = 'D:/Projects/poc-data-extraction/outputs/01a164f0-97a1-7433-b313-b15481e862d4';
let workbook;
try {
  workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(`${output}/Revisione_10_pratiche_agosto_da_compilare.xlsx`));
} catch (error) {
  console.error(String(error.message).slice(0, 2000));
  process.exit(1);
}
for (const [sheetName, range, filename] of [['Revisione', 'C67:H70', 'final_fidi_preview.png'], ['Revisione', 'C157:H159', 'final_fidi_columns_preview.png'], ['Istruzioni', 'A1:A15', 'final_instructions_preview.png']]) {
  const blob = await workbook.render({ sheetName, range, scale: 1, format: 'png' });
  await fs.writeFile(`${output}/${filename}`, new Uint8Array(await blob.arrayBuffer()));
}
console.log('Final workbook reopened and rendered.');
process.exit(0);
