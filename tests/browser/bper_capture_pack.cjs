const { after, before, test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const repo = path.resolve(__dirname, '../..');
const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'bper-capture-test-'));
const html = path.join(scratch, 'simulatore.html');

function capture(...args) {
    return spawnSync(process.execPath, [
        'bper-emulator/capture_bper_dataset.cjs', '--html', html, ...args,
    ], { cwd: repo, encoding: 'utf8', timeout: 90_000 });
}

before(() => {
    const result = spawnSync(process.env.PYTHON || 'python', [
        'bper-emulator/serve_bper_simulator.py', '--db', path.join(scratch, 'pratiche.sqlite3'), '--export', html,
    ], { cwd: repo, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
});

after(() => {
    if (path.dirname(scratch) === path.resolve(os.tmpdir()) && path.basename(scratch).startsWith('bper-capture-test-')) {
        fs.rmSync(scratch, { recursive: true });
    }
});

function catalogue() {
    const text = fs.readFileSync(html, 'utf8');
    const start = text.indexOf('window.BperOffline = ') + 'window.BperOffline = '.length;
    return JSON.parse(text.slice(start, text.indexOf(';</script>', start)));
}

// RFC 4180 rows: the note values span several lines inside quotes.
function csvRows(text) {
    const rows = [[]];
    let field = '';
    let quoted = false;
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (quoted) {
            if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
            else if (c === '"') quoted = false;
            else field += c;
        } else if (c === '"') quoted = true;
        else if (c === ',') { rows.at(-1).push(field); field = ''; }
        else if (c === '\n') { rows.at(-1).push(field.replace(/\r$/, '')); field = ''; rows.push([]); }
        else field += c;
    }
    if (field || rows.at(-1).length) rows.at(-1).push(field);
    else rows.pop();
    return rows;
}

test('capture exports every screen and scheda state as a native PNG named by its CSV id, with a manifest', () => {
    const practice = catalogue().practices.find(p => p.key === 'demo');
    const out = path.join(scratch, 'selected');
    const result = capture('--out', out, '--practice', 'demo');
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(fs.readdirSync(out), ['demo']);
    const directory = path.join(out, 'demo');

    const screens = practice.availableSteps.map(step => 'screen ' + step);
    const schede = practice.schedaStates.map(state => state.name);
    assert.deepEqual(schede, ['scheda-privati-01', 'scheda-privati-02']);
    const stems = [...screens, ...schede];
    assert.deepEqual(fs.readdirSync(directory).sort(),
        [...stems.map(stem => stem + '.png'), 'dati.csv', 'manifest.json', 'practice-truth.csv'].sort());

    const sizes = new Map([...screens.map(s => [s, [842, 617]]), ...schede.map(s => [s, [1920, 945]])]);
    const images = stems.map(stem => fs.readFileSync(path.join(directory, stem + '.png')));
    stems.forEach((stem, i) => {
        assert.deepEqual([images[i].readUInt32BE(16), images[i].readUInt32BE(20)], sizes.get(stem), stem);
    });
    // Every state is its own picture: a capture that shot one state twice would repeat bytes.
    assert.equal(new Set(images.map(image => image.toString('base64'))).size, images.length);

    const text = fs.readFileSync(path.join(directory, 'dati.csv'), 'utf8');
    assert.ok(text.startsWith('\uFEFF'));
    const [header, ...rows] = csvRows(text.slice(1));
    assert.deepEqual(header, ['Fotogramma', 'Denominazione da attribuire', 'Valore rilevato']);
    assert.ok(rows.every(row => row.length === 3), 'every row has three fields');
    assert.deepEqual([...new Set(rows.map(row => row[0]))].sort(), [...stems].sort());
    assert.ok(rows.some(row => row[0] === 'screen 1' && row[2] === 'ALBA MARTINA'));

    const manifest = JSON.parse(fs.readFileSync(path.join(directory, 'manifest.json'), 'utf8'));
    assert.deepEqual(Object.keys(manifest), ['practice', 'role', 'generator']);
    assert.deepEqual(manifest, { practice: 'demo', role: 'sintetica', generator: 'bper-emulator' });
});

test('capture preserves an existing destination', () => {
    const out = fs.mkdtempSync(path.join(scratch, 'existing-'));
    fs.writeFileSync(path.join(out, 'dati.csv'), 'preservare');
    const result = capture('--out', out, '--practice', 'demo');
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /esiste/i);
    assert.deepEqual(fs.readdirSync(out), ['dati.csv']);
    assert.equal(fs.readFileSync(path.join(out, 'dati.csv'), 'utf8'), 'preservare');
});
