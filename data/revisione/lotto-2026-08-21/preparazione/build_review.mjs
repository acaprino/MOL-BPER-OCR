import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const runtimeRequire = createRequire('C:/Users/alfio/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json');
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(runtimeRequire.resolve('@oai/artifact-tool')).href);
const outputDir = 'D:/Projects/poc-data-extraction/outputs/01a164f0-97a1-7433-b313-b15481e862d4';
const inventory = JSON.parse(await fs.readFile(`${outputDir}/annotation_inventory.json`, 'utf8'));
const contextData = JSON.parse(await fs.readFile(`${outputDir}/context_images.json`, 'utf8'));
const contexts = new Map(contextData.images.map(item => [item.screen, item]));
const fieldCardData = JSON.parse(await fs.readFile(`${outputDir}/audit/field_cards.json`, 'utf8'));
const fieldCards = new Map(fieldCardData.rows.map(item => [`${item.screen}/${item.field_key}`, item]));
const existingResponses = JSON.parse(await fs.readFile(`${outputDir}/audit/existing_responses.json`, 'utf8'));
const workbook = Workbook.create();
const instructions = workbook.worksheets.add('Istruzioni');
const review = workbook.worksheets.add('Revisione');
const screenshots = workbook.worksheets.add('Schermate');
const navy = '#1F4E78';
const inputFill = '#FFF2CC';
const ink = '#172B4D';
const navigationLinks = [];

function addNavigationLink(sheet, address, location, label) {
  sheet.getRange(address).values = [[label]];
  sheet.getRange(address).format.font = { name: 'Arial', size: 10, color: navy };
  navigationLinks.push({ sheet: sheet.name, address, location, label });
}

for (const sheet of [instructions, review, screenshots]) {
  sheet.showGridLines = false;
}

const instructionLines = [
  'Annotazione delle 10 pratiche di agosto',
  '34 schermate e 320 campi da verificare. Compila questo nuovo lotto; la revisione delle altre 12 pratiche è già completata.',
  '',
  'Cosa compilare',
  'Nel foglio Revisione compila solo le celle gialle: Trascrizione, Esito e Note. Le risposte sono inizialmente vuote.',
  'Il bordo rosso indica il testo da leggere; più bordi possono appartenere allo stesso campo. Non trascrivere icone o badge. Il nome della schermata apre l’immagine completa.',
  'Trascrivi esattamente il testo visibile, conservando zeri iniziali, cifre, separatori, punteggiatura, a capo e puntini di troncamento. N/D è testo.',
  '',
  'Come scegliere Esito',
  'TRASCRITTO: il valore è interamente visibile e leggibile. Scrivilo nella colonna Trascrizione.',
  'VUOTO: la posizione del campo è visibile ed effettivamente vuota. Lascia vuota Trascrizione.',
  'NON LEGGIBILE: il valore è presente ma non si riesce a leggerlo con certezza. Spiega il dubbio nelle Note.',
  'NON VISIBILE: il campo è fuori dall’immagine, coperto da un tooltip o nascosto dallo scorrimento. Non equivale a vuoto.',
  'PARZIALE: è leggibile solo una parte del valore. Trascrivi solo quella parte e specifica nelle Note cosa manca.',
  'Una riga senza Esito è ancora da compilare. Non copiare valori da altre schermate e non completare parti nascoste.',
  '',
  'Indicazioni per i campi',
  'Il numero della pratica identifica il caso; non è il valore NDG. Leggi sempre NDG dall’immagine.',
  'Fidi: usa la prima riga della tabella FIDI visibile, mantenendo insieme numero, rapporto, descrizione, scadenza, importo e tipo operazione. Non usare la tabella Garanzie.',
  'Soggetti: numera le righe dall’alto (1–4) e mantieni insieme NDG, denominazione e ruolo. Indica VUOTO per un soggetto assente solo se la fine della tabella è visibile.',
  'Note da Richiesta: trascrivi il contenuto visibile, senza completare il testo oltre il riquadro. In Note_chiuso della pratica 51800301 le note sono visibili solo in parte.',
  'I ritagli sono specifici per campo e visualizzati senza riduzione. Il testo dentro i riquadri conserva i pixel originali. Le schermate complete restano inalterate nel foglio Schermate.',
  'Non ordinare le righe del foglio Revisione: le immagini sono associate alla disposizione delle righe. Per spostarti usa i collegamenti e il numero della pratica.',
  '',
  'Perimetro di questo lotto',
  'Sono comprese tutte le 34 schermate utili delle 10 pratiche. Le 4 schermate Note a Istruttoria sono escluse dal lotto di annotazione.',
  'Sono presenti 11 tooltip dei campi previsti. Altri 6 tooltip mostrano contenuti diversi: nelle relative schermate annota solo i campi elencati, senza attribuire il popup a un altro campo.',
  'Questo lotto non contiene Scheda Privati né il tooltip Descrizione BMB. Servono ulteriori pratiche per verificarli.',
  '',
  'Richiesta di nuove pratiche',
  'Obiettivo: 20 nuove pratiche complete, eventualmente in due lotti da 10. Devono essere diverse dalle pratiche già fornite.',
  'Dare priorità a Scheda Privati compilata, tooltip M-CONSAP e CONSAP DR BIS, tabelle Fidi con più righe, Soggetti e Note da Richiesta.',
  'Per ogni pratica includere tutte le pagine utili, gli eventuali scorrimenti e i tooltip aperti, mantenendo le normali condizioni di acquisizione sul PC o sulla VDI.',
  'Accompagnare le nuove schermate con i valori corretti verificati, indicando anche campi vuoti, parti non visibili e parti non leggibili.',
];
instructions.getRange(`A1:A${instructionLines.length}`).values = instructionLines.map(value => [value]);
instructions.getRange(`A1:A${instructionLines.length}`).format = { font: { name: 'Arial', size: 11, color: ink }, wrapText: true, verticalAlignment: 'center', rowHeight: 38, columnWidthPx: 1120 };
instructions.getRange('A1').format.font = { name: 'Arial', size: 16, bold: true, color: navy };
instructions.getRange('A1').format.rowHeight = 34;
for (const row of [4, 9, 17, 25, 30]) {
  instructions.getRange(`A${row}`).format.font = { name: 'Arial', size: 12, bold: true, color: navy };
  instructions.getRange(`A${row}`).format.rowHeight = 28;
}
for (let index = 0; index < instructionLines.length; index++) {
  if (!instructionLines[index]) instructions.getRange(`A${index + 1}`).format.rowHeight = 12;
}

const rowsByScreen = new Map();
inventory.annotations.forEach((item, index) => {
  if (!rowsByScreen.has(item.screen)) rowsByScreen.set(item.screen, index + 2);
});
instructions.getRange('A37').values = [['Vai alla pratica']];
instructions.getRange('A37').format = { font: { name: 'Arial', size: 12, bold: true, color: navy }, rowHeight: 28 };
const practiceIds = [...new Set(inventory.screens.map(item => item.practice))];
practiceIds.forEach((practice, index) => {
  const screens = inventory.screens.filter(item => item.practice === practice);
  const count = inventory.annotations.filter(item => item.practice === practice).length;
  const firstRow = rowsByScreen.get(screens[0].screen);
  addNavigationLink(instructions, `A${index + 38}`, `'Revisione'!A${firstRow}`, `Pratica ${practice} (${screens.length} schermate, ${count} campi)`);
  instructions.getRange(`A${index + 38}`).format = { font: { name: 'Arial', size: 11, color: navy }, rowHeight: 26 };
});
const screenshotRows = new Map();
screenshots.getRange('A:L').format.columnWidthPx = 100;
let imageRow = 2;
for (const screen of inventory.screens) {
  const context = contexts.get(screen.screen);
  if (!context) throw new Error(`Missing context: ${screen.screen}`);
  const width = Math.min(1200, context.original_width);
  const height = context.original_height * width / context.original_width;
  const blockRows = Math.ceil(height / 32) + 5;
  screenshotRows.set(screen.screen, imageRow);
  screenshots.getRange(`A${imageRow}:L${imageRow + blockRows - 1}`).format = { font: { name: 'Arial', size: 11, color: ink }, rowHeightPx: 32 };
  screenshots.getRange(`A${imageRow}`).values = [[`Pratica ${screen.practice} / ${screen.filename}`]];
  screenshots.getRange(`A${imageRow}`).format.font = { name: 'Arial', size: 12, bold: true, color: navy };
  addNavigationLink(screenshots, `A${imageRow + 1}`, `'Revisione'!A${rowsByScreen.get(screen.screen)}`, 'Torna ai campi da annotare');
  const bytes = await fs.readFile(screen.screenshot_path);
  screenshots.images.add({ dataUrl: `data:image/png;base64,${bytes.toString('base64')}`, anchor: { from: { row: imageRow + 1, col: 0 }, extent: { widthPx: width, heightPx: height } } });
  imageRow += blockRows;
}

const headers = ['N.', 'Pratica', 'Schermata completa', 'Campo', 'Valore da leggere (riquadro rosso)', 'Trascrizione', 'Esito', 'Note', 'ID schermata'];
const rows = inventory.annotations.map((item, index) => {
  const card = fieldCards.get(`${item.screen}/${item.field_key}`);
  const old = existingResponses[index];
  if (!card || old.screen !== item.screen || old.display_name !== item.display_name) throw new Error('Field identity mismatch');
  const previousGeneratedNote = item.notes.length ? item.notes.join(' ') : null;
  const humanNote = old.note !== previousGeneratedNote ? old.note : null;
  const note = [card.note, humanNote].filter(Boolean).join('\n') || null;
  return [index + 1, item.practice, null, item.display_name, card.image_path ? null : card.cell_text, old.transcription, old.outcome, note, item.screen];
});
review.getRange(`A1:I${rows.length + 1}`).values = [headers, ...rows];
review.getRange(`A1:I${rows.length + 1}`).format = { font: { name: 'Arial', size: 10, color: ink }, verticalAlignment: 'top', wrapText: true };
const widths = { A: 44, B: 92, C: 180, D: 190, E: 1200, F: 280, G: 150, H: 340, I: 240 };
for (const [column, width] of Object.entries(widths)) review.getRange(`${column}1:${column}${rows.length + 1}`).format.columnWidthPx = width;
review.getRange('A1:I1').format = { fill: navy, font: { name: 'Arial', size: 10, bold: true, color: '#FFFFFF' }, wrapText: true, horizontalAlignment: 'center', verticalAlignment: 'center', rowHeight: 36 };
review.getRange(`F2:H${rows.length + 1}`).format.fill = inputFill;
review.getRange(`B2:B${rows.length + 1}`).setNumberFormat('@');
review.getRange(`F2:F${rows.length + 1}`).setNumberFormat('@');
review.getRange(`G2:G${rows.length + 1}`).dataValidation = { rule: { type: 'list', values: ['TRASCRITTO', 'VUOTO', 'NON LEGGIBILE', 'NON VISIBILE', 'PARZIALE'] } };
review.getRange(`F2:G${rows.length + 1}`).conditionalFormats.addCustom('AND($G2="TRASCRITTO",$F2="")', { fill: '#FCE4D6', font: { color: '#9C0006' } });
review.getRange(`F2:G${rows.length + 1}`).conditionalFormats.addCustom('AND($G2="VUOTO",$F2<>"")', { fill: '#FCE4D6', font: { color: '#9C0006' } });
review.freezePanes.freezeRows(1);
review.freezePanes.freezeColumns(4);

for (let index = 0; index < inventory.annotations.length; index++) {
  const item = inventory.annotations[index];
  const row = index + 2;
  const card = fieldCards.get(`${item.screen}/${item.field_key}`);
  let width = 0;
  let height = 0;
  if (card.image_path) {
    const scale = Math.min(1184 / card.image_width, 530 / card.image_height, 2.5);
    if (scale < 1) throw new Error(`Image would be reduced: ${item.screen}/${item.field_key}`);
    width = card.image_width * scale;
    height = card.image_height * scale;
  }
  review.getRange(`A${row}:I${row}`).format.rowHeightPx = Math.max(116, height + 12);
  if (index === 0 || inventory.annotations[index - 1].practice !== item.practice) {
    review.getRange(`A${row}:I${row}`).format.borders = { top: { style: 'medium', color: navy } };
  }
  addNavigationLink(review, `C${row}`, `'Schermate'!A${screenshotRows.get(item.screen)}`, `${item.screen.split('__')[1]}.png`);
  if (card.image_path) {
    const bytes = await fs.readFile(card.image_path);
    review.images.add({ dataUrl: `data:image/png;base64,${bytes.toString('base64')}`, anchor: { from: { row: row - 1, col: 4, rowOffsetPx: 6, colOffsetPx: 6 }, extent: { widthPx: width, heightPx: height } } });
  } else {
    review.getRange(`E${row}`).format.fill = '#F2F4F7';
  }
}

workbook.recalculate();
console.log((await workbook.inspect({ kind: 'table', range: 'Revisione!A1:D4', include: 'values,formulas', tableMaxRows: 4, tableMaxCols: 4, maxChars: 1800 })).ndjson);
console.log((await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 20 }, summary: 'Final formula error scan', maxChars: 2000 })).ndjson);
for (const [name, range, filename] of [['Istruzioni', 'A1:A15', 'instructions_preview.png'], ['Revisione', 'C1:H3', 'review_preview.png'], ['Schermate', 'A2:L26', 'screenshots_preview.png']]) {
  const preview = await workbook.render({ sheetName: name, range, scale: 1, format: 'png' });
  await fs.writeFile(`${outputDir}/${filename}`, new Uint8Array(await preview.arrayBuffer()));
}
const outputPath = `${outputDir}/Revisione_10_pratiche_agosto_da_compilare.xlsx`;
await (await SpreadsheetFile.exportXlsx(workbook)).save(outputPath);
await fs.writeFile(`${outputDir}/workbook_metadata.json`, JSON.stringify({ output: outputPath, practices: inventory.counts.practices, screens: inventory.screens.length, annotation_rows: rows.length, screenshot_rows: Object.fromEntries(screenshotRows), review_first_rows: Object.fromEntries(rowsByScreen), navigation_links: navigationLinks, field_card_revision: true, embedded_field_images: fieldCardData.image_count }, null, 2));
console.log(JSON.stringify({ outputPath, rows: rows.length, screens: inventory.screens.length }));
process.exit(0);
