"""Predictions of the saved LiLT model_v2 (Modal volume bper-lilt-spike) for the examples in ft_out/examples.json.

No training: rebuilds ft_out/train_result_v2.json after the session scratchpad was lost. normalize /
chunks / predict are the exact functions model_v2 was trained and evaluated with.

    modal run modal_predict_v2.py
"""

import json
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
app = modal.App("bper-lilt-predict-v2")
vol = modal.Volume.from_name("bper-lilt-spike")
cpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("transformers", "numpy", "huggingface_hub")
)

ROLES = [
    "O", "ndg", "denominazione", "tipo", "stato", "fase", "creazione", "evidenze", "filiale_relazione",
    "n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op",
    "sogg_ndg", "sogg_denominazione", "sogg_ruolo",
    "tooltip_evidenze", "tooltip_fido", "tooltip_garanzia", "note_della_richiesta",
]
R2I = {r: i for i, r in enumerate(ROLES)}

# Training log of model_v2 (modal_ft_lilt_v2.py, 2026-09-29), kept for the record; epoch 3 selected on val_f1.
TRAIN_LOG = [
    {"epoch": 1, "loss": 0.7294, "val_f1": 0.8869, "test_f1": 0.6842},
    {"epoch": 2, "loss": 0.1061, "val_f1": 0.8472, "test_f1": 0.7267},
    {"epoch": 3, "loss": 0.0404, "val_f1": 0.9338, "test_f1": 0.7645},
    {"epoch": 4, "loss": 0.0242, "val_f1": 0.9121, "test_f1": 0.743},
    {"epoch": 5, "loss": 0.0096, "val_f1": 0.9138, "test_f1": 0.7781},
]


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
        if cur and cur_len + ntok[i] > max_len:
            groups.append(cur); cur, cur_len = [], 0
        cur.append(i); cur_len += ntok[i]; last_row = row
    if cur:
        groups.append(cur)
    encs = []
    for g in groups:
        enc = tok([words[i]["text"] for i in g], is_split_into_words=True, truncation=True, max_length=512)
        wid = enc.word_ids()
        bbox = [[0, 0, 0, 0] if j is None else words[g[j]]["box"] for j in wid]
        encs.append({"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"], "bbox": bbox,
                     "word_ids": wid, "group": g})
    return encs


def predict(model, tok, ex, torch):
    ex = normalize(json.loads(json.dumps(ex)))
    preds = ["O"] * len(ex["words"])
    probs = [0.0] * len(ex["words"])
    dev = next(model.parameters()).device
    for c in chunks(ex, tok):
        with torch.inference_mode():
            out = model(input_ids=torch.tensor([c["input_ids"]], device=dev),
                        attention_mask=torch.tensor([c["attention_mask"]], device=dev),
                        bbox=torch.tensor([c["bbox"]], device=dev))
        p = out.logits[0].float().softmax(-1).cpu()
        prev = None
        for t, j in enumerate(c["word_ids"]):
            if j is not None and j != prev:
                k = int(p[t].argmax())
                preds[c["group"][j]] = ROLES[k]
                probs[c["group"][j]] = round(float(p[t, k]), 3)
            prev = j
    return preds, probs


@app.function(image=cpu_image, cpu=(4.0, 4.0), memory=8192, timeout=1800, volumes={"/vol": vol})
def predict_all(examples: list) -> dict:
    import torch
    from transformers import AutoTokenizer, LiltForTokenClassification

    torch.set_num_threads(4)
    tok = AutoTokenizer.from_pretrained("/vol/model_v2")
    model = LiltForTokenClassification.from_pretrained("/vol/model_v2").eval()
    out = {}
    for e in examples:
        preds, probs = predict(model, tok, e, torch)
        out[e["id"]] = {"split": e["split"], "pred": preds, "prob": probs}
    return out


@app.local_entrypoint()
def main():
    examples = json.load(open(HERE / "ft_out/examples.json", encoding="utf-8"))
    res = {"loss": TRAIN_LOG, "best_epoch": 3, "predictions": predict_all.remote(examples)}
    (HERE / "ft_out/train_result_v2.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    print("PREDICTIONS", len(res["predictions"]), flush=True)
