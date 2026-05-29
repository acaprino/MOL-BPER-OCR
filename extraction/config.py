"""Configuration constants and environment variable handling."""
import os
from typing import Dict, Any, List

# ============================================================
# Pathing & IO
# ============================================================
INPUT_DIR = os.getenv("INPUT_DIR", "mnt/data").strip()
GROUND_TRUTH_CSV = os.path.join(INPUT_DIR, "dati.csv")

PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS", "4"))
PARALLEL_ENABLED = os.getenv("PARALLEL_ENABLED", "1").strip() == "1"

# ============================================================
# Model Config
# ============================================================
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o").strip()
LLM_MODEL_ANCHOR = os.getenv("LLM_MODEL_ANCHOR", LLM_MODEL).strip()
LLM_THINKING_LEVEL = os.getenv("LLM_THINKING_LEVEL", "").strip().lower()

PROVIDER_MODELS = {
    "openai": ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"],
    "gemini": [
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-exp",
        "gemini-2.0-flash-thinking-exp",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
    ],
}

# Pricing (USD per 1M tokens)
PRICING_PER_1M = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "o1": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 1.10, "output": 4.40},
    "gemini-1.5-pro": {"input": 1.25, "output": 3.75},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-exp": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-thinking-exp": {"input": 0.10, "output": 0.40},
    "gemini-3-flash-preview": {"input": 0.10, "output": 0.40},
    "gemini-3.1-flash-lite-preview": {"input": 0.25, "output": 1.50},
}

# ============================================================
# Extraction Logic Config
# ============================================================
MAX_CALLS_PER_SCREEN = int(os.getenv("MAX_CALLS_PER_SCREEN", "4"))
STOP_ON_ANCHOR_UNCERTAIN = os.getenv("STOP_ON_ANCHOR_UNCERTAIN", "0") == "1"
ANCHOR_CONF_MIN = float(os.getenv("ANCHOR_CONF_MIN", "0.95"))

# Crops (relative coordinates 0.0-1.0: left, top, right, bottom)
CONTENT_CROP = (0.18, 0.12, 0.98, 0.98)
HEADER_IN_CONTENT = (0.00, 0.00, 1.00, 0.22)

# Retry crops mirati (raggruppati per aree funzionali)
RETRY_AREAS = {
    "HEADER": (0.00, 0.00, 1.00, 0.35),  # ndg, den, tipo, stato, fase, evidenze
    "BODY": (0.00, 0.25, 1.00, 0.75),    # fidi, garanzie, soggetti
    "FOOTER": (0.00, 0.65, 1.00, 1.00),  # note_della_richiesta
}

AREA_TO_FIELDS = {
    "HEADER": ["ndg", "denominazione", "tipo", "stato", "fase", "evidenze", "filiale_relazione", "ultima_validazione_scheda"],
    "BODY": [
        "n_fido", "rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op",
        "ndg_1", "denominazione_1", "ruolo_1",
        "ndg_2", "denominazione_2", "ruolo_2",
        "ndg_3", "denominazione_3", "ruolo_3",
        "ndg_4", "denominazione_4", "ruolo_4",
        "professione_principale", "retribuzione_annua_netta", "tipo_contratto", "numero_mensilita",
        "dal", "datore_di_lavoro_anagrafica", "rating_ufficiale", "score_cgs",
        "nr_altri_componenti_nucleo", "di_cui_percepiscono_reddito", "importo_totale_annuo_nucleo"
    ],
    "FOOTER": ["note_della_richiesta", "note_scheda_privati"]
}

# Map fields to their retry areas
FIELD_RETRY_MAP: Dict[str, str] = {}
for area, fields in AREA_TO_FIELDS.items():
    for f in fields:
        FIELD_RETRY_MAP[f] = area


# Debug
DEBUG_MODE = os.getenv("DEBUG_MODE", "0").strip() == "1"
DEBUG_SAVE_CROPS = os.getenv("DEBUG_SAVE_CROPS", "0") == "1"
DEBUG_CROP_DIR = os.path.join(INPUT_DIR, "debug_crops")

# ============================================================
# Helpers
# ============================================================
def get_screenshot_paths(gt: Dict[str, Any], base_dir: str = ".") -> List[str]:
    import re
    names = sorted(gt.keys(), key=lambda s: (re.sub(r"\D+", "", s) or "0", s))
    paths = []
    for name in names:
        ext = os.path.splitext(name)[1].lower()
        if ext in (".png", ".jpg", ".jpeg"):
            paths.append(os.path.join(base_dir, name))
        else:
            paths.append(os.path.join(base_dir, f"{name}.png"))
    return paths
