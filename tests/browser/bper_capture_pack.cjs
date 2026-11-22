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

test('capture exports a synthetic practice as native PNGs with matching CSV screen ids', () => {
    const out = path.join(scratch, 'selected');
    const result = capture('--out', out, '--practice', 'demo');
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(fs.readdirSync(out), ['demo']);
    const directory = path.join(out, 'demo');
    const files = fs.readdirSync(directory);
    const csv = fs.readFileSync(path.join(directory, 'dati.csv'), 'utf8');
    assert.ok(csv.startsWith('\uFEFFFotogramma'));
    assert.match(csv, /ALBA MARTINA/);
    const images = files.filter(file => file.endsWith('.png')).sort();
    assert.ok(images.includes('screen 4.png') && images.includes('screen 9.png'));
    const ids = [...csv.matchAll(/^"?screen ([1-9])"?[,;]/gm)].map(match => 'screen ' + match[1] + '.png');
    assert.deepEqual([...new Set(ids)].sort(), images);
    for (const file of images) {
        const image = fs.readFileSync(path.join(directory, file));
        assert.equal(image.readUInt32BE(16), 842);
        assert.equal(image.readUInt32BE(20), 617);
    }
    assert.notDeepEqual(fs.readFileSync(path.join(directory, 'screen 4.png')),
        fs.readFileSync(path.join(directory, 'screen 9.png')));
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
