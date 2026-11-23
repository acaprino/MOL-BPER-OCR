// Render the same standalone site as an operator and publish one CLI dataset per dossier.
// Test practices stay closed until a frozen candidate (ADR 0027): a page holds them only when exported with
// --include-archive --include-test, and capturing one needs --include-test here too.
const fs = require('node:fs/promises');
const { lstatSync } = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { parseArgs } = require('node:util');

const usage = 'node bper-emulator/capture_bper_dataset.cjs --html Simulatore-BPER.html --out cartella-nuova [--practice demo,sim-002 | --all] [--include-test]';
const SITE_VIEWPORT = { width: 842, height: 617 };

function selectedPractices(catalog, requested, all, includeTest) {
    if (!catalog.length) throw new Error("L’HTML non contiene un catalogo sintetico. Rigeneralo con --export.");
    const byKey = new Map(catalog.map(practice => [practice.key, practice]));
    const defaultSelection = all ? catalog : catalog.slice(0, 3);
    const keys = requested.length ? [...new Set(requested)] : defaultSelection.map(p => p.key);
    return keys.map(key => {
        const practice = byKey.get(key);
        if (!practice || key === 'reference') throw new Error('Pratica sintetica sconosciuta: ' + key);
        if (!/^[a-z0-9][a-z0-9_-]*$/i.test(key) || /^(con|prn|aux|nul|com[0-9]|lpt[0-9])$/i.test(key)) {
            throw new Error('Chiave non utilizzabile come nome cartella: ' + key);
        }
        if (!Array.isArray(practice.steps) || !practice.steps.length || !practice.csv || !practice.record ||
            !practice.steps.every(n => Number.isInteger(n) && n >= 1 && n <= 9)) {
            throw new Error('Schermate o valori attesi mancanti per ' + key);
        }
        // The manifest's role keeps test material from being taken for training data.
        if (typeof practice.role !== 'string' || !practice.role.trim()) throw new Error('Ruolo mancante per ' + key);
        // Same convention as include_test in src/training: the blind test stays unseen until the final measure.
        if (practice.role === 'test' && !includeTest) {
            throw new Error('La pratica ' + key + ' ha ruolo test: le pratiche di test restano sigillate fino alla ' +
                'misura finale (ADR 0027) e non si catturano. Aggiungi --include-test solo per quella misura.');
        }
        if (!Array.isArray(practice.schedaStates) || (practice.schedaStates.length && !(practice.schedaId && practice.schedaNdg)) ||
            !practice.schedaStates.every(s => /^scheda-privati-\d{2}$/.test(s.name) &&
                Number.isInteger(s.scroll) && Number.isInteger(s.noteScroll))) {
            throw new Error('Stati della Scheda Privati non validi per ' + key);
        }
        return practice;
    });
}

async function settle(page) {
    await page.evaluate(async () => {
        await document.fonts.ready;
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
}

// Scheda Privati is its own page, opened by its route on the same file and measured on a maximised
// 1920 px browser (1903 px of page plus its scrollbar). Each state differs in its query, so every state
// is a full load that renders and scrolls from scratch.
async function captureScheda(page, base, practice, directory) {
    await page.setViewportSize({ width: 1920, height: 945 });
    try {
        for (const state of practice.schedaStates) {
            const url = new URL(base.href);
            url.searchParams.set('practice', practice.key);
            url.searchParams.set('scroll', String(state.scroll));
            url.searchParams.set('noteScroll', String(state.noteScroll));
            // The page's customer: in a joint practice one holder, not the practice's own NDG.
            url.hash = '/schede/' + encodeURIComponent(practice.schedaNdg) + '/' + encodeURIComponent(practice.schedaId);
            await page.goto(url.href);
            await page.waitForFunction(ndg => document.body?.dataset.ready === 'true' &&
                document.querySelector('[data-bind="ndg"]')?.textContent === ndg, practice.schedaNdg);
            await settle(page);
            await page.screenshot({ path: path.join(directory, state.name + '.png') });
        }
    } finally {
        await page.setViewportSize(SITE_VIEWPORT);
    }
}

async function capturePractice(page, url, practice, staging) {
    const directory = path.join(staging, practice.key);
    await fs.mkdir(directory);
    url.searchParams.set('practice', practice.key);
    for (const step of practice.steps) {
        url.hash = String(step);
        await page.goto(url.href);
        // A fragment can change before the corresponding panels have been shown.
        await page.waitForFunction(({ key, step }) =>
            document.querySelector('#frame[data-ready]') &&
            document.querySelector('#practice')?.value === key &&
            document.querySelector('#screen')?.value === String(step) &&
            document.getElementById('original')?.hidden,
        { key: practice.key, step });
        await settle(page);
        await page.screenshot({ path: path.join(directory, 'screen ' + step + '.png') });
    }
    await captureScheda(page, url, practice, directory);
    await fs.writeFile(path.join(directory, 'dati.csv'), '\uFEFF' + practice.csv.replace(/^\uFEFF/, ''), 'utf8');
    // One row per field of the practice, for the live edge-agent run that consolidates one row per practice.
    await fs.writeFile(path.join(directory, 'practice-truth.csv'), '\uFEFF' + practice.record, 'utf8');
    const manifest = { practice: practice.key, role: practice.role, generator: 'bper-emulator' };
    await fs.writeFile(path.join(directory, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n', 'utf8');
}

async function main() {
    const { values } = parseArgs({ options: {
        html: { type: 'string' }, out: { type: 'string' },
        practice: { type: 'string', multiple: true }, all: { type: 'boolean' }, 'include-test': { type: 'boolean' },
        help: { type: 'boolean', short: 'h' },
    } });
    if (values.help) {
        console.log(usage);
        return;
    }
    if (!values.html || !values.out || (values.all && values.practice)) throw new Error(usage);
    const requested = (values.practice || []).flatMap(value => value.split(',').map(key => key.trim()));
    const output = path.resolve(values.out);
    if (lstatSync(output, { throwIfNoEntry: false })) throw new Error('La destinazione esiste già: ' + output);
    await fs.access(values.html);
    const url = pathToFileURL(path.resolve(values.html));
    url.searchParams.set('capture', '1');
    const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
    const browser = await chromium.launch({ channel: 'chrome' });
    let staging;
    const parent = path.dirname(output);
    try {
        const page = await browser.newPage({ viewport: SITE_VIEWPORT, deviceScaleFactor: 1, offline: true });
        page.setDefaultTimeout(8000);
        await page.goto(url.href);
        const catalog = await page.evaluate(() => (window.BperOffline?.practices || []).map(profile => ({
            key: profile.key, steps: profile.availableSteps, csv: window.BperOffline.truth?.[profile.key],
            record: window.BperOffline.practiceTruth?.[profile.key],
            role: profile.role, schedaNdg: profile.scheda?.ndg, schedaId: profile.scheda?.schedaId,
            schedaStates: profile.schedaStates,
        })));
        const selected = selectedPractices(catalog, requested, values.all, values['include-test']);
        await fs.mkdir(parent, { recursive: true });
        staging = await fs.mkdtemp(path.join(parent, '.bper-capture-'));
        for (const practice of selected) await capturePractice(page, url, practice, staging);
        // Publish only complete dossiers. A concurrent successful run has a nonempty destination.
        await fs.rename(staging, output);
        staging = undefined;
        const count = selected.reduce((total, profile) => total + profile.steps.length + profile.schedaStates.length, 0);
        console.log(`Salvate ${count} schermate di ${selected.length} pratiche in ${output}`);
    } finally {
        try {
            await browser.close();
        } finally {
            if (staging && path.dirname(path.resolve(staging)) === parent && path.basename(staging).startsWith('.bper-capture-')) {
                await fs.rm(staging, { recursive: true });
            }
        }
    }
}

main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
});
