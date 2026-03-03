"""Text normalization, field classification, and dataset mismatch guard."""
import re
from difflib import SequenceMatcher
from typing import Dict, Any, Optional, Tuple, List
from extraction.fields import CSV_TO_SCHEMA, FIELD_KEYS, _SOGGETTI_KEY_MAP

# ============================================================
# Post-processing (categorical mapping)
# ============================================================
TIPO_MAPPING: Dict[str, str] = {
    "mutui spesa": "BPI Mutui",
    "mutuo spesa": "BPI Mutui",
    "bpi mutui": "BPI Mutui",
}

def normalize_tipo(val: Any) -> Any:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    key = s.lower()
    return TIPO_MAPPING.get(key, s)

# ============================================================
# Basic Normalizers
# ============================================================
def is_nullish(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in ("", "n/d", "nd", "---", "null", "none", "nan")

def norm_text(x: Any) -> str:
    s = "" if x is None else str(x)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def norm_number_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    # Remove currency, spaces, dots (thousands), replace comma with dot
    s = s.replace("€", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "")
    s = s.replace(",", ".")
    # Final cleanup: keep only digits and one dot
    s = re.sub(r"[^\d.]", "", s)
    try:
        if not s: return ""
        return f"{float(s):.2f}"
    except:
        return s.strip()

# ============================================================
# Field handling
# ============================================================
def safe_field(fields: Dict[str, Any], key: str) -> Dict[str, Any]:
    f = (fields or {}).get(key)
    if isinstance(f, dict):
        return {
            "value": f.get("value"),
            "confidence": float(f.get("confidence", 0.0) or 0.0),
            "evidence_text": f.get("evidence_text"),
            "section": f.get("section"),
        }
    return {"value": None, "confidence": 0.0, "evidence_text": None, "section": None}

def safe_set_field(fields: Dict[str, Any], key: str, *, value=None, confidence=None, evidence_text=None, section=None) -> None:
    if fields is None:
        return
    f = fields.get(key)
    if not isinstance(f, dict):
        f = {"value": None, "confidence": 0.0, "evidence_text": None, "section": None}
        fields[key] = f
    if value is not None or f.get("value") is None:
        f["value"] = value
    if confidence is not None:
        f["confidence"] = float(confidence or 0.0)
    if evidence_text is not None:
        f["evidence_text"] = evidence_text
    if section is not None:
        f["section"] = section

def pick_best(f1: Dict[str, Any], f2: Dict[str, Any]) -> Dict[str, Any]:
    v1 = f1.get("value")
    v2 = f2.get("value")
    if is_nullish(v1) and not is_nullish(v2):
        return f2
    if not is_nullish(v1) and is_nullish(v2):
        return f1
    c1 = f1.get("confidence", 0.0) or 0.0
    c2 = f2.get("confidence", 0.0) or 0.0
    return f1 if c1 >= c2 else f2

def merge_field_sources(
    field_sources: Dict[str, str],
    field_key: str,
    current: Dict[str, Any],
    candidate: Dict[str, Any],
    candidate_source: str,
) -> Dict[str, Any]:
    chosen = pick_best(current, candidate)
    if chosen is candidate:
        field_sources[field_key] = candidate_source
    return chosen

# ============================================================
# Classification (Accuracy)
# ============================================================
def classify_field(gt_val: Any, pred_val: Any, field_key: Optional[str] = None) -> Tuple[str, str]:
    """Returns (status, reason). Status: OK, WRONG, MISSING, HALLUCINATED, OK_NULL."""
    gt_null = is_nullish(gt_val) or (str(gt_val).strip().lower() == "nan")
    pr_null = is_nullish(pred_val)

    if gt_null and pr_null:
        return "OK_NULL", ""
    if not gt_null and pr_null:
        return "MISSING", "Valore presente in GT ma non estratto."
    if gt_null and not pr_null:
        return "HALLUCINATED", f"Valore estratto ('{pred_val}') ma assente in GT."

    # Both present
    # Check if it's a numeric field
    numeric_fields = ["importo_euro", "ndg", "n_fido"]
    if field_key and any(nf in field_key.lower() for nf in numeric_fields):
        gt_n = norm_number_str(gt_val)
        pr_n = norm_number_str(pred_val)
        if gt_n == pr_n:
            return "OK", ""
        return "WRONG", f"Mismatch numerico: GT='{gt_n}' vs PRED='{pr_n}'"

    # Text fields
    t1 = norm_text(gt_val)
    t2 = norm_text(pred_val)
    if t1 == t2:
        return "OK", ""
    
    # Fuzzy match for long texts
    if len(t1) > 20:
        ratio = SequenceMatcher(None, t1, t2).ratio()
        if ratio >= 0.85:
            return "OK", f"Fuzzy match: {ratio:.2f}"
        return "WRONG", f"Fuzzy match insufficient: {ratio:.2f}"

    return "WRONG", f"Mismatch testuale: GT='{t1}' vs PRED='{t2}'"

def get_pred_value_for_gt_key(pred: Dict[str, Any], gt_key: str) -> Tuple[Optional[str], Any, float, Optional[str], Optional[str]]:
    """Helper for evaluation to find the predicted value and meta given a GT key."""
    schema_key = CSV_TO_SCHEMA.get(gt_key)
    if not schema_key:
        return None, None, 0.0, None, None
    
    f_data = safe_field(pred.get("fields", {}), schema_key)
    return schema_key, f_data["value"], f_data["confidence"], f_data["evidence_text"], f_data["section"]

# ============================================================
# Dataset Mismatch Guard
# ============================================================
def _resolve_anchor_value(fields: Dict[str, Any], soggetti: List[Dict[str, Any]], key: str) -> Optional[str]:
    # Try fields first
    val = (fields.get(key) or {}).get("value")
    if not is_nullish(val):
        return str(val)
    # Try soggetti
    for s in soggetti:
        val = s.get(key)
        if not is_nullish(val):
            return str(val)
    return None

def dataset_mismatch_guard(gt_kv: Dict[str, Any], pred: Dict[str, Any]) -> bool:
    """True if NDG or Denominazione mismatch heavily, suggesting wrong GT row for this screen."""
    gt_ndg = gt_kv.get("NDG") or gt_kv.get("ndg")
    gt_den = gt_kv.get("Denom.") or gt_kv.get("DENOMINAZIONE")
    
    pred_fields = pred.get("fields", {}) or {}
    soggetti = pred.get("soggetti") or []
    
    pr_ndg = _resolve_anchor_value(pred_fields, soggetti, "ndg")
    pr_den = _resolve_anchor_value(pred_fields, soggetti, "denominazione")
    
    if gt_ndg and pr_ndg and norm_number_str(gt_ndg) != norm_number_str(pr_ndg):
        return True
    if gt_den and pr_den and norm_text(gt_den) != norm_text(pr_den):
        return True
    return False
