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
