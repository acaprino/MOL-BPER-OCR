"""Derive modal_ft_lilt_v2.py from modal_ft_lilt.py: reframing augmentation, class weights, early stopping on a validation practice."""

import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
src, dst = HERE / "modal_ft_lilt.py", HERE / "modal_ft_lilt_v2.py"
s = src.read_text(encoding="utf-8")


def rep(a: str, b: str) -> None:
    global s
    assert s.count(a) == 1, (a[:80], s.count(a))
    s = s.replace(a, b)


rep('app = modal.App("bper-lilt-spike")', 'app = modal.App("bper-lilt-spike-v2")')

rep('''def augment(ex, rng):
    words = []
    sx, sy = rng.uniform(0.6, 1.2), rng.uniform(0.6, 1.2)
    tx, ty = rng.uniform(-150, 150), rng.uniform(-150, 150)
''', '''def _reframe(ex, rng):
    """Keep a random window around the labeled words and stretch it to the full 0-1000 frame.

    Live frames put the page in the middle of a wide window; the 848 px references have the page
    filling the frame. Cropping the periphery away teaches the model the second framing too.
    """
    lab_words = [w for w, l in zip(ex["words"], ex["labels"]) if l != "O"] or ex["words"]
    bx0 = min(w["nx0"] for w in lab_words)
    by0 = min(w["ny0"] for w in lab_words)
    bx1 = max(w["nx1"] for w in lab_words)
    by1 = max(w["ny1"] for w in lab_words)
    cx0, cy0 = max(0.0, bx0 - rng.uniform(0, 300)), max(0.0, by0 - rng.uniform(0, 300))
    cx1, cy1 = min(1000.0, bx1 + rng.uniform(0, 300)), min(1000.0, by1 + rng.uniform(0, 300))
    W, H = max(1.0, cx1 - cx0), max(1.0, cy1 - cy0)
    words, labels = [], []
    for w, l in zip(ex["words"], ex["labels"]):
        cx, cy = (w["nx0"] + w["nx1"]) / 2, (w["ny0"] + w["ny1"]) / 2
        if l == "O" and not (cx0 <= cx <= cx1 and cy0 <= cy <= cy1):
            continue
        labels.append(l)
        words.append(dict(w, nx0=1000 * (w["nx0"] - cx0) / W, nx1=1000 * (w["nx1"] - cx0) / W,
                          ny0=1000 * (w["ny0"] - cy0) / H, ny1=1000 * (w["ny1"] - cy0) / H))
    return {"words": words, "labels": labels}


def augment(ex, rng):
    if rng.random() < 0.5:
        ex = _reframe(ex, rng)
    words = []
    sx, sy = rng.uniform(0.75, 1.1), rng.uniform(0.75, 1.1)
    tx, ty = rng.uniform(-80, 80), rng.uniform(-80, 80)
''')

rep('''    for c in chunks(dict(ex, labels=["O"] * len(ex["words"])), tok):
        with torch.inference_mode():
            out = model(input_ids=torch.tensor([c["input_ids"]]), attention_mask=torch.tensor([c["attention_mask"]]),
                        bbox=torch.tensor([c["bbox"]]))
        p = out.logits[0].softmax(-1)''', '''    dev = next(model.parameters()).device
    for c in chunks(dict(ex, labels=["O"] * len(ex["words"])), tok):
        with torch.inference_mode():
            out = model(input_ids=torch.tensor([c["input_ids"]], device=dev),
                        attention_mask=torch.tensor([c["attention_mask"]], device=dev),
                        bbox=torch.tensor([c["bbox"]], device=dev))
        p = out.logits[0].float().softmax(-1).cpu()''')

rep('''@app.function(image=image, gpu="L4", timeout=3600, volumes={"/vol": vol})
def train(examples: list, epochs: int = 6, variants: int = 40, seed: int = 7) -> dict:''',
'''def _word_f1(model, tok, exs, torch):
    tp = fp = fn = 0
    for e in exs:
        preds, _ = predict(model, tok, e, torch)
        for g, p in zip(e["labels"], preds):
            if p != "O" and p == g:
                tp += 1
            else:
                fp += p != "O"
                fn += g != "O"
    return round(2 * tp / max(1, 2 * tp + fp + fn), 4)


@app.function(image=image, gpu="L4", timeout=5400, volumes={"/vol": vol})
def train(examples: list, epochs: int = 8, variants: int = 10, seed: int = 7) -> dict:''')

rep('''    train_ex = [normalize(e) for e in examples if e["split"] == "train"]''',
'''    train_ex = [normalize(e) for e in examples if e["split"] == "train"]
    val_ex = [e for e in examples if e["split"] == "val"]
    test_ex = [e for e in examples if e["split"] == "test"]
    freq = {r: 1 for r in ROLES}
    for e in train_ex:
        for lab_ in e["labels"]:
            freq[lab_] += 1
    med = sorted(freq[r] for r in ROLES if r != "O")[len(ROLES) // 2]
    weights = torch.tensor([1.0 if r == "O" else min(5.0, max(1.0, (med / freq[r]) ** 0.5) * 2.0)
                            for r in ROLES]).cuda()
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights, ignore_index=-100)''')

rep('''            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(input_ids=ids, attention_mask=am, bbox=bb, labels=lab).loss''',
'''            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(input_ids=ids, attention_mask=am, bbox=bb).logits
            loss = loss_fn(logits.float().view(-1, len(ROLES)), lab.view(-1))''')

rep('''    log = []
    model.train()''', '''    log, best, bad = [], None, 0
    model.train()''')

rep('''            tot += float(loss)
        log.append(round(tot / ((len(data) + 7) // 8), 4))
    train_s = time.time() - t0
''', '''            tot += float(loss.detach())
        model.eval()
        val_f1 = _word_f1(model, tok, val_ex, torch) if val_ex else None
        test_f1 = _word_f1(model, tok, test_ex, torch)  # reported only, never used to select
        model.train()
        log.append({"epoch": ep + 1, "loss": round(tot / ((len(data) + 7) // 8), 4), "val_f1": val_f1, "test_f1": test_f1})
        print(log[-1], flush=True)
        if val_f1 is not None and (best is None or val_f1 > best[0]):
            best = (val_f1, ep + 1, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()})
            bad = 0
        else:
            bad += 1
            if bad >= 2:
                break
    train_s = time.time() - t0
    if best is not None:
        model.load_state_dict(best[2])
''')

rep('''    model.save_pretrained("/vol/model"); tok.save_pretrained("/vol/model"); vol.commit()''',
    '''    model.save_pretrained("/vol/model_v2"); tok.save_pretrained("/vol/model_v2"); vol.commit()''')
rep('''    return {"sequences": len(data), "epochs": epochs, "loss": log, "train_seconds": round(train_s, 1), "predictions": out}''',
    '''    return {"sequences": len(data), "epochs": epochs, "loss": log, "best_epoch": best[1] if best else None,
            "train_seconds": round(train_s, 1), "predictions": out}''')
rep('''    tok = AutoTokenizer.from_pretrained("/vol/model")
    model = LiltForTokenClassification.from_pretrained("/vol/model").eval()''',
    '''    tok = AutoTokenizer.from_pretrained("/vol/model_v2")
    model = LiltForTokenClassification.from_pretrained("/vol/model_v2").eval()''')
rep('''def main(epochs: int = 6, variants: int = 40):''', '''def main(epochs: int = 8, variants: int = 10):''')
rep('''    (HERE / "ft_out/train_result.json").write_text''', '''    (HERE / "ft_out/train_result_v2.json").write_text''')
rep('''    print(f"TRAIN sequences={res['sequences']} epochs={res['epochs']} loss={res['loss']} seconds={res['train_seconds']}", flush=True)''',
    '''    print(f"TRAIN sequences={res['sequences']} best_epoch={res['best_epoch']} log={res['loss']} seconds={res['train_seconds']}", flush=True)''')
rep('''    benches = [bench_pc4.spawn(examples, False), bench_pc4.spawn(examples, True),
               bench_vdi2.spawn(examples, False), bench_vdi2.spawn(examples, True)]''',
    '''    benches = [bench_pc4.spawn(examples, False), bench_vdi2.spawn(examples, False)]''')
rep('''    (HERE / "ft_out/bench_result.json").write_text''', '''    (HERE / "ft_out/bench_result_v2.json").write_text''')

ast.parse(s)
dst.write_text(s, encoding="utf-8")
print("wrote", dst.name)
