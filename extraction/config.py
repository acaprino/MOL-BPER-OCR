"""Configuration constants and environment variable handling."""
import os

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
        "gemini-3.6-flash",
        "gemini-3.8-flash",
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
    # Prezzo introduttivo fino al 2026-12-31; dal 2027-01-01 diventa 1.50/7.50
    "gemini-3.6-flash": {"input": 0.75, "output": 3.75},
    # Stesso listino introduttivo: 0.75/3.75 fino al 2026-12-31, dal 2027-01-01 1.50/7.50
    # (https://ai.google.dev/gemini-api/docs/pricing, verificato il 2026-09-29)
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75},
}

# ============================================================
# Extraction Logic Config
# ============================================================
STOP_ON_ANCHOR_UNCERTAIN = os.getenv("STOP_ON_ANCHOR_UNCERTAIN", "0") == "1"
ANCHOR_CONF_MIN = float(os.getenv("ANCHOR_CONF_MIN", "0.95"))
# Confidence below which a field marks its area for a retry pass.
RETRY_CONF_MIN = float(os.getenv("RETRY_CONF_MIN", "0.60"))

# Upper bound on the long side of an image entering extract_from_image().
# The CLI path already normalizes to 1800px; this only clamps oversized raw
# frames on the edge-agent path so a full-resolution capture cannot blow up
# image-token cost and payload size. Purely dimensional (no enhancement).
MAX_IMAGE_LONG_SIDE = int(os.getenv("MAX_IMAGE_LONG_SIDE", "2000"))

# Crops (relative coordinates 0.0-1.0: left, top, right, bottom)
#
# These fractions are calibrated on the 848x679 window screenshots in mnt/data:
# 0.18 on the left is the navigator's share of THAT window's width. The navigator
# is laid out in CSS pixels, so on a wider window its share shrinks and 0.18 cuts
# into the first table columns. Measured on a real 1536x1032 capture: the crop's
# left edge landed at x=276, past the NDG, Denom., Tipo and Importo columns, and
# NDG 32084406 was extracted as "06". select_content_crop() therefore applies the
# crop only when the framing matches the calibration (see imaging.py).
CONTENT_CROP = (0.18, 0.12, 0.98, 0.98)
# Nominal figure: the references actually span 846x677 to 850x680 (ADR 0001
# generalized "848x679" from one file); the spread is absorbed by the tolerance.
CONTENT_CROP_CALIBRATED_ASPECT = 848 / 679
# Tight on purpose: every validated framing shares one aspect, and the two failure
# modes are asymmetric. Cropping an uncalibrated frame silently destroys fields;
# not cropping a calibrated one only costs image tokens.
CONTENT_CROP_ASPECT_TOLERANCE = 0.05
# Aspect alone is not identity: 1280x1024 (5:4, a standard legacy full-screen
# resolution) sits 0.09% from 848/679 and would pass any aspect tolerance. The
# references are 846-850 px wide and normalize_image() never upscales, so an
# image outside this size band cannot be one of them, whatever its aspect.
CONTENT_CROP_LONG_SIDE_RANGE = (800, 900)
HEADER_IN_CONTENT = (0.00, 0.00, 1.00, 0.22)

# Targeted retry crops (grouped by functional area)
RETRY_AREAS = {
    "HEADER": (0.00, 0.00, 1.00, 0.35),  # ndg, den, tipo, stato, fase, evidenze
    "BODY": (0.00, 0.25, 1.00, 0.75),    # fidi, garanzie, soggetti
    "FOOTER": (0.00, 0.65, 1.00, 1.00),  # note_della_richiesta
}

# Declaration order defines retry priority (most important first): the pipeline
# retries weak areas in this order under the per-screen call budget, so HEADER
# must stay first. Do not alphabetize.
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

# 1 anchor + 1 main + one retry per declared area. Derived, not a literal: the
# retry budget is spent in AREA_TO_FIELDS order, so anything below this leaves
# the trailing areas structurally unreachable. A page that shows a single
# section (e.g. Note da Richiesta) makes every *other* area look weak, since
# their fields legitimately are not there, and those areas would consume the
# whole budget before the one holding the page's payload is ever retried.
MAX_CALLS_PER_SCREEN = int(
    os.getenv("MAX_CALLS_PER_SCREEN", str(2 + len(AREA_TO_FIELDS)))
)


# Debug
DEBUG_MODE = os.getenv("DEBUG_MODE", "0").strip() == "1"
DEBUG_SAVE_CROPS = os.getenv("DEBUG_SAVE_CROPS", "0") == "1"
DEBUG_CROP_DIR = os.path.join(INPUT_DIR, "debug_crops")
