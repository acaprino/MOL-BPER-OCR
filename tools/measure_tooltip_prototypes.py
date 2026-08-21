"""Prototipi interamente nella popolazione live: reggono tutte e nove le classi?

Storia della misura, perche' i numeri qui sotto abbiano un riferimento:

1. Aggiungere CROP da registrazioni Teams alle classi pagina fece crollare i
   riferimenti da 9/9 a 1/9: un prototipo mediato su due popolazioni non
   somiglia a nessuna delle due.
2. Il primo giro con gli scatti di Rita (ADR 0011) monto' le classi tooltip
   sopra i riferimenti (~848px) mescolandoli agli scatti (~1890px): stessa
   malattia, riferimenti a 5/9, errori tutti 6<->8 con margini 0.004-0.036.
3. Questo giro fa cio' che l'ADR 0011 aveva dichiarato mancante: un set di
   prototipi PER TUTTE E NOVE LE CLASSI costruito solo con gli scatti diretti
   di Rita (consegne 2026-08-19 tooltip e 2026-08-21 pagine base), senza
   mescolare popolazioni. I 9 riferimenti non fanno piu' da prototipo: il
   classificatore serve solo il percorso live (router local-first), dove
   nessun frame e' un riferimento a 848px.

Split: per classe, meta' scatti diventano prototipi e meta' restano fuori come
test. La classe 7 ha un solo esemplare: va nel prototipo e la classe resta non
testabile, dichiarato invece che nascosto. Le quattro schermate 'Note a
Istruttoria' (BPER, fuori dalle 9 classi) fanno da negativi di processo: il
router le adotta in locale solo con margine >= 0.10 (local_margin_min), quindi
qui devono restare sotto soglia o scartate.

I 9 riferimenti sono riportati a titolo informativo, senza fare da criterio:
sono l'altra popolazione, e il percorso file che li serve non passa dal
classificatore.
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "edge-agent")
from PIL import Image

REPO = Path(".")
TPL = REPO / "edge-agent/assets/templates/bper"
TOOLTIPS = REPO / "tests/fixtures/frames/tooltips-rita"
BASE = REPO / "tests/fixtures/frames/no-tooltip-rita"

MARGIN_GATE = 0.10  # local_margin_min del router (edge-agent/config.py)

# (dir, file) per classe: meta' prototipo, meta' test
PROTO = {
    "screen 1": [(BASE, "rita-base-1a.png"), (BASE, "rita-base-1c.png")],
    "screen 2": [(BASE, "rita-base-2a.png"), (BASE, "rita-base-2c.png")],
    "screen 3": [(TOOLTIPS, "rita-tooltip-1a.png"), (TOOLTIPS, "rita-tooltip-1c.png")],
    "screen 4": [(BASE, "rita-base-4a.png"), (BASE, "rita-base-4c.png")],
    "screen 5": [(BASE, "rita-base-5a.png"), (BASE, "rita-base-5c.png")],
    "screen 6": [(TOOLTIPS, "rita-tooltip-2a.png"), (TOOLTIPS, "rita-tooltip-2c.png"),
                 (TOOLTIPS, "rita-tooltip-2e.png")],
    "screen 7": [(TOOLTIPS, "rita-tooltip-3b.png")],
    "screen 8": [(TOOLTIPS, "rita-tooltip-3a.png"), (TOOLTIPS, "rita-tooltip-3d.png"),
                 (TOOLTIPS, "rita-tooltip-4b.png")],
    # Chiuso E aperto: con il solo chiuso, l'aperto finiva su screen 5 con margine
    # 0.220 (adozione sbagliata). Entrambi nel prototipo, classe non testabile.
    "screen 9": [(BASE, "rita-base-9a-chiuso.png"), (BASE, "rita-base-9a-aperto.png")],
    # Scarto live per le pagine BPER fuori processo: la classe SCARTO-fuori-processo
    # esistente e' popolata da ritagli di registrazione (altra popolazione) e non
    # cattura questi scatti; una classe separata evita di mescolare le popolazioni.
    "SCARTO-fuori-processo-live": [(BASE, "rita-istruttoria-b-chiuso.png"),
                                   (BASE, "rita-istruttoria-c-aperto.png")],
}
TEST = {
    "screen 1": [(BASE, "rita-base-1b.png"), (BASE, "rita-base-1d.png"),
                 (BASE, "rita-base-1e.png")],   # 1e: zoom ridotto, tutte le colonne
    "screen 2": [(BASE, "rita-base-2b.png"), (BASE, "rita-base-2d.png")],
    "screen 3": [(TOOLTIPS, "rita-tooltip-1b.png"), (TOOLTIPS, "rita-tooltip-1d.png")],
    "screen 4": [(BASE, "rita-base-4b.png")],
    "screen 5": [(BASE, "rita-base-5b.png")],
    "screen 6": [(TOOLTIPS, "rita-tooltip-2b.png"), (TOOLTIPS, "rita-tooltip-2d.png")],
    "screen 7": [],
    "screen 8": [(TOOLTIPS, "rita-tooltip-3c.png"), (TOOLTIPS, "rita-tooltip-4a.png"),
                 (TOOLTIPS, "rita-tooltip-4c.png"), (TOOLTIPS, "rita-tooltip-4d.png")],
    "screen 9": [],  # chiuso e aperto entrambi nel prototipo: non testabile
}
FUORI_PROCESSO = [  # BPER, tab 'Note a Istruttoria': tenute fuori dallo scarto live
    "rita-istruttoria-b-aperto.png", "rita-istruttoria-c-chiuso.png",
]

work = Path(tempfile.mkdtemp()) / "bper"
work.mkdir(parents=True)
# Niente 'screen N.png' in root: i riferimenti non fanno da prototipo.
for d in TPL.glob("SCARTO-*"):
    shutil.copytree(d, work / d.name)
for cls, files in PROTO.items():
    (work / cls).mkdir()
    for src_dir, f in files:
        shutil.copy(src_dir / f, work / cls / f)

from page_classifier import (BPERPagePrototypeClassifier, DEFAULT_CROP_ROI,
                             DEFAULT_SIMILARITY_THRESHOLD)

clf = BPERPagePrototypeClassifier(templates_dir=work, crop_roi=DEFAULT_CROP_ROI,
                                  similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
                                  device="cpu")
info = clf.info()
print(f"prototipi: {info['num_prototypes']} classi, tutte da scatti diretti\n")

print("--- scatti tenuti fuori (mai visti dai prototipi): il criterio ---")
tot = good_n = 0
for cls, files in TEST.items():
    for src_dir, f in files:
        r = clf.classify_detailed(Image.open(src_dir / f))
        good = r.label == cls
        tot += 1
        good_n += good
        flag = "OK " if good else "!! "
        gate = "adottato" if (r.label and r.margin >= MARGIN_GATE) else "ripiego LLM"
        print(f"  {flag}{f:26} atteso {cls:9} -> {str(r.label):10} "
              f"margine {r.margin:5.3f} [{gate}]")
print(f"  {good_n}/{tot} corretti")
print("  (screen 7: un solo esemplare; screen 9: chiuso+aperto entrambi nel "
      "prototipo; classi non testabili)\n")

print(f"--- pagine BPER fuori processo: mai adottate con margine >= {MARGIN_GATE} ---")
ok_neg = 0
for f in FUORI_PROCESSO:
    r = clf.classify_detailed(Image.open(BASE / f))
    safe = r.rejected_by is not None or r.label is None or r.margin < MARGIN_GATE
    ok_neg += safe
    flag = "OK " if safe else "!! "
    print(f"  {flag}{f:28} -> {str(r.label):22} margine {r.margin:5.3f} "
          f"scartato_da={r.rejected_by}")
print(f"  {ok_neg}/{len(FUORI_PROCESSO)} sotto soglia o scartate\n")

print("--- i 9 riferimenti (informativo: altra popolazione, percorso file) ---")
ok = 0
for n in range(1, 10):
    r = clf.classify_detailed(Image.open(REPO / f"mnt/data/screen {n}.png"))
    good = r.label == f"screen {n}"
    ok += good
    flag = "OK " if good else ".. "
    print(f"  {flag}screen {n} -> {str(r.label):10} margine {r.margin:5.3f}")
print(f"  {ok}/9 (non e' un criterio: il percorso live non vede mai questa famiglia)\n")

print("--- i negativi sintetici devono restare scartati ---")
for nome, im in (("desktop", Image.new("RGB", (1920, 1080), (32, 34, 38))),
                 ("grigio", Image.new("RGB", (1920, 1080), (128, 128, 128)))):
    r = clf.classify_detailed(im)
    print(f"  {nome:9} label={r.label} scartato_da={r.rejected_by}")

print(f"\ndir di lavoro (per ispezione): {work}")
