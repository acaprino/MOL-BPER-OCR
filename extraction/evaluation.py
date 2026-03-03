"""Ground truth loading, accuracy evaluation, debug reporting, and cost summary."""
import os
import json
from typing import Dict, Any, List, Tuple
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
            ok = (status == "OK" or status == "OK_NULL")
            
            # RAW
            total_raw += 1
            correct_raw += int(ok)
            
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
    for k, (c, t) in sorted(per_field_filt.items()):
        print(f"  {k:40s} {c:3d}/{t:3d} = {(c/t):.2%}")
        
    return {
        "acc_raw": acc_raw,
        "acc_filt": acc_filt,
        "per_field_filt": per_field_filt
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
                "reason": reason,
                "source_attempt": source_attempt,
                "screen_calls": meta_agg.get("calls"),
                "screen_total_tokens": meta_agg.get("total_tokens"),
                "screen_estimated_cost_usd": meta_agg.get("estimated_cost_usd"),
                "screen_latency_ms": meta_agg.get("latency_ms"),
                "_status": pred.get("_status"),
            })
            
    pd.DataFrame(rows).to_csv(out_csv_path, index=False, encoding="utf-8-sig")

# ============================================================
# Export to CSV
# ============================================================
def export_to_csv(outputs: Dict[str, Dict[str, Any]], out_csv_path: str):
    """
    Exports the extracted data to a flat CSV file.
    """
    rows = []
    for scr, out in outputs.items():
        fields = out.get("fields", {})
        # Main fields
        for f_key in FIELD_KEYS:
            f_data = fields.get(f_key)
            if isinstance(f_data, dict):
                rows.append({
                    "screen": scr,
                    "category": "FIELD",
                    "field": f_key,
                    "value": f_data.get("value"),
                    "confidence": f_data.get("confidence"),
                    "evidence_text": f_data.get("evidence_text"),
                    "section": f_data.get("section")
                })
        
        # Tables
        for tbl_name in ["soggetti", "fidi", "garanzie"]:
            items = out.get(tbl_name, [])
            for i, item in enumerate(items):
                for k, v in item.items():
                    if k == "confidence" or k == "evidence_text": continue # skip meta
                    rows.append({
                        "screen": scr,
                        "category": tbl_name.upper(),
                        "field": f"{tbl_name}[{i}].{k}",
                        "value": v,
                        "confidence": item.get("confidence"),
                        "evidence_text": item.get("evidence_text"),
                        "section": ""
                    })

    pd.DataFrame(rows).to_csv(out_csv_path, index=False, encoding="utf-8-sig")

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
