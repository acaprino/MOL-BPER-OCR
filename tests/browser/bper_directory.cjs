// Browser component checks for the rendered practice search and single-result table.
const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const assets = path.resolve(__dirname, '../../bper-emulator/site');
const profiles = Array.from({ length: 10 }, (_, i) => ({
    key: 'fixture-' + i, ndg: '000040' + String(i).padStart(2, '0'),
    number: '8000' + i, name: i === 9 ? 'D’ALBÈRO SOFÌA' : 'VERDI ' + i,
    date: '11/11/2026', state: 'LAV', phase: 'IST', branch: '4571',
    creditTotal: '180.020,35', type: 'BPI Mutui', evidence: '', evidenceTooltip: '',
}));
let browser;
before(async () => { browser = await chromium.launch({ channel: 'chrome' }); });
after(async () => { await browser?.close(); });

async function load(t) {
    const page = await browser.newPage({ viewport: { width: 848, height: 515 } });
    t.after(() => page.close());
    await page.setContent('<section id="list-view"></section><div id="selection"></div>');
    await page.addStyleTag({ path: path.join(assets, 'list.css') });
    await page.addScriptTag({ path: path.join(assets, 'list.js') });
    return page;
}

async function openDirectory(t) {
    const page = await load(t);
    await page.evaluate(practices => {
        BperList.directory(document.querySelector('#list-view'), practices, {
            openPractice: p => { document.querySelector('#selection').textContent = p.number; },
        });
    }, profiles);
    return page;
}

test('search finds dossiers by accent-insensitive name, leading-zero NDG and practice number', async t => {
    const page = await openDirectory(t);
    const search = page.getByRole('searchbox');
    for (const query of ["d'albero sofia", '00004009', '80009']) {
        await search.fill(query);
        const results = page.getByRole('table').locator('tbody tr');
        assert.equal(await results.count(), 1);
        assert.match(await results.innerText(), /D’ALBÈRO SOFÌA/);
        assert.equal(await page.getByRole('status').innerText(), '1 risultato');
    }
    await search.fill('nessuna pratica corrispondente');
    assert.match(await page.getByRole('table').innerText(), /Nessun risultato/);
    await page.getByRole('button', {name: 'Cancella ricerca'}).click();
    assert.equal(await page.getByRole('status').innerText(), '10 risultati');
});

test('the second page opens the selected practice from the keyboard', async t => {
    const page = await openDirectory(t);
    const table = page.getByRole('table');
    assert.equal(await table.getByText('D’ALBÈRO SOFÌA').count(), 0);
    await page.getByRole('button', {name: 'Pagina successiva'}).click();
    const result = table.getByRole('row').filter({ hasText: 'D’ALBÈRO SOFÌA' });
    await result.press('Enter');
    assert.equal(await page.locator('#selection').innerText(), '80009');
    await page.getByRole('button', {name: 'Pagina precedente'}).click();
    assert.equal(await table.getByText('D’ALBÈRO SOFÌA').count(), 0);
});

test('a dossier without evidence shows its real amount and no evidence tooltip', async t => {
    const page = await load(t);
    await page.evaluate(practice => {
        BperList.render(document.querySelector('#list-view'), practice, {
            openPractice: () => {}, onState: () => {},
        });
        BperList.show(3);
    }, profiles[0]);
    assert.match(await page.getByRole('table', { name: 'Elenco pratiche' }).innerText(), /180\.020,35/);
    assert.equal(await page.getByRole('tooltip').count(), 0);
    assert.equal(await page.getByRole('button', { name: /Evidenze/ }).count(), 0);
});

async function renderList(t, practice = profiles[0]) {
    const page = await load(t);
    await page.evaluate(practice => {
        BperList.render(document.querySelector('#list-view'), practice, {
            openPractice: () => { document.querySelector('#selection').textContent += 'opened;'; },
            onState: () => {},
        });
        BperList.show(1);
    }, practice);
    return page;
}

test('a click on the list row does not open the practice', async t => {
    const page = await renderList(t);
    await page.getByRole('table', { name: 'Elenco pratiche' }).getByRole('cell', { name: 'VERDI 0' }).click();
    assert.equal(await page.locator('#selection').innerText(), '');
});

test('the row actions menu opens the practice', async t => {
    const page = await renderList(t);
    await page.getByRole('button', { name: 'Azioni pratica 80000' }).click();
    assert.deepEqual(await page.getByRole('menuitem').allInnerTexts(),
        ['Avvia Lavorazione', 'Visualizza Pratica', 'Monitoraggio Pratica', 'Sospendi', 'Abbandona']);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    assert.equal(await page.locator('#selection').innerText(), 'opened;');
    assert.equal(await page.getByRole('menu').count(), 0);
});

test('escape closes the row actions menu and returns to its button', async t => {
    const page = await renderList(t);
    const kebab = page.getByRole('button', { name: 'Azioni pratica 80000' });
    await kebab.focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('menu').count(), 0);
    assert.equal(await kebab.evaluate(button => button === document.activeElement), true);
    assert.equal(await page.locator('#selection').innerText(), '');
});

test('hovering the name shows it in full beside the pointer', async t => {
    const page = await renderList(t, { ...profiles[0], name: 'VERDI GIOVANNI MARIA ANTONIETTA' });
    const cell = page.getByRole('cell', { name: 'VERDI GIOVANNI MARIA ANTONIETTA' });
    const box = await cell.boundingBox();
    await page.mouse.move(box.x + 12, box.y + 9);
    const tooltip = page.getByRole('tooltip');
    assert.equal(await tooltip.innerText(), 'VERDI GIOVANNI MARIA ANTONIETTA');
    const tip = await tooltip.boundingBox();
    // Reference screen 3 puts the box 11 px right of and 6 px below the pointer.
    assert.deepEqual([Math.round(tip.x - box.x - 12), Math.round(tip.y - box.y - 9)], [11, 6]);
    await page.mouse.move(2, 2);
    assert.equal(await page.getByRole('tooltip').count(), 0);
});

test('a long name is cut on one line with an ellipsis inside its column', async t => {
    // The video's list shows a long joint name as "LA ROSA ..." in a one-line row (spec sections 6 and 15), in a box
    // as wide as the column's label; the column falls back to the label: 102-104 CSS px at 100%, 74-75 here (19.3).
    const page = await renderList(t, { ...profiles[0], name: 'VERDI GIOVANNI MARIA ANTONIETTA' });
    const cell = page.getByRole('cell', { name: 'VERDI GIOVANNI MARIA ANTONIETTA' });
    const shape = await cell.evaluate(td => {
        const box = td.querySelector('[data-field="denominazione"]');
        const range = document.createRange();
        range.selectNodeContents(box);
        const lines = new Set([...range.getClientRects()].map(rect => Math.round(rect.top)));
        return { lines: lines.size, cut: box.scrollWidth > box.clientWidth, ellipsis: getComputedStyle(box).textOverflow,
            rowHeight: td.parentElement.getBoundingClientRect().height, width: td.getBoundingClientRect().width };
    });
    assert.ok(Math.abs(shape.width - 75) <= 2, `column ${shape.width} px`);
    delete shape.width;
    assert.deepEqual(shape, { lines: 1, cut: true, ellipsis: 'ellipsis', rowHeight: 36 });
});

// The Denom. column of a one-row list for the given name: its width, and whether the name shows whole.
async function nameColumn(t, name) {
    const page = await renderList(t, { ...profiles[0], name });
    return page.getByRole('cell', { name }).evaluate(td => {
        const shown = td.querySelector('[data-field="denominazione"]') || td;
        const range = document.createRange();
        range.selectNodeContents(td);
        return { width: td.getBoundingClientRect().width, text: range.getBoundingClientRect().width,
            whole: shown === td && td.scrollWidth <= td.clientWidth };
    });
}

test('a name up to 127 px shows whole and sizes its column; a wider one is cut and the column keeps the label width', async t => {
    // The same boundary as the truth (bper_simulator_truth.list_name_fits): 126.06 px fits, 127.24 px is cut.
    const fits = await nameColumn(t, 'ROCCAFORTE ROSALBA');
    const shorter = await nameColumn(t, 'VERDI GIOVANNI');
    const cut = await nameColumn(t, 'BELLAVISTA BENEDETTA');
    const longer = await nameColumn(t, 'BELLAVISTA BENEDETTA MARIA ANTONIETTA ROSALBA');
    assert.deepEqual([fits.whole, shorter.whole], [true, true]);
    // The column follows the text: the same padding around either name.
    assert.ok(Math.abs((fits.width - fits.text) - (shorter.width - shorter.text)) < 0.5);
    assert.ok(fits.width - shorter.width > 30, `${fits.width} vs ${shorter.width} px`);
    assert.deepEqual([cut.whole, longer.whole], [false, false]);
    assert.equal(cut.width, longer.width);
    assert.ok(cut.width < fits.width - 60, `cut column ${cut.width} px`);
});

async function textEdges(page) {
    return page.getByRole('table', { name: 'Elenco pratiche' }).evaluate(table => [1, 2, 3].map(i => {
        const range = document.createRange();
        range.selectNodeContents(table.tBodies[0].rows[0].cells[i]);
        const box = range.getBoundingClientRect();
        return [box.left, box.right];
    }));
}

test('an APP or ABB row adds a checkbox and moves NDG and what follows 30 CSS px right, not ABI', async t => {
    // MOL 05 51:25 and MOL 06 11:23 (spec 19.3 point 3): ABI keeps its place, the ABI-NDG gap grows from 49 to 79-80 px
    // at 100% (21.7 px here).
    const plain = await textEdges(await renderList(t));
    for (const state of ['APP', 'ABB']) {
        const page = await renderList(t, { ...profiles[0], state });
        assert.equal(await page.getByRole('checkbox', { name: 'Seleziona pratica 80000' }).count(), 1);
        const [abi, ndg, name] = await textEdges(page);
        assert.ok(Math.abs(abi[1] - plain[0][1]) < 0.5, `ABI moved ${abi[1] - plain[0][1]} px`);
        assert.ok(Math.abs(ndg[1] - plain[1][1] - 21.7) < 1, `NDG moved ${ndg[1] - plain[1][1]} px`);
        assert.ok(Math.abs(name[0] - plain[2][0] - 21.7) < 1, `Denom. moved ${name[0] - plain[2][0]} px`);
    }
    assert.equal(await (await renderList(t)).getByRole('checkbox').count(), 0);
});

async function typeCell(page) {
    await page.getByRole('scrollbar', { name: /Scorri le colonne/ }).press('Home');
    return page.getByRole('table', { name: 'Elenco pratiche' }).getByRole('cell').nth(5);
}

test('the type cell shows the product code and its hover the long name', async t => {
    const page = await renderList(t, { ...profiles[0], typeCode: 'BMS', typeName: 'BPI Mutui Standard' });
    const cell = await typeCell(page);
    assert.equal(await cell.innerText(), 'BMS');
    await cell.hover();
    assert.equal(await page.getByRole('tooltip').innerText(), 'BPI Mutui Standard');
});

test('without a product code the type cell shows the product type', async t => {
    const page = await renderList(t);
    assert.equal(await (await typeCell(page)).innerText(), 'BPI Mutui');
});

test('hovering the evidence shows its description beside the pointer', async t => {
    const page = await renderList(t, { ...profiles[0], evidence: 'B', evidenceTooltip: 'Origination BSTORE' });
    const box = await page.getByRole('button', { name: 'Evidenze B' }).boundingBox();
    await page.mouse.move(box.x + 3, box.y + 4);
    const tip = await page.getByRole('tooltip').boundingBox();
    assert.deepEqual([Math.round(tip.x - box.x - 3), Math.round(tip.y - box.y - 4)], [11, 6]);
});

test('the extended list shows the stored assignment date', async t => {
    const page = await load(t);
    await page.evaluate(practice => {
        BperList.render(document.querySelector('#list-view'), practice, { openPractice() {}, onState() {} });
        BperList.show(2);
    }, { ...profiles[0], assigned: '14/11/2026' });
    assert.equal(await page.getByRole('cell', { name: '14/11/2026', exact: true }).count(), 1);
});

test('the icon legend link shows above a list with rows, with or without evidence', async t => {
    // Every calibration Elenco screenshot shows "Legenda Icone", also over rows without an evidence code.
    const page = await renderList(t);
    assert.equal(await page.getByText('Legenda Icone').isVisible(), true);
});

// The Evidenze cell of a one-row list: the centre of each code letter group, the 2.0 chip and the actions cell, in px.
async function evidenceCell(t, evidence, evidenceTooltip = '') {
    const page = await renderList(t, { ...profiles[0], evidence, evidenceTooltip });
    const shape = await page.getByRole('table', { name: 'Elenco pratiche' }).evaluate(table => {
        const row = table.tBodies[0].rows[0];
        const field = row.querySelector('[data-field="evidenze"]');
        const marks = [];
        if (field) {
            // One centre per run of letters: "B V" has two codes, "BC" one.
            const range = document.createRange();
            const walker = document.createTreeWalker(field, NodeFilter.SHOW_TEXT);
            for (let node; (node = walker.nextNode());) {
                for (const match of node.data.matchAll(/\S+/g)) {
                    range.setStart(node, match.index);
                    range.setEnd(node, match.index + match[0].length);
                    const box = range.getBoundingClientRect();
                    marks.push(box.left + box.width / 2);
                }
            }
        }
        const chip = row.querySelector('.bl-version').getBoundingClientRect();
        const style = field && getComputedStyle(field);
        return { text: field?.textContent, marks, chip: { left: chip.left, right: chip.right },
            actions: row.cells[row.cells.length - 1].getBoundingClientRect().left,
            look: style && [style.fontSize, style.fontWeight, style.color] };
    });
    return { page, ...shape };
}

test('each evidence code is a mark of its own, packed leftwards from the 2.0 chip', async t => {
    // Calibration screens at 90-100%: the marks sit in 25.5 CSS px slots (18.5 here); the nearest one is centred where
    // reference screens 1-3 have the lone B, 10.7 px left of the chip (the calibration screens: 12).
    const two = await evidenceCell(t, 'B V', 'Origination BSTORE');
    assert.equal(two.text.replace(/\s+/g, ' ').trim(), 'B V');
    assert.equal(two.marks.length, 2);
    assert.ok(Math.abs(two.marks[1] - two.marks[0] - 18.5) <= 0.5, `marks ${two.marks.map(x => x.toFixed(1))}`);
    assert.ok(Math.abs(two.chip.left - two.marks[1] - 10.7) <= 0.75, `last mark ${(two.chip.left - two.marks[1]).toFixed(1)} px from the chip`);
    const one = await evidenceCell(t, 'BC');
    assert.ok(Math.abs(one.chip.left - one.marks[0] - 10.7) <= 0.75, `BC ${(one.chip.left - one.marks[0]).toFixed(1)} px from the chip`);
});

test('the 2.0 chip keeps its place before the actions whatever the evidence, as in the real cell', async t => {
    // Calibration screens: chip to actions 47.5 ref px whether the cell holds one mark or six; the emulator's chip ends where
    // reference screens 1-3 have it, 38.3 px before the actions column.
    const gaps = [];
    for (const [evidence, tip] of [['', ''], ['B', 'Origination BSTORE'], ['B V', 'Origination BSTORE'], ['BM', '']]) {
        const cell = await evidenceCell(t, evidence, tip);
        gaps.push(cell.actions - cell.chip.right);
    }
    assert.ok(gaps.every(gap => Math.abs(gap - 38.3) <= 0.5), `chip to actions ${gaps.map(g => g.toFixed(2))}`);
});

test('a code without a description is drawn like the B code that has one', async t => {
    // BC and BM (no description in the data) show in the same small green bold letters as B in the calibration screens.
    const plain = await evidenceCell(t, 'BC');
    const described = await evidenceCell(t, 'B', 'Origination BSTORE');
    assert.deepEqual(plain.look, described.look);
});

test('at rest the evidence tooltip sits beside its B mark, wherever the mark is', async t => {
    // Reference screen 3 puts the box 10.8 px right of the B's centre and 9 px under the row's middle; in the real cell the
    // B moves left when other marks follow it, and its tooltip with it.
    for (const evidence of ['B', 'B V']) {
        const page = await load(t);
        await page.evaluate(practice => {
            BperList.render(document.querySelector('#list-view'), practice, { openPractice() {}, onState() {} });
            BperList.show(3);
        }, { ...profiles[0], evidence, evidenceTooltip: 'Origination BSTORE' });
        const place = await page.evaluate(() => {
            const field = document.querySelector('.bl-results [data-field="evidenze"]');
            const range = document.createRange();
            const node = field.querySelector('*')?.firstChild ?? field.firstChild;
            range.setStart(node, node.data.indexOf('B'));
            range.setEnd(node, node.data.indexOf('B') + 1);
            const mark = range.getBoundingClientRect();
            const row = document.querySelector('.bl-results tbody tr').getBoundingClientRect();
            const tip = document.querySelector('#bper-evidence-tooltip').getBoundingClientRect();
            return [tip.left - (mark.left + mark.width / 2), tip.top - (row.top + row.height / 2)];
        });
        assert.ok(Math.abs(place[0] - 10.8) <= 0.75 && Math.abs(place[1] - 9) <= 0.75, `${evidence}: ${place.map(v => v.toFixed(2))}`);
    }
});

// The marks of each row's Evidenze cell (data-mark: a code's letters, or the kind of mark) for many practices at once.
async function cellMarks(t, practices) {
    const page = await load(t);
    return page.evaluate(list => list.map(practice => {
        BperList.render(document.querySelector('#list-view'), practice, { openPractice() {}, onState() {} });
        const field = document.querySelector('.bl-results [data-field="evidenze"]');
        return { marks: [...field.querySelectorAll('[data-mark]')].map(mark => mark.dataset.mark),
            text: field.textContent.replace(/\s+/g, ' ').trim() };
    }), practices);
}

const ORDER = ['clip', 'note', 'B', 'diamond', 'V', 'loop', 'p'];
const invented = Array.from({ length: 240 }, (_, i) => ({
    ...profiles[0], key: 'sim-' + String(i + 1).padStart(3, '0'), role: 'sintetica', evidence: 'B V' }));

test('an invented practice shows the other marks of the real cell around its codes, in the real order', async t => {
    // Calibration fold, 12 list rows: clip, note bubble, the B code, diamond, V, loop arrow, pink P, always in this order.
    for (const { marks, text } of await cellMarks(t, invented)) {
        assert.equal(text, 'B V');
        assert.deepEqual(marks, ORDER.filter(kind => marks.includes(kind)), marks.join(' '));
    }
});

test('the other marks show about as often as in the calibration fold, the same for the same practice', async t => {
    // Rows with the mark in the 12 calibration rows: clip 11, note 4, diamond 3, loop 6, P 6.
    const expected = { clip: 11 / 12, note: 4 / 12, diamond: 3 / 12, loop: 6 / 12, p: 6 / 12 };
    const first = await cellMarks(t, invented);
    for (const [kind, share] of Object.entries(expected)) {
        const seen = first.filter(cell => cell.marks.includes(kind)).length / first.length;
        assert.ok(Math.abs(seen - share) <= 0.08, `${kind}: ${seen.toFixed(2)} of the rows, expected ${share.toFixed(2)}`);
    }
    assert.deepEqual(await cellMarks(t, invented.slice(0, 20)), first.slice(0, 20));
});

test('an archive practice and the reference show their codes alone', async t => {
    // What the other marks of a real practice are is not known: they are not invented for it.
    const cells = await cellMarks(t, [{ ...invented[0], role: 'addestramento' }, { ...invented[0], role: undefined }]);
    assert.deepEqual(cells.map(cell => cell.marks), [['B', 'V'], ['B', 'V']]);
});

test('an invented practice draws the marks the truth counts for it', async t => {
    // bper_simulator_truth.evidence_slots counts six for sim-029 (tests/test_bper_simulator_truth.py): the list's
    // geometry at the end of the scroll depends on it.
    const [cell] = await cellMarks(t, [{ ...profiles[0], key: 'sim-029', role: 'sintetica', evidence: 'B' }]);
    assert.deepEqual(cell.marks, ['clip', 'note', 'B', 'diamond', 'loop', 'p']);
});

test('a row draws at most six marks, the most a calibration row shows', async t => {
    // gen2-024 would draw seven: the rarest other mark (the diamond) is left out.
    const [cell] = await cellMarks(t, [{ ...profiles[0], key: 'gen2-024', role: 'sintetica', evidence: 'B V' }]);
    assert.deepEqual(cell.marks, ['clip', 'note', 'B', 'V', 'loop', 'p']);
});
