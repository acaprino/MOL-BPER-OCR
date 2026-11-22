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

test('the extended list shows the stored assignment date', async t => {
    const page = await load(t);
    await page.evaluate(practice => {
        BperList.render(document.querySelector('#list-view'), practice, { openPractice() {}, onState() {} });
        BperList.show(2);
    }, { ...profiles[0], assigned: '14/11/2026' });
    assert.equal(await page.getByRole('cell', { name: '14/11/2026', exact: true }).count(), 1);
});
