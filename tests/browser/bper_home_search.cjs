// Home, Ricerca Pratica and the "pratica già in lavorazione" dialog of Nuova PEF (video spec sections 3-5 and 8).
// Run against the local simulator (BPER_TEST_URL) with Playwright and Chrome installed.
const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const base = process.env.BPER_TEST_URL || 'http://127.0.0.1:8765';
const MESSAGE = 'PDCGPC0002A :Attenzione! Pratica chiusa in modo anomalo oppure già in lavorazione su altro terminale, continuare?';
let browser;

before(async () => { browser = await chromium.launch({ channel: 'chrome' }); });
after(async () => { await browser?.close(); });

// The operator's screen: 1280 x 897 CSS px at 100% zoom (spec section 16.1).
async function open(t, path = '/') {
    const page = await browser.newPage({ viewport: { width: 1280, height: 897 } });
    t.after(() => page.close());
    await page.goto(new URL(path, base).href);
    await page.locator('#frame[data-ready]').waitFor({ timeout: 4000 });
    return page;
}

async function catalogue(page) {
    return page.evaluate(async () => (await (await fetch('/api/practices.json')).json()).practices);
}

const tab = (page, name) => page.getByRole('button', { name, exact: true });

async function visibleTabs(page) {
    const names = [];
    for (const name of ['Home', 'Ricerca Pratica', 'Elenco Pratiche']) if (await tab(page, name).count()) names.push(name);
    if (await page.getByRole('button', { name: /^PEF 2\.0 - Pratica/ }).count()) names.push('practice');
    return names;
}

async function current(page) {
    return page.evaluate(() => [...document.querySelectorAll('.pef-nav [aria-current="page"]')]
        .filter(tab => !tab.hidden).map(tab => tab.getAttribute('aria-label') || tab.textContent.trim()));
}

async function openSearch(page) {
    await page.getByRole('button', { name: 'RICERCA', exact: true }).click();
    await page.getByRole('textbox', { name: 'N° PRATICA' }).waitFor({ timeout: 2000 });
}

// The rows of the operator's results table, as [NDG, Denom., N°, Stato].
async function resultRows(page) {
    await tab(page, 'Elenco Pratiche').waitFor({ timeout: 5000 });
    await page.waitForFunction(() => !document.querySelector('#list-view').hidden);
    return page.getByRole('table', { name: 'Elenco pratiche' }).evaluate(table =>
        [...table.tBodies[0].rows].map(row => [...row.cells].map(cell => cell.textContent.trim()))
            .map(cells => cells.length > 4 ? [cells[2], cells[3], cells[4], cells[7]] : cells));
}

async function chooseStates(page, keep) {
    await page.getByRole('button', { name: 'STATO' }).click();
    for (const state of ['In Lavorazione', 'In Attesa', 'Sospesa', 'Respinta', 'Abbandonata']) {
        const box = page.getByRole('checkbox', { name: state });
        if (await box.evaluate(input => input.checked) !== keep.includes(state)) await box.click();
    }
    await page.keyboard.press('Escape');
}

test('the application opens on the home page with only the home tab', async t => {
    const page = await open(t);
    assert.deepEqual(await visibleTabs(page), ['Home']);
    assert.deepEqual(await current(page), ['Home']);
    const home = page.getByRole('region', { name: 'Home' });
    assert.equal(await home.getByRole('button', { name: 'RIEPILOGO RICHIESTA STAMPE' }).count(), 1);
    assert.equal(await home.getByRole('button', { name: 'RICERCA', exact: true }).count(), 1);
    for (const [label, value] of [['PROVENIENZA', 'Tutte'], ['ODL', 'Le mie pratiche']]) {
        const select = home.getByRole('combobox', { name: label });
        assert.equal(await select.evaluate(s => s.selectedOptions[0].text), value);
        assert.equal(await select.evaluate(s => s.disabled), true);
    }
    const chips = home.getByRole('group', { name: 'Filtri rapidi' }).getByRole('button');
    assert.deepEqual(await chips.allInnerTexts(),
        ['CREDITO INTENZIONALE', 'DELIBERA SEMPLIFICATA', 'RESTITUITE', 'IN ATTESA', 'SOSPESE']);
    assert.equal(await page.locator('#list-view').isVisible(), false);
});

test('RICERCA opens the Ricerca Pratica tab with the search form', async t => {
    const page = await open(t);
    await openSearch(page);
    assert.deepEqual(await visibleTabs(page), ['Home', 'Ricerca Pratica']);
    assert.deepEqual(await current(page), ['Ricerca Pratica']);
    const form = page.getByRole('region', { name: 'Ricerca Pratica' });
    assert.equal(await form.getByRole('combobox', { name: 'ABI' }).evaluate(s => s.selectedOptions[0].text), '05387-BPER');
    assert.equal(await form.getByRole('tab', { name: 'NDG / Numero Pratica' }).getAttribute('aria-selected'), 'true');
    assert.equal(await form.getByRole('tab', { name: 'Unità Organizzativa' }).getAttribute('aria-selected'), 'false');
    for (const name of ['NDG RICHIEDENTE', 'N° PRATICA', 'MATRICOLA', 'NOME']) {
        assert.equal(await form.getByRole('textbox', { name }).inputValue(), '', name);
    }
    assert.equal(await form.getByRole('button', { name: 'RICERCA ANAGRAFICA' }).count(), 1);
    assert.equal(await form.getByRole('button', { name: 'STATO' }).innerText(),
        'In Lavorazione; In Attesa; Sospesa; Respinta; Abbandonata');
    for (const [name, value] of [['EVIDENZE', 'Seleziona'], ['TIPO PRATICA', 'Tutte'], ['PROVENIENZA', 'Tutte'], ['FASE', 'Tutte']]) {
        assert.equal(await form.getByRole('combobox', { name }).evaluate(s => s.selectedOptions[0].text), value, name);
    }
});

test('the home tab returns to the dashboard and keeps the tabs already opened', async t => {
    const page = await open(t);
    await openSearch(page);
    await tab(page, 'Home').click();
    assert.equal(await page.getByRole('region', { name: 'Home' }).isVisible(), true);
    assert.deepEqual(await visibleTabs(page), ['Home', 'Ricerca Pratica']);
    assert.deepEqual(await current(page), ['Home']);
    await tab(page, 'Ricerca Pratica').click();
    assert.deepEqual(await current(page), ['Ricerca Pratica']);
});

test('submitting a practice number greys the other criteria while the search runs', async t => {
    const page = await open(t);
    const demo = (await catalogue(page)).find(p => p.key === 'demo');
    await openSearch(page);
    const form = page.getByRole('region', { name: 'Ricerca Pratica' });
    await form.getByRole('textbox', { name: 'N° PRATICA' }).fill(demo.number);
    await page.keyboard.press('Enter');
    const disabled = await form.evaluate(root => Object.fromEntries([...root.querySelectorAll('input:not([type="checkbox"]), select, button[aria-haspopup]')]
        .map(control => [control.labels?.[0]?.textContent.trim() || control.getAttribute('aria-label') ||
            document.getElementById(control.getAttribute('aria-labelledby'))?.textContent.trim(), control.disabled])));
    assert.deepEqual(disabled, {
        'ABI': false, 'NDG RICHIEDENTE': true, 'N° PRATICA': false, 'MATRICOLA': true, 'NOME': true,
        'STATO': true, 'EVIDENZE': true, 'TIPO PRATICA': true, 'PROVENIENZA': true, 'FASE': true,
    });
    assert.equal(await tab(page, 'Elenco Pratiche').count(), 0);
    assert.deepEqual(await resultRows(page), [[demo.ndg, demo.name, demo.number, demo.state]]);
});

test('the search adds the Elenco Pratiche tab with its results and active filters', async t => {
    const page = await open(t);
    const demo = (await catalogue(page)).find(p => p.key === 'demo');
    await openSearch(page);
    await page.getByRole('textbox', { name: 'N° PRATICA' }).fill(demo.number);
    await page.keyboard.press('Enter');
    await resultRows(page);
    assert.deepEqual(await visibleTabs(page), ['Home', 'Ricerca Pratica', 'Elenco Pratiche']);
    assert.deepEqual(await current(page), ['Elenco Pratiche']);
    assert.equal(await page.locator('.bl-result-count').innerText(), '1 risultati');
    await page.getByText('Filtri Attivi', { exact: true }).click();
    assert.equal(await page.locator('.bl-filters > div').innerText(), 'N° Pratica ' + demo.number);
    // Once the search is over the criteria can be changed again.
    await tab(page, 'Ricerca Pratica').click();
    assert.equal(await page.getByRole('textbox', { name: 'NDG RICHIEDENTE' }).evaluate(input => input.disabled), false);
    assert.equal(await page.getByRole('textbox', { name: 'N° PRATICA' }).inputValue(), demo.number);
});

test('the state criterion lists every practice of the catalogue in the chosen states', async t => {
    const page = await open(t);
    const expected = (await catalogue(page)).filter(p => p.state === 'SOSP');
    assert.ok(expected.length > 1, 'the catalogue has suspended practices');
    await openSearch(page);
    await chooseStates(page, ['Sospesa']);
    assert.equal(await page.getByRole('button', { name: 'STATO' }).innerText(), 'Sospesa');
    await page.getByRole('region', { name: 'Ricerca Pratica' }).getByRole('button', { name: 'RICERCA', exact: true }).click();
    const rows = await resultRows(page);
    assert.deepEqual(rows.map(row => row[2]).sort(), expected.map(p => p.number).sort());
    assert.ok(rows.every(row => row[3] === 'SOSP'));
    assert.equal(await page.locator('.bl-result-count').innerText(), expected.length + ' risultati');
    await page.getByText('Filtri Attivi', { exact: true }).click();
    assert.equal(await page.locator('.bl-filters > div').innerText(), 'Stato Sospesa');
});

test('the NDG, phase and type criteria combine', async t => {
    const page = await open(t);
    const practices = await catalogue(page);
    const sample = practices.find(p => p.phase === 'DEL' && p.typeCode === 'BMB');
    const expected = practices.filter(p => p.phase === 'DEL' && p.typeCode === 'BMB');
    await openSearch(page);
    const form = page.getByRole('region', { name: 'Ricerca Pratica' });
    await form.getByRole('combobox', { name: 'FASE' }).selectOption('DEL');
    await form.getByRole('combobox', { name: 'TIPO PRATICA' }).selectOption('BMB');
    await form.getByRole('button', { name: 'RICERCA', exact: true }).click();
    assert.deepEqual((await resultRows(page)).map(row => row[2]).sort(), expected.map(p => p.number).sort());
    await tab(page, 'Ricerca Pratica').click();
    await form.getByRole('textbox', { name: 'NDG RICHIEDENTE' }).fill(sample.ndg);
    await form.getByRole('button', { name: 'RICERCA', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.bl-result-count')?.textContent === '1 risultati');
    assert.deepEqual(await resultRows(page), [[sample.ndg, sample.name, sample.number, sample.state]]);
});

test('a search without matches shows an empty list', async t => {
    const page = await open(t);
    const missing = '99999999';
    assert.ok(!(await catalogue(page)).some(p => p.ndg === missing));
    await openSearch(page);
    await page.getByRole('textbox', { name: 'NDG RICHIEDENTE' }).fill(missing);
    await page.keyboard.press('Enter');
    assert.deepEqual(await resultRows(page), [['Nessun risultato']]);
    assert.equal(await page.locator('.bl-result-count').innerText(), '0 risultati');
});

test('a practice opened from the results keeps the results in the Elenco tab', async t => {
    const page = await open(t);
    const expected = (await catalogue(page)).filter(p => p.phase === 'DEL');
    await openSearch(page);
    const form = page.getByRole('region', { name: 'Ricerca Pratica' });
    await form.getByRole('combobox', { name: 'FASE' }).selectOption('DEL');
    await form.getByRole('button', { name: 'RICERCA', exact: true }).click();
    const rows = await resultRows(page);
    assert.equal(rows.length, expected.length);
    const [ndg, , number] = rows[1];
    await page.getByRole('button', { name: 'Azioni pratica ' + number }).click();
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    await page.waitForFunction(() => location.hash === '#4');
    assert.deepEqual(await visibleTabs(page), ['Home', 'Ricerca Pratica', 'Elenco Pratiche', 'practice']);
    assert.equal(await page.getByRole('button', { name: /^PEF 2\.0 - Pratica/ }).innerText(), 'PEF 2.0 - Pratica: ' + number);
    assert.match(await page.locator('.pd-identity').innerText(), new RegExp('NDG: ' + ndg + ' '));
    await tab(page, 'Elenco Pratiche').click();
    assert.deepEqual(await resultRows(page), rows);
    assert.deepEqual(await visibleTabs(page), ['Home', 'Ricerca Pratica', 'Elenco Pratiche', 'practice']);
    assert.deepEqual(await current(page), ['Elenco Pratiche']);
});

test('scrolling the results list keeps the results instead of jumping to a practice', async t => {
    const page = await open(t);
    await openSearch(page);
    await page.getByRole('combobox', { name: 'FASE' }).selectOption('DEL');
    await page.getByRole('region', { name: 'Ricerca Pratica' }).getByRole('button', { name: 'RICERCA', exact: true }).click();
    const rows = await resultRows(page);
    await page.getByRole('scrollbar', { name: /Scorri le colonne/ }).press('End');
    await page.waitForTimeout(300);
    assert.equal((await page.evaluate(() => new URL(location.href).searchParams.get('practice'))), null);
    assert.equal(await page.locator('#detail-view').isVisible(), false);
    assert.deepEqual(await resultRows(page), rows);
});

test('the search form has a direct link', async t => {
    const page = await open(t, '/#ricerca');
    assert.deepEqual(await visibleTabs(page), ['Home', 'Ricerca Pratica']);
    assert.deepEqual(await current(page), ['Ricerca Pratica']);
    assert.equal(await page.getByRole('textbox', { name: 'N° PRATICA' }).isVisible(), true);
});

test('a direct link to a practice keeps the tabs of the reference screenshots', async t => {
    const page = await open(t, '/?practice=demo#1');
    assert.deepEqual(await visibleTabs(page), ['Home', 'Ricerca Pratica', 'Elenco Pratiche']);
    assert.deepEqual(await current(page), ['Elenco Pratiche']);
    await page.keyboard.press('4');
    await page.waitForFunction(() => location.hash === '#4');
    assert.deepEqual(await visibleTabs(page), ['Home', 'Ricerca Pratica', 'Elenco Pratiche', 'practice']);
});

test('the console keeps the catalogue search by NDG, name or number', async t => {
    const page = await open(t, '/?console=1');
    const demo = (await catalogue(page)).find(p => p.key === 'demo');
    const panel = page.locator('#controls');
    await panel.getByRole('searchbox').fill(demo.number);
    assert.equal(await panel.getByRole('status').innerText(), '1 risultato');
    await panel.getByRole('table', { name: 'Catalogo pratiche' }).getByRole('row').filter({ hasText: demo.name }).press('Enter');
    await page.waitForFunction(() => location.hash === '#4');
    assert.equal((await page.evaluate(() => new URL(location.href).searchParams.get('practice'))), 'demo');
    assert.equal(await page.getByRole('region', { name: 'Home' }).count(), 0);
});

test('with the dialog flag the practice opens behind the "già in lavorazione" dialog', async t => {
    const page = await open(t, '/?practice=demo&modal=1#4');
    const dialog = page.getByRole('alertdialog');
    assert.equal(await dialog.innerText(), MESSAGE + '\nAnnulla\nConferma');
    const covered = () => page.locator('.pd-identity').evaluate(node => {
        const r = node.getBoundingClientRect();
        return !node.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
    });
    assert.equal(await covered(), true);
    // Grey over the whole PEF 2.0 frame, the dialog in the middle of its page area: 8 video px left of the frame's
    // centre, about half the frame's vertical scrollbar, and 2 lower (frame 18m13s).
    const box = await page.evaluate(() => {
        const rect = selector => document.querySelector(selector).getBoundingClientRect();
        const [veil, frame, dialog] = [rect('.pm-veil'), rect('.pd-window'), rect('.pm-veil [role="alertdialog"]')];
        return { left: veil.left - frame.left, top: veil.top - frame.top, right: veil.right - frame.right,
                 centre: [veil.left + veil.width / 2 - dialog.left - dialog.width / 2,
                          veil.top + veil.height / 2 - dialog.top - dialog.height / 2] };
    });
    assert.ok(Math.abs(box.left) <= 1 && Math.abs(box.top) <= 1 && box.right >= -1, JSON.stringify(box));
    assert.ok(Math.abs(box.centre[0] - 8.5) <= 1 && Math.abs(box.centre[1] + 2.3) <= 1, JSON.stringify(box));
    await dialog.getByRole('button', { name: 'Conferma' }).click();
    assert.equal(await page.getByRole('alertdialog').count(), 0);
    assert.equal(await covered(), false);
});

test('Annulla also closes the dialog', async t => {
    const page = await open(t, '/?practice=demo&modal=1#5');
    await page.getByRole('alertdialog').getByRole('button', { name: 'Annulla' }).click();
    assert.equal(await page.getByRole('alertdialog').count(), 0);
});

test('without the dialog flag the practice opens directly', async t => {
    const page = await open(t, '/?practice=demo#4');
    assert.equal(await page.getByRole('alertdialog').count(), 0);
});

test('with the dialog flag a practice opened from the list menu shows the dialog', async t => {
    const page = await open(t, '/?practice=demo&modal=1#1');
    assert.equal(await page.getByRole('alertdialog').count(), 0);
    await page.getByRole('button', { name: /Azioni pratica/ }).click();
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    await page.waitForFunction(() => location.hash === '#4');
    assert.equal(await page.getByRole('alertdialog').innerText(), MESSAGE + '\nAnnulla\nConferma');
});

// A synthetic wheel event does not scroll; whether the list keeps it for its columns is what tells the two apart.
async function wheelOnRow(page) {
    return page.getByRole('table', { name: 'Elenco pratiche' }).evaluate(table => {
        const bar = document.querySelector('.bl-results-bar');
        const before = bar.getAttribute('aria-valuenow');
        const event = new WheelEvent('wheel', { deltaY: 120, bubbles: true, cancelable: true });
        table.tBodies[0].rows[0].cells[2].dispatchEvent(event);
        return { kept: event.defaultPrevented, moved: bar.getAttribute('aria-valuenow') !== before };
    });
}

test('the mouse wheel scrolls a long results list down instead of sideways', async t => {
    const page = await open(t);
    await openSearch(page);
    await page.getByRole('combobox', { name: 'FASE' }).selectOption('DEL');
    await page.getByRole('region', { name: 'Ricerca Pratica' }).getByRole('button', { name: 'RICERCA', exact: true }).click();
    assert.ok((await resultRows(page)).length > 10);
    assert.deepEqual(await wheelOnRow(page), { kept: false, moved: false });
});

test('the mouse wheel still scrolls the columns of a one-row list', async t => {
    const page = await open(t, '/?practice=demo#1');
    assert.deepEqual(await wheelOnRow(page), { kept: true, moved: true });
});
