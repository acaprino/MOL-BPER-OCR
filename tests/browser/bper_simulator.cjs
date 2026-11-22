// Run against the local simulator with Playwright and Chrome installed.
const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { readFileSync } = require('node:fs');
const path = require('node:path');

const base = process.env.BPER_TEST_URL || 'http://127.0.0.1:8765';
let browser;

before(async () => {
    browser = await chromium.launch({ channel: 'chrome' });
});
after(async () => { await browser?.close(); });

async function open(t, path = '/', origin = base) {
    const page = await browser.newPage({ viewport: { width: 1120, height: 820 } });
    t.after(() => page.close());
    const url = new URL(origin);
    const route = new URL(path, 'http://test.local');
    url.search = route.search;
    url.hash = route.hash;
    await page.goto(url.href);
    await page.locator('#frame[data-ready]').waitFor({ timeout: 4000 });
    return page;
}

async function expectStep(page, value) {
    await page.waitForFunction(step => location.hash === '#' + step, value, { timeout: 3000 });
}

test('opening the simulator displays the HTML site from the top edge of the viewport', async t => {
    const page = await open(t);
    assert.equal(await page.locator('#controls').isVisible(), false);
    const header = page.locator('header').filter({ hasText: 'Gestione Pratiche' });
    const rect = await header.boundingBox();
    assert.ok(rect);
    assert.equal(rect.x, 0);
    assert.equal(rect.y, 0);
    assert.equal(rect.width, page.viewportSize().width);
    assert.equal(await page.locator('img:visible').count(), 0);
});

test('an operator can follow the dossier from the list through guarantees to notes', async t => {
    const page = await open(t);
    await page.getByRole('searchbox').fill('90000001');
    await page.locator('#list-view').getByText('ALBA MARTINA', { exact: true }).click();
    await expectStep(page, 4);
    const detail = page.locator('#detail-view');
    assert.match(await detail.innerText(), /ALBA LUCA/);
    await detail.getByRole('button', { name: /Avvia Step Succ/ }).click();
    await expectStep(page, 5);
    for (const step of [6, 7, 8]) {
        await detail.locator(`[data-tooltip-step="${step}"]`).hover();
        await expectStep(page, step);
        assert.ok((await detail.getByRole('tooltip').innerText()).length > 12);
        await page.getByText('Gestione Pratiche', { exact: true }).hover();
        await expectStep(page, 5);
    }
    await detail.getByRole('button', { name: 'Note da Richiesta', exact: true }).click();
    await expectStep(page, 9);
    assert.match(await detail.innerText(), /120.000/);
    await page.getByRole('button', { name: 'Elenco Pratiche', exact: true }).click();
    await expectStep(page, 1);
});

test('changing dossier keeps the synthetic identity through capture and reload', async t => {
    const page = await open(t, '/?console=1#4');
    await page.getByLabel('Pratica', { exact: true }).selectOption('demo');
    const popupEvent = page.waitForEvent('popup');
    await page.getByRole('button', { name: 'Apri finestra di cattura' }).click();
    const popup = await popupEvent;
    t.after(() => popup.close());
    await popup.reload();
    await popup.locator('#detail-view').getByText('ALBA MARTINA', { exact: true }).first().waitFor();
    assert.match(await popup.title(), /BPER/);
    assert.equal(await popup.locator('#controls').isVisible(), false);
    assert.doesNotMatch(await popup.locator('#detail-view').innerText(), /LUNARDI/);
});

test('scrolling the list reveals assignment columns and the evidence tooltip', async t => {
    const page = await open(t, '/?practice=demo');
    const slider = page.getByRole('slider', { name: /Scorri le colonne/ });
    await slider.focus();
    await slider.press('End');
    await expectStep(page, 2);
    await page.getByRole('button', { name: 'Evidenze B' }).hover();
    await expectStep(page, 3);
    assert.equal(await page.getByRole('tooltip').innerText(), 'Origination BSTORE');
});

test('leaving a focused evidence tooltip keeps the newly selected detail screen', async t => {
    const page = await open(t, '/?practice=demo&capture=1#3');
    const evidence = page.getByRole('button', { name: 'Evidenze B' });
    await evidence.focus();
    await evidence.hover();
    await page.keyboard.press('4');
    await page.mouse.move(4, 4);
    await page.locator('#detail-view').getByRole('button', { name: /Avvia Step Succ/ })
        .waitFor({ timeout: 2000 });
    await expectStep(page, 4);
});

test('a selected dossier publishes its ground truth and survives a direct link', async t => {
    const page = await open(t, '/?console=1&practice=sim-002#4');
    assert.equal(await page.getByLabel('Pratica', { exact: true }).inputValue(), 'sim-002');
    const identity = await page.locator('.pd-identity').innerText();
    const ndg = identity.match(/\b\d{8}\b/)[0];
    const download = page.getByRole('link', { name: 'Scarica dati.csv' });
    const csv = await download.evaluate(async link => (await fetch(link.href)).text());
    assert.ok(csv.includes(ndg));
    await page.reload();
    await page.locator('#frame[data-ready]').waitFor();
    assert.equal(await page.locator('.pd-identity').innerText(), identity);
    await page.getByRole('button', { name: 'Ricerca Pratica', exact: true }).click();
    await page.getByRole('searchbox').fill(ndg);
    assert.ok((await page.getByRole('table').first().innerText()).includes(ndg));
});

test('all nine reference pages contain exactly the original website pixels', {
    skip: !process.env.BPER_REFERENCE_TEST_URL && 'requires the --include-reference export or server',
}, async t => {
    const page = await open(t, '/?mode=reference&capture=1#1', process.env.BPER_REFERENCE_TEST_URL);
    const origins = [[3,59], [3,60], [3,60], [3,59], [3,60], [3,60], [3,60], [4,60], [4,60]];
    const reference = JSON.parse(readFileSync(
        path.join(__dirname, '../../tools/reference/fotogrammi.json'), 'utf8'));
    await page.setViewportSize({ width: 842, height: 617 });
    for (let step = 1; step <= 9; step++) {
        const png = readFileSync(path.join(__dirname, '../../data/dataset/pratiche', reference.pratica,
            reference.fotogrammi['screen ' + step] + '.png'));
        await page.keyboard.press(String(step));
        await expectStep(page, step);
        await page.locator('#original').evaluate(async image => {
            await image.decode();
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        });
        const screenshot = await page.screenshot();
        const identical = await page.evaluate(async ([expected, actual, [left, top]]) => {
            async function pixels(base64, x, y) {
                const img = new Image();
                img.src = 'data:image/png;base64,' + base64;
                await img.decode();
                const canvas = document.createElement('canvas');
                canvas.width = img.width;
                canvas.height = img.height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                return ctx.getImageData(x, y, 842, 617).data;
            }
            const [a, b] = await Promise.all([pixels(expected, left, top), pixels(actual, 0, 0)]);
            return a.length === b.length && a.every((value, index) => value === b[index]);
        }, [png.toString('base64'), screenshot.toString('base64'), origins[step - 1]]);
        assert.ok(identical, 'reference screen ' + step);
    }
});
