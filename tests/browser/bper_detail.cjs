const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

let browser;
before(async () => { browser = await chromium.launch({ channel: 'chrome' }); });
after(async () => { await browser?.close(); });

async function open(t) {
    const page = await browser.newPage();
    t.after(() => page.close());
    page.setDefaultTimeout(2000);
    const assets = path.resolve(__dirname, '../../bper-emulator/site');
    await page.setContent('<section id="detail-view"></section>');
    await page.addStyleTag({ path: path.join(assets, 'detail.css') });
    await page.addScriptTag({ path: path.join(assets, 'detail.js') });
    await page.evaluate(() => {
        const practice = {
            ndg: '90000000', name: 'CLIENTE FITTIZIO', number: '99000000', created: '10/01/2026',
            operatorName: 'Operatrice Sintetica', operatorId: 'U910000', officeCode: '92001001',
            noteAuthor: 'Redattore Sintetico', subjects: [], guarantees: [],
            fidi: [
                { id: 'F1', description: 'M.CONSAP >=80%', tooltip: 'Descrizione del primo fido' },
                { id: 'F2', description: 'SECONDO FIDO', tooltip: 'Descrizione del secondo fido' },
            ],
        };
        window.route = 5;
        BperDetail.render(document.querySelector('#detail-view'), practice, {
            openList: () => { window.route = 1; }, onState: n => { window.route = n; },
        });
        BperDetail.show(5);
    });
    return page;
}

test('the inner dashboard label keeps the operator inside the PEF detail', async t => {
    const page = await open(t);
    await page.getByText('CRUSCOTTO PRATICHE', { exact: true }).click();
    assert.equal(await page.evaluate(() => window.route), 5);
    assert.equal(await page.getByText('DETTAGLIO PRATICA', { exact: true }).getAttribute('aria-current'), 'page');
});

test('credit rows expose their own tooltip without switching to another credit', async t => {
    const page = await open(t);
    const second = page.getByRole('button', { name: 'SECONDO FIDO' });
    await second.focus();
    assert.equal(await page.getByRole('tooltip').innerText(), 'Descrizione del secondo fido');
    assert.equal(await page.evaluate(() => window.route), 5);
    await second.press('Escape');
    assert.equal(await page.getByRole('tooltip').isVisible(), false);
    await page.getByRole('button', { name: 'M.CONSAP >=80%' }).hover();
    assert.equal(await page.getByRole('tooltip').innerText(), 'Descrizione del primo fido');
    assert.equal(await page.evaluate(() => window.route), 6);
});

test('the open credit tooltip leaves its wrapped short description readable', async t => {
    const page = await open(t);
    const description = page.getByRole('button', { name: 'M.CONSAP >=80%' });
    await description.hover();
    const popup = await page.getByRole('tooltip').boundingBox();
    const lines = await description.evaluate(button => {
        const range = document.createRange();
        range.selectNodeContents(button);
        return [...range.getClientRects()].map(rect => rect.toJSON());
    });
    assert.ok(lines.length > 1);
    for (const line of lines) {
        assert.ok(popup.y >= line.bottom || popup.y + popup.height <= line.top ||
                  popup.x >= line.right || popup.x + popup.width <= line.left);
    }
});

test('the detail header and note identify the staff supplied with the dossier', async t => {
    const page = await open(t);
    assert.match(await page.locator('.pd-mast').innerText(), /Operatrice Sintetica.*910000.*92001001/);
    await page.getByRole('button', { name: 'Note da Richiesta', exact: true }).click();
    assert.match(await page.locator('.pd-byline').innerText(), /Redattore Sintetico/);
});
