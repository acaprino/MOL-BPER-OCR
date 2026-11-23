// Check, in the browser, that every capture state's truth rows match what the page shows.
//
//   node bper-emulator/audit_truth.cjs --html Simulatore-BPER.html [--practice demo,sim-002 | --all]
//        [--reference] [--include-test] [--json report.json]
//
// For each practice and capture state (842 x 617 for screens 1-9, 1920 x 945 for Scheda Privati, as the
// capture pack shoots them), each element marked with data-field (Scheda Privati: data-bind) is read and judged:
//   visible    every character inside the viewport and every clipping or scrolling ancestor, not cut by its own
//              overflow (scrollWidth/scrollHeight), not covered by another element, not hidden;
//   clipped    part of it is cut or covered; invisible: none of it shows.
// Then (i) each visible, non-empty field must be in the state's truth with the same text (whitespace
// normalised), and (ii) no truth row may assert a non-empty value that no visible element shows. Scalar fields
// of a table are read from its first row only. Only counts, practice keys and field keys are printed: never a
// value, since an exported page may hold real practices (--include-archive). Test practices are refused unless
// --include-test, as the capture refuses them (ADR 0027). Playwright comes from PLAYWRIGHT_MODULE, as in
// capture_bper_dataset.cjs.
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { parseArgs } = require('node:util');

const SITE = { width: 842, height: 617 };
const SCHEDA = { width: 1920, height: 945 };
const SCHEDA_BINDS = { ndg: 'ndg', name: 'denominazione' };

function parseCsv(text) {
    const rows = [];
    let row = [], cell = '', quoted = false;
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (quoted) {
            if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
            else if (c === '"') quoted = false;
            else cell += c;
        } else if (c === '"') quoted = true;
        else if (c === ',') { row.push(cell); cell = ''; }
        else if (c === '\n' || c === '\r') {
            if (c === '\r' && text[i + 1] === '\n') i++;
            row.push(cell); rows.push(row); row = []; cell = '';
        } else cell += c;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows;
}

// Truth rows by state, keyed by field: {"screen 1": {ndg: "..."}, "scheda-privati-01": {...}}.
function truthByState(csv, labels) {
    const keyOf = Object.fromEntries(Object.entries(labels).map(([key, label]) => [label, key]));
    const states = {};
    for (const [state, label, value] of parseCsv(csv.replace(/^﻿/, '')).slice(1)) {
        if (!state) continue;
        const key = keyOf[label.trim()];
        if (key) (states[state] ??= {})[key] = value;
    }
    return states;
}

// Runs in the page: every marked element as {field, row, status, text}.
function readFields(scheda) {
    const W = innerWidth, H = innerHeight;
    const boxOf = el => {
        const r = el.getBoundingClientRect();
        const scale = el.offsetWidth ? r.width / el.offsetWidth : 1;
        const left = r.left + el.clientLeft * scale, top = r.top + el.clientTop * scale;
        return { l: left, t: top, r: left + el.clientWidth * scale, b: top + el.clientHeight * scale };
    };
    // The viewport and the boxes of the clipping ancestors; with self, also the element's own box (for its text).
    const clips = (el, self) => {
        const boxes = [{ l: 0, t: 0, r: W, b: H }];
        for (let node = self ? el : el.parentElement; node && node !== document.documentElement; node = node.parentElement) {
            const style = getComputedStyle(node);
            if (style.overflowX !== 'visible' || style.overflowY !== 'visible') boxes.push(boxOf(node));
        }
        return boxes;
    };
    // How much of the rectangles lies inside every clip box, and whether another element covers them.
    // text: the rectangles are the element's characters, which its own box clips too; else its border box.
    function judge(el, rects, { occlusion = true, text = true } = {}) {
        rects = rects.filter(r => r.width > 0.5 && r.height > 0.5);
        if (!rects.length || !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return 'invisible';
        const boxes = clips(el, text);
        let inside = 0, outside = 0;
        for (const r of rects) {
            // A text line box overhangs its glyphs: a quarter of its height may cross a box's edge.
            const v = text ? r.height / 4 : 0.5;
            const full = boxes.every(b => r.left >= b.l - 0.5 && r.right <= b.r + 0.5 && r.top >= b.t - v && r.bottom <= b.b + v);
            const none = boxes.some(b => r.right <= b.l || r.left >= b.r || r.bottom <= b.t || r.top >= b.b);
            if (full) inside++; else if (none) outside++;
        }
        if (outside === rects.length) return 'invisible';
        let status = inside === rects.length ? 'visible' : 'clipped';
        if (occlusion) {
            let hits = 0, samples = 0;
            // A sliver narrower than a glyph is the collapsed space at a line's wrap: nothing to cover.
            for (const r of rects.filter(r => r.width >= 3)) {
                for (const fx of [0.15, 0.5, 0.85]) {
                    const x = r.left + r.width * fx, y = r.top + r.height / 2;
                    if (x < 0 || y < 0 || x >= W || y >= H) continue;
                    samples++;
                    const top = document.elementFromPoint(x, y);
                    if (top && (top === el || el.contains(top))) hits++;
                }
            }
            if (samples && !hits) return 'invisible';
            if (hits < samples) status = 'clipped';
        }
        return status;
    }
    // The element's own text nodes: a tooltip shown inside it (role=tooltip) is an element of its own.
    const ownText = el => {
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, { acceptNode: node =>
            node.parentElement.closest('[role="tooltip"]') && !el.matches('[role="tooltip"]') ? NodeFilter.FILTER_REJECT
                : NodeFilter.FILTER_ACCEPT });
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        return nodes;
    };
    const textOf = el => ownText(el).map(node => node.data).join('');
    const textRects = (el, start, end) => {
        const range = document.createRange();
        if (start === undefined) {
            return ownText(el).flatMap(node => { range.selectNodeContents(node); return [...range.getClientRects()]; });
        } else {
            // The text node(s) of the element hold the template's text: locate both offsets in them.
            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
            let offset = 0, node;
            while ((node = walker.nextNode())) {
                const length = node.data.length;
                if (start >= offset && start <= offset + length) range.setStart(node, start - offset);
                if (end >= offset && end <= offset + length) { range.setEnd(node, end - offset); break; }
                offset += length;
            }
        }
        return [...range.getClientRects()];
    };
    const ownOverflow = el => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1;
    const out = [];
    if (scheda) {
        for (const el of document.querySelectorAll('[data-bind]')) {
            const bind = el.dataset.bind;
            const field = bind.startsWith('fields.') ? bind.slice(7) : SCHEDA_BINDS_PAGE[bind];
            if (!field) continue;
            if (el.tagName === 'TEXTAREA') {
                // The note: only the lines whose whole line box is inside the box, as a reader sees them.
                const style = getComputedStyle(el);
                const lineHeight = parseFloat(style.lineHeight), padding = parseFloat(style.paddingTop);
                const lines = el.value.split('\n');
                const wraps = Math.abs(el.scrollHeight - Math.max(el.clientHeight, padding + lines.length * lineHeight)) > 1;
                const shown = lines.filter((_, i) => padding + i * lineHeight >= el.scrollTop - 0.5 &&
                    padding + (i + 1) * lineHeight <= el.scrollTop + el.clientHeight + 0.5);
                const status = judge(el, [el.getBoundingClientRect()], { occlusion: false, text: false });
                out.push({ field, row: 0, status: wraps ? 'clipped' : status, text: shown.join('\n') });
                continue;
            }
            const value = 'value' in el ? el.value : el.textContent;
            const rects = 'value' in el ? [el.getBoundingClientRect()] : textRects(el);
            let status = judge(el, rects, { text: !('value' in el) });
            if (status === 'visible' && 'value' in el && ownOverflow(el)) status = 'clipped';
            out.push({ field, row: 0, status, text: value });
        }
        return out;
    }
    for (const el of document.querySelectorAll('[data-field]')) {
        const fields = el.dataset.field.split(' ');
        const row = Number(el.dataset.row || 0);
        const tooltip = el.getAttribute('role') === 'tooltip';
        if (fields.length === 1) {
            let status = judge(el, textRects(el), { occlusion: !tooltip });
            const style = getComputedStyle(el);
            if (status === 'visible' && style.overflow !== 'visible' && ownOverflow(el) && !el.querySelector('[role="tooltip"]')) {
                status = 'clipped';
            }
            if (status === 'visible' && style.textOverflow === 'ellipsis') {
                // An ellipsis replaces the last characters as soon as the text is wider than the box, by any amount.
                const rects = textRects(el);
                const width = Math.max(...rects.map(r => r.right)) - Math.min(...rects.map(r => r.left));
                if (width > el.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) + 0.01) status = 'clipped';
            }
            out.push({ field: fields[0], row, status, text: textOf(el) });
            continue;
        }
        // Several fields in one text ("NDG: {ndg} - {denominazione}"): judge each one's characters.
        const pattern = el.dataset.template.replace(/[.*+?^$()|[\]\\]/g, '\\$&')
            .replace(/\{(\w+)\}/g, (_, name) => `(?<${name}>.*?)`);
        const match = new RegExp('^' + pattern + '$', 'sd').exec(el.textContent);
        for (const name of fields) {
            const [start, end] = match?.indices.groups[name] ?? [0, 0];
            out.push({ field: name, row, status: match ? judge(el, textRects(el, start, end)) : 'clipped',
                       text: match ? match.groups[name] : '' });
        }
    }
    // A description tooltip fills the field of the description it belongs to (data-tooltip-field).
    const popup = document.querySelector('.pd-tooltip');
    const anchor = popup && !popup.hidden && document.querySelector('[aria-describedby="pd-tip"][data-tooltip-field]');
    if (anchor) out.push({ field: anchor.dataset.tooltipField, row: 0, status: judge(popup, textRects(popup), { occlusion: false }),
                           text: popup.textContent });
    return out;
}

const normal = text => String(text ?? '').replace(/\s+/g, ' ').trim();

// Rules (i) and (ii) for one state: the violations as {rule, reason, field}.
function compare(elements, truth) {
    const violations = [];
    const scalar = elements.filter(e => e.row <= 1);
    for (const e of scalar) {
        if (e.status !== 'visible' || !normal(e.text)) continue;
        if (!(e.field in truth)) violations.push({ rule: 'i', reason: 'shown, not in truth', field: e.field });
        else if (normal(truth[e.field]) !== normal(e.text)) violations.push({ rule: 'i', reason: 'text differs', field: e.field });
    }
    for (const [field, value] of Object.entries(truth)) {
        if (!normal(value)) continue;
        const candidates = scalar.filter(e => e.field === field);
        if (candidates.some(e => e.status === 'visible' && normal(e.text) === normal(value))) continue;
        const reason = !candidates.length ? 'no element' : candidates.some(e => e.status === 'visible') ? 'text differs'
            : candidates.some(e => e.status === 'clipped') ? 'clipped' : 'invisible';
        violations.push({ rule: 'ii', reason, field });
    }
    return violations;
}

async function settle(page) {
    await page.evaluate(async () => {
        await document.fonts.ready;
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
}

// readFields runs in the page, which does not have this file's constants: they travel with its source.
const SCHEDA_BINDS_SOURCE = `const SCHEDA_BINDS_PAGE = ${JSON.stringify(SCHEDA_BINDS)};`;

async function auditPractice(page, base, practice, truth) {
    const results = [];
    await page.setViewportSize(SITE);
    for (const step of practice.steps) {
        const url = new URL(base.href);
        url.searchParams.set('capture', '1');
        url.searchParams.set('practice', practice.key);
        url.hash = String(step);
        await page.goto(url.href);
        await page.waitForFunction(({ key, step }) => document.querySelector('#frame[data-ready]') &&
            document.querySelector('#practice')?.value === key && document.querySelector('#screen')?.value === String(step),
        { key: practice.key, step });
        await settle(page);
        const elements = await page.evaluate(source => (0, eval)(source)(false), `(() => { ${SCHEDA_BINDS_SOURCE} return ${readFields.toString()}; })()`);
        results.push({ state: 'screen ' + step, violations: compare(elements, truth['screen ' + step] || {}) });
    }
    await page.setViewportSize(SCHEDA);
    for (const state of practice.schedaStates || []) {
        const url = new URL(base.href);
        url.searchParams.set('practice', practice.key);
        url.searchParams.set('scroll', String(state.scroll));
        url.searchParams.set('noteScroll', String(state.noteScroll));
        url.hash = '/schede/' + encodeURIComponent(practice.schedaNdg) + '/' + encodeURIComponent(practice.schedaId);
        await page.goto(url.href);
        await page.waitForFunction(ndg => document.body?.dataset.ready === 'true' &&
            document.querySelector('[data-bind="ndg"]')?.textContent === ndg, practice.schedaNdg);
        await settle(page);
        const elements = await page.evaluate(source => (0, eval)(source)(true), `(() => { ${SCHEDA_BINDS_SOURCE} return ${readFields.toString()}; })()`);
        results.push({ state: state.name, violations: compare(elements, truth[state.name] || {}) });
    }
    return results;
}

async function main() {
    const { values } = parseArgs({ options: {
        html: { type: 'string' }, practice: { type: 'string', multiple: true }, all: { type: 'boolean' },
        reference: { type: 'boolean' }, 'include-test': { type: 'boolean' }, json: { type: 'string' },
    } });
    if (!values.html) throw new Error('Uso: node bper-emulator/audit_truth.cjs --html PAGINA.html [--practice a,b | --all] [--reference]');
    const base = pathToFileURL(path.resolve(values.html));
    const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
    const browser = await chromium.launch({ channel: 'chrome' });
    try {
        const page = await browser.newPage({ viewport: SITE, deviceScaleFactor: 1, offline: true });
        page.setDefaultTimeout(15000);
        await page.goto(base.href + '?capture=1');
        const offline = await page.evaluate(() => {
            const o = window.BperOffline;
            return { labels: o.fieldLabels, reference: o.practice ? { truth: o.referenceTruth } : null,
                     practices: o.practices.map(p => ({ key: p.key, role: p.role, steps: p.availableSteps, truth: o.truth[p.key],
                        schedaNdg: p.scheda?.ndg, schedaId: p.scheda?.schedaId, schedaStates: p.schedaStates })) };
        });
        if (!offline.labels) throw new Error("L'HTML non ha le etichette dei campi: rigeneralo con --export.");
        const requested = (values.practice || []).flatMap(v => v.split(',').map(k => k.trim()));
        let chosen = values.all ? offline.practices : offline.practices.filter(p => requested.includes(p.key));
        const unknown = requested.filter(k => !offline.practices.some(p => p.key === k));
        if (unknown.length) throw new Error('Pratiche sconosciute: ' + unknown.join(', '));
        const sealed = chosen.filter(p => p.role === 'test');
        if (sealed.length && !values['include-test']) {
            throw new Error(sealed.length + ' pratiche con ruolo test: restano sigillate fino alla misura finale (ADR 0027). ' +
                'Escludile, oppure aggiungi --include-test solo per quella misura.');
        }
        if (values.reference) {
            if (!offline.reference?.truth) throw new Error("L'HTML non ha la pratica di riferimento: esportalo con --include-reference.");
            chosen = [...chosen, { key: 'reference', role: 'riferimento', steps: [1, 2, 3, 4, 5, 6, 7, 8, 9], truth: offline.reference.truth }];
        }
        const report = { practices: 0, states: 0, violations: {}, byPractice: {} };
        for (const practice of chosen) {
            const truth = truthByState(practice.truth, offline.labels);
            const results = await auditPractice(page, base, practice, truth);
            report.practices++;
            report.states += results.length;
            for (const { state, violations } of results) {
                for (const v of violations) {
                    const name = `(${v.rule}) ${v.reason}: ${v.field} @ ${state.replace(/scheda-privati-(0[2-9]|[1-9]\d)$/, 'scheda-privati-bottom')}`;
                    report.violations[name] = (report.violations[name] || 0) + 1;
                    (report.byPractice[practice.key] ??= []).push(`${state} ${v.rule} ${v.reason} ${v.field}`);
                }
            }
        }
        if (values.json) fs.writeFileSync(values.json, JSON.stringify(report, null, 2) + '\n');
        console.log(`Pratiche ${report.practices}, stati ${report.states}, violazioni ${Object.values(report.violations).reduce((a, b) => a + b, 0)}`);
        for (const [name, count] of Object.entries(report.violations).sort()) console.log(`${String(count).padStart(5)}  ${name}`);
        if (Object.keys(report.violations).length) process.exitCode = 2;
    } finally {
        await browser.close();
    }
}

if (require.main === module) {
    main().catch(error => {
        console.error(error.message);
        process.exitCode = 1;
    });
}
module.exports = { compare, parseCsv, truthByState };
