"""Ground truth loading, accuracy evaluation, debug reporting, and cost summary."""

import os
from typing import Dict, Any, List

import pandas as pd

from extraction.config import get_screenshot_paths
from extraction.fields import FIELD_KEYS, CSV_TO_SCHEMA
from extraction.normalization import (
    norm_text,
    norm_number_str,
    classify_field,
    dataset_mismatch_guard,
    get_pred_value_for_gt_key,
)


# ============================================================
# Screenshot path inference
# ============================================================

def infer_screenshots_from_gt(gt: Dict[str, Dict[str, Any]], base_dir: str = ".") -> List[str]:
    """Backward-compatible alias for get_screenshot_paths()."""
    return get_screenshot_paths(gt, base_dir=base_dir)


# ============================================================
# Ground truth loader
# ============================================================

def _find_column(df_columns: list, candidates: List[str], label: str) -> str:
    """Find the first matching column name from a list of candidates."""
    for c in candidates:
        if c in df_columns:
            return c
    raise ValueError(f"Cannot find {label} column in CSV. Columns={df_columns}")


def load_ground_truth(csv_path: str) -> Dict[str, Dict[str, Any]]:
    """Load ground truth CSV. Returns: { "screen 1": { "NDG": "...", ... }, ... }"""
    df = pd.read_csv(csv_path)
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


# ============================================================
# Evaluation
# ============================================================

def eval_outputs(outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]]) -> None:
    total_raw = correct_raw = 0
    total_filt = correct_filt = 0

    per_field_raw: Dict[str, List[int]] = {}
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

            if schema_key in ("retribuzione_annua_netta", "importo_totale_annuo_altri_componenti", "ndg"):
                ok = norm_number_str(pred_val) == norm_number_str(gt_val)
            else:
                ok = norm_text(pred_val) == norm_text(gt_val)

            # RAW
            total_raw += 1
            correct_raw += int(ok)
            per_field_raw.setdefault(schema_key, [0, 0])
            per_field_raw[schema_key][0] += int(ok)
            per_field_raw[schema_key][1] += 1

            # FILTERED
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
    for k, (c, t) in sorted(per_field_filt.items(), key=lambda x: x[0]):
        print(f"  {k:40s} {c:3d}/{t:3d} = {(c/t):.2%}")


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

            status = "DATASET_MISMATCH" if mismatch else classify_field(gt_val, pred_val, field_key=source_key)

            source_attempt = ""
            if source_key in FIELD_KEYS:
                source_attempt = field_sources.get(source_key, "")

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
                "source_attempt": source_attempt,
                "screen_calls": meta_agg.get("calls"),
                "screen_total_tokens": meta_agg.get("total_tokens"),
                "screen_estimated_cost_usd": meta_agg.get("estimated_cost_usd"),
                "screen_latency_ms": meta_agg.get("latency_ms"),
                "_status": pred.get("_status"),
            })

    pd.DataFrame(rows).to_csv(out_csv_path, index=False, encoding="utf-8")


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
