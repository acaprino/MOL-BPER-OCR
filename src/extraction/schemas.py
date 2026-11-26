"""Pydantic models for structured VLM output (used by LangChain .with_structured_output())."""
import math
from typing import Optional, List, Any
from pydantic import BaseModel, Field, create_model, field_validator

from extraction.fields import FIELD_KEYS

# ============================================================
# Field-level models
# ============================================================
class _ConfidenceModel(BaseModel):
    """Base that clamps a model-supplied ``confidence`` into [0.0, 1.0].

    VLMs occasionally emit NaN/inf or out-of-range confidences; left raw they
    silently flip pick_best() and the retry gate. Normalizing at the parse
    boundary keeps every downstream comparison well-behaved.
    """

    @field_validator("confidence", check_fields=False)
    @classmethod
    def _clamp_confidence(cls, v: Any) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return min(1.0, max(0.0, f))


class FieldResult(_ConfidenceModel):
    value: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None
    section: Optional[str] = None

class Soggetto(_ConfidenceModel):
    ndg: Optional[str] = None
    denominazione: Optional[str] = None
    ruolo: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None

class Fido(_ConfidenceModel):
    n_fido: Optional[str] = None
    rapporto: Optional[str] = None
    descrizione: Optional[str] = None
    scadenza: Optional[str] = None
    importo_euro: Optional[str] = None
    tipo_op: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None

class Garanzia(_ConfidenceModel):
    n_gar: Optional[str] = None
    descrizione: Optional[str] = None
    fido: Optional[str] = None
    ndg: Optional[str] = None
    denominazione: Optional[str] = None
    importo_percentuale: Optional[str] = None
    tipo_op: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None

# ============================================================
# Dynamic fields model (single source of truth via FIELD_KEYS)
# ============================================================
FieldsModel = create_model(
    "FieldsModel",
    **{k: (Optional[FieldResult], None) for k in FIELD_KEYS},
)

# ============================================================
# Top-level response models
# ============================================================
class ExtractionResponse(BaseModel):
    fields: FieldsModel = Field(default_factory=FieldsModel)
    soggetti: List[Soggetto] = Field(default_factory=list)
    fidi: List[Fido] = Field(default_factory=list)
    garanzie: List[Garanzia] = Field(default_factory=list)

class AnchorFields(BaseModel):
    numero_pratica: Optional[FieldResult] = Field(default=None, description=(
        "Complete PEF file number. Set section to elenco for a unique result row, "
        "or dettaglio for the active file header. Otherwise leave the value null."
    ))
    ndg: Optional[FieldResult] = None
    denominazione: Optional[FieldResult] = None

class AnchorResponse(BaseModel):
    fields: AnchorFields = Field(default_factory=AnchorFields)

# ============================================================
# Backward-compatible aliases
# ============================================================
RESPONSE_SCHEMA = ExtractionResponse
ANCHOR_SCHEMA = AnchorResponse
