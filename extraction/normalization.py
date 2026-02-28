"""Text normalization, field classification, and dataset mismatch guard."""

import re
from difflib import SequenceMatcher
from typing import Dict, Any, Optional, Tuple

from extraction.fields import CSV_TO_SCHEMA, _SOGGETTI_KEY_MAP

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
# Nullish / text helpers
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
    s = s.replace(".", "").replace(",", "")
    return s


# ============================================================
# Field accessors
# ============================================================

def safe_field(fields: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Fields may be None under the JSON schema. Always returns a dict with defaults."""
    f = (fields or {}).get(key)
    if isinstance(f, dict):
        return {
            "value": f.get("value"),
            "confidence": float(f.get("confidence", 0.0) or 0.0),
            "evidence_text": f.get("evidence_text"),
            "section": f.get("section"),
        }
    return {"value": None, "confidence": 0.0, "evidence_text": None, "section": None}


def safe_set_field(
    fields: Dict[str, Any],
    key: str,
    *,
    value: Any = None,
    confidence: Optional[float] = None,
    evidence_text: Optional[str] = None,
    section: Optional[str] = None,
) -> None:
    """Ensure fields[key] is a dict (not None) and set provided attributes safely."""
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


def pick_best(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    if not a:
        return b
    if not b:
        return a
    av, bv = a.get("value"), b.get("value")
    an, bn = is_nullish(av), is_nullish(bv)
    if an and not bn:
        return b
    if bn and not an:
        return a
    return a if a.get("confidence", 0.0) >= b.get("confidence", 0.0) else b


def merge_field_sources(
    field_sources: Dict[str, str],
    field_key: str,
    current: Dict[str, Any],
    candidate: Dict[str, Any],
    candidate_source: str,
) -> Dict[str, Any]:
    """Pick best AND track source attempt for the winning value."""
    chosen = pick_best(current, candidate)
    if chosen is candidate:
        field_sources[field_key] = candidate_source
    return chosen


# ============================================================
# Field-specific normalizers (private)
# ============================================================

def _extract_date_ddmmyyyy(s: Any) -> str:
    if s is None:
        return ""
    m = re.search(r"(\b\d{2}/\d{2}/\d{4}\b)", str(s))
    return m.group(1) if m else ""


def _norm_company(s: Any) -> str:
    if s is None:
        return ""
    x = str(s).upper()
    x = re.sub(r"[^A-Z0-9 ]+", " ", x)
    x = re.sub(r"\bS\s*P\s*A\b", "SPA", x)
    x = re.sub(r"\bS\.?P\.?A\.?\b", "SPA", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def _norm_text_aggressive(s: Any) -> str:
    if s is None:
        return ""
    x = str(s).lower()
    x = re.sub(r"[\r\n\t]+", " ", x)
    x = re.sub(r"[^a-z0-9àèéìòù ]+", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ============================================================
# classify_field — strategy dispatch (refactored from CC=11)
# ============================================================

_FIELD_COMPARATORS: Dict[str, Any] = {
    "ultima_validazione": lambda gt, pr: _extract_date_ddmmyyyy(gt) == _extract_date_ddmmyyyy(pr),
    "datore_lavoro_anagrafica": lambda gt, pr: _norm_company(gt) == _norm_company(pr),
    "note": lambda gt, pr: _similar(_norm_text_aggressive(gt), _norm_text_aggressive(pr)) >= 0.90,
}


def classify_field(gt_val: Any, pred_val: Any, field_key: Optional[str] = None) -> str:
    """Returns: OK, WRONG, MISSING, HALLUCINATED, OK_NULL."""
    gt_null = is_nullish(gt_val) or (str(gt_val).strip().lower() == "nan")
    pr_null = is_nullish(pred_val)

    if not gt_null and pr_null:
        return "MISSING"
    if gt_null and not pr_null:
        return "HALLUCINATED"
    if gt_null and pr_null:
        return "OK_NULL"

    # Both present — use field-specific comparator or default
    comparator = _FIELD_COMPARATORS.get(field_key)  # type: ignore[arg-type]
    if comparator:
        return "OK" if comparator(gt_val, pred_val) else "WRONG"
    return "OK" if norm_text(pred_val) == norm_text(gt_val) else "WRONG"


# ============================================================
# Tabular subject parsing
# ============================================================

def _parse_tabular_subject_key(gt_key: str) -> Optional[Tuple[str, int]]:
    """Return (base_key, idx0) if gt_key is like 'NDG 1' or 'DENOMINAZIONE 2'."""
    m = re.match(r"^(NDG|DENOMINAZIONE|RUOLO)\s+(\d+)$", gt_key.strip(), re.IGNORECASE)
    if not m:
        return None
    base = m.group(1).upper()
    idx0 = int(m.group(2)) - 1
    if idx0 < 0:
        return None
    return base, idx0


def get_pred_value_for_gt_key(
    pred: Dict[str, Any], gt_key: str
) -> Tuple[Optional[str], Any, float, Optional[str], Optional[str]]:
    """Returns (source, value, confidence, evidence_text, section)."""
    gt_key_norm = str(gt_key).strip()

    # 1) Handle tabular keys -> soggetti array
    parsed = _parse_tabular_subject_key(gt_key_norm)
    if parsed:
        base, idx0 = parsed
        key = _SOGGETTI_KEY_MAP.get(base)
        soggetti = pred.get("soggetti") or []
        if key and idx0 < len(soggetti) and isinstance(soggetti[idx0], dict):
            s = soggetti[idx0]
            return (
                f"soggetti[{idx0}].{key}",
                s.get(key),
                s.get("confidence", 0.0),
                s.get("evidence_text"),
                None,
            )
        return (f"soggetti[{idx0}].{key}", None, 0.0, None, None)

    # 2) Normal fields mapping via CSV_TO_SCHEMA
    schema_key = CSV_TO_SCHEMA.get(gt_key_norm)
    if not schema_key:
        return (None, None, 0.0, None, None)
    field = safe_field((pred.get("fields", {}) or {}), schema_key)
    if not isinstance(field, dict):
        return (schema_key, None, 0.0, None, None)
    return (
        schema_key,
        field.get("value"),
        field.get("confidence", 0.0),
        field.get("evidence_text"),
        field.get("section"),
    )


# ============================================================
# Dataset mismatch guard (anchor-based)
# ============================================================

def _resolve_anchor_value(
    pred_fields: Dict[str, Any],
    soggetti: list,
    field_key: str,
) -> Any:
    """Extract anchor value from fields, falling back to first soggetti row."""
    val = (pred_fields.get(field_key) or {}).get("value")
    if is_nullish(val) and soggetti and isinstance(soggetti[0], dict):
        val = soggetti[0].get(field_key)
    return val


def dataset_mismatch_guard(gt_kv: Dict[str, Any], pred: Dict[str, Any]) -> bool:
    """Returns True if GT keys clearly belong to a different record than what we extracted."""
    gt_ndg = gt_kv.get("NDG") or gt_kv.get("NDG 1")
    gt_den = gt_kv.get("DENOMINAZIONE") or gt_kv.get("DENOMINAZIONE 1")

    pred_fields = pred.get("fields", {}) or {}
    soggetti = pred.get("soggetti") or []

    pr_ndg = _resolve_anchor_value(pred_fields, soggetti, "ndg")
    pr_den = _resolve_anchor_value(pred_fields, soggetti, "denominazione")

    if gt_ndg and pr_ndg and norm_number_str(gt_ndg) != norm_number_str(pr_ndg):
        return True
    if gt_den and pr_den and norm_text(gt_den) != norm_text(pr_den):
        return True
    return False
