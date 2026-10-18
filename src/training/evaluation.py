"""Reconstruct OCR roles and measure exact values without the VLM evaluator.

Only ``None`` is absent in the reviewed corpus. In particular, visible ``N/D``
text is a value. Alignment exclusions never remove a reviewed field from the
end-to-end denominator, and no approximate text matching earns correctness.
"""

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from training.schema import field_role, vocabulary


IGNORED_LABELS = {"IGNORE", -100, None}
SUBJECT_ROLES = {"sogg_ndg", "sogg_denominazione", "sogg_ruolo"}
FIDI_ROLES = ("n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op")
METRIC_VERSION = "strict-v3-fidi-first-row"
QUANTITY_FIELDS = {
    "importo_euro", "retribuzione_annua_netta", "importo_totale_annuo_nucleo",
    "nr_altri_componenti_nucleo", "di_cui_percepiscono_reddito", "numero_mensilita",
}


def normalize_value(field: str, value: Any) -> Any:
    """Normalize representation while retaining identifier digits and suffixes."""
    if value is None:
        return None
    text = " ".join(unicodedata.normalize("NFKC", str(value)).split()).casefold()
    if field == "ndg" or re.fullmatch(r"ndg_[1-4]", field):
        identifier = re.sub(r"[^a-z0-9]", "", text)
        return (identifier.lstrip("0") or "0") if identifier.isdigit() else identifier
    if field in {"rapporto", "n_fido"}:
        return re.sub(r"\s+", "", text)
    if field in QUANTITY_FIELDS:
        number = text.replace("€", "").replace(" ", "")
        if "," in number:
            number = number.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+", number):
            number = number.replace(".", "")
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", number):
            try:
                return Decimal(number)
            except InvalidOperation:
                pass
    # OCR places spaces on either side of punctuation inconsistently. Keep the
    # punctuation itself and every word boundary between letters or digits.
    return "".join(
        char for index, char in enumerate(text)
        if char != " " or not any(
            unicodedata.category(text[neighbor]).startswith("P")
            for neighbor in (index - 1, index + 1) if 0 <= neighbor < len(text)
        )
    )


def classify_value(field: str, expected: Any, predicted: Any) -> str:
    """Classify one observed field; missing predictions are represented by None."""
    if expected is None:
        return "correct_null" if predicted is None else "hallucinated"
    if predicted is None:
        return "missing"
    return "correct" if normalize_value(field, expected) == normalize_value(field, predicted) else "wrong"


def _box(word: dict[str, Any]) -> list[float]:
    if "bbox" in word:
        return [float(v) for v in word["bbox"]]
    if "box" in word:
        return [float(v) for v in word["box"]]
    return [float(word[k]) for k in ("x0", "y0", "x1", "y1")]


def _lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group visual lines, including OCR cells split into separate line objects."""
    if not words:
        return []
    tolerance = 0.5 * median(max(1.0, _box(w)[3] - _box(w)[1]) for w in words)
    lines: list[list[dict[str, Any]]] = []
    centers: list[float] = []
    for word in sorted(words, key=lambda w: (_box(w)[1] + _box(w)[3]) / 2):
        center = (_box(word)[1] + _box(word)[3]) / 2
        if not lines or abs(center - centers[-1]) > tolerance:
            lines.append([word])
            centers.append(center)
        else:
            lines[-1].append(word)
            centers[-1] = sum((_box(w)[1] + _box(w)[3]) / 2 for w in lines[-1]) / len(lines[-1])
    return [sorted(line, key=lambda w: _box(w)[0]) for line in lines]


def _join(words: list[dict[str, Any]]) -> str:
    return " ".join(str(w["text"]) for line in _lines(words) for w in line).strip()


def _subject_row_centers(
    words: list[dict[str, Any]], by_role: dict[str, list[dict[str, Any]]],
) -> tuple[list[float], float]:
    """Locate rows from OCR geometry without promoting raw words to predictions."""
    subjects = [w for role in SUBJECT_ROLES for w in by_role.get(role, [])]
    if not subjects:
        return [], 0.0
    height = median(max(1.0, _box(w)[3] - _box(w)[1]) for w in subjects)
    tolerance = height / 2
    top = min((_box(w)[1] + _box(w)[3]) / 2 for w in subjects) - tolerance
    bottom = max((_box(w)[1] + _box(w)[3]) / 2 for w in subjects) + tolerance
    numeric = [
        w for w in words
        if re.fullmatch(r"\d[\d., ]*", str(w["text"]).strip())
        and top <= (_box(w)[1] + _box(w)[3]) / 2 <= bottom
    ]
    ndgs = by_role.get("sogg_ndg", [])
    if ndgs:
        column = median(_box(w)[0] for w in ndgs)
        markers = ndgs + [w for w in numeric if abs(_box(w)[0] - column) <= tolerance]
    else:
        # Without a predicted NDG, require a repeated numeric column to the
        # left of the predicted subject cells before trusting it as row marks.
        left = min(_box(w)[0] for w in subjects)
        candidates = [w for w in numeric if _box(w)[2] <= left]
        columns: list[list[dict[str, Any]]] = []
        for word in sorted(candidates, key=lambda w: _box(w)[0]):
            if not columns or abs(_box(word)[0] - _box(columns[-1][0])[0]) > tolerance:
                columns.append([word])
            else:
                columns[-1].append(word)
        repeated = [column for column in columns if len(_lines(column)) >= 2]
        markers = repeated[-1] if repeated else []
    if markers:
        return [median((_box(w)[1] + _box(w)[3]) / 2 for w in line) for line in _lines(markers)], tolerance
    centers: list[float] = []
    previous: float | None = None
    for line in _lines(subjects):
        center = median((_box(w)[1] + _box(w)[3]) / 2 for w in line)
        if previous is None or center - previous > 1.5 * height:
            centers.append(center)
        previous = center
    return centers, tolerance


def _center_y(word: dict[str, Any]) -> float:
    return (_box(word)[1] + _box(word)[3]) / 2


def _first_fido_row(
    words: list[dict[str, Any]], by_role: dict[str, list[dict[str, Any]]],
) -> None:
    """Keep the FIDI roles of the topmost table row; the reviewed values are one row."""
    anchors = by_role.get("n_fido", [])
    if not anchors:
        return
    anchor = min(anchors, key=_center_y)
    left, height = _box(anchor)[0], max(1.0, _box(anchor)[3] - _box(anchor)[1])
    below = [_center_y(w) for w in words
             if abs(_box(w)[0] - left) <= height and _center_y(w) > _center_y(anchor) + height]
    if not below:
        return
    bottom = (_center_y(anchor) + min(below)) / 2
    for role in FIDI_ROLES:
        if role in by_role:
            by_role[role] = [w for w in by_role[role] if _center_y(w) < bottom]
            if not by_role[role]:
                del by_role[role]


def decode_fields(
    example: dict[str, Any], predicted_roles: list[str],
    probabilities: list[float] | None = None,
) -> dict[str, str]:
    """Decode raw OCR text using predicted roles, subject-row and FIDI-row geometry.

    The ground-truth values do not influence reconstruction. Probabilities are
    accepted for the prediction contract; no hidden confidence cutoff is used.
    """
    words = example["words"]
    if len(predicted_roles) != len(words):
        raise ValueError("Prediction length must match the OCR word length")
    if probabilities is not None and len(probabilities) != len(words):
        raise ValueError("Probability length must match the OCR word length")
    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for word, role in zip(words, predicted_roles):
        if role not in IGNORED_LABELS and role != "O":
            by_role[role].append(word)
    _first_fido_row(words, by_role)
    fields = {role: _join(ws) for role, ws in by_role.items() if role not in SUBJECT_ROLES}
    centers, tolerance = _subject_row_centers(words, by_role)
    for index, center in enumerate(centers[:4]):
        top = center - tolerance if index else float("-inf")
        bottom = centers[index + 1] - tolerance if index + 1 < len(centers) else float("inf")
        for role, key in (("sogg_ndg", "ndg"), ("sogg_denominazione", "denominazione"), ("sogg_ruolo", "ruolo")):
            in_row = [w for w in by_role.get(role, []) if top <= (_box(w)[1] + _box(w)[3]) / 2 < bottom]
            if in_row:
                fields[f"{key}_{index + 1}"] = _join(in_row)
    return fields


def _prediction(example: dict[str, Any], predictions: dict[str, Any]) -> tuple[list[str], list[float] | None]:
    item = predictions.get(example["id"])
    if item is None:
        return ["O"] * len(example["words"]), None
    if isinstance(item, list):
        return item, None
    roles = item.get("pred", item.get("predicted_roles"))
    if roles is None:
        raise ValueError(f"Missing predicted roles for {example['id']}")
    return roles, item.get("prob", item.get("probabilities"))


def _summary(statuses: list[str]) -> dict[str, Any]:
    counts = Counter(statuses)
    correct = counts["correct"] + counts["correct_null"]
    return {
        "total": len(statuses), "correct": correct,
        "accuracy": correct / len(statuses) if statuses else None,
        "counts": dict(counts),
    }


def _available(example: dict[str, Any], field: str, expected: Any, oracle: dict[str, str]) -> bool:
    if expected is None:
        return True
    alignment = example.get("field_alignment", {}).get(field)
    if isinstance(alignment, bool):
        return alignment
    if isinstance(alignment, dict):
        for name in ("available", "exact_text", "exact", "aligned"):
            if isinstance(alignment.get(name), bool):
                if alignment[name] and "ocr_text" in alignment:
                    return classify_value(field, expected, alignment["ocr_text"]) == "correct"
                return alignment[name]
        if "status" in alignment:
            return alignment["status"] in {"exact", "aligned", "available", "exact_match"}
    if isinstance(alignment, str):
        return alignment in {"exact", "aligned", "available", "exact_match"}
    return classify_value(field, expected, oracle.get(field)) == "correct"


def _availability(records: list[dict[str, Any]]) -> dict[str, Any]:
    available = sum(r["content_available"] for r in records)
    present = [r for r in records if r["expected"] is not None]
    present_available = sum(r["content_available"] for r in present)
    return {
        "total": len(records), "available": available,
        "unavailable": len(records) - available,
        "rate": available / len(records) if records else None,
        "non_null_total": len(present), "non_null_available": present_available,
        "non_null_rate": present_available / len(present) if present else None,
    }


def _oracle(example: dict[str, Any]) -> dict[str, str]:
    """Fields decoded from the reviewed labels: what the OCR words can yield."""
    return decode_fields(example, example.get("labels", ["O"] * len(example["words"])))


def _record(
    example: dict[str, Any], field: str, expected: Any, predicted: Any,
    oracle: dict[str, str], abstained: bool = False,
) -> dict[str, Any]:
    return {
        "id": example["id"], "practice": example["practice"], "split": example["split"],
        "field": field, "expected": expected, "predicted": predicted,
        "status": classify_value(field, expected, predicted),
        "content_available": _available(example, field, expected, oracle),
        "abstained": abstained,
    }


def _field_report(
    examples: list[dict[str, Any]], records: list[dict[str, Any]], missing: list[str],
    word_metrics_for: Callable[[list[dict[str, Any]]], dict[str, Any]] | None,
) -> dict[str, Any]:
    """Summarize field records identically for role and field-value predictions."""
    all_fields = sorted({field for e in examples for field in e["values"]})

    def summarize(selected: list[dict[str, Any]]) -> dict[str, Any]:
        summary = _summary([r["status"] for r in selected])
        summary["abstained"] = sum(r["abstained"] for r in selected)
        summary["by_field"] = {}
        for field in all_fields:
            rows = [r for r in selected if r["field"] == field]
            summary["by_field"][field] = {
                **_summary([r["status"] for r in rows]),
                "abstained": sum(r["abstained"] for r in rows),
                "content_availability": _availability(rows),
            }
        summary["content_availability"] = _availability(selected)
        return summary

    def words(selected: list[dict[str, Any]]) -> dict[str, Any] | None:
        return word_metrics_for(selected) if word_metrics_for else None

    overall = summarize(records)
    splits = sorted({"train", "val", "test"} | {e["split"] for e in examples})
    by_split = {split: summarize([r for r in records if r["split"] == split]) for split in splits}
    for split, summary in by_split.items():
        summary["word_metrics"] = words([e for e in examples if e["split"] == split])
    return {
        "metric_version": METRIC_VERSION,
        "overall": {k: v for k, v in overall.items() if k != "by_field"},
        "by_field": overall["by_field"], "by_split": by_split,
        "word_metrics": words(examples), "records": records,
        "missing_predictions": missing, "complete": not missing,
    }


def evaluate_predictions(
    examples: list[dict[str, Any]], predictions: dict[str, Any],
) -> dict[str, Any]:
    """Measure every reviewed field, retaining OCR failures in the denominator."""
    records: list[dict[str, Any]] = []
    for example in examples:
        roles, probabilities = _prediction(example, predictions)
        fields = decode_fields(example, roles, probabilities)
        oracle = _oracle(example)
        records.extend(_record(example, field, expected, fields.get(field), oracle)
                       for field, expected in example["values"].items())
    covered_roles = {field_role(field) for e in examples for field in e["values"]}

    def covered_word_metrics(selected: list[dict[str, Any]]) -> dict[str, Any]:
        metrics = word_metrics(selected, predictions)
        for role in sorted(covered_roles):
            metrics["by_role"].setdefault(role, _role_scores(0, 0, 0))
        return metrics

    missing = [e["id"] for e in examples if e["id"] not in predictions]
    return _field_report(examples, records, missing, covered_word_metrics)


def _role_scores(tp: int, fp: int, fn: int) -> dict[str, Any]:
    return {
        "tp": tp, "fp": fp, "fn": fn, "support": tp + fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def word_metrics(
    examples: list[dict[str, Any]], predictions: dict[str, Any],
) -> dict[str, Any]:
    """Report role F1; ignored words contribute neither positives nor errors."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    ignored = 0
    for example in examples:
        predicted, probabilities = _prediction(example, predictions)
        decode_fields(example, predicted, probabilities)
        labels = example.get("labels", ["IGNORE"] * len(example["words"]))
        if len(labels) != len(predicted):
            raise ValueError("Label length must match the OCR word length")
        for gold, guess in zip(labels, predicted):
            if gold in IGNORED_LABELS:
                ignored += 1
                continue
            if gold == guess and gold != "O":
                counts[gold]["tp"] += 1
            elif gold != guess:
                if gold != "O":
                    counts[gold]["fn"] += 1
                if guess not in IGNORED_LABELS and guess != "O":
                    counts[guess]["fp"] += 1
    by_role = {role: _role_scores(c["tp"], c["fp"], c["fn"]) for role, c in sorted(counts.items())}
    totals = Counter[str]()
    for count in counts.values():
        totals.update(count)
    return {
        "micro": _role_scores(totals["tp"], totals["fp"], totals["fn"]),
        "by_role": by_role, "ignored_words": ignored,
    }


FIELD_PREDICTION_KEYS = {"fields", "abstained"}


def _validate_field_prediction(screen: str, item: Any, known_fields: set[str]) -> None:
    if not isinstance(item, dict) or not isinstance(item.get("fields"), dict):
        raise ValueError(f"Prediction for {screen} needs a 'fields' mapping")
    unexpected = sorted(set(item) - FIELD_PREDICTION_KEYS)
    if unexpected:
        raise ValueError(f"Prediction for {screen} has unexpected key(s): {unexpected}")
    abstained = item.get("abstained", [])
    if not isinstance(abstained, list) or not all(isinstance(field, str) for field in abstained):
        raise ValueError(f"Prediction for {screen}: 'abstained' must be a list of field names")
    for field in [*item["fields"], *abstained]:
        if field not in known_fields:
            raise ValueError(f"Prediction for {screen} names an unknown field: {field}")
    for field, value in item["fields"].items():
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Field {field} on {screen} must be a string or None")
        if value is not None and not value.strip():
            raise ValueError(f"Field {field} on {screen} is empty; use None for an absent value")
    both = sorted(set(item["fields"]) & set(abstained))
    if both:
        raise ValueError(f"Field(s) {both} on {screen} are both predicted and abstained")


def evaluate_field_values(
    examples: list[dict[str, Any]], predictions: dict[str, Any],
) -> dict[str, Any]:
    """Measure field-level predictions with the comparator and summaries of the role path.

    Each screen maps to ``{"fields": {field: text or None}, "abstained": [field, ...]}``.
    Absent and abstained fields score as absent values. A screen without an entry
    scores every field as absent and leaves the report incomplete. Word metrics
    do not apply to field-level predictions and are reported as ``None``.
    """
    known_fields = set(vocabulary()[0])
    unknown = sorted(set(predictions) - {e["id"] for e in examples})
    if unknown:
        raise ValueError(f"Field predictions for unknown screen(s): {unknown}")
    for screen, item in predictions.items():
        _validate_field_prediction(screen, item, known_fields)
    records: list[dict[str, Any]] = []
    for example in examples:
        item = predictions.get(example["id"], {"fields": {}})
        abstained = set(item.get("abstained", []))
        oracle = _oracle(example)
        records.extend(_record(example, field, expected, item["fields"].get(field), oracle, field in abstained)
                       for field, expected in example["values"].items())
    missing = [e["id"] for e in examples if e["id"] not in predictions]
    return _field_report(examples, records, missing, None)
