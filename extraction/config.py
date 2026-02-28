"""Environment configuration, crop constants, and pricing."""

import os
import re
from typing import Dict, Tuple, Any, List, Optional


# ============================================================
# Input / output paths
# ============================================================

DEFAULT_GROUND_TRUTH = "dati.csv"

INPUT_DIR = os.getenv("INPUT_DIR", "mnt/data")
GROUND_TRUTH_CSV = os.path.join(INPUT_DIR, DEFAULT_GROUND_TRUTH)

# ============================================================
# Parallelism & limits
# ============================================================

PARALLEL_WORKERS = int(os.getenv("PARALLEL_WORKERS", "4"))
MAX_CALLS_PER_SCREEN = int(os.getenv("MAX_CALLS_PER_SCREEN", "4"))
STOP_ON_ANCHOR_UNCERTAIN = os.getenv("STOP_ON_ANCHOR_UNCERTAIN", "0") == "1"
PARALLEL_ENABLED = os.getenv("PARALLEL_ENABLED", "1") == "1"

# ============================================================
# Model selection
# ============================================================

MODEL_MAIN = os.getenv("OPENAI_MODEL", "gpt-4o")
MODEL_ANCHOR = os.getenv("OPENAI_MODEL_ANCHOR", MODEL_MAIN)

# ============================================================
# Pricing (USD per 1M tokens)
# ============================================================

PRICING_PER_1M: Dict[str, Dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

# ============================================================
# Crop regions (percentuali — invarianti rispetto a risoluzione/PC)
# ============================================================

# Content crop: rimuove sidebar e topbar browser (tipico)
CONTENT_CROP: Tuple[float, float, float, float] = (0.18, 0.12, 0.98, 0.98)

# Header dentro il contenuto (per NDG / Denominazione)
HEADER_IN_CONTENT: Tuple[float, float, float, float] = (0.00, 0.00, 1.00, 0.22)

# Retry crops mirati (sempre nel sistema di riferimento del CONTENT)
# Nota: sono volutamente "larghi" per essere robusti allo scroll / layout.
FIELD_RETRY_MAP: Dict[str, Tuple[float, float, float, float]] = {
    # Sezione entrate / redditi (tipicamente parte alta centrale)
    "professione_principale": (0.00, 0.12, 1.00, 0.48),
    "numero_mensilita": (0.00, 0.12, 1.00, 0.48),
    "retribuzione_annua_netta": (0.00, 0.12, 1.00, 0.48),
    "tipo_contratto": (0.00, 0.12, 1.00, 0.55),
    "datore_lavoro_anagrafica": (0.18, 0.25, 0.98, 0.62),
    "dal": (0.00, 0.12, 1.00, 0.55),
    # Evidenze/Tipo spesso in griglia "pratiche"
    "tipo": (0.00, 0.00, 1.00, 0.25),
    "evidenze": (0.00, 0.00, 1.00, 0.30),
    # Situazione familiare / note tipicamente più in basso
    "nr_altri_componenti_nucleo_familiare": (0.00, 0.40, 1.00, 0.78),
    "di_cui_percepiscono_reddito": (0.00, 0.40, 1.00, 0.78),
    "importo_totale_annuo_altri_componenti": (0.00, 0.40, 1.00, 0.82),
    "note": (0.00, 0.55, 1.00, 1.00),
}

# ============================================================
# Anchor confidence threshold
# ============================================================

ANCHOR_CONF_MIN = float(os.getenv("ANCHOR_CONF_MIN", "0.95"))

# ============================================================
# Debug
# ============================================================

DEBUG_SAVE_CROPS = os.getenv("DEBUG_SAVE_CROPS", "0") == "1"
DEBUG_CROP_DIR = os.path.join(INPUT_DIR, "debug_crops")


# ============================================================
# Screenshot path helpers (replaces global SCREENSHOTS mutation)
# ============================================================

def get_screenshot_paths(gt: Dict[str, Dict[str, Any]], base_dir: Optional[str] = None) -> List[str]:
    """Build an ordered list of screenshot file paths from GT keys.

    Replaces the old pattern of mutating a global ``SCREENSHOTS`` list.
    """
    if base_dir is None:
        base_dir = os.getenv("SCREENSHOT_DIR", INPUT_DIR)

    names = sorted(gt.keys(), key=lambda s: (re.sub(r"\D+", "", s) or "0", s))
    paths: List[str] = []
    for name in names:
        candidate = (
            os.path.join(base_dir, f"{name}.png")
            if not name.lower().endswith(".png")
            else os.path.join(base_dir, name)
        )
        if os.path.exists(candidate):
            paths.append(candidate)
            continue
        candidate2 = os.path.join(base_dir, name)
        if os.path.exists(candidate2):
            paths.append(candidate2)
            continue
        # Not found — still append canonical path for visibility
        paths.append(os.path.join(base_dir, f"{name}.png"))
    return paths
