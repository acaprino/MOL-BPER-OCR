// PEF 2.0 pages and states of the MOL recordings that the reference screenshots lack (video spec 18.2): the navigator
// with several groups open and its callout, Recupero Segnalazioni, the lower blocks of Gestione Fidi e Garanzie, Note
// Delibere Precedenti, the visualizzazione variant, the Avvertenza of the navigator's X and the logout page after it; and
// the native geometry of the PEF 2.0 frame (spec 16.7). Run like bper_simulator.cjs: a server at BPER_TEST_URL, Playwright from
// PLAYWRIGHT_MODULE. Native waits are checked with wide margins, so that a busy machine does not fail them.
const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const base = process.env.BPER_TEST_URL || 'http://127.0.0.1:8765';
let browser;

before(async () => { browser = await chromium.launch({ channel: 'chrome' }); });
after(async () => { await browser?.close(); });

// The operator's screen: 1280 x 897 CSS px at 100% zoom (spec 16.1).
async function open(t, query, viewport = { width: 1280, height: 897 }) {
    const page = await browser.newPage({ viewport });
    t.after(() => page.close());
    await page.goto(base + '/' + query);
    await page.locator('#frame[data-ready]').waitFor({ timeout: 6000 });
    return page;
}

const sidebar = page => page.locator('#detail-view .pd-sidebar');
const navItem = (page, name) => sidebar(page).getByRole('button', { name, exact: true });
const callout = page => sidebar(page).locator('[aria-current="page"]');
const region = (page, name) => page.getByRole('region', { name, exact: true });
const alerts = page => region(page, 'Recupero Segnalazioni');
const resolutions = page => region(page, 'Note Delibere Precedenti');
const wait = page => page.locator('#detail-view').getByText('Attendere... caricamento in corso', { exact: true });
const overlay = page => page.getByRole('status').filter({ hasText: 'Recupero Fidi e Garanzie in corso' });
const statusOf = (page, name) => navItem(page, name).getAttribute('data-status');
const near = (actual, expected, tolerance, label) =>
    assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: ${actual} (expected ${expected} +- ${tolerance})`);

async function catalog(page) {
    return page.evaluate(async () => (await (await fetch('/api/practices.json')).json()).practices);
}

// The detail and PEF pages scripts alone, without the application, on a practice of the archive (a real customer).
async function openAlone(t, changes = {}, options = {}) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 897 } });
    t.after(() => page.close());
    const assets = path.resolve(__dirname, '../../bper-emulator/site');
    await page.setContent('<section id="detail-view" style="position:relative;display:block;width:1000px;height:700px"></section>');
    for (const name of ['detail.css', 'pef-extra.css']) await page.addStyleTag({ path: path.join(assets, name) });
    for (const name of ['pef-extra.js', 'detail.js']) await page.addScriptTag({ path: path.join(assets, name) });
    await page.evaluate(([changes, options]) => {
        const practice = {
            key: 'arch-000', role: 'addestramento', ndg: '80000000', name: 'TITOLARE REALE', number: '88000000',
            created: '10/01/2026', operatorName: 'Operatrice', operatorId: 'U910000', officeCode: '92001001',
            branch: '1234', branchName: 'FILIALE REALE', phase: 'DEL', noteAuthor: 'Redattore', notes: '',
            subjects: [{ ndg: '80000000', name: 'TITOLARE REALE', role: 'Richiedente' },
                       { ndg: '80000001', name: 'GARANTE REALE', role: 'Garante' }],
            fidi: [{ id: 'F1', description: 'M. CASA', tooltip: '1 - MUTUO' }], guarantees: [], ...changes,
        };
        BperDetail.render(document.querySelector('#detail-view'), practice, { onState: () => {}, ...options });
        BperDetail.show(4);
    }, [changes, options]);
    return page;
}

// ---- the navigator ----

test('Recupero Segnalazioni opens from the navigator under the identity box and keeps the screen', async t => {
    const page = await open(t, '?practice=demo&loading=off#4');
    await navItem(page, 'Recupero Segnalazioni').click();
    const section = alerts(page);
    await section.waitFor({ timeout: 1000 });
    const text = await section.innerText();
    for (const label of ['Soggetto corrente:', 'Situazione al', 'Banche Dati Interne', 'Banche Dati Esterne',
                         'Politiche Creditizie', 'Accordato/Utilizzato', 'Nota alla verifica preliminare'])
        assert.ok(text.includes(label), label);
    assert.equal(await section.getByRole('button', { name: 'Presa Visione >', exact: true }).isVisible(), true);
    assert.equal(await page.locator('.pd-identity').isVisible(), true);
    assert.equal(await page.locator('[data-panel="subjects"]').isVisible(), false);
    assert.equal(await page.evaluate(() => [location.hash, document.querySelector('.pd-window').dataset.page].join()),
                 '#4,segnalazioni');
});

test('the callout marks the last navigator page opened, not the current step of the practice', async t => {
    const page = await open(t, '?practice=demo&loading=off#4');
    assert.equal(await callout(page).innerText(), 'Elenco Soggetti');
    await navItem(page, 'Recupero Segnalazioni').click();
    assert.equal(await callout(page).innerText(), 'Recupero Segnalazioni');
    assert.equal(await statusOf(page, 'Elenco Soggetti'), 'current');
    assert.equal(await statusOf(page, 'Recupero Segnalazioni'), 'todo');
    // Funzioni > Gestione Documentale is not a navigator page: the callout stays (spec 18.1, MOL 05).
    await page.locator('#detail-view').getByRole('link', { name: /Gestione Documentale/ }).click();
    await region(page, 'Gestione Documentale').waitFor({ timeout: 1000 });
    assert.equal(await callout(page).innerText(), 'Recupero Segnalazioni');
});

test('group headers open and close their items, several groups at once', async t => {
    const page = await open(t, '?practice=demo&loading=off#4');
    const group = name => navItem(page, name);
    assert.equal(await group('Istruttoria').getAttribute('aria-expanded'), 'false');
    await group('Istruttoria').click();
    assert.equal(await group('Istruttoria').getAttribute('aria-expanded'), 'true');
    assert.equal(await navItem(page, 'Note Delibere Precedenti').isVisible(), true);
    assert.equal(await navItem(page, 'Recupero Segnalazioni').isVisible(), true);
    await group('Verifica Preliminare').click();
    assert.equal(await group('Verifica Preliminare').getAttribute('aria-expanded'), 'false');
    assert.equal(await navItem(page, 'Recupero Segnalazioni').count(), 0);
    assert.equal(await navItem(page, 'Note Delibere Precedenti').isVisible(), true);
    await group('Proposta').click();
    assert.equal(await navItem(page, 'Dati Riepilogo').isVisible(), true);
    assert.equal(await page.evaluate(() => location.hash), '#4');
});

test('a screen key brings back the navigator of the reference screenshots', async t => {
    const fresh = {};
    for (const step of [4, 5]) {
        const page = await open(t, `?practice=demo&loading=off#${step}`);
        fresh[step] = await sidebar(page).evaluate(node => node.innerHTML);
    }
    const page = await open(t, '?practice=demo&loading=off#4');
    await navItem(page, 'Istruttoria').click();
    await navItem(page, 'Recupero Segnalazioni').click();
    for (const step of [5, 4]) {
        await page.keyboard.press(String(step));
        await page.waitForFunction(s => location.hash === '#' + s, step);
        assert.equal(await sidebar(page).evaluate(node => node.innerHTML), fresh[step], `screen ${step}`);
    }
});

// loading.js TIMES: an inner tab waits about 1.5 s (spec 9, 10.3), a navigator move 3 s (8 fps cut 04:59.5-05:02.5).
test('at native scale an inner tab answers after the red wait', async t => {
    const page = await open(t, '?practice=demo#5');
    await page.locator('.pd-worktabs').getByRole('button', { name: 'Note da Richiesta', exact: true }).click();
    const start = Date.now();
    assert.equal(await wait(page).isVisible(), true);
    assert.equal(await page.locator('[data-panel="credit"]').isVisible(), true);
    await page.waitForFunction(() => location.hash === '#9', undefined, { timeout: 4000 });
    const elapsed = Date.now() - start;
    assert.ok(elapsed >= 1000 && elapsed <= 3000, `answered after ${elapsed} ms`);
    assert.equal(await page.locator('[data-panel="notes"]').isVisible(), true);
    assert.equal(await wait(page).isVisible(), false);
});

test('at native scale a navigator move to a reference page answers after about three seconds', async t => {
    const page = await open(t, '?practice=demo#5');
    await navItem(page, 'Elenco Soggetti').click();
    const start = Date.now();
    assert.equal(await wait(page).isVisible(), true);
    assert.equal(await callout(page).innerText(), 'Gestione Fidi e Garanzie');
    await page.waitForFunction(() => location.hash === '#4', undefined, { timeout: 6000 });
    const elapsed = Date.now() - start;
    assert.ok(elapsed >= 2500 && elapsed <= 4500, `answered after ${elapsed} ms`);
    assert.equal(await page.locator('[data-panel="subjects"]').isVisible(), true);
    assert.equal(await callout(page).innerText(), 'Elenco Soggetti');
});

test('at native scale a description tooltip still opens at once', async t => {
    const page = await open(t, '?practice=demo#5');
    await page.locator('[data-tooltip-step="6"]').hover();
    await page.waitForFunction(() => location.hash === '#6', undefined, { timeout: 500 });
    assert.equal(await wait(page).count(), 0);
});

// ---- Recupero Segnalazioni ----

// MOL 01 02:42-03:00, MOL 04 01:04-01:20, MOL 11 02:03-02:22 (one sample every 2 s): the ring turns over Elenco
// Soggetti for 14-18 s before Recupero Segnalazioni shows.
test('at native scale Recupero Segnalazioni answers after about sixteen seconds of the red wait', async t => {
    const page = await open(t, '?practice=demo#4');
    await navItem(page, 'Recupero Segnalazioni').click();
    const start = Date.now();
    await page.waitForTimeout(1000);
    assert.equal(await wait(page).isVisible(), true);
    assert.equal(await alerts(page).isVisible(), false);
    assert.equal(await page.locator('[data-panel="subjects"]').isVisible(), true);
    assert.equal(await callout(page).innerText(), 'Elenco Soggetti');
    await alerts(page).waitFor({ timeout: 22000 });
    const elapsed = Date.now() - start;
    assert.ok(elapsed >= 14000 && elapsed <= 20000, `answered after ${elapsed} ms`);
    assert.equal(await wait(page).isVisible(), false);
    assert.equal(await callout(page).innerText(), 'Recupero Segnalazioni');
});

test('the capture window opens Recupero Segnalazioni without waiting', async t => {
    const page = await open(t, '?practice=demo&capture=1#4', { width: 842, height: 617 });
    await navItem(page, 'Recupero Segnalazioni').click();
    assert.equal(await alerts(page).isVisible(), true);
    assert.equal(await wait(page).isVisible(), false);
});

test('a screen key pressed while Recupero Segnalazioni loads is not replaced when the wait ends', async t => {
    const page = await open(t, '?practice=demo#4');
    await navItem(page, 'Recupero Segnalazioni').click();
    await page.waitForTimeout(300);
    await page.keyboard.press('9');
    await page.waitForFunction(() => location.hash === '#9');
    assert.equal(await wait(page).isVisible(), false);
    await page.waitForTimeout(18000);
    assert.equal(await alerts(page).isVisible(), false);
    assert.equal(await page.locator('[data-panel="notes"]').isVisible(), true);
});

test('the current subject lists every subject of the practice and choosing another reloads its data', async t => {
    const page = await open(t, '?practice=demo&loading=off#4');
    const { subjects } = (await catalog(page)).find(p => p.key === 'demo');
    await navItem(page, 'Recupero Segnalazioni').click();
    const select = alerts(page).getByRole('combobox', { name: 'Soggetto corrente:' });
    assert.deepEqual(await select.evaluate(s => [...s.options].map(o => o.textContent)),
                     subjects.map(s => `${s.ndg} - ${s.name} - ${s.role}`));
    assert.equal(await select.evaluate(s => s.selectedIndex), 0);
    await select.selectOption(`${subjects[1].ndg} - ${subjects[1].name} - ${subjects[1].role}`);
    assert.equal(await alerts(page).getByRole('combobox', { name: 'Soggetto corrente:' })
        .evaluate(s => s.selectedIndex), 1);
    assert.match(await alerts(page).innerText(), /Banche Dati Esterne/);
});

test('Recupero Segnalazioni of a practice is the same on every visit', async t => {
    const read = async () => {
        const page = await open(t, '?practice=sim-005&loading=off#4');
        await navItem(page, 'Recupero Segnalazioni').click();
        return alerts(page).evaluate(node => node.innerHTML);
    };
    assert.equal(await read(), await read());
});

test('a real practice shows Recupero Segnalazioni without an invented assessment', async t => {
    const page = await openAlone(t);
    await navItem(page, 'Recupero Segnalazioni').click();
    const section = alerts(page);
    await section.waitFor({ timeout: 1000 });
    assert.equal(await section.locator('.pd-dot').count(), 0);
    const values = await section.evaluate(node => [...node.querySelectorAll('[data-value]')].map(cell => cell.textContent.trim()));
    assert.ok(values.length > 10);
    assert.deepEqual(values.filter(Boolean), []);
});

// MOL 11 02:24-02:32: after Presa Visione the ring turns again and the page comes back on the next subject.
test('Presa Visione moves on to the next subject and stays on Recupero Segnalazioni', async t => {
    const page = await open(t, '?practice=demo&loading=off#4');
    await navItem(page, 'Recupero Segnalazioni').click();
    const index = () => alerts(page).getByRole('combobox', { name: 'Soggetto corrente:' }).evaluate(s => s.selectedIndex);
    const last = (await alerts(page).getByRole('combobox', { name: 'Soggetto corrente:' }).evaluate(s => s.length)) - 1;
    for (let step = 1; step <= last + 1; step++) {
        await alerts(page).getByRole('button', { name: 'Presa Visione >', exact: true }).click();
        assert.equal(await index(), Math.min(step, last));
    }
    assert.equal(await alerts(page).isVisible(), true);
    assert.equal(await callout(page).innerText(), 'Recupero Segnalazioni');
});

test('Avvia Step Succ. of Recupero Segnalazioni moves on to Elenco Soggetti of Istruttoria', async t => {
    const page = await open(t, '?practice=demo&loading=off#4');
    await navItem(page, 'Recupero Segnalazioni').click();
    await alerts(page).getByRole('button', { name: 'Avvia Step Succ. >', exact: true }).click();
    assert.equal(await page.locator('[data-panel="subjects"]').isVisible(), true);
    assert.equal(await page.evaluate(() => location.hash), '#4');
    assert.equal(await navItem(page, 'Istruttoria').getAttribute('data-status'), 'current');
    assert.equal(await callout(page).innerText(), 'Elenco Soggetti');
    assert.equal(await navItem(page, 'Verifica Preliminare').getAttribute('data-status'), 'done');
});

// ---- Note Delibere Precedenti ----

test('Avvia Step Succ. passes through Note Delibere Precedenti and its overlay before Gestione Fidi e Garanzie', async t => {
    const page = await open(t, '?practice=demo#4');
    await page.locator('[data-panel="subjects"]').getByRole('button', { name: /Avvia Step Succ/ }).click();
    const start = Date.now();
    await resolutions(page).waitFor({ timeout: 7000 });
    const shown = Date.now() - start;
    assert.equal(await callout(page).innerText(), 'Note Delibere Precedenti');
    assert.equal(await page.evaluate(() => location.hash), '#4');
    await overlay(page).waitFor({ timeout: 5000 });
    const covered = Date.now() - start;
    await page.waitForFunction(() => location.hash === '#5', undefined, { timeout: 9000 });
    const done = Date.now() - start;
    assert.ok(shown >= 1000 && covered - shown >= 1000 && done - covered >= 3500, `${shown} ${covered} ${done}`);
    assert.equal(await overlay(page).count(), 0);
    assert.equal(await page.locator('[data-panel="credit"]').isVisible(), true);
    assert.equal(await callout(page).innerText(), 'Gestione Fidi e Garanzie');
});

test('with loading off Avvia Step Succ. opens Gestione Fidi e Garanzie at once', async t => {
    const page = await open(t, '?practice=demo&loading=off#4');
    await page.locator('[data-panel="subjects"]').getByRole('button', { name: /Avvia Step Succ/ }).click();
    await page.waitForFunction(() => location.hash === '#5', undefined, { timeout: 500 });
    assert.equal(await resolutions(page).isVisible(), false);
    assert.equal(await page.locator('[data-panel="credit"]').isVisible(), true);
});

test('Note Delibere Precedenti opens from Istruttoria, stays, and its Avvia Step Succ. leads to Gestione Fidi', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await navItem(page, 'Note Delibere Precedenti').click();
    const section = resolutions(page);
    await section.waitFor({ timeout: 1000 });
    for (const label of ['Dati aggiornati al', 'Elenco delibere ultimi 12 mesi', '24 mesi'])
        assert.ok((await section.innerText()).includes(label), label);
    assert.equal(await callout(page).innerText(), 'Note Delibere Precedenti');
    assert.equal(await page.evaluate(() => [location.hash, document.querySelector('.pd-window').dataset.page].join()),
                 '#5,delibere');
    await section.getByRole('button', { name: 'Avvia Step Succ. >', exact: true }).click();
    assert.equal(await page.locator('[data-panel="credit"]').isVisible(), true);
    assert.equal(await callout(page).innerText(), 'Gestione Fidi e Garanzie');
});

test('invented practices list previous resolutions or the empty line, always the same for a practice', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    const keys = (await catalog(page)).filter(p => p.role === 'sintetica' && p.availableSteps.includes(5)).slice(0, 16);
    const seen = {};
    for (const p of keys) {
        const rows = [];
        for (let visit = 0; visit < (p === keys[0] ? 2 : 1); visit++) {
            await page.goto(`${base}/?practice=${p.key}&loading=off#5`);
            await page.locator('#frame[data-ready]').waitFor({ timeout: 6000 });
            await navItem(page, 'Note Delibere Precedenti').click();
            rows.push(await resolutions(page).evaluate(node => [...node.querySelectorAll('tbody tr')]
                .map(row => [...row.cells].map(cell => cell.textContent.trim()))));
        }
        if (rows.length === 2) assert.deepEqual(rows[0], rows[1]);
        seen[p.key] = rows[0];
        for (const cells of rows[0]) {
            assert.equal(cells[0], p.ndg);
            assert.match(cells[1], /^\d\d\/\d\d\/\d{4}$/);
            assert.equal(cells[2], p.branchName);
            assert.match(cells[3], /^\d{8}$/);
            assert.match(cells[4], /^\d{1,3}(\.\d{3})*$/);
        }
    }
    const lists = Object.values(seen);
    assert.ok(lists.some(rows => rows.length > 0), 'no practice with previous resolutions');
    assert.ok(lists.some(rows => rows.length === 0), 'no practice without previous resolutions');
    await page.goto(`${base}/?practice=${Object.keys(seen).find(k => !seen[k].length)}&loading=off#5`);
    await page.locator('#frame[data-ready]').waitFor({ timeout: 6000 });
    await navItem(page, 'Note Delibere Precedenti').click();
    assert.match(await resolutions(page).innerText(), /Elenco delibere precedenti non presente/);
});

test('a real practice has no previous resolutions', async t => {
    const page = await openAlone(t);
    await page.evaluate(() => BperDetail.show(5));
    await navItem(page, 'Note Delibere Precedenti').click();
    assert.match(await resolutions(page).innerText(), /Elenco delibere precedenti non presente/);
    assert.equal(await resolutions(page).locator('tbody tr').count(), 0);
});

// ---- the lower blocks of Gestione Fidi e Garanzie ----

test('scrolled to its end, Gestione Fidi e Garanzie shows Decalage and Note alle Politiche Creditizie', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await page.evaluate(() => { const frame = document.querySelector('.pd-window'); frame.scrollTop = frame.scrollHeight; });
    const credit = page.locator('[data-panel="credit"]');
    const decalage = credit.getByRole('table', { name: 'Decalage' });
    assert.equal(await decalage.isVisible(), true);
    assert.deepEqual(await decalage.evaluate(table => [...table.rows].map(row => [...row.cells].map(c => c.textContent.trim()))),
                     [['Effettivo a -12 mesi', '€ 0'], ['Teorico a +12 mesi', '€ 0']]);
    assert.equal(await credit.getByText('Note alle Politiche Creditizie', { exact: true }).isVisible(), true);
    assert.equal(await credit.getByRole('button', { name: 'Salva', exact: true }).isVisible(), true);
    assert.equal(await credit.getByRole('textbox', { name: 'Note alle Politiche Creditizie' }).isVisible(), true);
});

test('a real practice shows the lower blocks without an invented amount', async t => {
    const page = await openAlone(t);
    await page.evaluate(() => BperDetail.show(5));
    const decalage = page.locator('[data-panel="credit"]').getByRole('table', { name: 'Decalage' });
    assert.deepEqual(await decalage.evaluate(table => [...table.rows].map(row => [...row.cells].map(c => c.textContent.trim()))),
                     [['Effettivo a -12 mesi', ''], ['Teorico a +12 mesi', '']]);
});

test('the lower blocks stay under the capture view and keep the page length of the reference screenshots', async t => {
    const page = await open(t, '?practice=demo&capture=1#5', { width: 842, height: 617 });
    const all = (await catalog(page)).filter(p => p.availableSteps.includes(5));
    const shape = p => `${p.fidi.length}|${p.guarantees.length}|${p.subjects.length}`;
    const picks = [...new Map(all.map(p => [shape(p), p])).values()];
    for (const p of picks) {
        await page.goto(`${base}/?practice=${p.key}&capture=1#5`);
        await page.locator('#frame[data-ready]').waitFor({ timeout: 6000 });
        const box = await page.evaluate(() => {
            const frame = document.querySelector('.pd-window');
            const blocks = document.querySelector('[data-panel="credit"] .pd-lower');
            const page = document.querySelector('.pd-page');
            return { length: page.offsetHeight, top: blocks.getBoundingClientRect().top - frame.getBoundingClientRect().top,
                     bottom: blocks.getBoundingClientRect().bottom - page.getBoundingClientRect().top, view: frame.clientHeight };
        });
        assert.equal(box.length, 777, p.key);
        assert.ok(box.top >= box.view, `${p.key}: blocks at ${box.top} in a view of ${box.view}`);
        assert.ok(box.bottom <= 777, `${p.key}: blocks end at ${box.bottom}`);
    }
});

// ---- visualizzazione ----

test('in visualizzazione the navigator tools are greyed but the exit, Funzioni lists Modulistica, Refresh is greyed', async t => {
    const page = await open(t, '?practice=demo&loading=off&visualizzazione=1#5');
    const tools = sidebar(page).getByRole('toolbar');
    const states = await tools.evaluate(bar => [...bar.querySelectorAll('[role="button"]')]
        .map(tool => [tool.getAttribute('aria-label'), tool.getAttribute('aria-disabled')]));
    assert.deepEqual(states.map(([, disabled]) => disabled), ['true', 'true', 'true', 'true', 'false']);
    assert.equal(states.at(-1)[0], 'Esci dalla pratica');
    assert.equal(await sidebar(page).getByRole('link', { name: /Modulistica/ }).isVisible(), true);
    for (const name of ['Refresh Rapporti', 'Refresh Immobili'])
        assert.equal(await page.locator('[data-panel="credit"]').getByRole('button', { name }).getAttribute('aria-disabled'), 'true');
    await page.evaluate(() => { const frame = document.querySelector('.pd-window'); frame.scrollTop = frame.scrollHeight; });
    assert.equal(await page.locator('[data-panel="credit"]').getByRole('button', { name: 'Salva', exact: true }).count(), 0);
});

test('without the flag the navigator tools work, Modulistica is not listed and Refresh is enabled', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    const disabled = await sidebar(page).getByRole('toolbar').evaluate(bar => [...bar.querySelectorAll('[role="button"]')]
        .map(tool => tool.getAttribute('aria-disabled')));
    assert.deepEqual(disabled, ['false', 'false', 'false', 'false', 'false']);
    assert.equal(await sidebar(page).getByRole('link', { name: /Modulistica/ }).count(), 0);
    assert.equal(await page.locator('[data-panel="credit"]').getByRole('button', { name: 'Refresh Rapporti' })
        .getAttribute('aria-disabled'), 'false');
});

test('in visualizzazione the navigator follows the phase of the practice', async t => {
    const page = await open(t, '?practice=demo&loading=off#4');
    const practices = (await catalog(page)).filter(p => p.role === 'sintetica');
    const labels = { VEP: 'Verifica Preliminare', IST: 'Istruttoria', PRO: 'Proposta', DEL: 'Delibera' };
    for (const phase of Object.keys(labels)) {
        const p = practices.find(x => x.phase === phase);
        await page.goto(`${base}/?practice=${p.key}&loading=off&visualizzazione=1#4`);
        await page.locator('#frame[data-ready]').waitFor({ timeout: 6000 });
        const groups = await sidebar(page).evaluate(node => [...node.querySelectorAll('[data-group]')]
            .map(group => [group.dataset.group, group.dataset.status, group.getAttribute('aria-expanded')]));
        const current = groups.filter(([, status]) => status === 'current');
        assert.deepEqual(current.map(([key]) => key), [phase], p.key);
        assert.equal(current[0][2] ?? 'true', 'true', `${p.key}: current group open`);
        const order = groups.map(([key]) => key);
        const before = order.slice(0, order.indexOf(phase));
        assert.ok(groups.filter(([key]) => before.includes(key)).every(([, status]) => status === 'done'), p.key);
        assert.equal(await callout(page).innerText(), 'Elenco Soggetti');
        if (phase === 'PRO' || phase === 'DEL') {
            const header = await sidebar(page).locator('[data-group="DEL"]').innerText();
            assert.match(header, /^Delibera\s+UFF\.AN\.E\s+CONC\.CR\.[A-Z]+-\.\.\.$/, p.key);
        }
    }
});

test('in visualizzazione some practices passed through Richiesta and returned ones list Note alla Restituzione', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    const practices = (await catalog(page)).filter(p => p.role === 'sintetica' && p.availableSteps.includes(5)).slice(0, 24);
    const found = { richiesta: 0, without: 0, returned: 0 };
    for (const p of practices) {
        await page.goto(`${base}/?practice=${p.key}&loading=off&visualizzazione=1#5`);
        await page.locator('#frame[data-ready]').waitFor({ timeout: 6000 });
        const view = await sidebar(page).evaluate(node => ({
            groups: [...node.querySelectorAll('[data-group]')].map(group => group.dataset.group),
            items: [...node.querySelectorAll('[data-group="IST"] ~ .pd-subitem')].map(item => item.textContent.trim()),
        }));
        found[view.groups.includes('RIC') ? 'richiesta' : 'without']++;
        if (view.items[0] === 'Note alla Restituzione') found.returned++;
    }
    assert.ok(found.richiesta && found.without && found.returned, JSON.stringify(found));
});

test('a real practice in visualizzazione shows no invented deliberating body', async t => {
    const page = await openAlone(t, { phase: 'DEL' }, { visualizzazione: true });
    assert.equal((await sidebar(page).locator('[data-group="DEL"]').innerText()).trim(), 'Delibera');
});

// ---- Avvertenza ----

test('the X of the navigator asks Avvertenza PDCGPC0012A over the navigator, without greying the page', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await sidebar(page).getByRole('button', { name: 'Esci dalla pratica' }).click();
    const dialog = page.getByRole('alertdialog', { name: 'Avvertenza' });
    assert.equal(await dialog.innerText(), 'Avvertenza\nPDCGPC0012A :Uscire dalla pratica?\nAnnulla\nConferma');
    const box = await page.evaluate(() => {
        const rect = selector => document.querySelector(selector).getBoundingClientRect();
        const [dialog, frame, nav, identity] = [rect('[role="alertdialog"]'), rect('.pd-window'), rect('.pd-mainnav'), rect('.pd-identity')];
        const point = document.elementFromPoint(identity.x + identity.width / 2, identity.y + identity.height / 2);
        return { left: dialog.left - nav.left, centre: dialog.top + dialog.height / 2 - (frame.top + frame.height / 2),
                 width: dialog.width, identity: !!point.closest('.pd-identity') };
    });
    near(box.left, 43.6, 2, 'left edge inside the PEF page');
    near(box.centre, 0, 3, 'vertical centre on the frame');
    near(box.width, 718, 3, 'width');
    assert.equal(box.identity, true);
});

test('Annulla closes Avvertenza and stays on the practice', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await sidebar(page).getByRole('button', { name: 'Esci dalla pratica' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Annulla', exact: true }).click();
    assert.equal(await page.getByRole('alertdialog').count(), 0);
    assert.equal(await page.locator('[data-panel="credit"]').isVisible(), true);
    assert.equal(await page.evaluate(() => location.hash), '#5');
});

// MOL 06 15:32-15:36 and MOL 03 37:52-37:56: Conferma leaves the PEF 2.0 session. Its frame becomes a bare logout
// page asking to close the tab; the practice tab stays until the operator closes it.
const LOGOUT = 'Pagina logout PEF\nSi prega di chiudere il tab per poter procedere con la lavorazione/visualizzazione di altre PEF 2.0';

test('Conferma turns the frame into the PEF logout page and leaves the practice tab open', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await sidebar(page).getByRole('button', { name: 'Esci dalla pratica' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Conferma', exact: true }).click();
    assert.equal(await page.getByRole('alertdialog').count(), 0);
    assert.equal(await page.locator('.pd-logout').innerText(), LOGOUT);
    for (const hidden of ['.pd-mainnav', '.pd-identity', '[data-panel="credit"]'])
        assert.equal(await page.locator(hidden).isVisible(), false, hidden);
    assert.equal(await sidebar(page).isVisible(), false);
    assert.equal(await page.locator('#practice-tab').isVisible(), true);
    assert.equal(await page.evaluate(() => location.hash), '#5');
});

test('at native scale Avvertenza waits under the ring before the logout page', async t => {
    const page = await open(t, '?practice=demo#5');
    await sidebar(page).getByRole('button', { name: 'Esci dalla pratica' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Conferma', exact: true }).click();
    assert.equal(await page.getByRole('alertdialog').isVisible(), true);
    assert.equal(await page.locator('#detail-view .ld-spinner').count(), 1);
    await page.locator('.pd-logout').waitFor({ timeout: 4000 });
    assert.equal(await page.getByRole('alertdialog').count(), 0);
});

test('a screen key brings the practice back after the logout page', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    await sidebar(page).getByRole('button', { name: 'Esci dalla pratica' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Conferma', exact: true }).click();
    await page.keyboard.press('4');
    await page.waitForFunction(() => location.hash === '#4');
    assert.equal(await page.locator('.pd-logout').isVisible(), false);
    assert.equal(await page.locator('[data-panel="subjects"]').isVisible(), true);
});

test('a real practice shows the same logout page', async t => {
    const page = await openAlone(t);
    await sidebar(page).getByRole('button', { name: 'Esci dalla pratica' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Conferma', exact: true }).click();
    assert.equal(await page.locator('.pd-logout').innerText(), LOGOUT);
});

test('the new pages and blocks mark no extracted field', async t => {
    const page = await open(t, '?practice=demo&loading=off#5');
    assert.equal(await page.locator('[data-panel="credit"] .pd-lower [data-field]').count(), 0);
    await navItem(page, 'Note Delibere Precedenti').click();
    assert.equal(await resolutions(page).locator('[data-field]').count(), 0);
    await navItem(page, 'Verifica Preliminare').click();
    await navItem(page, 'Recupero Segnalazioni').click();
    assert.equal(await alerts(page).locator('[data-field]').count(), 0);
    await sidebar(page).getByRole('button', { name: 'Esci dalla pratica' }).click();
    assert.equal(await page.getByRole('alertdialog').locator('[data-field]').count(), 0);
});

// ---- native geometry of the PEF 2.0 frame (spec 16.7) ----

const WIDTHS = [[1164, 852], [1280, 897], [1422, 1041], [1600, 772]];

async function frameGeometry(page) {
    return page.evaluate(() => {
        const rect = selector => document.querySelector(selector)?.getBoundingClientRect();
        const vertical = rect('.pd-vertical'), horizontal = rect('.pd-horizontal');
        const lowest = Math.max(rect('.pd-window').bottom, vertical.bottom, horizontal?.height ? horizontal.bottom : 0);
        return { left: rect('#detail-view .pd-mainnav').left, thumb: innerWidth - (vertical.left + vertical.width / 2),
                 bottom: innerHeight - lowest };
    });
}

test('at native scale the PEF 2.0 page starts at 26.7 + W / 12 CSS px', async t => {
    for (const [width, height] of WIDTHS) {
        const page = await open(t, '?practice=demo&loading=off#5', { width, height });
        near((await frameGeometry(page)).left, 26.7 + width / 12, 0.5, `page left at ${width}`);
    }
});

test('at native scale the frame scrollbar sits 43 px and the frame ends 37 px from the window edges', async t => {
    for (const [width, height] of WIDTHS) {
        const page = await open(t, '?practice=demo&loading=off#5', { width, height });
        const geometry = await frameGeometry(page);
        near(geometry.thumb, 43.2, 0.7, `scrollbar centre at ${width}`);
        near(geometry.bottom, 37, 1, `bottom margin at ${width}`);
    }
});

test('at capture scale the frame keeps the box of the reference screenshots', async t => {
    const page = await open(t, '?practice=demo&capture=1#5', { width: 842, height: 617 });
    const box = await page.evaluate(() => ['.pd-window', '.pd-vertical', '.pd-horizontal']
        .map(selector => Object.values(document.querySelector(selector).getBoundingClientRect().toJSON()).slice(0, 4)));
    assert.deepEqual(box, [[89, 129, 719, 451], [808, 131, 9, 446], [90, 580, 715, 9]]);
});
