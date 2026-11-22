import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const runtimeRequire = createRequire('C:/Users/alfio/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json');
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(runtimeRequire.resolve('@oai/artifact-tool')).href);

const input = 'D:/Projects/poc-data-extraction/data/revisione/revisione/Revisione_ground_truth_v3_1.xlsx';
const output = 'D:/Projects/poc-data-extraction/outputs/01a164f0-97a1-7433-b313-b15481e862d4';
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
console.log((await workbook.inspect({ kind: 'sheet', include: 'id,name', maxChars: 1200 })).ndjson);
const preview = await workbook.render({ sheetName: 'Revisione', range: 'A1:J3', scale: 1, format: 'png' });
await fs.writeFile(`${output}/reference_review.png`, new Uint8Array(await preview.arrayBuffer()));
console.log('Reference rendered.');
