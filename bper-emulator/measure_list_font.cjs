// Measure, in Chrome, the font of the list's Denom. cell: the advance of each character and the kerning of each
// pair, so that the truth knows which names the cell cuts (bper_simulator_truth.list_name_fits); and the geometry of
// the list scrolled to its end, so that it knows what is left of the identity columns there
// (bper_simulator_truth.list_end_shows).
//
//   node bper-emulator/measure_list_font.cjs --html Simulatore-BPER.html
//
// Writes bper-emulator/list_font_metrics.json: the cell's font, the width up to which a name shows whole
// (innerWidth, list.js nameLimit), the widths in px, and "end" (reference px at 842 x 617). Rerun it when list.css
// or list.js change the list's columns or font, then check with audit_truth.cjs. Playwright comes from
// PLAYWRIGHT_MODULE, as in capture_bper_dataset.cjs.
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { parseArgs } = require('node:util');

const CHARACTERS = [..."ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ",
    ..."ÀÈÉÌÒÙÁÍÓÚÄËÏÖÜÇÑàèéìòùáíóúäëïöüçñ", ..."'’.,-&/()°\":;+_@#*!?…"];

async function main() {
    const { values } = parseArgs({ options: { html: { type: 'string' } } });
    if (!values.html) throw new Error('Uso: node bper-emulator/measure_list_font.cjs --html PAGINA.html');
    const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
    const browser = await chromium.launch({ channel: 'chrome' });
    try {
        const page = await browser.newPage({ viewport: { width: 842, height: 617 }, deviceScaleFactor: 1, offline: true });
        await page.goto(pathToFileURL(path.resolve(values.html)).href + '?capture=1&practice=demo#1');
        await page.waitForFunction(() => document.querySelector('.bl-results td[data-field="denominazione"]'));
        const metrics = await page.evaluate(characters => {
            const td = document.querySelector('.bl-results td[data-field="denominazione"]');
            const style = getComputedStyle(td);
            const font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
            const ctx = document.createElement('canvas').getContext('2d');
            ctx.font = font;
            const width = text => ctx.measureText(text).width;
            const round = value => Math.round(value * 10000) / 10000;
            const advance = Object.fromEntries(characters.map(c => [c, round(width(c))]));
            const kerning = {};
            for (const a of characters) {
                for (const b of characters) {
                    const adjust = width(a + b) - width(a) - width(b);
                    if (Math.abs(adjust) > 0.0005) kerning[a + b] = round(adjust);
                }
            }
            return { font, innerWidth: BperList.nameLimit, advance, kerning };
        }, CHARACTERS);
        // The demo practice at the end of the scroll (screen 3): its name is whole and wider than the label.
        await page.goto(pathToFileURL(path.resolve(values.html)).href + '?capture=1&practice=demo#3');
        await page.waitForFunction(() => document.querySelector('#screen')?.value === '3' &&
            document.querySelector('.bl-scroll')?.scrollLeft > 0);
        metrics.end = await page.evaluate(() => {
            const scroll = document.querySelector('.bl-scroll');
            const table = scroll.querySelector('table');
            const box = scroll.getBoundingClientRect(), whole = table.getBoundingClientRect();
            const [, , ndgCell, nameCell] = table.tBodies[0].rows[0].cells;
            const [, , , label, first] = table.tHead.rows[0].cells;
            const style = getComputedStyle(nameCell);
            const content = nameCell.getBoundingClientRect().width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
            const pinned = first.getBoundingClientRect().left - whole.left;
            const range = document.createRange();
            const textLeft = cell => { range.selectNodeContents(cell); return range.getBoundingClientRect().left - box.left; };
            range.selectNodeContents(label);
            const icon = label.lastElementChild;
            const labelWidth = range.getBoundingClientRect().width;
            // Where each text starts with the table at scroll 0 and nothing stuck: undo the scroll and the shift.
            const shift = name => parseFloat(table.style.getPropertyValue(name)) - scroll.scrollLeft;
            const round = value => Math.round(value * 10000) / 10000;
            // The Evidenze column: as wide as its label, or as its marks and chip need (an invented practice's other
            // marks, BperList.markShare): its width now, the label's, the cell without marks and one mark's slot.
            const heads = table.tHead.rows[0].cells, cells = table.tBodies[0].rows[0].cells;
            const evidenceHead = heads[heads.length - 2], evidenceCell = cells[cells.length - 2];
            const cellStyle = getComputedStyle(evidenceCell);
            const width = round(evidenceHead.getBoundingClientRect().width);
            // Without its marks the cell leaves the column to its label.
            const marks = [...evidenceCell.querySelectorAll('.bl-mark')];
            marks.forEach(mark => { mark.style.display = 'none'; });
            const evidenceLabel = evidenceHead.getBoundingClientRect().width;
            marks.forEach(mark => { mark.style.display = ''; });
            const chip = evidenceCell.querySelector('.bl-version');
            const evidence = {
                evidence: width, evidenceLabel: round(evidenceLabel),
                chip: round(parseFloat(cellStyle.paddingLeft) + parseFloat(cellStyle.paddingRight) + chip.getBoundingClientRect().width +
                    parseFloat(getComputedStyle(chip).marginLeft)),
                slot: round(evidenceCell.querySelector('.bl-mark').getBoundingClientRect().width),
            };
            // An APP row's checkbox widens NDG, and moves it and the name right by as much (ABI stays).
            const ndgHead = heads[2], before = ndgHead.getBoundingClientRect().width;
            table.classList.add('bl-selectable');
            const checkbox = round(ndgHead.getBoundingClientRect().width - before);
            table.classList.remove('bl-selectable');
            // Screen 1 (the capture window's start offset) shows Stato, Fase and Creazione left of the pinned Evidenze:
            // where each text starts at scroll 0, less the demo's name (a practice adds its own), its width, and the
            // actions' width.
            const ends = document.createRange();
            const textBox = cell => { ends.selectNodeContents(cell); return ends.getBoundingClientRect(); };
            const columns = Object.fromEntries([[7, 'stato'], [8, 'fase'], [9, 'creazione']].map(([index, field]) => {
                const text = textBox(cells[index]);
                return [field, [round(text.left - box.left + scroll.scrollLeft - content), round(text.width)]];
            }));
            return {
                view: round(box.width), rest: round(whole.width - pinned), pinned: round(pinned - content),
                label: round(labelWidth + parseFloat(getComputedStyle(icon).marginRight)),
                ndg: round(textLeft(ndgCell) - shift('--bl-pin-ndg')), name: round(textLeft(nameCell) - shift('--bl-pin-name')),
                settle: BperList.settled.slice(2), ...evidence, checkbox, selectable: BperList.selectable,
                markShare: BperList.markShare, maxMarks: BperList.maxMarks, columns, actions: round(heads[heads.length - 1].getBoundingClientRect().width),
                start: BperList.startingOffset,
            };
        });
        const target = path.join(__dirname, 'list_font_metrics.json');
        fs.writeFileSync(target, JSON.stringify(metrics) + '\n');
        console.log(`${target}: ${Object.keys(metrics.advance).length} caratteri, ${Object.keys(metrics.kerning).length} coppie`);
    } finally {
        await browser.close();
    }
}

main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
});
