// Loading states of Nuova PEF and of its PEF 2.0 frame (video spec sections 7, 9, 16.7, 17.2, 18 item 6): what
// shows while the application starts, while a row menu and a practice open, the PEF 2.0 wait, and the Scheda Privati
// launch, with their timing at native scale; ?loading=off and ?capture=1 skip every wait.
// Run against the local simulator (BPER_TEST_URL) with Playwright and Chrome installed. Timings are checked with
// wide margins (a few hundred ms) so that a busy machine does not fail them.
const { before, after, test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const base = process.env.BPER_TEST_URL || 'http://127.0.0.1:8765';
const SLACK = 400;
let browser;

before(async () => { browser = await chromium.launch({ channel: 'chrome' }); });
after(async () => { await browser?.close(); });

// The operator's screen: 1280 x 897 CSS px at 100% zoom (spec 16.1).
async function open(t, path, viewport = { width: 1280, height: 897 }) {
    const page = await browser.newPage({ viewport });
    t.after(() => page.close());
    await page.goto(new URL(path, base).href);
    await page.locator('#frame[data-ready]').waitFor({ timeout: 6000 });
    return page;
}

// Records every change of the shell's loading phase ("idle" when none) and of the row menu, with its time.
async function record(page) {
    await page.evaluate(() => {
        const app = document.querySelector('#application');
        const state = () => [app.dataset.loading || 'idle',
            document.querySelector('.bl-results')?.getAttribute('aria-busy') === 'true' ? 'busy' : '',
            document.querySelector('.bl-menu:not(.bl-ghost)') && !document.querySelector('.bl-menu:not(.bl-ghost)').hidden ? 'menu' : ''].join('|');
        window.__trace = [];
        window.__clicks = [];
        document.addEventListener('click', () => window.__clicks.push(performance.now()), true);
        let last = null;
        const tick = () => {
            const now = state();
            if (now !== last) window.__trace.push([now, performance.now()]);
            last = now;
        };
        tick();
        window.__tick = tick;
        window.__timer = setInterval(tick, 10);
    });
}

// [state, ms after the last recorded click] for each change, the current state included even if no tick saw it yet.
async function trace(page) {
    return page.evaluate(() => {
        window.__tick();
        const click = window.__clicks.at(-1);
        return window.__trace.map(([state, at]) => [state, Math.round(at - click)]);
    });
}

// When the shell first reached that phase after the click.
const phaseAt = (changes, phase) => changes.find(([state, at]) => at >= 0 && state.split('|')[0] === phase)?.[1];

async function openMenu(page) {
    await page.getByRole('button', { name: /Azioni pratica/ }).click();
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).waitFor({ timeout: 3000 });
}

const centre = box => [box.x + box.width / 2, box.y + box.height / 2];
// A ring's size is read from its own box in screen px (layout size times the zoom it is drawn at), never from its
// bounding box: the ring turns, and the bounding box of a turned square grows with the angle of that instant (up to
// 1.41 times at 45 degrees), so a busy machine catching another angle measured 52.4 for 47.4. Its centre does not
// move as it turns, so the bounding box still gives the centre.
const near = (actual, expected, tolerance, label) =>
    assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: ${actual} not within ${tolerance} of ${expected}`);

test('the row menu opens about half a second after its kebab, over a faded table with a ring on the row', async t => {
    const page = await open(t, '/?practice=demo#1');
    await record(page);
    await page.getByRole('button', { name: /Azioni pratica/ }).click();
    // While the table is busy (18m11s): header and row at about 45% contrast, the shell ring over the row's middle.
    await page.waitForFunction(() => document.querySelector('.bl-results').getAttribute('aria-busy') === 'true', null, { timeout: 1000 });
    const look = await page.evaluate(() => {
        const box = el => el.getBoundingClientRect().toJSON();
        const row = document.querySelector('.bl-results tbody tr');
        const ring = document.querySelector('.bl-content .ld-ring');
        const style = getComputedStyle(ring);
        return { ring: box(ring), size: [parseFloat(style.width) * ring.currentCSSZoom, parseFloat(style.height) * ring.currentCSSZoom],
                 scroll: box(document.querySelector('.bl-scroll')),
                 row: box(row), cell: getComputedStyle(row.cells[2]).color, menu: !document.querySelector('.bl-menu').hidden };
    });
    assert.equal(look.menu, false);
    near(centre(look.ring)[0], look.scroll.x + look.scroll.width / 2, 2, 'ring x');
    near(centre(look.ring)[1], look.row.y + look.row.height / 2, 2, 'ring y');
    near(look.size[0], 47.4, 3, 'ring width');
    near(look.size[1], 47.4, 3, 'ring height');
    assert.match(look.cell, /rgba\(.*, 0\.4\d*\)/);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).waitFor({ timeout: 2000 });
    const changes = await trace(page);
    const opened = changes.find(([state]) => state.endsWith('|menu'))[1];
    near(opened, 500, SLACK, 'menu after the kebab click');
});

test('opening a practice from the row menu shows its tab at once over a blank area with the shell ring', async t => {
    const page = await open(t, '/?practice=demo#1');
    await openMenu(page);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    const look = await page.evaluate(() => {
        const app = document.querySelector('#application');
        const element = document.querySelector('#shell-cover .ld-ring');
        const ring = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        const cover = document.querySelector('#shell-cover').getBoundingClientRect();
        const strip = document.querySelector('.pef-nav').getBoundingClientRect();
        return { phase: app.dataset.loading, hash: location.hash, ring: ring.toJSON(), cover: cover.toJSON(), strip: strip.bottom,
                 size: [parseFloat(style.width) * element.currentCSSZoom, parseFloat(style.height) * element.currentCSSZoom],
                 current: document.querySelector('#practice-tab').getAttribute('aria-current'),
                 background: getComputedStyle(document.querySelector('#shell-cover')).backgroundColor };
    });
    assert.equal(look.phase, 'blank');
    assert.equal(look.hash, '#4');
    assert.equal(look.current, 'page');
    assert.equal(look.background, 'rgb(253, 251, 249)');
    near(look.cover.y, look.strip, 1, 'cover top under the tab strip');
    // Spec 7: ~50 video px ring at x=675, y=668 of the 1350 x 1080 frame, i.e. 24 CSS px under the middle of the
    // area under the tab strip (the same 24 px in MOL 01 at 110%).
    near(centre(look.ring)[0], 640, 3, 'ring x');
    near(centre(look.ring)[1], (look.strip + 897) / 2 + 24, 4, 'ring y');
    near(look.size[0], 47.4, 3, 'ring width');
    near(look.size[1], 47.4, 3, 'ring height');
});

test('the closed row menu shows at the top left of the window for a quarter of a second', async t => {
    const page = await open(t, '/?practice=demo#1');
    await openMenu(page);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    const ghost = await page.evaluate(() => document.querySelector('.bl-ghost')?.getBoundingClientRect().toJSON());
    assert.ok(ghost, 'no ghost menu');
    near(ghost.x, 0, 2, 'ghost x');
    near(ghost.y, 0, 2, 'ghost y');
    await page.waitForFunction(() => !document.querySelector('.bl-ghost'), null, { timeout: 1500 });
});

test('the practice page comes through half drawn and washed out, then at full contrast about 7.4 s after the click', async t => {
    const page = await open(t, '/?practice=demo#1');
    await openMenu(page);
    await record(page);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    await page.waitForFunction(() => !document.querySelector('#application').dataset.loading, null, { timeout: 12000 });
    const changes = await trace(page);
    // Main recording 01:55-02:03 at 8 fps: blank 0-4.6 s, half drawn 4.6-5.9, washed with the ring to 6.6, without it
    // to 7.4 s (spec 7).
    near(phaseAt(changes, 'blank'), 0, SLACK, 'blank');
    near(phaseAt(changes, 'partial'), 4625, SLACK, 'partial');
    near(phaseAt(changes, 'washed'), 5875, SLACK, 'washed');
    near(phaseAt(changes, 'settle'), 6625, SLACK, 'settle');
    near(phaseAt(changes, 'idle'), 7375, SLACK, 'idle');
});

test('the washed-out page is the practice page under a half-transparent veil, the ring only until it settles', async t => {
    const page = await open(t, '/?practice=demo#1');
    await openMenu(page);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    const look = async phase => {
        await page.waitForFunction(p => document.querySelector('#application').dataset.loading === p, phase, { timeout: 9000 });
        return page.evaluate(() => ({
            veil: getComputedStyle(document.querySelector('#shell-cover')).backgroundColor,
            ring: document.querySelector('#shell-cover .ld-ring').checkVisibility(),
            // The half-drawn page has lost its navy bars (frame 02m01s), the identity bar among them.
            identity: getComputedStyle(document.querySelector('.pd-identity')).backgroundColor,
        }));
    };
    const partial = await look('partial');
    assert.deepEqual([partial.veil, partial.ring, partial.identity], ['rgba(253, 251, 249, 0.5)', true, 'rgba(0, 0, 0, 0)']);
    const washed = await look('washed');
    assert.equal(washed.ring, true);
    assert.notEqual(washed.identity, 'rgba(0, 0, 0, 0)');
    const settle = await look('settle');
    assert.deepEqual([settle.veil, settle.ring], ['rgba(253, 251, 249, 0.5)', false]);
});

test('another tab shown while the practice loads hides its cover until the practice tab is shown again', async t => {
    // A searched list keeps the practice tab when the Elenco is shown again (a direct link's list does not).
    const page = await open(t, '/#ricerca');
    await page.getByRole('textbox', { name: 'NDG RICHIEDENTE' }).fill('90000001');
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /Azioni pratica/ }).waitFor({ timeout: 4000 });
    await openMenu(page);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    await page.getByRole('button', { name: 'Elenco Pratiche', exact: true }).click();
    assert.equal(await page.locator('#shell-cover').isVisible(), false);
    await page.getByRole('button', { name: /^PEF 2\.0 - Pratica/ }).click();
    assert.equal(await page.locator('#shell-cover').isVisible(), true);
});

test('with the dialog flag a short blank comes before the dialog, and another after Conferma', async t => {
    const page = await open(t, '/?practice=demo&modal=1#1');
    await openMenu(page);
    await record(page);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    // The dialog is already laid out under the blank, so wait for the blank to go.
    await page.waitForFunction(() => !document.querySelector('#application').dataset.loading, null, { timeout: 3000 });
    let changes = await trace(page);
    // Video 18:12: the blank and its ring for 0.25 s, then the grey dialog.
    assert.ok(phaseAt(changes, 'blank') <= SLACK, JSON.stringify(changes));
    near(phaseAt(changes, 'idle'), 250, SLACK, 'dialog after');
    await page.getByRole('alertdialog').getByRole('button', { name: 'Conferma' }).click();
    assert.equal(await page.evaluate(() => document.querySelector('#application').dataset.loading), 'quiet');
    assert.equal(await page.locator('#shell-cover .ld-ring').isVisible(), false);
    await page.waitForFunction(() => !document.querySelector('#application').dataset.loading, null, { timeout: 2000 });
    changes = await trace(page);
    // 18:19: a blank without ring for 0.375 s, then the page at full contrast.
    near(changes.at(-1)[1], 375, SLACK, 'page after Conferma');
});

// The application loading in a full-window frame of a same-origin page, watched from its first moment: goto returns
// only after the load event, which on a busy machine can come after the start phases. window.__app() is its
// document; window.__phases lists every change of its loading phase, with its time.
async function boot(t, path) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 897 } });
    t.after(() => page.close());
    await page.goto(base + '/api/practices.json');
    await page.evaluate(path => {
        const frame = document.createElement('iframe');
        frame.style.cssText = 'position: fixed; inset: 0; width: 1280px; height: 897px; border: 0';
        window.__app = () => frame.contentDocument;
        window.__phases = [];
        let last = null;
        window.__timer = setInterval(() => {
            const app = frame.contentDocument?.querySelector('#application');
            const phase = app && (app.dataset.loading || 'idle');
            if (phase && phase !== last) window.__phases.push([phase, performance.now()]);
            last = phase || last;
        }, 5);
        frame.src = path;
        document.body.append(frame);
    }, path);
    return page;
}

test('the application starts on a splash, then a faded home, then the home', async t => {
    const page = await boot(t, '/');
    await page.waitForFunction(() => window.__app().querySelector('#application')?.dataset.loading === 'splash', null, { timeout: 3000 });
    const splash = await page.evaluate(() => {
        const document = window.__app();
        const logo = document.querySelector('#splash .pef-brand').getBoundingClientRect();
        return { logo: logo.toJSON(), ready: !!document.querySelector('#frame[data-ready]'),
                 background: document.defaultView.getComputedStyle(document.querySelector('#splash')).backgroundColor };
    });
    // Main recording 01:32.75 and 17:57: a white page, the logo (146 x 36 video px) 41 video px above the middle.
    assert.equal(splash.ready, false);
    assert.equal(splash.background, 'rgb(255, 255, 255)');
    near(centre(splash.logo)[0], 640, 3, 'logo x');
    near(centre(splash.logo)[1], 897 / 2 - 39.5, 4, 'logo y');
    near(splash.logo.width, 138, 8, 'logo width');
    await page.waitForFunction(() => window.__app().querySelector('#application').dataset.loading === 'home', null, { timeout: 3000 });
    // MOL 01 01:12.9 (spec 18 item 6): the panel faint, its buttons at full contrast; no codes, kebab, arrows or house.
    const home = await page.evaluate(() => {
        const document = window.__app();
        const opacity = selector => Number(document.defaultView.getComputedStyle(document.querySelector(selector)).opacity);
        const shown = selector => document.querySelector(selector).checkVisibility({ visibilityProperty: true });
        return { panel: opacity('.hm-panel'), buttons: opacity('.hm-actions'), codes: shown('#operator-codes'),
                 kebab: shown('.pef-menu-dots'), arrow: shown('.pef-arrow'), house: shown('#home-tab svg'),
                 name: shown('#operator-name'), tab: shown('#home-tab') };
    });
    assert.deepEqual(home, { panel: 0.2, buttons: 1, codes: false, kebab: false, arrow: false, house: false, name: true, tab: true });
    await page.waitForFunction(() => !!window.__app().querySelector('#frame[data-ready]'), null, { timeout: 2000 });
    assert.equal(await page.evaluate(() => window.__app().querySelector('#application').dataset.loading), undefined);
});

test('the start phases last as the recordings show them', async t => {
    const page = await boot(t, '/');
    await page.waitForFunction(() => !!window.__app().querySelector('#frame[data-ready]'), null, { timeout: 4000 });
    await page.waitForTimeout(50);
    const phases = await page.evaluate(() => window.__phases);
    const at = name => phases.find(([phase]) => phase === name)?.[1];
    // A bare quarter second, the splash 0.5 s, the faded home 0.375 s (01:32.75-01:33.5, MOL 01 01:12.4-01:13.25).
    assert.deepEqual(phases.map(([phase]) => phase).slice(-4), ['boot', 'splash', 'home', 'idle']);
    near(at('splash') - at('boot'), 250, SLACK, 'bare page');
    near(at('home') - at('splash'), 500, SLACK, 'splash');
    near(phases.at(-1)[1] - at('home'), 375, SLACK, 'faded home');
});

for (const flag of ['loading=off', 'capture=1']) {
    test(`with ?${flag} the start, the row menu and the practice need no wait`, async t => {
        const page = await open(t, `/?practice=demo&${flag}#1`);
        assert.equal(await page.evaluate(() => document.querySelector('#application').dataset.loading), undefined);
        await page.getByRole('button', { name: /Azioni pratica/ }).click();
        assert.equal(await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).isVisible(), true);
        await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
        assert.deepEqual(await page.evaluate(() => [document.querySelector('#application').dataset.loading ?? 'none',
            !!document.querySelector('.bl-ghost'), document.querySelector('#shell-cover').hidden]), ['none', false, true]);
    });

    test(`with ?${flag} the application opens on the home without a splash`, async t => {
        const page = await browser.newPage({ viewport: { width: 1280, height: 897 } });
        t.after(() => page.close());
        await page.goto(`${base}/?${flag}`);
        await page.evaluate(() => {
            window.__phases = new Set();
            const app = document.querySelector('#application');
            window.__timer = setInterval(() => app.dataset.loading && window.__phases.add(app.dataset.loading), 5);
        });
        await page.locator('#frame[data-ready]').waitFor({ timeout: 4000 });
        await page.waitForTimeout(300);
        assert.deepEqual(await page.evaluate(() => [...window.__phases]), []);
    });
}

// The pixels of two screenshots whose channels differ by more than 2 levels. A layer that went away can leave
// Chrome's anti-aliasing of a rounded corner 1-2 levels off (seen on the Funzioni box after an opening): no eye,
// classifier or OCR sees that, while a leftover veil, bare background or ring differs by tens of levels.
async function differing(page, a, b) {
    return page.evaluate(async ([a, b]) => {
        const pixels = async data => {
            const image = new Image();
            image.src = 'data:image/png;base64,' + data;
            await image.decode();
            const context = new OffscreenCanvas(image.width, image.height).getContext('2d');
            context.drawImage(image, 0, 0);
            return context.getImageData(0, 0, image.width, image.height).data;
        };
        const [x, y] = await Promise.all([pixels(a), pixels(b)]);
        if (x.length !== y.length) return -1;
        let count = 0;
        for (let i = 0; i < x.length; i += 4) {
            if (Math.max(Math.abs(x[i] - y[i]), Math.abs(x[i + 1] - y[i + 1]), Math.abs(x[i + 2] - y[i + 2])) > 2) count++;
        }
        return count;
    }, [a.toString('base64'), b.toString('base64')]);
}

// The waits only delay what is drawn: once over, the page is the one ?loading=off draws at once.
test('once its waits are over the home is the home drawn without waits', async t => {
    const shot = async flag => (await open(t, `/?${flag}`)).screenshot();
    const page = await open(t, '/?loading=off');
    assert.equal(await differing(page, await shot(''), await shot('loading=off')), 0);
});

test('once its opening is over a practice opened from the row menu is the one opened without waits', async t => {
    const shot = async flag => {
        const page = await open(t, `/?practice=demo${flag}#1`);
        await openMenu(page);
        await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
        await page.waitForFunction(() => !document.querySelector('#application').dataset.loading && !document.querySelector('.bl-ghost'),
            null, { timeout: 10000 });
        return page.screenshot();
    };
    const page = await open(t, '/?loading=off');
    assert.equal(await differing(page, await shot(''), await shot('&loading=off')), 0);
});

test('a direct link to a practice opens it without the splash or the opening sequence', async t => {
    const page = await open(t, '/?practice=demo#4');
    assert.equal(await page.evaluate(() => document.querySelector('#application').dataset.loading), undefined);
    assert.equal(await page.locator('#shell-cover').isVisible(), false);
});

test('a PEF 2.0 request shows the red wait line and the navy ring over the frame, then its answer', async t => {
    const page = await open(t, '/?practice=demo#4');
    const during = await page.evaluate(() => {
        window.__answered = false;
        BperLoading.run(document.querySelector('#detail-view'), 600, () => { window.__answered = true; });
        const frame = document.querySelector('.pd-window').getBoundingClientRect();
        const ring = document.querySelector('#detail-view .ld-spinner').getBoundingClientRect();
        const wait = document.querySelector('.pd-page .ld-wait');
        return { text: wait.textContent, colour: getComputedStyle(wait).color, answered: window.__answered,
                 ring: [ring.x + ring.width / 2 - frame.x - frame.width / 2, ring.y + ring.height / 2 - frame.y - frame.height / 2] };
    });
    assert.deepEqual([during.text, during.colour, during.answered], ['Attendere... caricamento in corso', 'rgb(238, 0, 0)', false]);
    near(during.ring[0], 0, 2, 'ring x');
    near(during.ring[1], 0, 2, 'ring y');
    await page.waitForFunction(() => window.__answered, null, { timeout: 1000 + SLACK });
    assert.equal(await page.locator('#detail-view .ld-wait, #detail-view .ld-spinner').count(), 0);
});

test('a jump to another state with a key drops a PEF 2.0 request still waiting', async t => {
    const page = await open(t, '/?practice=demo#4');
    await page.evaluate(() => {
        window.__answered = false;
        BperLoading.run(document.querySelector('#detail-view'), 600, () => { window.__answered = true; });
    });
    await page.keyboard.press('5');
    await page.waitForFunction(() => location.hash === '#5');
    await page.waitForTimeout(600 + SLACK);
    assert.deepEqual(await page.evaluate(() => [window.__answered,
        document.querySelectorAll('#detail-view .ld-wait, #detail-view .ld-spinner').length]), [false, 0]);
});

test('a PEF 2.0 request with ?loading=off is answered at once and draws nothing', async t => {
    const page = await open(t, '/?practice=demo&loading=off#4');
    const state = await page.evaluate(() => {
        let answered = false;
        BperLoading.run(document.querySelector('#detail-view'), 600, () => { answered = true; });
        return [answered, document.querySelectorAll('#detail-view .ld-wait, #detail-view .ld-spinner').length];
    });
    assert.deepEqual(state, [true, 0]);
});

// The stand-in drives one page only: the new window is an empty frame of this page, which window.open hands back.
async function catchWindow(page) {
    await page.evaluate(() => {
        window.open = (url, name) => {
            const frame = document.createElement('iframe');
            frame.name = name;
            document.body.append(frame);
            window.__opened = { url, frame };
            if (url) frame.src = url;
            return frame.contentWindow;
        };
    });
}

test('Apri Scheda Privati first shows a blank "Caricamento in corso..." page for about 4 s, then the Scheda Privati', async t => {
    const page = await open(t, '/?console=1&practice=demo#4');
    await catchWindow(page);
    await page.getByRole('button', { name: 'Apri Scheda Privati' }).click();
    const started = await page.evaluate(() => performance.now());
    const loading = await page.evaluate(() => {
        const doc = window.__opened.frame.contentDocument;
        return { url: window.__opened.url, title: doc.title, text: doc.body.innerText.trim(), background: getComputedStyle(doc.body).backgroundColor };
    });
    assert.deepEqual(loading, { url: '', title: 'Caricamento in corso...', text: '', background: 'rgb(255, 255, 255)' });
    await page.waitForFunction(() => { try { return window.__opened.frame.contentDocument.title === 'BPER Scheda Privati'; } catch { return false; } },
        null, { timeout: 4000 + 2000 });
    const shown = await page.evaluate(() => [performance.now(), window.__opened.frame.contentWindow.location.hash]);
    near(shown[0] - started, 4000, 1000, 'Scheda after');
    assert.match(shown[1], /^#\/schede\/[^/]+\/[^/]+$/);
});

test('Apri Scheda Privati with ?loading=off opens the Scheda Privati at once', async t => {
    const page = await open(t, '/?console=1&practice=demo&loading=off#4');
    await catchWindow(page);
    await page.getByRole('button', { name: 'Apri Scheda Privati' }).click();
    assert.match(await page.evaluate(() => window.__opened.url), /\/schede\/SchedaPrivati\/#\/schede\//);
});

test('the header kebab sits 44 px from the right edge at native scale, at every width seen', async t => {
    for (const [width, height] of [[1164, 849], [1280, 897], [1422, 1040], [1600, 772]]) {
        const page = await open(t, '/?practice=demo#1', { width, height });
        const dots = await page.locator('.pef-menu-dots').boundingBox();
        near(width - (dots.x + dots.width / 2), 44, 0.5, `kebab at ${width}`);
    }
});

test('at capture scale the header kebab stays where the reference screenshots have it', async t => {
    const page = await open(t, '/?practice=demo&capture=1#1', { width: 842, height: 617 });
    const dots = await page.locator('.pef-menu-dots').boundingBox();
    near(842 - (dots.x + dots.width / 2), 31, 0.05, 'kebab');
});

test('at 1600 x 772 the Elenco scrolls vertically under the tab strip; at 1280 x 897 it fits', async t => {
    const measure = async viewport => {
        const page = await open(t, '/?practice=demo#1', viewport);
        return page.evaluate(() => {
            const view = document.querySelector('#list-view');
            const zoom = view.getBoundingClientRect().height / view.offsetHeight;
            return { range: (view.scrollHeight - view.clientHeight) * zoom, overflow: getComputedStyle(view).overflowY };
        });
    };
    const short = await measure({ width: 1600, height: 772 });
    // MOL 07 02:29: the thumb is 91% of the track, about 60 CSS px of scroll (spec 16.7).
    assert.equal(short.overflow, 'auto');
    near(short.range, 60, 15, 'scroll range at 1600 x 772');
    assert.equal((await measure({ width: 1280, height: 897 })).range, 0);
});

// The X of the practice tab closes it (MOL 06 15:36, after the logout page of Uscire dalla pratica; MOL 03 37:56).
const practiceTab = page => page.getByRole('button', { name: /^PEF 2\.0 - Pratica/ });

test('the X of the practice tab closes the tab and shows Elenco Pratiche', async t => {
    const page = await open(t, '/?practice=demo&loading=off#4');
    await page.locator('#practice-tab i').click();
    assert.deepEqual(await page.evaluate(() => [location.hash, document.querySelector('#practice-tab').hidden,
        document.querySelector('#list-view').hidden, document.querySelector('#list-tab').getAttribute('aria-current')]),
        ['#1', true, false, 'page']);
});

test('a click on the practice tab away from its X shows the practice', async t => {
    // A searched list keeps the practice tab when the Elenco is shown again (a direct link's list does not).
    const page = await open(t, '/?loading=off#ricerca');
    await page.getByRole('textbox', { name: 'NDG RICHIEDENTE' }).fill('90000001');
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /Azioni pratica/ }).waitFor({ timeout: 4000 });
    await openMenu(page);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    await page.getByRole('button', { name: 'Elenco Pratiche', exact: true }).click();
    await page.locator('#practice-caption').click();
    assert.deepEqual(await page.evaluate(() => [location.hash, document.querySelector('#practice-tab').hidden,
        document.querySelector('#detail-view').hidden]), ['#4', false, false]);
});

test('the X of the practice tab keeps the searched results in Elenco Pratiche', async t => {
    const page = await open(t, '/?loading=off#ricerca');
    await page.getByRole('textbox', { name: 'NDG RICHIEDENTE' }).fill('90000001');
    await page.keyboard.press('Enter');
    const rows = () => page.getByRole('table', { name: 'Elenco pratiche' }).evaluate(table =>
        [...table.tBodies[0].rows].map(row => row.textContent.trim()));
    await page.getByRole('button', { name: /Azioni pratica/ }).waitFor({ timeout: 4000 });
    const found = await rows();
    await openMenu(page);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    await page.locator('#practice-tab i').click();
    assert.equal(await practiceTab(page).count(), 0);
    assert.deepEqual(await rows(), found);
});

test('the X of the practice tab during its opening drops the opening', async t => {
    const page = await open(t, '/?practice=demo#1');
    await openMenu(page);
    await page.getByRole('menuitem', { name: 'Visualizza Pratica' }).click();
    await page.locator('#practice-tab i').click();
    const phase = () => page.evaluate(() => document.querySelector('#application').dataset.loading ?? 'none');
    assert.deepEqual([await phase(), await page.locator('#shell-cover').isVisible()], ['none', false]);
    // Past the moment the half-drawn page would have come.
    await page.waitForTimeout(4625 + SLACK);
    assert.deepEqual([await phase(), await practiceTab(page).count()], ['none', 0]);
});

test('a search with ?loading=off lists what it finds at once', async t => {
    const page = await open(t, '/?loading=off#ricerca');
    await page.getByRole('textbox', { name: 'NDG RICHIEDENTE' }).fill('90000001');
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#list-view').isVisible(), true);
});
