// Gestione Documentale and its PDF viewer (site/docs.js) against the local simulator, with Playwright and Chrome.
// Run like bper_simulator.cjs: a server at BPER_TEST_URL, Playwright from PLAYWRIGHT_MODULE.
const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const base = process.env.BPER_TEST_URL || 'http://127.0.0.1:8765';
let browser;

before(async () => { browser = await chromium.launch({ channel: 'chrome' }); });
after(async () => { await browser?.close(); });

async function open(t, query) {
    const page = await browser.newPage({ viewport: { width: 1120, height: 820 } });
    t.after(() => page.close());
    await page.goto(base + '/' + query);
    await page.locator('#frame[data-ready]').waitFor({ timeout: 4000 });
    return page;
}

const link = page => page.locator('#detail-view').getByRole('link', { name: /Gestione Documentale/ });
const documents = page => page.getByRole('region', { name: 'Gestione Documentale' });
const viewer = page => page.getByRole('region', { name: 'Visualizzatore PDF' });
const wait = page => page.getByText('Attendere... caricamento in corso', { exact: true });

async function practice(page, key) {
    return page.evaluate(async k => (await (await fetch('/api/practices.json')).json()).practices.find(p => p.key === k), key);
}

// The documents text of a practice, opened at once.
async function documentsText(t, key) {
    const page = await open(t, `?practice=${key}&loading=off#5`);
    await link(page).click();
    return documents(page).evaluate(section => [...section.querySelectorAll('tbody tr')].map(row => row.textContent.trim()));
}

test('the Funzioni link opens Gestione Documentale under the identity box and keeps the screen', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await link(page).click();
    const section = documents(page);
    await section.waitFor({ timeout: 1000 });
    assert.match(await section.innerText(), /Filtro Documenti/);
    assert.equal(await page.locator('.pd-identity').isVisible(), true);
    assert.equal(await page.locator('[data-panel="credit"]').isVisible(), false);
    assert.equal(await page.locator('[data-panel="tabs"]').isVisible(), false);
    assert.equal(await page.evaluate(() => location.hash), '#5');
});

test('every subject of the practice has its own documents bar, the first one open', async t => {
    const page = await open(t, '?practice=demo&loading=off#4');
    const subjects = (await practice(page, 'demo')).subjects;
    await link(page).click();
    const bars = documents(page).locator('.gd-subject > h3 button');
    assert.deepEqual(await bars.allInnerTexts(), subjects.map(s => `${s.ndg} - ${s.name} - ${s.role}`));
    const expanded = [];
    for (let i = 0; i < subjects.length; i++) expanded.push(await bars.nth(i).getAttribute('aria-expanded'));
    assert.deepEqual(expanded, subjects.map((_, i) => String(i === 0)));
});

test('subject bars open and close their documents independently', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await link(page).click();
    const bars = documents(page).locator('.gd-subject > h3 button');
    const tables = documents(page).locator('.gd-subject > .gd-body');
    await bars.nth(1).click();
    assert.equal(await tables.nth(0).isVisible(), true);
    assert.equal(await tables.nth(1).isVisible(), true);
    await bars.nth(0).click();
    assert.equal(await tables.nth(0).isVisible(), false);
    assert.equal(await bars.nth(0).getAttribute('aria-expanded'), 'false');
    assert.equal(await tables.nth(1).isVisible(), true);
});

// The acquisition state of the rows the filter leaves visible, with the filter set to acquired documents.
async function filtered(t) {
    const page = await open(t, '?practice=demo&loading=off#5');
    await link(page).click();
    const section = documents(page);
    const shown = () => section.evaluate(s => [...s.querySelectorAll('.gd-table tbody tr')].filter(row => !row.hidden)
        .map(row => row.dataset.acquired));
    const all = await shown();
    await section.locator('.gd-acquired select').selectOption('Sì');
    await section.getByRole('button', { name: 'Applica', exact: true }).click();
    return { section, shown, all };
}

test('Applica keeps only the rows matching the filter', async t => {
    const { shown, all } = await filtered(t);
    assert.ok(all.includes('si') && all.includes('no'));
    assert.deepEqual(await shown(), all.filter(state => state === 'si'));
});

test('Reset shows every row again and disables itself', async t => {
    const { section, shown, all } = await filtered(t);
    await section.getByRole('button', { name: 'Reset', exact: true }).click();
    assert.deepEqual(await shown(), all);
    assert.equal(await section.locator('.gd-reset').evaluate(button => button.disabled), true);
});

test('opening the page shows the red wait line and the spinner for a realistic time', async t => {
    const page = await open(t, '?practice=demo#5');
    await link(page).click();
    assert.equal(await wait(page).isVisible(), true);
    assert.equal(await page.getByRole('progressbar', { name: 'Caricamento in corso' }).isVisible(), true);
    assert.equal(await wait(page).evaluate(el => getComputedStyle(el).color), 'rgb(238, 0, 0)');
    await page.waitForTimeout(800);
    assert.equal(await documents(page).isVisible(), false);
    assert.equal(await page.locator('[data-panel="credit"]').isVisible(), true);
    await documents(page).waitFor({ timeout: 2500 });
    assert.equal(await wait(page).isVisible(), false);
});

test('capture mode opens the page without artificial delays', async t => {
    const page = await open(t, '?practice=demo&capture=1#5');
    await link(page).click();
    assert.equal(await documents(page).isVisible(), true);
    assert.equal(await wait(page).isVisible(), false);
});

test('a screen key leaves the documents page for its canonical screen', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await link(page).click();
    await documents(page).waitFor({ timeout: 1000 });
    await page.keyboard.press('9');
    await page.waitForFunction(() => location.hash === '#9');
    assert.equal(await documents(page).isVisible(), false);
    assert.equal(await page.locator('[data-panel="notes"]').isVisible(), true);
});

test('a screen chosen while the page loads is not replaced when the wait ends', async t => {
    const page = await open(t, '?practice=demo#5');
    await link(page).click();
    await page.keyboard.press('9');
    await page.waitForTimeout(2200);
    assert.equal(await documents(page).isVisible(), false);
    assert.equal(await wait(page).isVisible(), false);
    assert.equal(await page.locator('[data-panel="notes"]').isVisible(), true);
});

test('an info icon shows its yellow tooltip below and left of the pointer after a short delay', async t => {
    const page = await open(t, '?practice=demo#5');
    await link(page).click();
    await documents(page).waitFor({ timeout: 3000 });
    const icon = documents(page).locator('.gd-info:visible').first();
    const box = await icon.boundingBox();
    const x = box.x + box.width * 0.6, y = box.y + box.height * 0.6;
    await page.mouse.move(x, y);
    await page.waitForTimeout(150);
    assert.equal(await page.getByRole('tooltip').isVisible(), false);
    await page.getByRole('tooltip').waitFor({ timeout: 1500 });
    const tip = page.getByRole('tooltip');
    assert.ok((await tip.innerText()).length > 10);
    assert.equal(await tip.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 225)');
    const rect = await tip.boundingBox();
    assert.ok(rect.x > x - 28 && rect.x < x - 12, `tooltip left ${rect.x} for pointer ${x}`);
    assert.ok(rect.y > y + 4 && rect.y < y + 18, `tooltip top ${rect.y} for pointer ${y}`);
});

test('in the capture window the tooltip still opens under and left of the pointer', async t => {
    const page = await open(t, '?practice=demo&capture=1#5');
    await link(page).click();
    const icon = documents(page).locator('.gd-info:visible').first();
    await icon.hover();
    const box = await icon.boundingBox();
    const x = box.x + box.width / 2, y = box.y + box.height / 2;
    const rect = await page.getByRole('tooltip').boundingBox();
    assert.ok(rect.x > x - 20 && rect.x < x - 10, `tooltip left ${rect.x} for pointer ${x}`);
    assert.ok(rect.y > y + 3 && rect.y < y + 12, `tooltip top ${rect.y} for pointer ${y}`);
});

test('the tooltip hides when the pointer leaves the icon', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await link(page).click();
    await documents(page).locator('.gd-info:visible').first().hover();
    await page.getByRole('tooltip').waitFor({ timeout: 1000 });
    await page.mouse.move(5, 5);
    assert.equal(await page.getByRole('tooltip').isVisible(), false);
});

test('a document icon opens the embedded PDF viewer with the Chrome toolbar', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    const { number } = await practice(page, 'demo');
    await link(page).click();
    await documents(page).getByRole('button', { name: /^Visualizza / }).first().click();
    const pdf = viewer(page);
    await pdf.waitFor({ timeout: 1000 });
    const toolbar = pdf.getByRole('toolbar');
    assert.ok((await toolbar.innerText()).startsWith(number + ' - '));
    assert.equal(await toolbar.getByLabel('Numero di pagina').inputValue(), '1');
    assert.match(await toolbar.innerText(), /\/\s*1[\s\S]*100%/);
    for (const name of ['Riduci', 'Ingrandisci', 'Adatta alla pagina', 'Ruota', 'Disegna', 'Scarica', 'Stampa'])
        assert.equal(await toolbar.getByRole('button', { name, exact: true }).isVisible(), true, name);
    assert.equal(await page.getByRole('button', { name: 'Indietro', exact: true }).isVisible(), true);
    assert.equal(await documents(page).locator('.gd-box').isVisible(), false);
});

test('with loading off the viewer opens on its final state, without the extraction toast', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await link(page).click();
    await documents(page).getByRole('button', { name: /^Visualizza / }).first().click();
    assert.equal(await viewer(page).locator('.pv-sheet').isVisible(), true);
    assert.equal(await page.getByText('Estrazione del testo dal PDF in corso...').isVisible(), false);
});

test('the viewer opens empty, then shows the page and the extraction toast, then hides the toast', async t => {
    const page = await open(t, '?practice=demo#5');
    await link(page).click();
    await documents(page).waitFor({ timeout: 3000 });
    await documents(page).getByRole('button', { name: /^Visualizza / }).first().click();
    await viewer(page).waitFor({ timeout: 2500 });
    assert.equal(await viewer(page).locator('.pv-sheet').isVisible(), false);
    const toast = page.getByRole('status').filter({ hasText: 'Estrazione del testo dal PDF in corso...' });
    await toast.waitFor({ timeout: 2000 });
    assert.equal(await viewer(page).locator('.pv-sheet').isVisible(), true);
    await page.waitForFunction(() => !document.querySelector('.pv-toast:not([hidden])'), undefined, { timeout: 6000 });
});

test('Indietro returns from the viewer to the documents list', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await link(page).click();
    await documents(page).getByRole('button', { name: /^Visualizza / }).first().click();
    await page.getByRole('button', { name: 'Indietro', exact: true }).click();
    assert.equal(await viewer(page).isVisible(), false);
    assert.match(await documents(page).innerText(), /Filtro Documenti/);
});

test('the documents of a practice are the same on every visit', async t => {
    assert.deepEqual(await documentsText(t, 'demo'), await documentsText(t, 'demo'));
});

test('practices with the same subjects and credit get different documents', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    const twin = await page.evaluate(async () => {
        const all = (await (await fetch('/api/practices.json')).json()).practices;
        const shape = p => p.subjects.map(s => s.role).join() + '|' + p.fidi.map(f => f.description).join();
        const demo = all.find(p => p.key === 'demo');
        return all.find(p => p.key !== 'demo' && shape(p) === shape(demo))?.key;
    });
    assert.ok(twin, 'no practice shaped like demo');
    const strip = rows => rows.map(row => row.replace(/\d{8}|[A-Z]{2,}(?: [A-Z]{2,})+/g, ''));
    assert.notDeepEqual(strip(await documentsText(t, 'demo')), strip(await documentsText(t, twin)));
});

// The detail and documents scripts alone, as bper_detail.cjs loads them (native timing), on an archive-like practice.
async function openAlone(t, changes = {}) {
    const page = await browser.newPage();
    t.after(() => page.close());
    const assets = path.resolve(__dirname, '../../bper-emulator/site');
    await page.setContent('<section id="detail-view"></section>');
    for (const name of ['detail.css', 'docs.css']) await page.addStyleTag({ path: path.join(assets, name) });
    for (const name of ['docs.js', 'detail.js']) await page.addScriptTag({ path: path.join(assets, name) });
    await page.evaluate(changes => {
        const practice = {
            key: 'arch-000', role: 'addestramento', ndg: '80000000', name: 'TITOLARE REALE', number: '88000000',
            created: '10/01/2026', operatorName: 'Operatrice', operatorId: 'U910000', officeCode: '92001001',
            noteAuthor: 'Redattore', subjects: [{ ndg: '80000000', name: 'TITOLARE REALE', role: 'Richiedente' }],
            fidi: [{ id: 'F1', description: 'M. CASA', tooltip: '1 - MUTUO' }], guarantees: [], ...changes,
        };
        BperDetail.render(document.querySelector('#detail-view'), practice, { onState: () => {} });
        BperDetail.show(5);
    }, changes);
    await link(page).click();
    await documents(page).waitFor({ timeout: 4000 });
    return page;
}

test('a real practice opens its documents as blank forms, never filled in its holder\'s name', async t => {
    const page = await openAlone(t);
    await documents(page).getByRole('button', { name: /^Visualizza / }).first().click();
    const sheet = viewer(page).locator('.pv-sheet');
    await sheet.waitFor({ timeout: 4000 });
    const text = await sheet.evaluate(el => el.textContent);
    assert.doesNotMatch(text, /TITOLARE REALE/);
    assert.match(text, /-{10}/);
});

test('a practice without its subject list still shows its holder\'s documents', async t => {
    const page = await openAlone(t, { subjects: [] });
    const bars = documents(page).locator('.gd-subject > h3 button');
    assert.deepEqual(await bars.allInnerTexts(), ['80000000 - TITOLARE REALE - Richiedente']);
});

test('the documents page marks no extracted field', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await link(page).click();
    await documents(page).getByRole('button', { name: /^Visualizza / }).first().click();
    assert.equal(await documents(page).locator('[data-field]').count(), 0);
});
