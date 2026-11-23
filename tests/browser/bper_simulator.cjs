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
    // Without the waits of the real application (tests/browser/bper_loading.cjs checks those).
    const page = await open(t, '/?loading=off');
    // The real flow (video spec sections 3-6): home, Ricerca Pratica, Elenco Pratiche, the row menu.
    await page.getByRole('button', { name: 'RICERCA', exact: true }).click();
    await page.getByRole('textbox', { name: 'NDG RICHIEDENTE' }).fill('90000001');
    await page.keyboard.press('Enter');
    const results = page.getByRole('table', { name: 'Elenco pratiche' });
    await page.getByRole('button', { name: 'Azioni pratica 99000001' }).waitFor({ timeout: 5000 });
    assert.deepEqual(await results.locator('tbody tr').allInnerTexts().then(rows => rows.map(row => row.includes('ALBA MARTINA'))), [true]);
    await page.getByRole('button', { name: 'Azioni pratica 99000001' }).click();
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
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
    const bar = page.getByRole('scrollbar', { name: /Scorri le colonne/ });
    await bar.focus();
    await bar.press('End');
    await expectStep(page, 2);
    await page.getByRole('button', { name: 'Evidenze B' }).hover();
    await expectStep(page, 3);
    assert.equal(await page.getByRole('tooltip').innerText(), 'Origination BSTORE');
});

test('dragging the list bar scrolls the columns', async t => {
    const page = await open(t, '/?practice=demo');
    const thumb = page.getByRole('scrollbar', { name: /Scorri le colonne/ }).locator('.bl-thumb');
    const box = await thumb.boundingBox();
    await page.mouse.move(box.x + 20, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + 220, box.y + box.height / 2, { steps: 5 });
    await page.mouse.up();
    await expectStep(page, 2);
});

test('the practice opens from the row actions menu, not from a click on the row', async t => {
    const page = await open(t, '/?practice=demo');
    await page.getByRole('table', { name: 'Elenco pratiche' }).getByRole('row').nth(1).click();
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => location.hash), '#1');
    await page.getByRole('button', { name: /Azioni pratica/ }).click();
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    await expectStep(page, 4);
});

test('the row actions menu opens the practice from the keyboard', async t => {
    // Enter twice in a row: the menu must be there at once, so without the row's wait (bper_loading.cjs).
    const page = await open(t, '/?practice=demo&loading=off');
    await page.getByRole('button', { name: /Azioni pratica/ }).focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Enter');
    await expectStep(page, 4);
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
    await page.getByRole('textbox', { name: 'NDG RICHIEDENTE' }).fill(ndg);
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => !document.querySelector('#list-view').hidden, undefined, { timeout: 5000 });
    const listed = await page.getByRole('table', { name: 'Elenco pratiche' })
        .evaluate(table => [...table.tBodies[0].rows].map(row => row.cells[2].textContent));
    assert.deepEqual(listed, [ndg]);
});

// Resizing (video spec section 16, CSS px at 100% zoom): nothing scales with the window.
const near = (actual, expected, tolerance) => Math.abs(actual - expected) <= tolerance;

async function pefGeometry(page) {
    return page.evaluate(() => {
        const frame = document.querySelector('.pd-window').getBoundingClientRect();
        return { page: document.querySelector('.pd-mainnav').getBoundingClientRect().width, left: frame.left };
    });
}

test('the capture window draws the site at the scale of the reference screenshots', async t => {
    const page = await open(t, '/?practice=demo&capture=1#5');
    // Spec section 0: the PEF 2.0 nav bar is 718 px wide in the references.
    assert.ok(near((await pefGeometry(page)).page, 718, 1.5));
});

test('at screen scale the PEF 2.0 page keeps 990 px while its frame follows the window', async t => {
    const page = await open(t, '/?practice=demo#5');
    for (const width of [1280, 1600]) {
        await page.setViewportSize({ width, height: 800 });
        await page.waitForFunction(w => innerWidth === w, width);
        const geometry = await pefGeometry(page);
        assert.ok(near(geometry.page, 990, 3), `page ${geometry.page} at ${width}`);
        assert.ok(near(geometry.left, 36 + (width - 72) / 12, 4.5), `frame left ${geometry.left} at ${width}`);
    }
});

test('the PEF 2.0 frame scrolls sideways only in a window narrower than about 1170 px', async t => {
    const page = await open(t, '/?practice=demo#5');
    const sideways = page.getByRole('slider', { name: 'Scorrimento orizzontale del dettaglio' });
    await page.setViewportSize({ width: 1150, height: 800 });
    await sideways.waitFor({ timeout: 2000 });
    await page.setViewportSize({ width: 1190, height: 800 });
    await page.waitForFunction(() => innerWidth === 1190);
    await page.waitForTimeout(100);
    assert.equal(await sideways.count(), 0);
});

test('a wider window uncovers more list columns without moving the pinned ones', async t => {
    const page = await open(t, '/?practice=demo#1');
    const measures = [];
    for (const width of [1280, 1600]) {
        await page.setViewportSize({ width, height: 800 });
        await page.waitForFunction(w => innerWidth === w, width);
        await page.waitForTimeout(100);
        measures.push(await page.evaluate(() => {
            const bar = document.querySelector('.bl-empty-bar');
            const header = name => [...document.querySelectorAll('.bl-results th')].find(th => th.textContent === name)
                .getBoundingClientRect();
            return { thumb: bar.querySelector('.bl-thumb').offsetWidth / bar.offsetWidth, abi: header('ABI').left,
                evidence: innerWidth - header('Evidenze').right, overflow: document.documentElement.scrollWidth - innerWidth };
        }));
    }
    const [narrow, wide] = measures;
    // Spec 16.3: the empty table's thumb is 65% of its track at 1280 and about 82% at 1600.
    assert.ok(near(narrow.thumb, 0.65, 0.015) && near(wide.thumb, 0.82, 0.015), JSON.stringify(measures));
    assert.ok(near(narrow.abi, wide.abi, 0.5) && near(narrow.evidence, wide.evidence, 1));
    assert.deepEqual([narrow.overflow, wide.overflow], [0, 0]);
});

test('a taller window gives the BStore table half of the extra height above it', async t => {
    // The reference (110%, about 852 CSS px of page height) and the video at 18:10 (100%, 897) show the
    // BStore title 537 and 562 (±2) CSS px from the top: about half of the height gained, the rest stays below.
    const page = await open(t, '/?practice=demo#1');
    const tops = [];
    for (const height of [852, 897, 997]) {
        await page.setViewportSize({ width: 1280, height });
        await page.waitForFunction(h => innerHeight === h, height);
        await page.waitForTimeout(100);
        tops.push(await page.evaluate(() => [
            document.querySelector('.bl-queue-title').getBoundingClientRect().top,
            document.querySelector('.bl-actions').getBoundingClientRect().top]));
    }
    const [reference, video, taller] = tops;
    assert.ok(near(video[0] - reference[0], 22.5, 1) && near(taller[0] - video[0], 50, 1), JSON.stringify(tops));
    assert.deepEqual([video[1], taller[1]], [reference[1], reference[1]]);
});

test('the capture window opens at the size of the reference screenshots', async t => {
    const page = await open(t, '/?console=1&practice=demo#4');
    await page.evaluate(() => { window.open = (url, name, features) => { window.opened = [url, features]; return {focus() {}}; }; });
    await page.getByRole('button', { name: 'Apri finestra di cattura' }).click();
    const [url, features] = await page.evaluate(() => window.opened);
    assert.equal(new URL(url).searchParams.get('capture'), '1');
    assert.match(features, /(^|,)width=842,height=617(,|$)/);
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
