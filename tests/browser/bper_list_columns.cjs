// Elenco Pratiche column widths at the native scale, against the video frames of spec section 19 (CSS px of the
// operator's browser at 100%). Run like bper_simulator.cjs: a server at BPER_TEST_URL, Playwright from PLAYWRIGHT_MODULE.
const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const base = process.env.BPER_TEST_URL || 'http://127.0.0.1:8765';
let browser;
let longName;
let shortName;
before(async () => {
    browser = await chromium.launch({ channel: 'chrome' });
    const catalogue = await (await fetch(new URL('/api/practices.json', base))).json();
    const practices = Array.isArray(catalogue) ? catalogue : catalogue.practices;
    // The longest name of the catalogue: 30 characters or more are always cut (section 19.3).
    longName = practices.reduce((a, b) => (b.name.length > a.name.length ? b : a));
    assert.ok(longName.name.length >= 30, 'the catalogue needs a practice with a long name');
    // A name of 12-14 characters: whole, and wider than the column's label.
    shortName = practices.find(p => p.name.length >= 12 && p.name.length <= 14);
    assert.ok(shortName, 'the catalogue needs a practice with a short name');
});
after(async () => { await browser?.close(); });

// The list of a practice at scroll 0 (or at the end), in a window of the given width.
async function list(t, key, width, { end = false, capture = false } = {}) {
    const page = await browser.newPage({ viewport: { width, height: 897 } });
    t.after(() => page.close());
    const url = new URL(base);
    url.search = `?practice=${encodeURIComponent(key)}${capture ? '&capture=1' : ''}`;
    url.hash = '1';
    await page.goto(url.href);
    await page.locator('#frame[data-ready]').waitFor({ timeout: 8000 });
    await page.getByRole('scrollbar', { name: /Scorri le colonne/ }).press(end ? 'End' : 'Home');
    return page;
}

// Columns of the populated table: {label: {left, width}} in viewport px, and the ink extent of each first-row cell.
function geometry(page) {
    return page.evaluate(() => {
        const table = document.querySelector('.bl-scroll table');
        const box = table.parentElement.getBoundingClientRect();
        const heads = [...table.tHead.rows[0].cells];
        const row = table.tBodies[0].rows[0];
        const text = cell => {
            const range = document.createRange();
            range.selectNodeContents(cell);
            const rects = [...range.getClientRects()].filter(r => r.width > 0.5);
            return rects.length ? { left: Math.min(...rects.map(r => r.left)), right: Math.max(...rects.map(r => r.right)) } : null;
        };
        return {
            container: { left: box.left, right: box.right },
            columns: Object.fromEntries(heads.map((th, i) => {
                const r = th.getBoundingClientRect();
                return [th.textContent || '#' + i, { left: r.left, width: r.width, cell: text(row.cells[i]) }];
            })),
        };
    });
}

const near = (actual, expected, tolerance, what) =>
    assert.ok(Math.abs(actual - expected) <= tolerance, `${what}: ${actual.toFixed(1)} px, expected ${expected} ± ${tolerance}`);

test('the columns keep the widths of section 19 at 1159, 1283 and 1608 px', async t => {
    // Section 19.3: content-sized, the same at every viewport. Long names fall back to the label: Denom. 102-104.
    const expected = { 'N°': 97, Tipo: 103, 'Importo €': 122, Stato: 110, Fase: 104, Creazione: 124, 'Data Ass./Del.': 155,
        Assegnata: 125, 'Dest.': 84, 'Delib.': 89, 'D.R.': 100, Area: 107, Filiale: 117, 'Denom.': 103 };
    const seen = [];
    for (const width of [1159, 1283, 1608]) {
        const { columns } = await geometry(await list(t, longName.key, width));
        seen.push(Object.fromEntries(Object.keys(expected).map(name => [name, columns[name].width])));
    }
    for (const [name, value] of Object.entries(expected)) {
        assert.ok(seen.every(widths => Math.abs(widths[name] - seen[0][name]) < 0.5), `${name} changes with the window`);
        near(seen[0][name], value, 4, name);
    }
});

test('a name that fits sets its column to the text plus the padding', async t => {
    // The reference practice (17 characters) gives 192 px (section 19.3); another whole name moves the column by just
    // its own difference in width.
    const reference = (await geometry(await list(t, 'reference', 1283))).columns['Denom.'];
    near(reference.width, 192, 3, 'Denom.');
    const page = await list(t, shortName.key, 1283);
    assert.equal(await page.locator('.bl-scroll .bl-cut').count(), 0);
    const other = (await geometry(page)).columns['Denom.'];
    const text = column => column.cell.right - column.cell.left;
    near(reference.width - other.width, text(reference) - text(other), 0.5, 'Denom. difference');
});

test('a long name is cut in a box of about 80 px', async t => {
    const page = await list(t, longName.key, 1283);
    const { columns } = await geometry(page);
    const name = columns['Denom.'];
    const box = await page.locator('.bl-scroll td[data-field="denominazione"], .bl-scroll [data-field="denominazione"]').first()
        .evaluate(el => ({ width: el.getBoundingClientRect().width, cut: el.scrollWidth > el.clientWidth,
            ellipsis: getComputedStyle(el).textOverflow }));
    assert.deepEqual([box.cut, box.ellipsis], [true, 'ellipsis']);
    near(box.width, 79, 3, 'cut box');
    assert.ok(name.width < 110, `Denom. ${name.width} px`);
});

test('the identity columns start where the 18:10 frame shows them', async t => {
    // Video 18:10 at scroll 0 (1283 px, long name): ink from the table container's left edge.
    const { container, columns } = await geometry(await list(t, longName.key, 1283));
    const x = value => value - container.left;
    near(x(columns.ABI.cell.right), 129.4, 2.5, 'ABI value right edge');
    near(x(columns.NDG.cell.right), 254.9, 2.5, 'NDG value right edge');
    near(x(columns['Denom.'].cell.left), 280.5, 2.5, 'Denom. value left edge');
    near(x(columns['N°'].cell.right), 456.4, 3, 'N° value right edge');
});

test('scrolled, NDG settles 4 px and Denom. 13 px left of where they start', async t => {
    // Section 19.4 (1283 px): ABI keeps its place.
    const page = await list(t, longName.key, 1283);
    const start = (await geometry(page)).columns;
    await page.evaluate(() => {
        const scroll = document.querySelector('.bl-scroll');
        scroll.scrollLeft = 200;
        scroll.dispatchEvent(new Event('scroll'));
    });
    const moved = (await geometry(page)).columns;
    near(moved.ABI.cell.right - start.ABI.cell.right, 0, 0.5, 'ABI');
    near(moved.NDG.cell.right - start.NDG.cell.right, -4, 1.5, 'NDG');
    near(moved['Denom.'].cell.left - start['Denom.'].cell.left, -13, 1.5, 'Denom.');
});

test('at the end of the scroll the identity columns stay at 1283 px and leave at 1164 px', async t => {
    // Section 19.4: MOL 04 00:46 (1283, long name) keeps ABI, NDG and Denom.; MOL 01 01:30 (1164, the reference
    // practice) has lost ABI and NDG, and Denom. is cut at the container's left edge.
    const kept = await geometry(await list(t, longName.key, 1283, { end: true }));
    for (const name of ['ABI', 'NDG', 'Denom.']) {
        assert.ok(kept.columns[name].cell.left >= kept.container.left, `${name} left the container at 1283`);
    }
    const lost = await geometry(await list(t, 'reference', 1164, { end: true }));
    for (const name of ['ABI', 'NDG']) {
        assert.ok(lost.columns[name].cell.right <= lost.container.left, `${name} still shows at 1164`);
    }
    const name = lost.columns['Denom.'].cell;
    assert.ok(name.left < lost.container.left && name.right > lost.container.left, 'Denom. is not cut at the left edge');
});
