"""Word-aligned LiLT training and inference shared by local and remote runs."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import time
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from training.dataset import DATASET_VERSION

BASE_MODEL = "nielsr/lilt-xlm-roberta-base"
IGNORE_LABEL = "IGNORE"


KNOWN_SPLITS = ("train", "val", "test")


def dataset_fingerprint(examples: list[dict[str, Any]], roles: list[str]) -> str:
    payload = json.dumps({"examples": examples, "roles": roles}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_reviewed_dataset(examples: list[dict[str, Any]], roles: list[str], manifest: dict[str, Any]) -> None:
    """Fail closed on an incomplete, modified, or unreviewed corpus of a known version."""
    validate_splits(examples)
    if manifest.get("dataset_version") != DATASET_VERSION or manifest.get("leakage_audit", {}).get("status") != "passed":
        raise ValueError(f"A dataset built from the archive (version {DATASET_VERSION!r}) with a passed leakage audit is required")
    actual_counts = {"reviewed_rows": sum(len(example["values"]) for example in examples),
                     "screens": len(examples), "practices": len({example["practice"] for example in examples})}
    if any(manifest.get(key) != value for key, value in actual_counts.items()):
        raise ValueError(f"Dataset counts in the manifest must be {actual_counts}")
    if manifest.get("roles") != roles or len(roles) != len(set(roles)) or "O" not in roles or IGNORE_LABEL in roles:
        raise ValueError("Role order must exactly match the unique manifest vocabulary")
    if manifest.get("dataset_content_sha256") != dataset_fingerprint(examples, roles):
        raise ValueError("Dataset content fingerprint does not match its reviewed manifest hash")
    practice_splits = {split: {example["practice"] for example in examples if example["split"] == split}
                       for split in KNOWN_SPLITS}
    if "practice_splits" in manifest and any(set(manifest["practice_splits"].get(split, [])) != practices
                                             for split, practices in practice_splits.items() if practices):
        raise ValueError("Example practice splits differ from the manifest")
    for example in examples:
        if len(example["labels"]) != len(example["words"]):
            raise ValueError("Each reviewed OCR word needs one aligned label")
        if any(label not in roles and label != IGNORE_LABEL for label in example["labels"]):
            raise ValueError("A reviewed OCR word has an unknown role")
        normalize_boxes(example)


# ============================================================
# Image geometry and lossless word alignment
# ============================================================


def normalize_boxes(example: dict[str, Any]) -> list[list[int]]:
    """Map pixel boxes onto LiLT's 0..1000 grid using the entire image."""
    width, height = example["image_size"]
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    boxes = []
    for word in example["words"]:
        coords = [float(word[key]) for key in ("x0", "y0", "x1", "y1")]
        if not all(math.isfinite(value) for value in coords):
            raise ValueError("A word box contains a non-finite coordinate")
        if coords[0] > coords[2] or coords[1] > coords[3]:
            raise ValueError("A word box has inverted edges")
        boxes.append([
            max(0, min(1000, round(1000 * value / dimension)))
            for value, dimension in zip(coords, (width, height, width, height))
        ])
    return boxes


def _checked_word_ids(encoding: Any, word_count: int) -> list[int | None]:
    word_ids = encoding.word_ids()
    if len(word_ids) != len(encoding["input_ids"]):
        raise ValueError("Tokenizer word IDs do not align with token IDs")
    observed = [index for index in word_ids if index is not None]
    if set(observed) != set(range(word_count)) or observed != sorted(observed):
        raise ValueError("Tokenizer dropped, reordered, or misnumbered a word")
    return word_ids


def _word_groups(words: list[dict[str, Any]], counts: list[int], capacity: int) -> list[list[int]]:
    rows: list[list[int]] = []
    for index, word in enumerate(words):
        if rows and word.get("row", index) == words[rows[-1][-1]].get("row", rows[-1][-1]):
            rows[-1].append(index)
        else:
            rows.append([index])
    fidi_row = next((ri for ri, r in enumerate(rows) if any(words[i]["text"].strip() == "FIDI" for i in r)), None)
    garanzie_row = next((ri for ri, r in enumerate(rows) if any(words[i]["text"].strip() == "GARANZIE" for i in r)), len(rows))
    groups, current, length = [], [], 0
    for ri, row in enumerate(rows):
        row_length = sum(counts[index] for index in row)
        if fidi_row is not None and ri == fidi_row and current:
            fidi_block = sum(counts[i] for r2 in rows[fidi_row:max(fidi_row + 1, garanzie_row)] for i in r2)
            if length + fidi_block > capacity:
                groups.append(current)
                current, length = [], 0
        if current and length + row_length > capacity:
            groups.append(current)
            current, length = [], 0
        for index in row:
            if counts[index] > capacity:
                raise ValueError(f"A word at index {index} is longer than the token window")
            if current and length + counts[index] > capacity:
                groups.append(current)
                current, length = [], 0
            current.append(index)
            length += counts[index]
    if current:
        groups.append(current)
    return groups


def encode_chunks(example: dict[str, Any], tokenizer: Any, roles: list[str], max_length: int = 512) -> list[dict[str, Any]]:
    """Encode whole words once, keeping rows together whenever a row fits."""
    words = example["words"]
    labels = example.get("labels", ["O"] * len(words))
    if len(labels) != len(words):
        raise ValueError("Every input word must have one label")
    if len(roles) != len(set(roles)) or "O" not in roles or IGNORE_LABEL in roles:
        raise ValueError("Roles must be unique, contain O, and exclude IGNORE")
    if any(label not in roles and label != IGNORE_LABEL for label in labels):
        raise ValueError("An input word has an unknown role")
    if not words:
        return []
    boxes = normalize_boxes(example)
    capacity = max_length - tokenizer.num_special_tokens_to_add(pair=False)
    if capacity < 1:
        raise ValueError("The token window has no room for a word")
    bare = tokenizer([word["text"] for word in words], is_split_into_words=True,
                     add_special_tokens=False, truncation=False)
    counts = Counter(_checked_word_ids(bare, len(words)))
    groups = _word_groups(words, [counts[i] for i in range(len(words))], capacity)
    role_ids = {role: index for index, role in enumerate(roles)}
    chunks = []
    for group in groups:
        encoded = tokenizer([words[index]["text"] for index in group],
                            is_split_into_words=True, add_special_tokens=True, truncation=False)
        word_ids = _checked_word_ids(encoded, len(group))
        if len(encoded["input_ids"]) > max_length:
            raise ValueError("Tokenizer exceeded the token window; no labeled word was truncated")
        chunk_boxes, targets, seen = [], [], set()
        for index in word_ids:
            if index is None:
                chunk_boxes.append([0, 0, 0, 0])
                targets.append(-100)
                continue
            source = group[index]
            chunk_boxes.append(boxes[source])
            label = labels[source]
            targets.append(role_ids[label] if index not in seen and label != IGNORE_LABEL else -100)
            seen.add(index)
        chunks.append({"input_ids": encoded["input_ids"], "attention_mask": encoded["attention_mask"],
                       "bbox": chunk_boxes, "labels": targets, "word_ids": word_ids, "group": group})
    return chunks


def predict(model: Any, tokenizer: Any, example: dict[str, Any], roles: list[str], max_length: int = 512) -> tuple[list[str], list[float]]:
    """Return one role and confidence per input word, in the original order."""
    import torch

    device = next(model.parameters()).device
    predictions, probabilities = ["O"] * len(example["words"]), [0.0] * len(example["words"])
    model.eval()
    inference_example = {**example, "labels": ["O"] * len(example["words"])}
    for chunk in encode_chunks(inference_example, tokenizer, roles, max_length):
        tensors = {key: torch.tensor([chunk[key]], device=device)
                   for key in ("input_ids", "attention_mask", "bbox")}
        with torch.inference_mode():
            scores = model(**tensors).logits[0].float().softmax(-1).cpu()
        if scores.shape[-1] != len(roles):
            raise ValueError("Model classifier and supplied role vocabulary differ")
        seen = set()
        for token_index, local_word in enumerate(chunk["word_ids"]):
            if local_word is None or local_word in seen:
                continue
            seen.add(local_word)
            source = chunk["group"][local_word]
            role_index = int(scores[token_index].argmax())
            predictions[source] = roles[role_index]
            probabilities[source] = round(float(scores[token_index, role_index]), 6)
    return predictions, probabilities


# ============================================================
# Split isolation, augmentation, and evaluation
# ============================================================


def validate_splits(examples: list[dict[str, Any]]) -> None:
    practices: dict[str, str] = {}
    identifiers = set()
    for example in examples:
        split, practice, identifier = example["split"], example["practice"], example["id"]
        if split not in KNOWN_SPLITS:
            raise ValueError(f"Unknown split: {split}")
        if identifier in identifiers:
            raise ValueError(f"Duplicate example identifier: {identifier}")
        identifiers.add(identifier)
        if practice in practices and practices[practice] != split:
            raise ValueError("A practice appears in more than one split")
        practices[practice] = split
    if not {"train", "val"} <= {example["split"] for example in examples}:
        raise ValueError("Training requires nonempty train and val splits")


def _augment(example: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Apply modest geometry jitter and non-zero digit substitutions to training copies."""
    augmented = copy.deepcopy(example)
    width, height = example["image_size"]
    sx, sy = rng.uniform(0.995, 1.005), rng.uniform(0.995, 1.005)
    tx, ty = rng.uniform(-0.003, 0.003) * width, rng.uniform(-0.003, 0.003) * height
    for word, label in zip(augmented["words"], augmented["labels"]):
        for key, scale, offset, limit in (("x0", sx, tx, width), ("x1", sx, tx, width),
                                          ("y0", sy, ty, height), ("y1", sy, ty, height)):
            word[key] = max(0, min(limit, word[key] * scale + offset))
        if label != IGNORE_LABEL:
            word["text"] = "".join(
                str(rng.randint(1, 9)) if char in "123456789" else char
                for char in word["text"]
            )
    return augmented


def _reframe(example: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Frame a training copy differently, as a screenshot taken with another window, scroll or crop would be.

    LiLT reads each word's position relative to the whole image. The training screens are nearly all framed alike,
    while the screens of the later lots go from 1218 to 1924 wide and from 853 to 1299 tall, and lose the header when
    scrolled. The ranges come from those screens. Words that fall out of the new frame leave with their labels.
    """
    width, height = example["image_size"]
    left = rng.uniform(0.0, 0.18) * width if rng.random() < 0.3 else 0.0
    right = rng.uniform(0.0, 0.38) * width if rng.random() < 0.3 else 0.0
    top = rng.uniform(0.0, 0.45) * height if rng.random() < 0.6 else 0.0
    bottom = rng.uniform(0.0, 0.15) * height if rng.random() < 0.4 else 0.0
    taller = rng.uniform(0.0, 0.3) * height if rng.random() < 0.3 else 0.0
    new_width, new_height = width - left - right, height - top - bottom
    words, labels = [], []
    for word, label in zip(example["words"], example["labels"]):
        center_x, center_y = (word["x0"] + word["x1"]) / 2 - left, (word["y0"] + word["y1"]) / 2 - top
        if 0 <= center_x <= new_width and 0 <= center_y <= new_height:
            words.append({**word, "x0": max(0.0, word["x0"] - left), "x1": min(new_width, word["x1"] - left),
                          "y0": max(0.0, word["y0"] - top), "y1": min(new_height, word["y1"] - top)})
            labels.append(label)
    return {**example, "image_size": [new_width, new_height + taller], "words": words, "labels": labels}


CREDIT_FIELDS = {"n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op"}
NOTE_ROLES = {"note_della_richiesta", "note_scheda_privati"}


def score_predictions(examples: list[dict[str, Any]], predictions: dict[str, Any], roles: list[str]) -> dict[str, Any]:
    """Report whole-field accuracy, credit-table accuracy, non-note F1, and micro word F1."""
    from training.evaluation import evaluate_predictions, word_metrics

    metrics = word_metrics(examples, predictions)
    field_report = evaluate_predictions(examples, predictions)
    credit_records = [r for r in field_report["records"] if r["field"] in CREDIT_FIELDS]
    credit_correct = sum(r["status"] in {"correct", "correct_null"} for r in credit_records)
    credit_accuracy = (credit_correct / len(credit_records)) if credit_records else None
    non_note_tp = sum(c["tp"] for r, c in metrics["by_role"].items() if r not in NOTE_ROLES)
    non_note_fp = sum(c["fp"] for r, c in metrics["by_role"].items() if r not in NOTE_ROLES)
    non_note_fn = sum(c["fn"] for r, c in metrics["by_role"].items() if r not in NOTE_ROLES)
    non_note_denom = 2 * non_note_tp + non_note_fp + non_note_fn
    non_note_f1 = (2 * non_note_tp / non_note_denom) if non_note_denom else None
    total, correct = 0, 0
    for example in examples:
        predicted = predictions[example["id"]]["pred"]
        if len(predicted) != len(example["labels"]):
            raise ValueError("Predictions do not cover all input words")
        for gold, actual in zip(example["labels"], predicted):
            if gold == IGNORE_LABEL:
                continue
            total += 1
            correct += gold == actual
    absent = {"tp": 0, "fp": 0, "fn": 0, "support": 0, "precision": None, "recall": None, "f1": None}
    by_role = {role: metrics["by_role"].get(role, dict(absent)) for role in roles if role != "O"}
    return {
        "precision": metrics["micro"]["precision"],
        "recall": metrics["micro"]["recall"],
        "f1": metrics["micro"]["f1"],
        "non_note_f1": non_note_f1,
        "field_accuracy": field_report["overall"]["accuracy"],
        "credit_field_accuracy": credit_accuracy,
        "word_accuracy": round(correct / max(1, total), 6),
        "evaluated_words": total,
        "ignored_words": metrics["ignored_words"],
        "per_role": by_role,
    }


def _evaluate(model: Any, tokenizer: Any, examples: list[dict[str, Any]], roles: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    predictions = {}
    for example in examples:
        labels, probabilities = predict(model, tokenizer, example, roles)
        predictions[example["id"]] = {"split": example["split"], "practice": example["practice"],
                                       "pred": labels, "prob": probabilities}
    return score_predictions(examples, predictions, roles), predictions


def _write_json(path: Path, content: Any) -> None:
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# Fresh-pretrained training, validation selection, one final test
# ============================================================


def train_model(
    examples: list[dict[str, Any]], roles: list[str], output_dir: Path,
    dataset_manifest: dict[str, Any], *, base_path: str = BASE_MODEL,
    base_revision: str | None = None, epochs: int = 8, variants: int = 2,
    seed: int = 7, batch_size: int = 2, accumulation_steps: int = 4,
    learning_rate: float = 3e-5, device: str = "cuda", patience: int = 2,
    final_test: bool = False,
) -> dict[str, Any]:
    """Train a new model; test labels never participate in checkpoint selection.

    The test practices stay out unless ``final_test`` asks for it, which only a frozen candidate does: the dataset
    must then have been built with ``include_test``.
    """
    import torch
    from transformers import AutoTokenizer, LiltForTokenClassification

    validate_splits(examples)
    if not (1 <= epochs <= 16 and 0 <= variants <= 3 and 1 <= batch_size <= 4
            and 1 <= accumulation_steps <= 8 and 1 <= patience <= 4):
        raise ValueError("Training parameters exceed the bounded experiment limits")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    rng = random.Random(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    tokenizer = AutoTokenizer.from_pretrained(base_path, use_fast=True)
    model = LiltForTokenClassification.from_pretrained(
        base_path, num_labels=len(roles), ignore_mismatched_sizes=True,
        id2label={index: role for index, role in enumerate(roles)},
        label2id={role: index for index, role in enumerate(roles)},
    ).to(device)
    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()
    train_examples = [example for example in examples if example["split"] == "train"]
    val_examples = [example for example in examples if example["split"] == "val"]
    test_examples = [example for example in examples if example["split"] == "test"]
    if final_test and not test_examples:
        raise ValueError("final_test needs the test practices: build the dataset with include_test")
    data = []
    for example in train_examples:
        data.extend(encode_chunks(example, tokenizer, roles))
        for variant in range(variants):
            copy_ = _augment(example, rng)
            data.extend(encode_chunks(_reframe(copy_, rng) if variant else copy_, tokenizer, roles))
    data = [chunk for chunk in data if any(target != -100 for target in chunk["labels"])]
    if not data:
        raise ValueError("No supervised training words remain")
    role_counts = Counter(label for example in train_examples for label in example["labels"]
                          if label not in {"O", IGNORE_LABEL})
    median = sorted(role_counts.values())[len(role_counts) // 2] if role_counts else 1
    reference = max(median, 100)
    weights = torch.tensor([1.0 if role == "O" else min(5.0, max(1.0, (reference / max(1, role_counts[role])) ** 0.5))
                            for role in roles], device=device)
    criterion = torch.nn.CrossEntropyLoss(weight=weights, ignore_index=-100)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)
    batches_per_epoch = math.ceil(len(data) / batch_size)
    total_steps = epochs * math.ceil(batches_per_epoch / accumulation_steps)
    warmup = max(1, round(total_steps * 0.1))

    def lr_multiplier(step: int) -> float:
        if step < warmup:
            return (step + 1) / warmup
        return max(0.0, (total_steps - step) / max(1, total_steps - warmup))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_multiplier)
    started = time.perf_counter()
    log, best_weights, best_metric, best_epoch, stale = [], None, (-1.0, -1.0, -1.0), None, 0
    for epoch in range(1, epochs + 1):
        model.train()
        rng.shuffle(data)
        total_loss = 0.0
        optimizer.zero_grad(set_to_none=True)
        for batch_index, start in enumerate(range(0, len(data), batch_size)):
            batch = data[start:start + batch_size]
            length = max(len(chunk["input_ids"]) for chunk in batch)
            tensors = {}
            for key, pad_value in (("input_ids", tokenizer.pad_token_id), ("attention_mask", 0),
                                   ("bbox", [0, 0, 0, 0]), ("labels", -100)):
                tensors[key] = torch.tensor([chunk[key] + [pad_value] * (length - len(chunk[key]))
                                             for chunk in batch], device=device)
            labels = tensors.pop("labels")
            if device.startswith("cuda"):
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    logits = model(**tensors).logits
            else:
                logits = model(**tensors).logits
            loss = criterion(logits.float().reshape(-1, len(roles)), labels.reshape(-1))
            total_loss += float(loss.detach())
            group_start = (batch_index // accumulation_steps) * accumulation_steps
            group_size = min(accumulation_steps, batches_per_epoch - group_start)
            (loss / group_size).backward()
            if (batch_index + 1) % accumulation_steps == 0 or batch_index + 1 == batches_per_epoch:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
        validation, _ = _evaluate(model, tokenizer, val_examples, roles)
        entry = {
            "epoch": epoch,
            "loss": round(total_loss / batches_per_epoch, 6),
            "val_f1": validation["f1"],
            "val_non_note_f1": validation["non_note_f1"],
            "val_field_accuracy": validation["field_accuracy"],
            "val_credit_field_accuracy": validation["credit_field_accuracy"],
        }
        log.append(entry)
        print(json.dumps(entry), flush=True)
        candidate_metric = (
            validation["field_accuracy"] if validation["field_accuracy"] is not None else -1.0,
            validation["non_note_f1"] if validation["non_note_f1"] is not None else -1.0,
            validation["f1"] if validation["f1"] is not None else -1.0,
        )
        if candidate_metric > best_metric:
            best_metric, best_epoch, stale = candidate_metric, epoch, 0
            best_weights = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        else:
            stale += 1
            if stale >= patience:
                break
    if best_weights is None:
        raise RuntimeError("No validation checkpoint was selected")
    model.load_state_dict(best_weights)
    validation, val_predictions = _evaluate(model, tokenizer, val_examples, roles)
    test_metrics, test_predictions = _evaluate(model, tokenizer, test_examples, roles) if final_test else (None, {})
    elapsed = round(time.perf_counter() - started, 3)
    model.eval().cpu().float()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    settings = {"epochs_max": epochs, "variants_train_only": variants, "seed": seed,
                "batch_size": batch_size, "accumulation_steps": accumulation_steps,
                "learning_rate": learning_rate, "early_stopping_patience": patience,
                "max_length": 512, "device": device}
    fingerprints = dataset_fingerprint(examples, roles)
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "base_model": BASE_MODEL,
                "base_revision": base_revision, "initialization": "fresh pretrained; no BPER checkpoint",
                "dataset_sha256": fingerprints, "dataset_manifest": dataset_manifest,
                "settings": settings,
                "checkpoint_selection": "validation whole-field accuracy, then non-note word F1, then word micro F1",
                "test_evaluations": 1 if final_test else 0, "best_epoch": best_epoch,
                "train_sequences_including_augmentation": len(data), "train_seconds": elapsed,
                "packages": {"torch": str(torch.__version__),
                             "transformers": str(__import__("transformers").__version__)}}
    metrics = {"validation": validation, "test": test_metrics}
    splits = {split: {"practices": sorted({example["practice"] for example in examples if example["split"] == split}),
                      "examples": [example["id"] for example in examples if example["split"] == split]}
              for split in KNOWN_SPLITS}
    for filename, content in (("training_manifest.json", manifest), ("splits.json", splits),
                              ("labelmap.json", {"roles": roles}), ("metrics.json", metrics),
                              ("training_log.json", log), ("validation_predictions.json", val_predictions),
                              ("test_predictions.json", test_predictions)):
        _write_json(output_dir / filename, content)
    return {"best_epoch": best_epoch, "train_seconds": elapsed, "train_log": log,
            "metrics": metrics, "test_predictions": test_predictions,
            "validation_predictions": val_predictions, "manifest": manifest,
            "model_files": sorted(path.name for path in output_dir.iterdir() if path.is_file())}
