"""Ground truth loading, accuracy evaluation, debug reporting, and cost summary."""
import csv
import os
from typing import Dict, Any, List
import pandas as pd
from openpyxl import load_workbook
from extraction.fields import FIELD_KEYS, CSV_TO_SCHEMA
from extraction.normalization import (
    classify_field,
    dataset_mismatch_guard,
    get_pred_value_for_gt_key,
    escape_csv_formula,
)

# ============================================================
# CSV writing
# ============================================================
def _write_csv(rows: List[Dict[str, Any]], out_csv_path: str) -> None:
    """Write rows to an Excel-friendly CSV, neutralizing formula injection."""
    df = pd.DataFrame(rows)
    for col in df.columns:
        df[col] = df[col].map(escape_csv_formula)
    df.to_csv(out_csv_path, index=False, encoding="utf-8-sig", sep=";")

# ============================================================
# Ground truth loader
# ============================================================
def _find_column(df_columns: list, candidates: List[str], label: str) -> str:
    """Find the first matching column name from a list of candidates."""
    for c in candidates:
        if c in df_columns:
            return c
    raise ValueError(f"Cannot find {label} column in CSV. Columns={df_columns}")

def _read_gt_csv(csv_path: str) -> pd.DataFrame:
    """Read the ground-truth CSV tolerant of separator and encoding.

    Italian-Excel exports are frequently ``;``-separated and cp1252-encoded,
    while the pipeline's own exports are ``;``-separated utf-8-sig. ``sep=None``
    with the python engine sniffs ``,`` vs ``;``; encodings are tried in order.
    """
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(csv_path, sep=None, engine="python", encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return pd.read_csv(csv_path)  # last resort: pandas defaults


def load_ground_truth(csv_path: str) -> Dict[str, Dict[str, Any]]:
    """Load ground truth CSV. Returns: { "screen 1": { "NDG": "...", ... }, ... }"""
    df = _read_gt_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]

    screen_col = _find_column(
        df.columns.tolist(),
        ["Screenshot", "Fotogramma", "Screen", "screen"],
        "screen",
    )
    value_col = _find_column(
        df.columns.tolist(),
        ["Valore rilevato", "Valore rilevato ", "Valore", "Value"],
        "value",
    )
    key_col = _find_column(
        df.columns.tolist(),
        ["Denominazione da attribuire", "Denominazione", "Campo", "Field"],
        "key",
    )

    df[screen_col] = df[screen_col].astype(str).str.strip()
    df[key_col] = df[key_col].astype(str).str.strip()
    df[value_col] = df[value_col].astype(str).str.strip()

    gt: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        scr = row[screen_col]
        key = row[key_col]
        val = row[value_col]
        if key is None or str(key).strip().lower() in ("", "nan", "none"):
            continue
        key = str(key).strip()
        if val is None or str(val).strip().lower() in ("nan",):
            val = ""
        gt.setdefault(scr, {})[key] = val
    return gt


def load_practice_truth(workbook_path: str, practice: str) -> Dict[str, Dict[str, Any]]:
    """Truth of one practice from the archive workbook: its sheet, keyed by page like the screenshot files."""
    workbook = load_workbook(workbook_path, read_only=True)
    try:
        if practice not in workbook.sheetnames:
            raise ValueError(f"No sheet for practice {practice} in {workbook_path}")
        rows = workbook[practice].iter_rows(values_only=True)
        header = next(rows)
        screen, key, value = (header.index(column) for column in ("Schermata", "Campo", "Valore"))
        gt: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            if row[key] in (None, ""):
                continue
            gt.setdefault(str(row[screen]).strip(), {})[str(row[key]).strip()] = (
                "" if row[value] is None else str(row[value]).strip())
        return gt
    finally:
        workbook.close()


def load_dataset_truth(valori_path: str, practice: str) -> Dict[str, Dict[str, Any]]:
    """Truth of one practice from the clean archive's valori.csv, keyed by screenshot file stem (ADR 0032)."""
    gt: Dict[str, Dict[str, Any]] = {}
    with open(valori_path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            owner, screen = row["Schermata"].split("/", 1)
            if owner == practice and row["Campo"].strip():
                gt.setdefault(screen, {})[row["Campo"].strip()] = row["Valore"].strip()
    if not gt:
        raise ValueError(f"No values for practice {practice} in {valori_path}")
    return gt


def resolve_ground_truth(input_dir: str) -> Dict[str, Dict[str, Any]]:
    """Truth of a screenshot folder: its own dati.csv, else the clean archive's valori.csv (ADR 0032), else its
    sheet of the archive workbook beside it (ADR 0029)."""
    csv_path = os.path.join(input_dir, "dati.csv")
    if os.path.exists(csv_path):
        return load_ground_truth(csv_path)
    folder = os.path.normpath(input_dir)
    valori_path = os.path.join(os.path.dirname(os.path.dirname(folder)), "valori.csv")
    if os.path.exists(valori_path):
        return load_dataset_truth(valori_path, os.path.basename(folder))
    workbook_path = os.path.join(os.path.dirname(folder), "pratiche.xlsx")
    if not os.path.exists(workbook_path):
        raise FileNotFoundError(f"No dati.csv in {input_dir} and no archive workbook at {workbook_path}")
    return load_practice_truth(workbook_path, os.path.basename(folder))

# ============================================================
# Evaluation
# ============================================================
def eval_outputs(outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    total_raw = correct_raw = 0
    total_filt = correct_filt = 0
    per_field_filt: Dict[str, List[int]] = {}

    for scr, kv in gt.items():
        pred = outputs.get(scr)
        if not pred:
            continue

        mismatch = dataset_mismatch_guard(kv, pred)

        for csv_key, gt_val in kv.items():
            csv_key_norm = str(csv_key).strip()
            schema_key = CSV_TO_SCHEMA.get(csv_key_norm)
            if not schema_key:
                continue

            pred_val = (pred.get("fields", {}).get(schema_key) or {}).get("value")
            status, _ = classify_field(gt_val, pred_val, field_key=schema_key)
            ok = status in ("OK", "OK_NULL")

            total_raw += 1
            correct_raw += int(ok)

            if not mismatch:
                total_filt += 1
                correct_filt += int(ok)
                per_field_filt.setdefault(schema_key, [0, 0])
                per_field_filt[schema_key][0] += int(ok)
                per_field_filt[schema_key][1] += 1

    acc_raw = (correct_raw / total_raw) if total_raw else 0.0
    acc_filt = (correct_filt / total_filt) if total_filt else 0.0

    print(f"\nOVERALL (RAW):      {correct_raw}/{total_raw} = {acc_raw:.2%}")
    print(f"OVERALL (FILTERED): {correct_filt}/{total_filt} = {acc_filt:.2%}\n")

    print("Per-field (FILTERED):")
    for k, (c, t) in sorted(per_field_filt.items()):
        print(f"  {k:40s} {c:3d}/{t:3d} = {(c/t):.2%}")

    return {
        "acc_raw": acc_raw,
        "acc_filt": acc_filt,
        "per_field_filt": per_field_filt,
    }

# ============================================================
# Debug report
# ============================================================
def build_debug_report(
    outputs: Dict[str, Dict[str, Any]],
    gt: Dict[str, Dict[str, Any]],
    out_csv_path: str,
) -> None:
    """Debug report with per-(screen, GT-key) rows."""
    rows: List[Dict[str, Any]] = []
    for scr, gt_kv in gt.items():
        pred = outputs.get(scr)
        if not pred:
            continue

        mismatch = dataset_mismatch_guard(gt_kv, pred)
        field_sources = pred.get("_field_sources", {}) or {}
        meta_agg = pred.get("_meta_agg", {}) or {}

        for gt_key, gt_val in gt_kv.items():
            gt_key_norm = str(gt_key).strip()
            source_key, pred_val, conf, evidence, section = get_pred_value_for_gt_key(pred, gt_key_norm)
            if source_key is None:
                continue

            status, reason = classify_field(gt_val, pred_val, field_key=source_key)
            if mismatch:
                status = "DATASET_MISMATCH"

            source_attempt = field_sources.get(source_key, "") if source_key in FIELD_KEYS else ""

            rows.append({
                "screen": scr,
                "field": source_key,
                "gt_key": gt_key_norm,
                "gt_value": gt_val,
                "pred_value": pred_val,
                "confidence": conf,
                "evidence_text": evidence,
                "section": section,
                "status": status,
                "reason": reason,
                "source_attempt": source_attempt,
                "screen_calls": meta_agg.get("calls"),
                "screen_total_tokens": meta_agg.get("total_tokens"),
                "screen_estimated_cost_usd": meta_agg.get("estimated_cost_usd"),
                "screen_latency_ms": meta_agg.get("latency_ms"),
                "_status": pred.get("_status"),
            })

    _write_csv(rows, out_csv_path)

# ============================================================
# Export to CSV
# ============================================================
def export_to_csv(outputs: Dict[str, Dict[str, Any]], out_csv_path: str) -> None:
    """Exports the extracted data to a flat CSV file."""
    rows = []
    for scr, out in outputs.items():
        canonical_fields = out.get("canonical_fields") or []
        if canonical_fields:
            for entry in canonical_fields:
                rows.append({
                    "screen": scr,
                    "category": "FIELD",
                    "field": entry.get("display_name") or entry.get("schema_key"),
                    "schema_key": entry.get("schema_key"),
                    "page_key": entry.get("page_key"),
                    "page_name": entry.get("page_name"),
                    "value": entry.get("value"),
                    "confidence": entry.get("confidence"),
                    "evidence_text": entry.get("evidence_text"),
                    "section": entry.get("section"),
                })
        else:
            fields = out.get("fields", {})
            for f_key in FIELD_KEYS:
                f_data = fields.get(f_key)
                if isinstance(f_data, dict):
                    rows.append({
                        "screen": scr,
                        "category": "FIELD",
                        "field": f_key,
                        "schema_key": f_key,
                        "page_key": None,
                        "page_name": None,
                        "value": f_data.get("value"),
                        "confidence": f_data.get("confidence"),
                        "evidence_text": f_data.get("evidence_text"),
                        "section": f_data.get("section"),
                    })

        for tbl_name in ["soggetti", "fidi", "garanzie"]:
            for i, item in enumerate(out.get(tbl_name, [])):
                for k, v in item.items():
                    if k in ("confidence", "evidence_text"):
                        continue
                    rows.append({
                        "screen": scr,
                        "category": tbl_name.upper(),
                        "field": f"{tbl_name}[{i}].{k}",
                        "value": v,
                        "confidence": item.get("confidence"),
                        "evidence_text": item.get("evidence_text"),
                        "section": "",
                    })

    _write_csv(rows, out_csv_path)

# ============================================================
# Cost summary
# ============================================================
def print_cost_summary(outputs: Dict[str, Dict[str, Any]]) -> None:
    print("\nCOST SUMMARY (per screen):")
    total_cost = 0.0
    total_tokens = 0
    total_calls = 0
    for scr, out in outputs.items():
        agg = out.get("_meta_agg", {})
        cost = float(agg.get("estimated_cost_usd", 0.0) or 0.0)
        toks = int(agg.get("total_tokens", 0) or 0)
        calls = int(agg.get("calls", 0) or 0)
        total_cost += cost
        total_tokens += toks
        total_calls += calls
        print(f"  {scr:10s}  calls={calls:2d}  tokens={toks:5d}  cost=${cost:.4f}  status={out.get('_status')}")
    print(f"\nTOTAL: calls={total_calls}  tokens={total_tokens}  cost=${total_cost:.4f}\n")


# ============================================================
# Evaluator class
# ============================================================

class Evaluator:
    """Bundles ground truth with evaluation, reporting, and cost summary."""

    def __init__(self, gt: Dict[str, Dict[str, Any]]) -> None:
        self._gt = gt

    def eval(self, outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Run accuracy evaluation against ground truth."""
        return eval_outputs(outputs, self._gt)

    def build_debug_report(self, outputs: Dict[str, Dict[str, Any]], out_csv_path: str) -> None:
        """Write per-(screen, field) debug CSV."""
        build_debug_report(outputs, self._gt, out_csv_path)

    @staticmethod
    def print_cost_summary(outputs: Dict[str, Dict[str, Any]]) -> None:
        """Print per-screen token/cost summary."""
        print_cost_summary(outputs)
