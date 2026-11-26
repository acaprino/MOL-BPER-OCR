// How the Scheda Privati renders (bper-emulator/site/scheda): NON CENSITO needs a named employer. Run like
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

async function open(t, scheda) {
    const page = await browser.newPage({ viewport: { width: 1920, height: 945 } });
    t.after(() => page.close());
    await page.goto(`${base}/schede/SchedaPrivati/#/schede/${scheda.ndg}/${scheda.schedaId}`);
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
