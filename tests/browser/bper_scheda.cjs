// How the Scheda Privati renders (bper-emulator/site/scheda): NON CENSITO needs a named employer, the USCITE
// CONTINUATIVE rows follow the data, and the page is ready only at the scroll it was asked for. Run like
// bper_pef_pages.cjs: a server at BPER_TEST_URL, Playwright from PLAYWRIGHT_MODULE. The capture window is
// 1920 x 945 CSS px (measure_scheda.py, audit_truth.cjs).
const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const base = process.env.BPER_TEST_URL || 'http://127.0.0.1:8765';
let browser;

before(async () => { browser = await chromium.launch({ channel: 'chrome' }); });
after(async () => { await browser?.close(); });

async function schede() {
    const { practices } = await (await fetch(base + '/api/practices.json')).json();
    return practices.map(p => p.scheda).filter(Boolean);
}

async function visit(t, scheda, query = '') {
    const page = await browser.newPage({ viewport: { width: 1920, height: 945 } });
    t.after(() => page.close());
    await page.goto(`${base}/schede/SchedaPrivati/${query}#/schede/${scheda.ndg}/${scheda.schedaId}`);
    return page;
}

async function open(t, scheda) {
    const page = await visit(t, scheda);
    await page.locator('body[data-ready="true"]').waitFor({ timeout: 6000 });
    return page;
}

test('the NON CENSITO mark needs a named employer', async t => {
    const all = await schede();
    const selfEmployed = all.find(s => s.fields.tipo_contratto === 'LAVORATORE AUTONOMO');
    const unregistered = all.find(s => s.details.employerNdg === '0');
    assert.ok(selfEmployed && unregistered);
    assert.ok(!await (await open(t, selfEmployed)).locator('.sp-census').isVisible(), 'self-employed: an empty box');
    assert.ok(await (await open(t, unregistered)).locator('.sp-census').isVisible(), 'an employer typed in by hand');
});

test('the outgoing rows render under USCITE CONTINUATIVE', async t => {
    const all = await schede();
    const two = all.find(s => s.details.outgoings.length === 2);
    const none = all.find(s => s.details.outgoings.length === 0);
    assert.ok(two && none);
    const page = await open(t, two);
    assert.deepEqual(await page.locator('#uscite .sp-outgoing h4').allTextContents(),
        ['USCITA CONTINUATIVA 1', 'USCITA CONTINUATIVA 2']);
    assert.deepEqual(await page.locator('#uscite .sp-outgoing input').evaluateAll(inputs => inputs.map(i => i.value)),
        two.details.outgoings.flatMap(o => [o.description, o.annualAmount, o.due, o.residual]));
    assert.equal(await (await open(t, none)).locator('.sp-outgoing').count(), 0);
});

test('a scroll the page cannot reach leaves the page not ready', async t => {
    const [scheda] = await schede();
    const page = await visit(t, scheda, '?scroll=5000');
    await page.locator('body[data-scroll-mismatch]').waitFor({ timeout: 6000 });
    const { ready, mismatch, end } = await page.evaluate(() => {
        const main = document.querySelector('.sp-main');
        return { ready: document.body.dataset.ready, mismatch: document.body.dataset.scrollMismatch,
                 end: main.scrollHeight - main.clientHeight };
    });
    assert.equal(ready, undefined);
    assert.equal(mismatch, `5000/${end}`);
});
