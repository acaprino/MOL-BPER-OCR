// Scripted operator for the live edge-agent test (live_test.py): drives the BPER emulator in a real Chrome window
// through the Chrome DevTools Protocol, with CDP input events only (the OS mouse and keyboard are never touched),
// and reports what the page shows as timestamped probes: the truth timeline the harness scores against.
//
//   node bper-emulator/live_driver.cjs --url http://127.0.0.1:PORT/ --scenario resolved.json --out DIR
//        [--headless] [--record] [--chrome-ui 87]
//
// stdout carries one JSON event per line (ready, action, settled, skip, probe, frame, error, done). A headed run
// waits for "go" on stdin after "ready", and every run waits for "quit" after "done" before closing Chrome.
// --record (headless) saves a viewport PNG at each change of the page and every 300 ms while it loads.
'use strict';

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const { parseArgs } = require('node:util');

const CHROME = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const now = () => Date.now() / 1000;
const emit = (event, data = {}) => process.stdout.write(JSON.stringify({ event, t: now(), ...data }) + '\n');

const HOVER = {
    evidence: '#list-view .bl-evidence',
    fido: '#detail-view [data-tooltip-step="6"]',
    'guarantee-1': '#detail-view [data-tooltip-step="7"]',
    'guarantee-2': '#detail-view [data-tooltip-step="8"]',
};
const TAB_STEP = { fidi: '5', note: '9' };

// What the page shows, read from the DOM: view, loading flags, list offset and tooltip, detail page and tooltip.
const PROBE = `(() => {
  const q = s => document.querySelector(s);
  const shown = el => !!el && !el.hidden && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const app = q('#application');
  const s = { ready: !!q('#frame[data-ready]') };
  s.view = ['home', 'search', 'list', 'detail'].find(v => { const el = q('#' + v + '-view'); return el && !el.hidden; }) || null;
  s.loading = !!(app && app.dataset.loading) || shown(q('#shell-cover')) || shown(q('#splash'))
    || !!q('#detail-view .ld-wait, #detail-view .ld-spinner') || !!q('#list-view .ld-ring') || !!q('.rp-submit:disabled');
  s.veil = shown(q('.pm-veil'));
  s.ghost = !!q('.bl-ghost');
  if (s.view === 'list') {
    const sc = q('#bl-results-scroll');
    s.scroll = sc ? Math.round(sc.scrollLeft) : 0;
    s.scrollMax = sc ? Math.max(0, Math.round(sc.scrollWidth - sc.clientWidth)) : 0;
    s.tooltip = shown(q('#bper-evidence-tooltip'));
    s.menu = shown(q('#list-view .bl-menu'));
    s.hint = shown(q('#list-view .bl-hint'));
    s.rows = [...document.querySelectorAll('#list-view .bl-results tbody [data-field="ndg"]')].map(td => td.textContent.trim());
  }
  if (s.view === 'detail') {
    const w = q('#detail-view .pd-window');
    s.page = w ? (w.dataset.page || null) : null;
    s.tooltip = shown(q('#pd-tip'));
    const d = q('#detail-view [aria-describedby="pd-tip"]');
    s.tooltipStep = d ? Number(d.dataset.tooltipStep) : null;
    const id = q('#detail-view .pd-identity');
    const m = id ? id.textContent.match(/NDG:\\s*([^\\s-]+)/) : null;
    s.ndg = m ? m[1] : null;
    s.notice = !!q('#detail-view .nd-notice');
    s.viewOnly = !!q('#detail-view [data-action="next"][aria-disabled="true"]');
    s.alert = !!q('#detail-view .pd-alert');
    s.scrollTop = w ? Math.round(w.scrollTop) : 0;
  }
  s.title = document.title;
  return s;
})()`;

class Session {
    constructor(url) {
        this.ws = new WebSocket(url);
        this.id = 0;
        this.pending = new Map();
        this.opened = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
        this.ws.onmessage = event => {
            const msg = JSON.parse(event.data);
            if (msg.id && this.pending.has(msg.id)) {
                const { resolve, reject } = this.pending.get(msg.id);
                this.pending.delete(msg.id);
                msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
            }
        };
    }
    // A command sent while the page navigates can stay unanswered: without the timeout the probe loop would stop
    // on it and every later wait would read a stale state.
    async send(method, params = {}, timeoutMs = 10000) {
        await this.opened;
        const id = ++this.id;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.pending.delete(id);
                reject(new Error(`${method}: no answer within ${timeoutMs} ms`));
            }, timeoutMs);
            this.pending.set(id, {
                resolve: value => { clearTimeout(timer); resolve(value); },
                reject: error => { clearTimeout(timer); reject(error); },
            });
            this.ws.send(JSON.stringify({ id, method, params }));
        });
    }
    close() { try { this.ws.close(); } catch { /* closing */ } }
}

async function evaluate(page, expression) {
    const { result, exceptionDetails } = await page.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, 3000);
    if (exceptionDetails) throw new Error('evaluate: ' + (exceptionDetails.exception?.description || exceptionDetails.text));
    return result.value;
}

// The page as an operator opens it: native waits unless the scenario turns them off, the practice's mode.
function pageUrl(base, scenario, mode) {
    const url = new URL(base);
    if (!scenario.loading) url.searchParams.set('loading', 'off');
    if (mode === 'visualizzazione') url.searchParams.set('visualizzazione', '1');
    return url.href;
}

function firstMode(scenario) {
    const first = scenario.steps.find(step => step.practice);
    return first ? (scenario.modes || {})[first.practice] || 'lavorazione' : 'lavorazione';
}

// ------------------------------------------------------------------ Chrome

async function launch({ headless, geometry, profile, viewport }) {
    fs.mkdirSync(path.join(profile, 'Default'), { recursive: true });
    // Browser zoom as an operator sets it (Ctrl +/-): the page zooms, Chrome's own bars stay at 100%. A zoom by
    // --force-device-scale-factor would shrink the tab strip and the address bar as well.
    const level = Math.log(geometry.zoom) / Math.log(1.2);
    fs.writeFileSync(path.join(profile, 'Default', 'Preferences'), JSON.stringify({
        partition: { default_zoom_level: { x: level } },
        browser: { has_seen_welcome_page: true }, translate: { enabled: false },
    }));
    const [w, h] = headless ? [viewport[0] + 16, viewport[1] + 95] : geometry.window;
    const [x, y] = geometry.position;
    const args = ['--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
        '--disable-search-engine-choice-screen', '--disable-sync', '--disable-extensions', '--disable-component-update',
        '--disable-default-apps', '--disable-features=Translate,DownloadBubble,ChromeWhatsNewUI', '--hide-crash-restore-bubble',
        '--test-type', '--password-store=basic', '--force-device-scale-factor=1', `--window-position=${x},${y}`,
        `--window-size=${w},${h}`, ...(headless ? ['--headless=new', '--hide-scrollbars=false'] : []), 'about:blank'];
    const proc = spawn(CHROME, args, { stdio: 'ignore' });
    let port = 0;
    for (let i = 0; i < 300 && !port; i++) {
        try { port = Number(fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]); } catch { /* starting */ }
        if (!port) await sleep(100);
    }
    if (!port) throw new Error('Chrome did not open its DevTools port');
    const base = `http://127.0.0.1:${port}`;
    const version = await (await fetch(base + '/json/version')).json();
    const browser = new Session(version.webSocketDebuggerUrl);
    let target;
    for (let i = 0; i < 50 && !target; i++) {
        target = (await (await fetch(base + '/json/list')).json()).find(t => t.type === 'page');
        if (!target) await sleep(100);
    }
    const page = new Session(target.webSocketDebuggerUrl);
    await page.send('Page.enable');
    await page.send('Runtime.enable');
    const { windowId } = await browser.send('Browser.getWindowForTarget', { targetId: target.id });
    return { proc, browser, page, windowId };
}

async function metrics(page) {
    return evaluate(page, '({ inner: [innerWidth, innerHeight], outer: [outerWidth, outerHeight], dpr: devicePixelRatio })');
}

// Headless Chrome draws no bars, so its window is sized until the viewport, in device pixels, is the viewport a
// headed window of the scenario's size would have under Chrome's tab strip and toolbar.
async function fitViewport(page, browser, windowId, viewport) {
    for (let i = 0; i < 4; i++) {
        await sleep(150);
        const m = await metrics(page);
        const dw = viewport[0] - Math.round(m.inner[0] * m.dpr);
        const dh = viewport[1] - Math.round(m.inner[1] * m.dpr);
        if (!dw && !dh) return;
        const { bounds } = await browser.send('Browser.getWindowBounds', { windowId });
        await browser.send('Browser.setWindowBounds', { windowId, bounds: { width: bounds.width + dw, height: bounds.height + dh } });
    }
}

// ------------------------------------------------------------------ the operator

class Operator {
    constructor({ page, browser, windowId, scenario, catalogue, headless, viewportOf, url }) {
        Object.assign(this, { page, browser, windowId, scenario, catalogue, headless, viewportOf, url });
        this.geometry = { ...scenario.geometry };
        this.state = null;
        this.signature = '';
        this.since = 0;
        this.factor = 1;
        this.probing = false;
    }

    // ---- probes
    async probe() {
        const state = await evaluate(this.page, PROBE);
        state.win = [...this.geometry.window];
        const signature = JSON.stringify({ ...state, title: undefined });
        if (signature !== this.signature) {
            this.signature = signature;
            this.since = Date.now();
            this.state = state;
            emit('probe', { state });
            if (this.recorder) await this.recorder.capture();
        } else if (this.recorder && state.loading) {
            await this.recorder.maybeAnimate();
        }
        return state;
    }

    async probeLoop() {
        this.probing = true;
        while (this.probing) {
            try { await this.probe(); } catch { /* the page may be navigating */ }
            await sleep(100);
        }
    }

    // Wait until the page is not loading, matches what the step expects, and has not changed for 300 ms.
    async settle(expect = () => true, timeoutMs = 25000, what = 'state') {
        const end = Date.now() + timeoutMs;
        while (Date.now() < end) {
            const s = this.state;
            if (s && s.ready && !s.loading && !s.ghost && expect(s) && Date.now() - this.since >= 300) {
                emit('settled', { what, state: s });
                return s;
            }
            await sleep(50);
        }
        throw new Error(`no settled ${what} within ${timeoutMs} ms (last: ${JSON.stringify(this.state)})`);
    }

    // ---- input events
    async mouse(type, x, y, extra = {}) {
        await this.page.send('Input.dispatchMouseEvent', { type, x: x / this.factor, y: y / this.factor, button: 'none', ...extra });
    }

    async click(x, y) {
        await this.mouse('mouseMoved', x, y);
        await this.mouse('mousePressed', x, y, { button: 'left', buttons: 1, clickCount: 1 });
        await this.mouse('mouseReleased', x, y, { button: 'left', buttons: 0, clickCount: 1 });
    }

    async key(key, code, keyCode, extra = {}) {
        await this.page.send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, windowsVirtualKeyCode: keyCode, ...extra });
        await this.page.send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: keyCode });
    }

    // Centre of the first visible element matching the selector, in the page's CSS pixels; null when none shows.
    async center(selector) {
        return evaluate(this.page, `(() => {
            const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.getClientRects().length);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return [r.left + r.width / 2, r.top + r.height / 2, r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth];
        })()`);
    }

    async clickOn(selector) {
        const at = await this.center(selector);
        if (!at) throw new Error('nothing to click: ' + selector);
        await this.click(at[0], at[1]);
        return at;
    }

    // CDP takes mouse coordinates in its own units; measure them against clientX once, at a neutral point.
    async calibrate() {
        await evaluate(this.page, `window.__liveCalib = null; addEventListener('mousemove', e => { window.__liveCalib = [e.clientX, e.clientY]; }, { once: true }); 1`);
        await this.page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 40, y: 40, button: 'none' });
        await sleep(50);
        const seen = await evaluate(this.page, 'window.__liveCalib');
        this.factor = seen && seen[0] ? seen[0] / 40 : 1;
        emit('action', { do: 'calibrate', factor: this.factor });
    }

    async park() {
        // A point of the application header that has no hover effect, so the pointer changes no pixel.
        const at = await evaluate(this.page, `(() => { const r = document.querySelector('.pef-header')?.getBoundingClientRect();
            return r ? [r.left + Math.min(300, r.width * 0.3), r.top + r.height / 2] : [5, 5]; })()`);
        await this.mouse('mouseMoved', at[0], at[1]);
    }

    // ---- steps
    // The page was opened once, before "ready" (the window needs its title for the harness's check).
    async start() {
        await this.settle(s => s.view === 'home', 30000, 'home');
        await this.calibrate();
        await this.park();
    }

    // The mode is page-wide in the emulator (?visualizzazione=1), as the real application sets it per practice
    // before the page opens: a practice in the other mode needs the page loaded again.
    async ensureMode(key) {
        const mode = (this.scenario.modes || {})[key] || 'lavorazione';
        if (mode === this.mode) return;
        this.mode = mode;
        emit('action', { do: 'mode-reload', practice: key, mode });
        await this.page.send('Page.navigate', { url: pageUrl(this.url, this.scenario, mode) });
        await sleep(500);
        await this.settle(s => s.view === 'home', 30000, 'home in ' + mode);
        await this.park();
    }

    async search(key) {
        await this.ensureMode(key);
        const p = this.practice(key);
        if (this.state?.view !== 'search') {
            const tab = await this.center('#search-tab');
            if (tab) await this.click(tab[0], tab[1]);
            else await this.clickOn('#home-view .hm-primary');
            await this.settle(s => s.view === 'search', 10000, 'search form');
        }
        await this.clickOn('#rp-ndg');
        await this.key('a', 'KeyA', 65, { modifiers: 2, commands: ['selectAll'] });
        await this.page.send('Input.insertText', { text: p.ndg });
        await this.key('Enter', 'Enter', 13, { text: '\r', unmodifiedText: '\r' });
        await this.park();
        await this.settle(s => s.view === 'list' && (s.rows || []).includes(p.ndg), 15000, 'results');
    }

    async open(key) {
        const p = this.practice(key);
        await this.clickOn(`#list-view .bl-kebab[aria-label="Azioni pratica ${p.number}"]`);
        await this.settle(s => s.view === 'list' && s.menu, 10000, 'row menu');
        await this.clickOn('#list-view .bl-menu button');
        await this.park();
        await this.settle(s => s.view === 'detail' && s.page === 'subjects' && s.ndg === p.ndg, 30000, 'soggetti');
    }

    async next() {
        const greyed = await evaluate(this.page,
            `!!document.querySelector('#detail-view [data-action="next"][aria-disabled="true"]')`);
        if (greyed) {
            // In visualizzazione "Avvia Step Succ." is greyed: an operator opens Gestione Fidi from the navigator.
            emit('action', { do: 'next-via-navigator' });
            if (!(await this.center('#detail-view [data-nav="IST.fidi"]'))) await this.clickOn('#detail-view [data-group="IST"]');
            await this.clickOn('#detail-view [data-nav="IST.fidi"]');
        } else {
            await this.clickOn('#detail-view [data-action="next"]');
        }
        await this.park();
        await this.settle(s => s.view === 'detail' && s.page === 'credit', 30000, 'fidi e garanzie');
    }

    async tab(to) {
        await this.clickOn(`#detail-view .pd-worktabs button[data-step="${TAB_STEP[to]}"]`);
        await this.park();
        await this.settle(s => s.view === 'detail' && s.page === (to === 'note' ? 'notes' : 'credit'), 15000, to);
    }

    async list() {
        await this.clickOn('#list-tab');
        await this.park();
        await this.settle(s => s.view === 'list', 10000, 'list');
    }

    async scrollList(to) {
        const box = await this.center('#bl-results-scroll');
        if (!box) throw new Error('no list to scroll');
        for (let attempt = 0; attempt < 4; attempt++) {
            await sleep(150);
            const s = this.state;
            // From the list's own range, read now: the site's offsets move (native state 1 opens at 0).
            const target = to === 'start' ? 0 : to === 'end' ? s.scrollMax : Math.round(s.scrollMax / 2);
            const delta = target - s.scroll;
            if (Math.abs(delta) <= 2) break;
            await this.page.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: box[0] / this.factor, y: box[1] / this.factor,
                deltaX: delta, deltaY: 0, button: 'none' });
            await sleep(120);
        }
        await this.park();
        await this.settle(s => s.view === 'list', 5000, 'list ' + to);
    }

    async hover(target) {
        const at = await this.center(HOVER[target]);
        if (!at) return false;
        await this.mouse('mouseMoved', at[0], at[1]);
        await this.settle(s => s.tooltip, 5000, 'tooltip ' + target);
        return true;
    }

    async unhover() {
        await this.park();
        await this.settle(s => !s.tooltip, 5000, 'no tooltip');
    }

    async resize(step) {
        const [w, h] = step.window;
        const [x, y] = step.position || this.geometry.position;
        this.geometry = { ...this.geometry, window: [w, h], position: [x, y] };
        if (this.headless) await fitViewport(this.page, this.browser, this.windowId, this.viewportOf([w, h]));
        else await this.browser.send('Browser.setWindowBounds', { windowId: this.windowId,
            bounds: { left: x, top: y, width: w, height: h, windowState: 'normal' } });
        await sleep(400);
        await this.settle(() => true, 10000, 'resized');
    }

    practice(key) {
        const p = this.catalogue.get(key);
        if (!p) throw new Error('practice not in the catalogue: ' + key);
        return p;
    }

    async run() {
        let ok = true;
        for (const [index, step] of this.scenario.steps.entries()) {
            emit('action', { index, ...step });
            try {
                let shown = true;
                if (step.do === 'start') await this.start();
                else if (step.do === 'search') await this.search(step.practice);
                else if (step.do === 'open') await this.open(step.practice);
                else if (step.do === 'next') await this.next();
                else if (step.do === 'tab') await this.tab(step.to);
                else if (step.do === 'list') await this.list();
                else if (step.do === 'scroll-list') await this.scrollList(step.to);
                else if (step.do === 'hover') shown = await this.hover(step.target);
                else if (step.do === 'unhover') await this.unhover();
                else if (step.do === 'resize') await this.resize(step);
                else if (step.do === 'wait') await sleep(step.ms);
                if (!shown) {
                    emit('skip', { index, reason: 'not on this practice: ' + step.target });
                    continue;
                }
                const dwell = step.do === 'wait' ? 0 : (step.dwell_ms ?? this.scenario.dwell_ms);
                if (dwell) await sleep(dwell);
            } catch (error) {
                emit('error', { index, message: String(error.message || error) });
                ok = false;
                break;
            }
        }
        return ok;
    }
}

// ------------------------------------------------------------------ recording (headless)

class Recorder {
    constructor(page, operator, out) {
        Object.assign(this, { page, operator, out });
        this.count = 0;
        this.last = 0;
        fs.mkdirSync(path.join(out, 'frames'), { recursive: true });
    }

    async capture() {
        const t = now();
        const { data } = await this.page.send('Page.captureScreenshot', { format: 'png' });
        const file = `frames/${String(this.count++).padStart(5, '0')}.png`;
        fs.writeFileSync(path.join(this.out, file), Buffer.from(data, 'base64'));
        const g = this.operator.geometry;
        emit('frame', { file, window: [g.position[0], g.position[1], g.window[0], g.window[1]], shot_t: t });
        this.last = Date.now();
    }

    // A loading ring turns: live frames keep changing while it shows, so the recording does too.
    async maybeAnimate() {
        if (Date.now() - this.last >= 300) await this.capture();
    }
}

// ------------------------------------------------------------------ main

async function main() {
    const { values } = parseArgs({ options: {
        url: { type: 'string' }, scenario: { type: 'string' }, out: { type: 'string' },
        headless: { type: 'boolean' }, record: { type: 'boolean' }, 'chrome-ui': { type: 'string' },
        border: { type: 'string' }, edge: { type: 'string' },
    } });
    if (!values.url || !values.scenario || !values.out) throw new Error('usage: --url URL --scenario FILE --out DIR');
    const scenario = JSON.parse(fs.readFileSync(values.scenario, 'utf8'));
    const chromeUi = Number(values['chrome-ui'] || 87);
    // A headed window of this outer size shows its page in this many device pixels: invisible resize borders (left,
    // right, bottom), a frame line, the tab strip and toolbar above (measured by live_test.py on Windows 11).
    const border = Number(values.border || 7);
    const edge = Number(values.edge || 1);
    const viewportOf = ([w, h]) => [w - 2 * border - 2 * edge, h - border - chromeUi - edge];
    const headless = Boolean(values.headless);
    const catalogue = new Map((await (await fetch(new URL('/api/practices.json', values.url))).json())
        .practices.map(p => [p.key, p]));
    const stdin = readline.createInterface({ input: process.stdin });
    const commands = [];
    let waiter = null;
    stdin.on('line', line => { commands.push(line.trim()); if (waiter) waiter(); });
    stdin.on('close', () => { commands.push('quit'); if (waiter) waiter(); });
    const command = async (name, timeoutMs) => {
        const end = Date.now() + timeoutMs;
        while (Date.now() < end) {
            const index = commands.findIndex(c => c === name || c === 'quit');
            if (index >= 0) return commands.splice(index, 1)[0];
            await new Promise(resolve => { waiter = resolve; setTimeout(resolve, 200); });
            waiter = null;
        }
        return 'timeout';
    };

    const profile = fs.mkdtempSync(path.join(process.env.TEMP || process.env.TMP || values.out, 'bper-live-'));
    const viewport = viewportOf(scenario.geometry.window);
    let chrome;
    try {
        chrome = await launch({ headless, geometry: scenario.geometry, profile, viewport });
        const { page, browser, windowId } = chrome;
        if (!headless) {
            const [x, y] = scenario.geometry.position;
            const [w, h] = scenario.geometry.window;
            await browser.send('Browser.setWindowBounds', { windowId, bounds: { left: x, top: y, width: w, height: h, windowState: 'normal' } });
            if (scenario.geometry.maximized) await browser.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'maximized' } });
        }
        await page.send('Page.navigate', { url: pageUrl(values.url, scenario, firstMode(scenario)) });
        await sleep(800);
        if (headless) await fitViewport(page, browser, windowId, viewport);
        await page.send('Page.bringToFront');
        const operator = new Operator({ page, browser, windowId, scenario, catalogue, headless, viewportOf, url: values.url });
        operator.mode = firstMode(scenario);
        const m = await metrics(page);
        const { bounds } = await browser.send('Browser.getWindowBounds', { windowId });
        emit('ready', { pid: chrome.proc.pid, bounds, ...m });
        if (!headless && (await command('go', 120000)) !== 'go') throw new Error('no go from the harness');
        if (values.record) operator.recorder = new Recorder(page, operator, values.out);
        const loop = operator.probeLoop();
        const ok = await operator.run();
        await sleep(300);
        operator.probing = false;
        await loop;
        emit('done', { ok });
        await command('quit', headless ? 5000 : 60000);
    } finally {
        if (chrome) {
            try { await chrome.browser.send('Browser.close'); } catch { /* already closing */ }
            await sleep(800);
            try { chrome.proc.kill(); } catch { /* gone */ }
            chrome.page.close();
            chrome.browser.close();
        }
        for (let i = 0; i < 10; i++) {
            try { fs.rmSync(profile, { recursive: true, force: true }); break; } catch { await sleep(300); }
        }
        stdin.close();
    }
}

main().then(() => process.exit(0), error => {
    emit('error', { message: String(error.message || error), fatal: true });
    process.exit(1);
});
