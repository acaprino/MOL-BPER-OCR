// The truth audit on a small fixed set of synthetic practices, the reference practice and a pensioner, at capture
// scale in Chrome: clean on the served truth, and a truth row it removes or adds on purpose is caught.
// Playwright comes from PLAYWRIGHT_MODULE, as for the other browser tests.
const { after, before, test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const repo = path.resolve(__dirname, '../..');
const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'bper-audit-test-'));
const html = path.join(scratch, 'simulatore.html');
// The demo, a two-credit dossier, a dossier without the B evidence, and the first pensioner (chosen from the data:
// no test names a pensioner, test_bper_synthetic_db.py).
let practices;

function audit(page, ...args) {
    return spawnSync(process.execPath, ['bper-emulator/audit_truth.cjs', '--html', page, ...args],
        { cwd: repo, encoding: 'utf8', timeout: 300_000 });
}

// The exported page with the per-screen truth of one practice edited by `edit(csv)`.
function withTruth(key, edit) {
    const text = fs.readFileSync(html, 'utf8');
    const start = text.indexOf('window.BperOffline = ') + 'window.BperOffline = '.length;
    const end = text.indexOf(';</script>', start);
    const data = JSON.parse(text.slice(start, end));
    data.truth[key] = edit(data.truth[key]);
    const target = path.join(scratch, 'modificato.html');
    fs.writeFileSync(target, text.slice(0, start) + JSON.stringify(data).replace(/</g, '\\u003c') + text.slice(end));
    return target;
}

before(() => {
    const result = spawnSync(process.env.PYTHON || 'python', [
        'bper-emulator/serve_bper_simulator.py', '--db', path.join(scratch, 'pratiche.sqlite3'),
        '--include-reference', '--profiles', path.join(repo, 'tests/fixtures/bper_profiles_list_names.json'),
        '--export', html,
    ], { cwd: repo, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const text = fs.readFileSync(html, 'utf8');
    const start = text.indexOf('window.BperOffline = ') + 'window.BperOffline = '.length;
    const pensioner = JSON.parse(text.slice(start, text.indexOf(';</script>', start))).practices
        .find(p => p.scheda?.fields.professione_principale === 'PENSIONATO');
    // With the two invented names just under and over the width of the list's Denom. cell.
    practices = ['demo', 'sim-006', 'sim-007', pensioner.key, 'fittizia-sotto', 'fittizia-sopra'].join(',');
});

after(() => {
    if (path.dirname(scratch) === path.resolve(os.tmpdir()) && path.basename(scratch).startsWith('bper-audit-test-')) {
        fs.rmSync(scratch, { recursive: true });
    }
});

test('the served truth of every state matches what the page shows', () => {
    const result = audit(html, '--practice', practices, '--reference');
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /violazioni 0/);
});

test('a field shown on the page but missing from the truth is caught', () => {
    const page = withTruth('demo', csv => csv.replace(/^screen 2,Creazione,.*\r?\n/m, ''));
    const result = audit(page, '--practice', 'demo');
    assert.equal(result.status, 2);
    assert.match(result.stdout, /\(i\) shown, not in truth: creazione @ screen 2/);
});

test('a truth row for a field the page does not show is caught', () => {
    // Stato is scrolled out of view at the middle scroll of the list.
    const page = withTruth('demo', csv => csv.replace(/^(screen 2,Creazione,.*\r?\n)/m, '$1screen 2,Stato,LAV\r\n'));
    const result = audit(page, '--practice', 'demo');
    assert.equal(result.status, 2);
    assert.match(result.stdout, /\(ii\) (invisible|clipped): stato @ screen 2/);
});

test('a list name asserted whole although the cell cuts it is caught', () => {
    const page = withTruth('fittizia-sopra', csv => csv.replace(/^(screen 1,NDG,.*\r?\n)/m, '$1screen 1,DENOMINAZIONE,BELLAVISTA BENEDETTA\r\n'));
    const result = audit(page, '--practice', 'fittizia-sopra');
    assert.equal(result.status, 2);
    assert.match(result.stdout, /\(ii\) clipped: denominazione @ screen 1/);
});

test('a test practice is refused, as the capture refuses it', () => {
    const page = withTruth('demo', csv => csv);
    // The first practice of the page is the demo: its role becomes test.
    fs.writeFileSync(page, fs.readFileSync(page, 'utf8').replace(/"role":"sintetica"/, '"role":"test"'));
    const result = audit(page, '--practice', 'demo');
    assert.equal(result.status, 1);
    assert.match(result.stderr, /ADR 0027/);
});
