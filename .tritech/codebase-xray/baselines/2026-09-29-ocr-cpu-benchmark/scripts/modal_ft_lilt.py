"""Throwaway spike: fine-tune LiLT-XLM-R (MIT) for word -> field role on the BPER screens, on Modal.

Train on the live captures (+ synthetic variants), predict on the 9 LUNARDI screens the
model never saw, then time CPU inference on the operator profiles.

    modal run modal_ft_lilt.py
"""

import json
import random
import re
import time
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
BASE = "nielsr/lilt-xlm-roberta-base"
app = modal.App("bper-lilt-spike")
vol = modal.Volume.from_name("bper-lilt-spike", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "transformers", "accelerate", "numpy", "huggingface_hub")
    .run_commands(f"python -c \"from huggingface_hub import snapshot_download; snapshot_download('{BASE}', local_dir='/base')\"")
)
cpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("transformers", "numpy", "huggingface_hub")
    .run_commands(f"python -c \"from huggingface_hub import snapshot_download; snapshot_download('{BASE}', local_dir='/base')\"")
)

ROLES = [
    "O", "ndg", "denominazione", "tipo", "stato", "fase", "creazione", "evidenze", "filiale_relazione",
    "n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op",
    "sogg_ndg", "sogg_denominazione", "sogg_ruolo",
    "tooltip_evidenze", "tooltip_fido", "tooltip_garanzia", "note_della_richiesta",
]
R2I = {r: i for i, r in enumerate(ROLES)}

SURNAMES = ["ROSSI", "BIANCHI", "FERRARI", "ESPOSITO", "RUSSO", "ROMANO", "COLOMBO", "RICCI", "MARINO", "GRECO",
            "BRUNO", "GALLO", "CONTI", "DE LUCA", "MANCINI", "COSTA", "GIORDANO", "RIZZO", "LOMBARDI", "MORETTI",
            "BARBIERI", "FONTANA", "SANTORO", "MARIANI", "RINALDI", "CARUSO", "FERRARA", "GALLI", "MARTINI", "LEONE"]
NAMES = ["MARIO", "GIUSEPPE", "LUCA", "ANDREA", "FRANCESCO", "PAOLA", "GIULIA", "SARA", "MARCO", "ANNA",
         "ELENA", "STEFANO", "LAURA", "ROBERTO", "CHIARA", "DAVIDE", "SILVIA", "MATTEO", "FEDERICA", "ALESSIO"]
CITIES = ["MILANO", "TORINO", "GENOVA", "BOLOGNA", "MODENA", "PARMA", "VERONA", "PADOVA", "BARI", "NAPOLI"]
NAME_ROLES = {"denominazione", "sogg_denominazione"}
CONFUSIONS = {"i": "l", "l": "i", "0": "O", "O": "0", "F": "E", "1": "l", "5": "S", "8": "B"}


# ============================================================ augmentation + encoding

def _swap_digits(text, rng):
    return re.sub(r"\d", lambda m: str(rng.randint(0, 9)), text)


def augment(ex, rng):
    words = []
    sx, sy = rng.uniform(0.6, 1.2), rng.uniform(0.6, 1.2)
    tx, ty = rng.uniform(-150, 150), rng.uniform(-150, 150)
    for w, lab in zip(ex["words"], ex["labels"]):
        if lab == "O" and rng.random() < 0.05:
            continue
        t = w["text"]
        if lab in NAME_ROLES and re.fullmatch(r"[A-Z][A-Z',.]*", t):
            t = rng.choice(SURNAMES + NAMES)
        elif lab == "filiale_relazione" and re.fullmatch(r"[A-Z]{3,}", t):
            t = rng.choice(CITIES)
        elif re.search(r"\d", t) and not re.fullmatch(r"[FG]\d", t):
            t = _swap_digits(t, rng)
        if rng.random() < 0.03 and t:
            i = rng.randrange(len(t))
            t = t[:i] + CONFUSIONS.get(t[i], t[i]) + t[i + 1:]
        words.append(dict(w, text=t, _label=lab))
    out = {"words": [], "labels": []}
    for w in words:
        box = [w["nx0"] * sx + tx, w["ny0"] * sy + ty, w["nx1"] * sx + tx, w["ny1"] * sy + ty]
        out["words"].append(dict(w, box=[int(min(1000, max(0, v))) for v in box]))
        out["labels"].append(w["_label"])
    return out


def normalize(ex):
    xs0 = min(w["x0"] for w in ex["words"]); ys0 = min(w["y0"] for w in ex["words"])
    xs1 = max(w["x1"] for w in ex["words"]); ys1 = max(w["y1"] for w in ex["words"])
    W, H = max(1.0, xs1 - xs0), max(1.0, ys1 - ys0)
    for w in ex["words"]:
        w["nx0"], w["nx1"] = 1000 * (w["x0"] - xs0) / W, 1000 * (w["x1"] - xs0) / W
        w["ny0"], w["ny1"] = 1000 * (w["y0"] - ys0) / H, 1000 * (w["y1"] - ys0) / H
        w["box"] = [int(min(1000, max(0, v))) for v in (w["nx0"], w["ny0"], w["nx1"], w["ny1"])]
    return ex


def chunks(ex, tok, max_len=500):
    """Whole-row chunks that fit the 512-token window; returns (encodings, word index per chunk)."""
    words = ex["words"]
    ntok = [max(1, len(tok(w["text"], add_special_tokens=False)["input_ids"])) for w in words]
    groups, cur, cur_len, last_row = [], [], 0, None
    for i, w in enumerate(words):
        row = w.get("row")
        if cur and cur_len + ntok[i] > max_len and row != last_row:
            groups.append(cur); cur, cur_len = [], 0
        if cur and cur_len + ntok[i] > max_len:  # a single row longer than the window
            groups.append(cur); cur, cur_len = [], 0
        cur.append(i); cur_len += ntok[i]; last_row = row
    if cur:
        groups.append(cur)
    encs = []
    for g in groups:
        enc = tok([words[i]["text"] for i in g], is_split_into_words=True, truncation=True, max_length=512)
        wid = enc.word_ids()
        bbox, labels, prev = [], [], None
        for j in wid:
            if j is None:
                bbox.append([0, 0, 0, 0]); labels.append(-100)
            else:
                bbox.append(words[g[j]]["box"])
                labels.append(R2I[ex["labels"][g[j]]] if (j != prev and "labels" in ex) else -100)
            prev = j
        encs.append({"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"], "bbox": bbox,
                     "labels": labels, "word_ids": wid, "group": g})
    return encs


def predict(model, tok, ex, torch):
    ex = normalize(json.loads(json.dumps(ex)))
    preds = ["O"] * len(ex["words"])
    probs = [0.0] * len(ex["words"])
    for c in chunks(dict(ex, labels=["O"] * len(ex["words"])), tok):
        with torch.inference_mode():
            out = model(input_ids=torch.tensor([c["input_ids"]]), attention_mask=torch.tensor([c["attention_mask"]]),
                        bbox=torch.tensor([c["bbox"]]))
        p = out.logits[0].softmax(-1)
        prev = None
        for t, j in enumerate(c["word_ids"]):
            if j is not None and j != prev:
                k = int(p[t].argmax())
                preds[c["group"][j]] = ROLES[k]
                probs[c["group"][j]] = round(float(p[t, k]), 3)
            prev = j
    return preds, probs


# ============================================================ Modal functions

@app.function(image=image, gpu="L4", timeout=3600, volumes={"/vol": vol})
def train(examples: list, epochs: int = 6, variants: int = 40, seed: int = 7) -> dict:
    import torch
    from transformers import AutoTokenizer, LiltForTokenClassification

    rng = random.Random(seed)
    torch.manual_seed(seed)
    tok = AutoTokenizer.from_pretrained("/base")
    model = LiltForTokenClassification.from_pretrained("/base", num_labels=len(ROLES)).cuda()

    train_ex = [normalize(e) for e in examples if e["split"] == "train"]
    data = []
    for e in train_ex:
        data += chunks(e, tok)
        for _ in range(variants):
            data += chunks(augment(e, rng), tok)
    t0 = time.time()
    opt = torch.optim.AdamW(model.parameters(), lr=4e-5, weight_decay=0.01)
    steps = epochs * ((len(data) + 7) // 8)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=4e-5, total_steps=steps, pct_start=0.1)
    log = []
    model.train()
    for ep in range(epochs):
        rng.shuffle(data)
        tot = 0.0
        for b in range(0, len(data), 8):
            batch = data[b:b + 8]
            L = max(len(x["input_ids"]) for x in batch)
            pad = lambda seq, v: seq + [v] * (L - len(seq))  # noqa: E731
            ids = torch.tensor([pad(x["input_ids"], tok.pad_token_id) for x in batch]).cuda()
            am = torch.tensor([pad(x["attention_mask"], 0) for x in batch]).cuda()
            bb = torch.tensor([pad(x["bbox"], [0, 0, 0, 0]) for x in batch]).cuda()
            lab = torch.tensor([pad(x["labels"], -100) for x in batch]).cuda()
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(input_ids=ids, attention_mask=am, bbox=bb, labels=lab).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            tot += float(loss)
        log.append(round(tot / ((len(data) + 7) // 8), 4))
    train_s = time.time() - t0

    model.eval().cpu().float()
    model.save_pretrained("/vol/model"); tok.save_pretrained("/vol/model"); vol.commit()
    out = {}
    for e in examples:
        preds, probs = predict(model, tok, e, torch)
        out[e["id"]] = {"split": e["split"], "pred": preds, "prob": probs}
    return {"sequences": len(data), "epochs": epochs, "loss": log, "train_seconds": round(train_s, 1), "predictions": out}


def _bench(examples, threads, quantize):
    import torch
    from transformers import AutoTokenizer, LiltForTokenClassification

    torch.set_num_threads(threads)
    tok = AutoTokenizer.from_pretrained("/vol/model")
    model = LiltForTokenClassification.from_pretrained("/vol/model").eval()
    if quantize:
        model = torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
    test = [e for e in examples if e["split"] == "test"]
    predict(model, tok, test[0], torch)  # warm-up
    times, preds = {}, {}
    for e in test:
        t0 = time.time()
        p, _ = predict(model, tok, e, torch)
        times[e["id"]] = round(time.time() - t0, 3)
        preds[e["id"]] = p
    return {"threads": threads, "int8": quantize, "seconds": times, "predictions": preds}


@app.function(image=cpu_image, cpu=(4.0, 4.0), memory=8192, timeout=1800, volumes={"/vol": vol})
def bench_pc4(examples: list, quantize: bool) -> dict:
    return {"profile": "pc4", **_bench(examples, 4, quantize)}


@app.function(image=cpu_image, cpu=(2.0, 2.0), memory=8192, timeout=1800, volumes={"/vol": vol})
def bench_vdi2(examples: list, quantize: bool) -> dict:
    return {"profile": "vdi2", **_bench(examples, 2, quantize)}


@app.local_entrypoint()
def main(epochs: int = 6, variants: int = 40):
    examples = json.load(open(HERE / "ft_out/examples.json", encoding="utf-8"))
    res = train.remote(examples, epochs, variants)
    (HERE / "ft_out/train_result.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    print(f"TRAIN sequences={res['sequences']} epochs={res['epochs']} loss={res['loss']} seconds={res['train_seconds']}", flush=True)
    benches = [bench_pc4.spawn(examples, False), bench_pc4.spawn(examples, True),
               bench_vdi2.spawn(examples, False), bench_vdi2.spawn(examples, True)]
    out = []
    for b in benches:
        r = b.get()
        out.append(r)
        s = list(r["seconds"].values())
        print(f"BENCH {r['profile']} int8={r['int8']} mean={sum(s)/len(s):.2f}s max={max(s):.2f}s", flush=True)
    (HERE / "ft_out/bench_result.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
