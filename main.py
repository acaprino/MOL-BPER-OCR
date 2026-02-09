
import os
import io
import json
import re
import time
import base64
from typing import Dict, Any, Optional, Tuple, List

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from PIL import Image, ImageEnhance, ImageFilter

from openai import OpenAI

# ============================================================
# CONFIG
# ============================================================

# Input files (override with INPUT_DIR env if desired)
DEFAULT_SCREENSHOTS = [
    "screen 1.png",
    "screen 2.png",
    "screen 3.png",
    "screen 4.png",
]
DEFAULT_GROUND_TRUTH = "dati.csv"

INPUT_DIR = os.getenv("INPUT_DIR", "mnt/data")
SCREENSHOTS = [os.path.join(INPUT_DIR, s) for s in DEFAULT_SCREENSHOTS]
GROUND_TRUTH_CSV = os.path.join(INPUT_DIR, DEFAULT_GROUND_TRUTH)

PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS", "4"))
MAX_CALLS_PER_SCREEN = int(os.getenv("MAX_CALLS_PER_SCREEN", "4"))
STOP_ON_ANCHOR_UNCERTAIN = os.getenv("STOP_ON_ANCHOR_UNCERTAIN", "0") == "1"  # keep 0: some screens may not show anchors

PARALLEL_ENABLED = os.getenv("PARALLEL_ENABLED", "1") == "1"

# Model selection (override via env)
MODEL_MAIN = os.getenv("OPENAI_MODEL", "gpt-4o")
MODEL_ANCHOR = os.getenv("OPENAI_MODEL_ANCHOR", MODEL_MAIN)

# Pricing (USD per 1M tokens) - keep configurable; pricing may change over time.
PRICING_PER_1M = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

# ------------------------------------------------------------
# Crops (percentuali) – invarianti rispetto a risoluzione/PC
# ------------------------------------------------------------
# Content crop: rimuove sidebar e topbar browser (tipico)
CONTENT_CROP = (0.18, 0.12, 0.98, 0.98)

# Header dentro il contenuto (per NDG / Denominazione)
HEADER_IN_CONTENT = (0.00, 0.00, 1.00, 0.22)

# Retry crops mirati (sempre nel sistema di riferimento del CONTENT)
# Nota: sono volutamente “larghi” per essere robusti allo scroll / layout.
FIELD_RETRY_MAP: Dict[str, Tuple[float, float, float, float]] = {
    # Sezione entrate / redditi (tipicamente parte alta centrale)
    "professione_principale": (0.00, 0.12, 1.00, 0.48),
    "numero_mensilita": (0.00, 0.12, 1.00, 0.48),
    "retribuzione_annua_netta": (0.00, 0.12, 1.00, 0.48),
    "tipo_contratto": (0.00, 0.12, 1.00, 0.55),
    "datore_lavoro_anagrafica": (0.18, 0.25, 0.98, 0.62),
    "dal": (0.00, 0.12, 1.00, 0.55),

    # Evidenze/Tipo spesso in griglia “pratiche”
    "tipo": (0.00, 0.00, 1.00, 0.25),
    "evidenze": (0.00, 0.00, 1.00, 0.30),

    # Situazione familiare / note tipicamente più in basso
    "nr_altri_componenti_nucleo_familiare": (0.00, 0.40, 1.00, 0.78),
    "di_cui_percepiscono_reddito": (0.00, 0.40, 1.00, 0.78),
    "importo_totale_annuo_altri_componenti": (0.00, 0.40, 1.00, 0.82),
    "note": (0.00, 0.55, 1.00, 1.00),
}

# Soglia confidenza “dura” per ancore (anti errori silenziosi)
ANCHOR_CONF_MIN = float(os.getenv("ANCHOR_CONF_MIN", "0.95"))

# Debug: salva i crop su disco (0/1)
DEBUG_SAVE_CROPS = os.getenv("DEBUG_SAVE_CROPS", "0") == "1"
DEBUG_CROP_DIR = os.path.join(INPUT_DIR, "debug_crops")

# ============================================================
# Target fields
# ============================================================
FIELD_KEYS = [
    "ndg",
    "denominazione",
    "tipo",
    "evidenze",
    "filiale_relazione",
    "ultima_validazione",
    "professione_principale",
    "numero_mensilita",
    "retribuzione_annua_netta",
    "tipo_contratto",
    "anagrafica",
    "dal",
    "rating_ufficiale",
    "score_cgs",
    "nr_altri_componenti_nucleo_familiare",
    "di_cui_percepiscono_reddito",
    "importo_totale_annuo_altri_componenti",
    "note",
]

CSV_TO_SCHEMA = {
    "NDG": "ndg",
    "DENOMINAZIONE": "denominazione",
    "Tipo": "tipo",
    "Evidenze": "evidenze",
    "Filiale relazione": "filiale_relazione",
    "Ultima validazione": "ultima_validazione",
    "Professione principale": "professione_principale",
    "Numero mensilità": "numero_mensilita",
    "Retribuzione annua netta": "retribuzione_annua_netta",
    "Tipo contratto": "tipo_contratto",
    "ANAGRAFICA": "anagrafica",
    "DAL": "dal",
    "RATING UFFICIALE": "rating_ufficiale",
    "SCORE CGS": "score_cgs",
    "Nr altri componenti nucleo familiare": "nr_altri_componenti_nucleo_familiare",
    "Di cui percepiscono reddito": "di_cui_percepiscono_reddito",
    "Importo totale annuo altri componenti nucleo familiare": "importo_totale_annuo_altri_componenti",
    "Note": "note",
}

_SOGGETTI_KEY_MAP = {
    "NDG": "ndg",
    "DENOMINAZIONE": "denominazione",
    "RUOLO": "ruolo"
}

# ============================================================
# Prompts
# ============================================================
PROMPT = """
Sei un sistema di estrazione dati da screenshot di una web app (UI banca).
Devi estrarre SOLO i campi richiesti e restituire JSON conforme allo schema.

Regole:
- Se ci sono più soggetti (NDG 1..3, Denominazione 1..3, Ruolo 1..3), estrai TUTTE le righe della tabella in "soggetti" mantenendo l'ordine dall'alto verso il basso.

- Se un valore non è presente o non è leggibile: value = null e confidence <= 0.3.
- Trattare "N/D", "ND", "---", vuoto come null.
- Non inventare mai valori.
- Per ogni campo: includi evidence_text (breve estratto) e section (titolo sezione se visibile).
- Se ci sono più soggetti (NDG 1..4, Denominazione 1..4, Ruolo 1..4), popola l'array soggetti.

Campi (label/sinonimi):
- ndg: "NDG"
- denominazione: "DENOMINAZIONE", "Nominativo"
- tipo: "Tipo"
- evidenze: "Evidenze"
- filiale_relazione: "Filiale relazione"
- ultima_validazione: "Ultima validazione"
- professione_principale: "PROFESSIONE PRINCIPALE"
- numero_mensilita: "NUMERO MENSILITÀ", "MENSILITA"
- retribuzione_annua_netta: "RETRIBUZIONE ANNUA NETTA"
- tipo_contratto: "TIPO CONTRATTO"
- datore_lavoro_anagrafica: "ANAGRAFICA" (nella sezione/tab "DATORE DI LAVORO")
- dal: "DAL"
- rating_ufficiale: "RATING UFFICIALE"
- score_cgs: "SCORE CGS"
- nr_altri_componenti_nucleo_familiare: "NR. ALTRI COMPONENTI NUCLEO FAMILIARE"
- di_cui_percepiscono_reddito: "DI CUI PERCEPISCONO REDDITO"
- importo_totale_annuo_altri_componenti: "IMPORTO TOTALE ANNUO"
- note: "NOTE", "NOTE CONCLUSIVE"

Restituisci SOLO JSON.
""".strip()

ANCHOR_PROMPT = """
Estrai SOLO i seguenti campi dallo screenshot:
- ndg
- denominazione

Regole:
- Se non sei assolutamente certo, restituisci null.
- NDG deve essere una sequenza numerica ESATTA (non stimare).
- Non inventare mai valori.
- Imposta confidence >= 0.95 solo se il valore è chiaramente leggibile.

Restituisci SOLO JSON conforme allo schema.
""".strip()

# ============================================================
# JSON Schemas (strict)
# ============================================================

RESPONSE_SCHEMA = {
    "name": "bper_screen_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "screen_id": {"type": "string"},
            "attempt": {"type": "string"},
            "fields": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    k: {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["string", "number", "integer", "null"]},
                            "confidence": {"type": "number"},
                            "evidence_text": {"type": ["string", "null"]},
                            "section": {"type": ["string", "null"]},
                        },
                        "required": ["value", "confidence", "evidence_text", "section"],
                    }
                    for k in FIELD_KEYS
                },
                "required": FIELD_KEYS,
            },
            "soggetti": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "ndg": {"type": ["string", "null"]},
                        "denominazione": {"type": ["string", "null"]},
                        "ruolo": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "evidence_text": {"type": ["string", "null"]},
                    },
                    "required": ["ndg", "denominazione", "ruolo", "confidence", "evidence_text"],
                },
            },
        },
        "required": ["screen_id", "attempt", "fields", "soggetti"],
    },
}

ANCHOR_SCHEMA = {
    "name": "bper_anchor_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "screen_id": {"type": "string"},
            "attempt": {"type": "string"},
            "fields": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ndg": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["string", "number", "integer", "null"]},
                            "confidence": {"type": "number"},
                            "evidence_text": {"type": ["string", "null"]},
                            "section": {"type": ["string", "null"]},
                        },
                        "required": ["value", "confidence", "evidence_text", "section"],
                    },
                    "denominazione": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["string", "number", "integer", "null"]},
                            "confidence": {"type": "number"},
                            "evidence_text": {"type": ["string", "null"]},
                            "section": {"type": ["string", "null"]},
                        },
                        "required": ["value", "confidence", "evidence_text", "section"],
                    },
                },
                "required": ["ndg", "denominazione"],
            },
        },
        "required": ["screen_id", "attempt", "fields"],
    },
}

# ============================================================
# Post-processing (categorial mapping)
# ============================================================

TIPO_MAPPING = {
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
# Helpers
# ============================================================

def infer_screenshots_from_gt(gt: Dict[str, Dict[str, Any]], base_dir: str = ".") -> List[str]:
    """
    Builds an ordered list of screenshot file paths from GT keys.
    Assumes files are named like 'screen 1.png' and located in base_dir (default: current working directory).
    """
    names = sorted(gt.keys(), key=lambda s: (re.sub(r"\D+", "", s) or "0", s))
    paths = []
    for name in names:
        candidate = os.path.join(base_dir, f"{name}.png") if not name.lower().endswith(".png") else os.path.join(base_dir, name)
        # Common naming from your project: 'screen 1.png'
        if os.path.exists(candidate):
            paths.append(candidate)
            continue
        # Try also with spaces normalized
        candidate2 = os.path.join(base_dir, name)
        if os.path.exists(candidate2):
            paths.append(candidate2)
            continue
        # If not found, still append the canonical expected path for visibility
        paths.append(os.path.join(base_dir, f"{name}.png"))
    return paths

def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = PRICING_PER_1M.get(model)
    if not p:
        return 0.0
    return (prompt_tokens / 1_000_000) * p["input"] + (completion_tokens / 1_000_000) * p["output"]

def normalize_image(img: Image.Image, long_side: int = 1800) -> Image.Image:
    w, h = img.size
    scale = long_side / max(w, h)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    img = ImageEnhance.Contrast(img).enhance(1.05)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
    return img

def crop_relative(img: Image.Image, box: Tuple[float, float, float, float]) -> Image.Image:
    w, h = img.size
    l = int(box[0] * w)
    t = int(box[1] * h)
    r = int(box[2] * w)
    b = int(box[3] * h)
    return img.crop((l, t, r, b))

def img_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def is_nullish(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in ("", "n/d", "nd", "---", "null", "none", "nan")

def safe_field(fields: Dict[str, Any], key: str) -> Dict[str, Any]:
    """
    Fields may be None under the JSON schema. This helper always returns a dict-like field with defaults.
    """
    f = (fields or {}).get(key)
    if isinstance(f, dict):
        # Ensure required keys exist
        return {
            "value": f.get("value"),
            "confidence": float(f.get("confidence", 0.0) or 0.0),
            "evidence_text": f.get("evidence_text"),
            "section": f.get("section"),
        }
    return {"value": None, "confidence": 0.0, "evidence_text": None, "section": None}



def safe_set_field(fields: Dict[str, Any], key: str, *, value=None, confidence=None, evidence_text=None, section=None) -> None:
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

def _extract_date_ddmmyyyy(s: Any) -> str:
    if s is None:
        return ""
    m = re.search(r"(\b\d{2}/\d{2}/\d{4}\b)", str(s))
    return m.group(1) if m else ""

def _norm_company(s: Any) -> str:
    if s is None:
        return ""
    x = str(s).upper()
    x = re.sub(r"[^A-Z0-9 ]+", " ", x)  # remove punctuation
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
    # lightweight similarity without extra deps
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()

def classify_field(gt_val, pred_val, field_key: Optional[str] = None) -> str:
    """
    Returns: OK, WRONG, MISSING, HALLUCINATED, OK_NULL
    field_key is optional and enables field-specific normalization.
    """
    gt_null = is_nullish(gt_val) or (str(gt_val).strip().lower() == "nan")
    pr_null = is_nullish(pred_val)

    if not gt_null and pr_null:
        return "MISSING"
    if gt_null and not pr_null:
        return "HALLUCINATED"
    if gt_null and pr_null:
        return "OK_NULL"

    # both present: field-specific compares
    if field_key == "ultima_validazione":
        return "OK" if _extract_date_ddmmyyyy(gt_val) == _extract_date_ddmmyyyy(pred_val) else "WRONG"

    if field_key == "datore_lavoro_anagrafica":
        return "OK" if _norm_company(gt_val) == _norm_company(pred_val) else "WRONG"

    if field_key == "note":
        a = _norm_text_aggressive(gt_val)
        b = _norm_text_aggressive(pred_val)
        return "OK" if _similar(a, b) >= 0.90 else "WRONG"

    # default exactish compare
    return "OK" if norm_text(pred_val) == norm_text(gt_val) else "WRONG"

def _parse_tabular_subject_key(gt_key: str):
    """Return (base_key, idx0) if gt_key is like 'NDG 1' or 'DENOMINAZIONE 2' or 'RUOLO 3'."""
    m = re.match(r"^(NDG|DENOMINAZIONE|RUOLO)\s+(\d+)$", gt_key.strip(), re.IGNORECASE)
    if not m:
        return None
    base = m.group(1).upper()
    idx0 = int(m.group(2)) - 1
    if idx0 < 0:
        return None
    return base, idx0

def get_pred_value_for_gt_key(pred: Dict[str, Any], gt_key: str):
    """
    Returns a tuple:
      (source, value, confidence, evidence_text, section)
    where source is either a schema field name (e.g. 'ndg') or 'soggetti[i].ndg'.
    """
    gt_key_norm = str(gt_key).strip()
    # 1) Handle tabular keys -> soggetti array
    parsed = _parse_tabular_subject_key(gt_key_norm)
    if parsed:
        base, idx0 = parsed
        key = _SOGGETTI_KEY_MAP.get(base)
        soggetti = pred.get("soggetti") or []
        if key and idx0 < len(soggetti) and isinstance(soggetti[idx0], dict):
            s = soggetti[idx0]
            return (f"soggetti[{idx0}].{key}",
                    s.get(key),
                    s.get("confidence", 0.0),
                    s.get("evidence_text"),
                    None)
        return (f"soggetti[{idx0}].{key}", None, 0.0, None, None)

    # 2) Normal fields mapping via CSV_TO_SCHEMA
    schema_key = CSV_TO_SCHEMA.get(gt_key_norm)
    if not schema_key:
        return (None, None, 0.0, None, None)
    field = safe_field((pred.get("fields", {}) or {}), schema_key)
    if not isinstance(field, dict):
        return (schema_key, None, 0.0, None, None)
    return (schema_key,
            field.get("value"),
            field.get("confidence", 0.0),
            field.get("evidence_text"),
            field.get("section"))



# ============================================================
# Dataset mismatch guard (anchor-based)
# ============================================================
def dataset_mismatch_guard(gt_kv: Dict[str, Any], pred: Dict[str, Any]) -> bool:
    """
    Returns True if the GT keys clearly belong to a different record than what we extracted.
    We use anchors (NDG / DENOMINAZIONE), falling back to the first row of 'soggetti' if needed.
    """
    gt_ndg = gt_kv.get("NDG") or gt_kv.get("NDG 1")
    gt_den = gt_kv.get("DENOMINAZIONE") or gt_kv.get("DENOMINAZIONE 1")

    pred_fields = pred.get("fields", {}) or {}
    pr_ndg = (pred_fields.get("ndg") or {}).get("value")
    pr_den = (pred_fields.get("denominazione") or {}).get("value")

    # fallback to first row of soggetti if fields anchors are empty
    soggetti = pred.get("soggetti") or []
    if is_nullish(pr_ndg) and soggetti and isinstance(soggetti[0], dict):
        pr_ndg = soggetti[0].get("ndg")
    if is_nullish(pr_den) and soggetti and isinstance(soggetti[0], dict):
        pr_den = soggetti[0].get("denominazione")

    if gt_ndg and pr_ndg and norm_number_str(gt_ndg) != norm_number_str(pr_ndg):
        return True
    if gt_den and pr_den and norm_text(gt_den) != norm_text(pr_den):
        return True
    return False

# ============================================================
# VLM calls (Chat Completions + Structured Outputs)
# ============================================================
def call_vlm(
    client: OpenAI,
    image_bytes: bytes,
    prompt: str,
    screen_id: str,
    attempt: str,
    model: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Estrai i campi richiesti dallo screenshot."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                ],
            },
        ],
        response_format={"type": "json_schema", "json_schema": schema},
    )
    dt_ms = int((time.time() - t0) * 1000)

    ##TODO: migliorare attesa risposta con controllo attivo per minimizzare i tempi

    out = json.loads(resp.choices[0].message.content)

    usage = getattr(resp, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
    total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    out["_meta"] = {
        "model": model,
        "screen_id": screen_id,
        "attempt": attempt,
        "latency_ms": dt_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": cost_usd,
    }
    out["screen_id"] = screen_id
    out["attempt"] = attempt
    return out

def call_vlm_with_retry(
    client: OpenAI,
    image_bytes: bytes,
    prompt: str,
    screen_id: str,
    attempt: str,
    model: str,
    schema: Dict[str, Any],
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    Retry wrapper for transient API errors (rate limits, timeouts).
    Keeps observability intact; each successful call returns the same structure as call_vlm().
    """
    last_err = None
    for i in range(max_retries):
        try:
            return call_vlm(
                client=client,
                image_bytes=image_bytes,
                prompt=prompt,
                screen_id=screen_id,
                attempt=attempt,
                model=model,
                schema=schema,
            )
        except Exception as e:
            #TODO: Better error handling

            last_err = e
            # Exponential backoff with jitter (bounded)
            sleep_s = min(8.0, (2 ** i) * 0.8) + (0.05 * i)
            time.sleep(sleep_s)
    raise last_err

def _save_debug_crop(img: Image.Image, screen_id: str, name: str) -> None:
    if not DEBUG_SAVE_CROPS:
        return
    os.makedirs(DEBUG_CROP_DIR, exist_ok=True)
    out_path = os.path.join(DEBUG_CROP_DIR, f"{screen_id}__{name}.png")
    img.save(out_path)

# ============================================================
# Anchor extraction (NDG, Denominazione)
# ============================================================
def extract_anchors(client: OpenAI, content_img: Image.Image, screen_id: str) -> Dict[str, Any]:
    header_img = crop_relative(content_img, HEADER_IN_CONTENT)
    _save_debug_crop(header_img, screen_id, "HEADER_IN_CONTENT")

    payload = img_to_png_bytes(header_img)
    out = call_vlm_with_retry(
        client=client,
        image_bytes=payload,
        prompt=ANCHOR_PROMPT,
        screen_id=screen_id,
        attempt="ANCHOR_HEADER",
        model=MODEL_ANCHOR,
        schema=ANCHOR_SCHEMA,
    )

    fields = out.get("fields", {})
    ndg = safe_field(fields, "ndg")
    den = safe_field(fields, "denominazione")

    # Gate duro: alta confidenza o null
    if ndg.get("confidence", 0.0) < ANCHOR_CONF_MIN:
        safe_set_field(fields, "ndg", value=None, confidence=ndg.get("confidence", 0.0), evidence_text=ndg.get("evidence_text"), section=ndg.get("section"))
    if den.get("confidence", 0.0) < ANCHOR_CONF_MIN:
        safe_set_field(fields, "denominazione", value=None, confidence=den.get("confidence", 0.0), evidence_text=den.get("evidence_text"), section=den.get("section"))

    return {
        "ndg": ndg,
        "denominazione": den,
        "_meta": out["_meta"],
    }

# ============================================================
# Main extraction per screen: 1 pass + retry condizionale
# ============================================================
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

def extract_from_screen(client: OpenAI, path: str) -> Dict[str, Any]:
    img = Image.open(path).convert("RGB")
    img = normalize_image(img)

    screen_id = os.path.splitext(os.path.basename(path))[0]

    # Content crop (baseline)
    content_img = crop_relative(img, CONTENT_CROP)
    _save_debug_crop(content_img, screen_id, "CONTENT")

    # 1) Extract anchors first (dedicated)
    anchors = extract_anchors(client, content_img, screen_id)

    # 2) Main pass: run on content
    payload = img_to_png_bytes(content_img)

    # Hint anchors in prompt (non cambia schema; migliora disambiguazione)
    anchor_hint = []
    if anchors["ndg"]["value"]:
        anchor_hint.append(f"NDG atteso: {anchors['ndg']['value']}")
    if anchors["denominazione"]["value"]:
        anchor_hint.append(f"Denominazione attesa: {anchors['denominazione']['value']}")
    prompt_with_hint = PROMPT + ("\n\n" + "\n".join(anchor_hint) if anchor_hint else "")

    main_out = call_vlm_with_retry(
        client=client,
        image_bytes=payload,
        prompt=prompt_with_hint,
        screen_id=screen_id,
        attempt="CONTENT_MAIN",
        model=MODEL_MAIN,
        schema=RESPONSE_SCHEMA,
    )

    attempts_meta = [anchors["_meta"], main_out["_meta"]]

    # 3) Merge anchors into main fields (anchors have higher priority if present)
    field_sources: Dict[str, str] = {k: "CONTENT_MAIN" for k in FIELD_KEYS}
    # initialize with main result
    result = main_out

    # Replace with gated anchors if available
    for k in ("ndg", "denominazione"):
        if anchors[k]["value"] is not None:
            result["fields"][k] = anchors[k]
            field_sources[k] = "ANCHOR_HEADER"

    # 4) Post-process tipo mapping (before retries)
    # Normalize categorical field "tipo" safely (field may be None under schema)
    tipo_field = (result.get("fields", {}) or {}).get("tipo")
    if isinstance(tipo_field, dict):
        tipo_field["value"] = normalize_tipo(tipo_field.get("value"))
        result["fields"]["tipo"] = tipo_field
# 5) Retry ONLY for missing/low-confidence fields
    for field_key, crop_box in FIELD_RETRY_MAP.items():
        current = result["fields"].get(field_key) or {}
        cur_val = current.get("value")
        cur_conf = float(current.get("confidence", 0.0) or 0.0)

        should_retry = is_nullish(cur_val) or (cur_conf < 0.55)
        if not should_retry:
            continue

        crop_img = crop_relative(content_img, crop_box)
        _save_debug_crop(crop_img, screen_id, f"RETRY_{field_key}")

        retry_out = call_vlm_with_retry(
            client=client,
            image_bytes=img_to_png_bytes(crop_img),
            prompt=prompt_with_hint,
            screen_id=screen_id,
            attempt=f"RETRY_{field_key}",
            model=MODEL_MAIN,
            schema=RESPONSE_SCHEMA,
        )
        attempts_meta.append(retry_out["_meta"])

        candidate = retry_out["fields"].get(field_key) or {}
        # Apply tipo mapping if retry is about tipo
        if field_key == "tipo":
            candidate["value"] = normalize_tipo(candidate.get("value"))

        result["fields"][field_key] = merge_field_sources(
            field_sources=field_sources,
            field_key=field_key,
            current=current,
            candidate=candidate,
            candidate_source=f"RETRY_{field_key}",
        )

    # 6) Aggregate meta (tokens/cost) for the whole screen
    meta_agg = {
        "model_main": MODEL_MAIN,
        "model_anchor": MODEL_ANCHOR,
        "calls": len(attempts_meta),
        "prompt_tokens": sum(int(m.get("prompt_tokens", 0) or 0) for m in attempts_meta),
        "completion_tokens": sum(int(m.get("completion_tokens", 0) or 0) for m in attempts_meta),
        "total_tokens": sum(int(m.get("total_tokens", 0) or 0) for m in attempts_meta),
        "estimated_cost_usd": round(sum(float(m.get("estimated_cost_usd", 0.0) or 0.0) for m in attempts_meta), 6),
        "latency_ms": sum(int(m.get("latency_ms", 0) or 0) for m in attempts_meta),
    }

    result["_attempts"] = attempts_meta
    result["_meta_agg"] = meta_agg
    result["_field_sources"] = field_sources

    # 7) Optional: anchor gate status (useful for routing/review)
    if result["fields"]["ndg"]["value"] is None or result["fields"]["denominazione"]["value"] is None:
        result["_status"] = "ANCHOR_UNCERTAIN"
    else:
        result["_status"] = "OK"

    return result

# ============================================================
# Ground truth loader
# ============================================================
def load_ground_truth(csv_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Supports both:
      - Screenshot, Denominazione da attribuire, Valore rilevato 
      - Fotogramma, Denominazione da attribuire, Valore rilevato 
    (some files may have trailing spaces in column names).
    Returns: { "screen 1": { "NDG": "...", ... }, ... }
    """
    df = pd.read_csv(csv_path)

    # Normalize columns (strip)
    df.columns = [str(c).strip() for c in df.columns]

    # Find screen column
    screen_col = None
    for c in ("Screenshot", "Fotogramma", "Screen", "screen"):
        if c in df.columns:
            screen_col = c
            break
    if screen_col is None:
        raise ValueError(f"Cannot find screen column in CSV. Columns={df.columns.tolist()}")

    # Find value column (some files have a trailing space)
    value_col = None
    for c in ("Valore rilevato", "Valore rilevato ", "Valore", "Value"):
        if c in df.columns:
            value_col = c
            break
    if value_col is None:
        raise ValueError(f"Cannot find value column in CSV. Columns={df.columns.tolist()}")

    key_col = None
    for c in ("Denominazione da attribuire", "Denominazione", "Campo", "Field"):
        if c in df.columns:
            key_col = c
            break
    if key_col is None:
        raise ValueError(f"Cannot find key column in CSV. Columns={df.columns.tolist()}")

    df[screen_col] = df[screen_col].astype(str).str.strip()
    df[key_col] = df[key_col].astype(str).str.strip()
    df[value_col] = df[value_col].astype(str).str.strip()

    gt: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        scr = row[screen_col]
        key = row[key_col]
        val = row[value_col]

        # Skip empty keys
        if key is None or str(key).strip().lower() in ("", "nan", "none"):
            continue
        key = str(key).strip()
        if val is None or str(val).strip().lower() in ("nan",):
            val = ""

        gt.setdefault(scr, {})[key] = val

    return gt

def eval_outputs(outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]]) -> None:
    # Two metrics: raw and filtered (exclude dataset mismatch)
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

            # Normalizzazione numeri per importi
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

def build_debug_report(outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]], out_csv_path: str):
    """
    Debug report with per-(screen, GT-key) rows.
    Uses get_pred_value_for_gt_key() so tabular keys (NDG 1..N etc.) map to soggetti[].
    """
    rows = []
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
# MAIN
# ============================================================
def main():
    client = OpenAI()  # uses OPENAI_API_KEY from env

    if not os.path.exists(GROUND_TRUTH_CSV):
        raise FileNotFoundError(f"Ground truth CSV not found: {GROUND_TRUTH_CSV}")

    gt = load_ground_truth(GROUND_TRUTH_CSV)

    # Infer screenshots from GT if present (supports 5+ screens)
    global SCREENSHOTS
    base_dir = os.getenv('SCREENSHOT_DIR', INPUT_DIR)  # Use INPUT_DIR by default
    SCREENSHOTS = infer_screenshots_from_gt(gt, base_dir=base_dir)

    outputs: Dict[str, Dict[str, Any]] = {}

    def _worker_extract(path: str) -> Tuple[str, Dict[str, Any]]:
        # Create a dedicated client per thread to avoid any thread-safety surprises
        local_client = OpenAI()
        screen_id_local = os.path.splitext(os.path.basename(path))[0]
        return screen_id_local, extract_from_screen(local_client, path)

    existing_paths = [p for p in SCREENSHOTS if os.path.exists(p)]
    missing_paths = [p for p in SCREENSHOTS if not os.path.exists(p)]
    for p in missing_paths:
        print(f"Warning: File not found {p}")

    if PARALLEL_ENABLED and PARALLEL_WORKERS > 1 and len(existing_paths) > 1:
        print(f"Parallel enabled: workers={PARALLEL_WORKERS}, screens={len(existing_paths)}")
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
            futs = {ex.submit(_worker_extract, p): p for p in existing_paths}
            for fut in as_completed(futs):
                p = futs[fut]
                screen_id = os.path.splitext(os.path.basename(p))[0]
                try:
                    sid, out = fut.result()
                    outputs[sid] = out
                    print(f"Done {sid}")
                except Exception as e:
                    print(f"ERROR extracting {screen_id}: {e}")
    else:
        for p in existing_paths:
            screen_id = os.path.splitext(os.path.basename(p))[0]
            print(f"Extracting {screen_id} ...")
            outputs[screen_id] = extract_from_screen(client, p)
    # Save outputs
    outputs_path = os.path.join(INPUT_DIR, "poc_outputs_improved.json")
    with open(outputs_path, "w", encoding="utf-8") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=2)

    # Evaluate & report
    eval_outputs(outputs, gt)

    debug_csv_path = os.path.join(INPUT_DIR, "poc_debug_improved.csv")
    build_debug_report(outputs, gt, debug_csv_path)
    print_cost_summary(outputs)

    print(f"Saved outputs: {outputs_path}")
    print(f"Saved debug report: {debug_csv_path}")
    if DEBUG_SAVE_CROPS:
        print(f"Saved debug crops to: {DEBUG_CROP_DIR}")

if __name__ == "__main__":
    main()


