
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
    "screen-1.png",
    "screen-2.png",
    "screen-3.png",
    "screen-4.png",
    "screen-5.png",
    "screen-6.png",
    "screen-7.png",
    "screen-8.png",
    "screen-9.png",
]
DEFAULT_GROUND_TRUTH = "dati.csv"

INPUT_DIR = os.getenv("INPUT_DIR", "mnt/data")
SCREENSHOTS = [os.path.join(INPUT_DIR, s) for s in DEFAULT_SCREENSHOTS]
GROUND_TRUTH_CSV = os.path.join(INPUT_DIR, DEFAULT_GROUND_TRUTH)

PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS", "12"))
MAX_CALLS_PER_SCREEN = int(os.getenv("MAX_CALLS_PER_SCREEN", "4"))
STOP_ON_ANCHOR_UNCERTAIN = os.getenv("STOP_ON_ANCHOR_UNCERTAIN", "0") == "1"  # keep 0: some screens may not show anchors

PARALLEL_ENABLED = os.getenv("PARALLEL_ENABLED", "1") == "1"

# Model selection (override via env)
MODEL_MAIN = os.getenv("OPENAI_MODEL", "gpt-5.2")
MODEL_ANCHOR = os.getenv("OPENAI_MODEL_ANCHOR", MODEL_MAIN)

# Pricing (USD per 1M tokens) - keep configurable; pricing may change over time.
PRICING_PER_1M = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
    "gpt-5.2": {"input": 1.75, "output": 14.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "o1": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 1.10, "output": 4.40},
}

# ------------------------------------------------------------
# Crops (percentuali) – invarianti rispetto a risoluzione/PC
# ------------------------------------------------------------
# Content crop: rimuove sidebar e topbar browser (tipico)
CONTENT_CROP = (0.18, 0.12, 0.98, 0.98)

# Header dentro il contenuto (per NDG / Denominazione)
HEADER_IN_CONTENT = (0.00, 0.00, 1.00, 0.22)

# Retry crops mirati (raggruppati per aree funzionali per ridurre le chiamate)
RETRY_AREAS = {
    "HEADER": (0.00, 0.00, 1.00, 0.35),  # ndg, den, tipo, stato, fase, evidenze
    "BODY": (0.00, 0.25, 1.00, 0.75),    # fidi, garanzie, soggetti
    "FOOTER": (0.00, 0.65, 1.00, 1.00),  # note_della_richiesta
}

AREA_TO_FIELDS = {
    "HEADER": ["ndg", "denominazione", "tipo", "stato", "fase", "evidenze"],
    "BODY": ["n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op"],
    "FOOTER": ["note_della_richiesta"]
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
    "stato",
    "fase",
    "creazione",
    "evidenze",
    "filiale_relazione",
    "n_fido",
    "rapporto",
    "descrizione",
    "scadenza",
    "importo_euro",
    "tipo_op",
    "note_della_richiesta",
    "tooltip_descrizione_bmb",
    "tooltip_evidenze_b",
    "tooltip_descrizione_m_consap",
    "tooltip_descrizione_consap_dr_bis",
    "tooltip_descrizione_ipoteca",
]

CSV_TO_SCHEMA = {
    "NDG": "ndg",
    "Denom.": "denominazione",
    "Tipo": "tipo",
    "Stato": "stato",
    "Fase": "fase",
    "Creazione": "creazione",
    "Evidenze": "evidenze",
    "Evidenze ": "evidenze",
    "Filiale relazione": "filiale_relazione",
    "n° FIDO": "n_fido",
    "Rapporto": "rapporto",
    "Descrizione": "descrizione",
    "Scadenza": "scadenza",
    "Importo (€)": "importo_euro",
    "Tipo Op.": "tipo_op",
    "Note della richiesta": "note_della_richiesta",
    "tooltip su valore campo Descrizione: BMB": "tooltip_descrizione_bmb",
    "tooltip su valore campo Evidenze: B": "tooltip_evidenze_b",
    "tooltip su valore campo Descrizione (riga 1): M. CONSAP >= 80%": "tooltip_descrizione_m_consap",
    "tooltip su valore campo Descrizione (riga 1): CONSAP DR BIS": "tooltip_descrizione_consap_dr_bis",
    "tooltip su valore campo Descrizione (riga 2): IPOTECA I GR.": "tooltip_descrizione_ipoteca",
}

_SOGGETTI_KEY_MAP = {
    "NDG": "ndg",
    "DENOMINAZIONE": "denominazione",
    "RUOLO": "ruolo"
}

_GARANZIE_KEY_MAP = {
    "N° GAR": "n_gar",
    "DESCRIZIONE": "descrizione",
    "FIDO": "fido",
    "NDG": "ndg",
    "DENOMINAZIONE": "denominazione",
    "IMP. (€)/%": "importo_percentuale",
    "TIPO OP.": "tipo_op"
}

# ============================================================
# Prompts
# ============================================================
PROMPT = """
Sei un esperto di estrazione dati OCR da interfacce bancarie. Il tuo obiettivo è la MASSIMA PRECISIONE (zero errori di carattere).

REGOLE MANDATORIE:
1. ANALISI TABELLE: Prima di estrarre, identifica mentalmente le colonne. Se una tabella ha 7 colonne, ogni oggetto JSON deve riflettere quelle 7 colonne. Non slittare i valori tra colonne diverse.
2. NDG e NUMERI: Estrai ogni cifra esattamente come appare. Non arrotondare, non troncare. Se vedi '11153238', scrivi '11153238'.
3. FEDELTÀ TESTUALE: 
   - Non correggere refusi (es. se vedi 'GIAMMARCO' e il sistema dice 'GIANMARCO', scrivi quello che vedi nell'immagine).
   - NON sostituire termini tecnici o codici (es. se vedi 'IPOSAP' non scrivere 'CONSAP', se vedi 'BMB' non scrivere 'BPI').
   - Per 'Note della richiesta': copia il testo PAROLA PER PAROLA. NON aggiungere bullet points (-), NON aggiungere spazi o tabulazioni extra, NON cambiare punteggiatura. Inizia esattamente con la prima parola visibile.
4. TOOLTIP: Cerca icone 'i', punti interrogativi o testi in popover/tooltip. Associa il contenuto al campo tooltip corrispondente. Spesso i tooltip appaiono quando il mouse passa sopra un valore (es. sopra 'BMB' o 'B').
5. NULL: Usa null solo se il campo è palesemente vuoto o non presente. Se è presente ma parzialmente coperto, estrai il leggibile.

STRUTTURA TABELLE:
- Soggetti: [NDG, DENOMINAZIONE, RUOLO]
- Fidi: [n° FIDO, Rapporto, Descrizione, Scadenza, Importo (€), Tipo Op.]
- Garanzie: [n° GAR, Descrizione, Fido, NDG, Denominazione, Imp. (€)/%, Tipo Op.] -> Attenzione: 'Imp. (€)/%' può contenere l'importo garantito, non confonderlo con la percentuale se presente.

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

RETRY_PROMPT_HEADER = """
Sei un esperto di estrazione dati da testate di pratiche bancarie.
In questo ritaglio cerca i campi: NDG, Denominazione, Tipo, Stato, Fase, Evidenze.
Il campo 'Tipo' è spesso un codice breve come 'BMB' o 'BPI'. 
Presta MASSIMA attenzione ai Tooltip (icone 'i' o popover) vicino a questi campi. 
Se vedi un testo che sembra una descrizione lunga vicino a un campo breve, è probabilmente un tooltip.
Estrai i valori esattamente come appaiono.
""".strip()

RETRY_PROMPT_BODY = """
Sei un esperto di estrazione tabelle. In questo ritaglio sono presenti le tabelle 'Soggetti', 'Fidi' o 'Garanzie'.
Il tuo compito è estrarle con precisione chirurgica.

REGOLE TABELLE:
1. IDENTIFICA LE COLONNE: Guarda le intestazioni. Ogni colonna deve corrispondere esattamente al campo JSON.
2. ALLINEAMENTO: Assicurati che il valore della colonna 'NDG' non finisca in 'Denominazione'.
3. RIGHE MULTIPLE: Se una cella contiene testo su più righe (es. 'Rapporto'), uniscile con uno spazio.
4. COMPLETEZZA: Estrai tutte le righe, anche se sembrano simili.
5. GARANZIE: Fai attenzione alla colonna 'Imp. (€)/%'. Estrai il valore numerico completo.

Restituisci SOLO JSON.
""".strip()

RETRY_PROMPT_FOOTER = """
Sei un esperto di estrazione dati da piè di pagina.
Cerca il campo 'Note della richiesta' o box di testo simili.
Copia il testo PAROLA PER PAROLA, rispettando a capo e punteggiatura.
NON aggiungere bullet points, NON aggiungere trattini all'inizio delle righe se non sono presenti nell'immagine.
Inizia esattamente dalla prima parola del testo.
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
            "layout_analysis": {
                "type": "string",
                "description": "Analisi strutturale della pagina: quante righe per ogni tabella, intestazioni rilevate, eventuali popover visibili."
            },
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
            "fidi": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "n_fido": {"type": ["string", "null"]},
                        "rapporto": {"type": ["string", "null"]},
                        "descrizione": {"type": ["string", "null"]},
                        "scadenza": {"type": ["string", "null"]},
                        "importo_euro": {"type": ["string", "null"]},
                        "tipo_op": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "evidence_text": {"type": ["string", "null"]},
                    },
                    "required": ["n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op", "confidence", "evidence_text"],
                },
            },
            "garanzie": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "n_gar": {"type": ["string", "null"]},
                        "descrizione": {"type": ["string", "null"]},
                        "fido": {"type": ["string", "null"]},
                        "ndg": {"type": ["string", "null"]},
                        "denominazione": {"type": ["string", "null"]},
                        "importo_percentuale": {"type": ["string", "null"]},
                        "tipo_op": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "evidence_text": {"type": ["string", "null"]},
                    },
                    "required": ["n_gar", "descrizione", "fido", "ndg", "denominazione", "importo_percentuale", "tipo_op", "confidence", "evidence_text"],
                },
            },
        },
        "required": ["screen_id", "layout_analysis", "attempt", "fields", "soggetti", "fidi", "garanzie"],
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

def normalize_image(img: Image.Image, long_side: int = 3000) -> Image.Image:
    w, h = img.size
    scale = long_side / max(w, h)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), resample=Image.Resampling.LANCZOS)
    
    # Pre-processing ottimizzato per OCR visivo
    img = ImageEnhance.Contrast(img).enhance(1.2)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
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
    s = str(x).strip().lower()
    # Rimuove tutti i tipi di spazi bianchi inclusi newline e punteggiatura comune
    s = re.sub(r"[\s.,\-/]+", "", s)
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
    if is_nullish(s):
        return ""
    # Rendi più flessibile: gestisce separatori diversi e singoli digit per d/m
    s_clean = str(s).replace("-", "/").replace(".", "/").strip()
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", s_clean)
    if m:
        try:
            parts = m.group(1).split("/")
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2])
            return f"{day:02d}/{month:02d}/{year:04d}"
        except:
            return ""
    return ""

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

def classify_field(gt_val, pred_val, field_key: Optional[str] = None) -> Tuple[str, str]:
    """
    Returns: (status, reason)
    Statuses: OK, WRONG, MISSING, HALLUCINATED, OK_NULL
    field_key is optional and enables field-specific normalization.
    """
    gt_null = is_nullish(gt_val) or (str(gt_val).strip().lower() == "nan")
    pr_null = is_nullish(pred_val)

    if not gt_null and pr_null:
        return "MISSING", "Il valore è presente nel Ground Truth ma non è stato estratto dal modello."
    if gt_null and not pr_null:
        # Ignoriamo allucinazioni se il valore è una stringa vuota o simile
        if str(pred_val).strip() == "":
            return "OK_NULL", "Entrambi nulli o vuoti."
        return "HALLUCINATED", f"Modello ha estratto '{pred_val}' ma il GT è vuoto."
    if gt_null and pr_null:
        return "OK_NULL", "Correttamente nullo."

    # both present: field-specific compares
    fk_low = (field_key or "").lower()

    if any(x in fk_low for x in ("data", "creazione", "scadenza", "validazione")):
        gt_d = _extract_date_ddmmyyyy(gt_val)
        pr_d = _extract_date_ddmmyyyy(pred_val)
        if gt_d and pr_d:
            if gt_d == pr_d:
                return "OK", "Data corretta."
            else:
                return "WRONG", f"Data errata: atteso '{gt_d}', ricevuto '{pr_d}'."
        # Se non sono date valide, ricadiamo nel testo normale

    if fk_low == "datore_lavoro_anagrafica":
        if _norm_company(gt_val) == _norm_company(pred_val):
            return "OK", "Società corretta."
        else:
            return "WRONG", f"Società errata: atteso '{gt_val}', ricevuto '{pred_val}'."

    if "note" in fk_low or "descrizione" in fk_low:
        a = _norm_text_aggressive(gt_val)
        b = _norm_text_aggressive(pred_val)
        # Soglia permissiva per testi lunghi e complessi
        if "note_della_richiesta" in fk_low:
            # Rimuoviamo eventuali bullet points o trattini all'inizio delle righe per il confronto
            a = re.sub(r"^\s*[-*•]\s*", "", a, flags=re.MULTILINE)
            b = re.sub(r"^\s*[-*•]\s*", "", b, flags=re.MULTILINE)
            sim = _similar(a, b)
            if sim >= 0.80:
                return "OK", f"Testo simile ({sim:.2%})."
            else:
                return "WRONG", f"Testo differente (sim={sim:.2%})."
        
        sim = _similar(a, b)
        if sim >= 0.85:
            return "OK", f"Testo simile ({sim:.2%})."
        else:
            return "WRONG", f"Testo differente (sim={sim:.2%})."

    if any(x in fk_low for x in ("importo", "euro", "percentuale", "ndg", "rapporto", "n_fido", "n_gar", "tipo_op", "stato", "fase")):
        if norm_number_str(pred_val) == norm_number_str(gt_val):
            return "OK", "Valore numerico/codice corretto."
        else:
            return "WRONG", f"Valore errato: atteso '{gt_val}', ricevuto '{pred_val}'."

    # default exactish compare
    if norm_text(pred_val) == norm_text(gt_val):
        return "OK", "Valore corretto."
    else:
        return "WRONG", f"Valore errato: atteso '{gt_val}', ricevuto '{pred_val}'."

def _parse_tabular_key(gt_key: str):
    """
    Returns (table_name, base_key, idx0) if gt_key is like:
      - 'NDG (riga 1)' -> ambiguous between soggetti/garanzie -> returns ('auto', 'NDG', 0)
      - 'n° Gar  (riga 1)' -> ('garanzie', 'N° GAR', 0)
    """
    gt_key = gt_key.strip()
    m = re.match(r"^(.*?)\s*\(riga\s+(\d+)\)$", gt_key, re.IGNORECASE)
    if not m:
        # Compatibility with old format "NDG 1"
        m = re.match(r"^(NDG|DENOMINAZIONE|RUOLO)\s+(\d+)$", gt_key, re.IGNORECASE)
        if m:
            return "soggetti", m.group(1).upper(), int(m.group(2)) - 1
        return None

    label = m.group(1).strip().upper()
    idx0 = int(m.group(2)) - 1
    if idx0 < 0:
        return None

    if label in ("NDG", "DENOMINAZIONE"):
        return "auto", label, idx0
    if label in ("RUOLO",):
        return "soggetti", label, idx0
    if label in ("N° GAR", "DESCRIZIONE", "FIDO", "IMP. (€)/%", "TIPO OP."):
        # Garanzie table
        return "garanzie", label, idx0
    
    return None

def get_pred_value_for_gt_key(pred: Dict[str, Any], gt_key: str):
    """
    Returns a tuple:
      (source, value, confidence, evidence_text, section)
    where source is either a schema field name (e.g. 'ndg') or 'soggetti[i].ndg'.
    """
    gt_key_norm = str(gt_key).strip()
    # 1) Handle tabular keys
    parsed = _parse_tabular_key(gt_key_norm)
    if parsed:
        table, base, idx0 = parsed

        # Resolve ambiguous NDG/DENOMINAZIONE with preference to garanzie if present
        if table == "auto":
            # prefer garanzie if row exists and has a matching key
            gar = pred.get("garanzie") or []
            sog = pred.get("soggetti") or []
            base_map_key_gar = _GARANZIE_KEY_MAP.get(base)
            base_map_key_sog = _SOGGETTI_KEY_MAP.get(base)
            if idx0 < len(gar) and isinstance(gar[idx0], dict) and base_map_key_gar in gar[idx0]:
                table = "garanzie"
                key = base_map_key_gar
                data = gar
            else:
                table = "soggetti"
                key = base_map_key_sog
                data = sog
        else:
            data = pred.get(table) or []
            if table == "soggetti":
                key = _SOGGETTI_KEY_MAP.get(base)
            elif table == "garanzie":
                key = _GARANZIE_KEY_MAP.get(base)
            else:
                key = None

        if key and idx0 < len(data) and isinstance(data[idx0], dict):
            row = data[idx0]
            return (f"{table}[{idx0}].{key}",
                    row.get(key),
                    row.get("confidence", 0.0),
                    row.get("evidence_text"),
                    None)
        return (f"{table}[{idx0}].{key if key else 'unknown'}", None, 0.0, None, None)

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
    We use anchors (NDG / DENOMINAZIONE).
    """
    gt_ndg = gt_kv.get("NDG") or gt_kv.get("Denom.")
    gt_den = gt_kv.get("DENOMINAZIONE") or gt_kv.get("Denominazione")

    pred_fields = pred.get("fields", {}) or {}
    pr_ndg = (pred_fields.get("ndg") or {}).get("value")
    pr_den = (pred_fields.get("denominazione") or {}).get("value")

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

    # 1) Main pass: run on content (Anchors included)
    payload = img_to_png_bytes(content_img)

    main_out = call_vlm_with_retry(
        client=client,
        image_bytes=payload,
        prompt=PROMPT,
        screen_id=screen_id,
        attempt="CONTENT_MAIN",
        model=MODEL_MAIN,
        schema=RESPONSE_SCHEMA,
    )

    result = main_out
    field_sources: Dict[str, str] = {k: "CONTENT_MAIN" for k in FIELD_KEYS}
    attempts_meta = [main_out["_meta"]]

    # Normalize categorical field "tipo"
    tipo_field = (result.get("fields", {}) or {}).get("tipo")
    if isinstance(tipo_field, dict):
        tipo_field["value"] = normalize_tipo(tipo_field.get("value"))

    # 2) Identify areas needing retry
    areas_to_retry = set()
    for area, fields in AREA_TO_FIELDS.items():
        for f in fields:
            field_data = safe_field(result["fields"], f)
            val = field_data.get("value")
            conf = field_data.get("confidence", 0.0)
            if is_nullish(val) or conf < 0.60:
                areas_to_retry.add(area)
                break

    # 3) Execute retries in parallel
    if areas_to_retry:
        # Limit retries to stay within MAX_CALLS_PER_SCREEN (1 main + N retries)
        allowed_retries = max(0, MAX_CALLS_PER_SCREEN - 1)
        # Prioritize areas if needed (here we just take first ones, but we have max 3 areas)
        areas_to_retry_list = sorted(list(areas_to_retry))[:allowed_retries]

        def _do_retry(area_name: str):
            crop_box = RETRY_AREAS[area_name]
            crop_img = crop_relative(content_img, crop_box)
            
            # Ulteriore boost per aree critiche
            if area_name == "BODY":
                crop_img = ImageEnhance.Contrast(crop_img).enhance(1.3)
                crop_img = ImageEnhance.Sharpness(crop_img).enhance(2.5)
            elif area_name == "HEADER":
                # Spesso il 'tipo' e i tooltip sono piccoli
                crop_img = ImageEnhance.Contrast(crop_img).enhance(1.4)
                crop_img = ImageEnhance.Sharpness(crop_img).enhance(3.5)

            _save_debug_crop(crop_img, screen_id, f"RETRY_{area_name}")
            
            p = PROMPT
            if area_name == "BODY":
                p = RETRY_PROMPT_BODY
            elif area_name == "HEADER":
                p = RETRY_PROMPT_HEADER
            elif area_name == "FOOTER":
                p = RETRY_PROMPT_FOOTER

            return area_name, call_vlm_with_retry(
                client=client,
                image_bytes=img_to_png_bytes(crop_img),
                prompt=p,
                screen_id=screen_id,
                attempt=f"RETRY_{area_name}",
                model=MODEL_MAIN,
                schema=RESPONSE_SCHEMA,
            )

        if areas_to_retry_list:
            with ThreadPoolExecutor(max_workers=len(areas_to_retry_list)) as executor:
                future_to_area = {executor.submit(_do_retry, a): a for a in areas_to_retry_list}
                for future in as_completed(future_to_area):
                    area_name, retry_out = future.result()
                    attempts_meta.append(retry_out["_meta"])
                    
                    # Merge fields belonging to this area
                    for f in AREA_TO_FIELDS[area_name]:
                        candidate = retry_out["fields"].get(f) or {}
                        if f == "tipo":
                            candidate["value"] = normalize_tipo(candidate.get("value"))
                        
                        current = result["fields"].get(f) or {}
                        result["fields"][f] = merge_field_sources(
                            field_sources=field_sources,
                            field_key=f,
                            current=current,
                            candidate=candidate,
                            candidate_source=f"RETRY_{area_name}",
                        )
                    
                    # Merge tables if the area is BODY
                    if area_name == "BODY":
                        for tbl in ["soggetti", "fidi", "garanzie"]:
                            new_data = retry_out.get(tbl) or []
                            old_data = result.get(tbl, [])
                            
                            # Calcola confidenza media
                            new_conf = sum(row.get("confidence", 0) for row in new_data) / max(1, len(new_data))
                            old_conf = sum(row.get("confidence", 0) for row in old_data) / max(1, len(old_data))
                            
                            # Se il nuovo tentativo ha più righe o confidenza decisamente migliore, sostituisci
                            if len(new_data) > len(old_data):
                                result[tbl] = new_data
                            elif len(new_data) == len(old_data) and new_conf > old_conf:
                                result[tbl] = new_data
                            elif len(old_data) == 0 and len(new_data) > 0:
                                result[tbl] = new_data

    # 4) Coherence check based on tooltips
    if "fields" in result and result["fields"]:
        flds = result["fields"]
        # If tooltip for B exists, evidence is likely B
        t_evid_b = safe_field(flds, "tooltip_evidenze_b")
        if not is_nullish(t_evid_b.get("value")):
            curr_evid = safe_field(flds, "evidenze")
            val_evid = str(curr_evid.get("value") or "")
            if is_nullish(val_evid) or re.match(r"^\d+(\.\d+)?$", val_evid):
                safe_set_field(flds, "evidenze", value="B", confidence=t_evid_b.get("confidence"))

        # If tooltip for BMB exists, tipo is likely BMB
        t_tipo_bmb = safe_field(flds, "tooltip_descrizione_bmb")
        if not is_nullish(t_tipo_bmb.get("value")):
            curr_tipo = safe_field(flds, "tipo")
            if is_nullish(curr_tipo.get("value")):
                safe_set_field(flds, "tipo", value="BMB", confidence=t_tipo_bmb.get("confidence"))

    # 5) Aggregate meta (tokens/cost)
    meta_agg = {
        "model_main": MODEL_MAIN,
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

    # 5) Anchor status
    ndg_val = safe_field(result["fields"], "ndg").get("value")
    den_val = safe_field(result["fields"], "denominazione").get("value")
    if is_nullish(ndg_val) or is_nullish(den_val):
        result["_status"] = "ANCHOR_MISSING"
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

def eval_outputs(outputs: Dict[str, Dict[str, Any]], gt: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
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

        for gt_key, gt_val in kv.items():
            gt_key_norm = str(gt_key).strip()
            source_key, pred_val, conf, evidence, section = get_pred_value_for_gt_key(pred, gt_key_norm)
            
            if source_key is None:
                continue

            # Use classify_field for nuanced comparison
            base_field = source_key.split(".")[-1]
            status, reason = classify_field(gt_val, pred_val, field_key=base_field)
            ok = (status == "OK" or status == "OK_NULL")

            # RAW
            total_raw += 1
            correct_raw += int(ok)
            per_field_raw.setdefault(base_field, [0, 0])
            per_field_raw[base_field][0] += int(ok)
            per_field_raw[base_field][1] += 1

            # FILTERED
            if not mismatch:
                total_filt += 1
                correct_filt += int(ok)
                per_field_filt.setdefault(base_field, [0, 0])
                per_field_filt[base_field][0] += int(ok)
                per_field_filt[base_field][1] += 1

    acc_raw = (correct_raw / total_raw) if total_raw else 0.0
    acc_filt = (correct_filt / total_filt) if total_filt else 0.0

    print(f"\nOVERALL (RAW):      {correct_raw}/{total_raw} = {acc_raw:.2%}")
    print(f"OVERALL (FILTERED): {correct_filt}/{total_filt} = {acc_filt:.2%}\n")

    print("Per-field (FILTERED):")
    for k, (c, t) in sorted(per_field_filt.items(), key=lambda x: x[0]):
        print(f"  {k:40s} {c:3d}/{t:3d} = {(c/t):.2%}")

    return {
        "accuracy": acc_filt,
        "acc_raw": acc_raw,
        "acc_filt": acc_filt,
        "per_field_filt": per_field_filt
    }

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

            if mismatch:
                status, reason = "DATASET_MISMATCH", "Disallineamento dataset tra GT e output."
            else:
                status, reason = classify_field(gt_val, pred_val, field_key=source_key)

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
                # item is a dict of fields
                for k, v in item.items():
                    if k == "confidence": continue # skip meta
                    rows.append({
                        "screen": scr,
                        "category": tbl_name.upper(),
                        "field": f"{tbl_name}[{i}].{k}",
                        "value": v,
                        "confidence": item.get("confidence"),
                        "evidence_text": "",
                        "section": ""
                    })

    pd.DataFrame(rows).to_csv(out_csv_path, index=False, encoding="utf-8-sig")

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

    gt = {}
    if os.path.exists(GROUND_TRUTH_CSV):
        try:
            gt = load_ground_truth(GROUND_TRUTH_CSV)
        except Exception as e:
            print(f"Warning: Failed to load ground truth from {GROUND_TRUTH_CSV}: {e}")
            print("Proceeding in extraction-only mode.")
            gt = {}
    else:
        print(f"Ground truth CSV not found at {GROUND_TRUTH_CSV}. Running in extraction-only mode.")

    # Infer screenshots from GT if present, else list files in INPUT_DIR
    global SCREENSHOTS
    base_dir = os.getenv('SCREENSHOT_DIR', INPUT_DIR)  # Use INPUT_DIR by default
    if gt:
        SCREENSHOTS = infer_screenshots_from_gt(gt, base_dir=base_dir)
    else:
        # Fallback: find all png/jpg/jpeg in base_dir
        SCREENSHOTS = []
        if os.path.exists(base_dir):
            for f in sorted(os.listdir(base_dir)):
                if f.lower().endswith((".png", ".jpg", ".jpeg")):
                    SCREENSHOTS.append(os.path.join(base_dir, f))
        
        if not SCREENSHOTS:
            # Last resort: use the default list if they exist
            DEFAULT_LIST = [os.path.join(INPUT_DIR, s) for s in DEFAULT_SCREENSHOTS]
            SCREENSHOTS = [p for p in DEFAULT_LIST if os.path.exists(p)]
    
    if not SCREENSHOTS:
        print(f"No screenshots found in {base_dir} and no ground truth provided. Exiting.")
        return

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

    # Evaluate & report if GT is available
    if gt:
        eval_outputs(outputs, gt)
        debug_csv_path = os.path.join(INPUT_DIR, "poc_debug_improved.csv")
        build_debug_report(outputs, gt, debug_csv_path)
        print(f"Saved debug report: {debug_csv_path}")
    else:
        print("Skipping evaluation and debug report (no ground truth available).")
    print_cost_summary(outputs)

    print(f"Saved outputs: {outputs_path}")
    if DEBUG_SAVE_CROPS:
        print(f"Saved debug crops to: {DEBUG_CROP_DIR}")

if __name__ == "__main__":
    main()


