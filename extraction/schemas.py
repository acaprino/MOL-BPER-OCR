"""Pydantic models for structured VLM output (used by LangChain .with_structured_output())."""
from typing import Optional, Union, List, Dict, Any
from pydantic import BaseModel, Field, create_model
from extraction.fields import FIELD_KEYS

# ============================================================
# Field-level models
# ============================================================
class FieldResult(BaseModel):
    value: Optional[Union[str, int, float]] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None
    section: Optional[str] = None

class Soggetto(BaseModel):
    ndg: Optional[str] = None
    denominazione: Optional[str] = None
    ruolo: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None

class Fido(BaseModel):
    n_fido: Optional[str] = None
    rapporto: Optional[str] = None
    descrizione: Optional[str] = None
    scadenza: Optional[str] = None
    importo_euro: Optional[str] = None
    tipo_op: Optional[str] = None
    confidence: float = 0.0
    evidence_text: Optional[str] = None

class Garanzia(BaseModel):
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
    screen_id: str = ""
    attempt: str = ""
    fields: FieldsModel = Field(default_factory=FieldsModel)
    soggetti: List[Soggetto] = Field(default_factory=list)
    fidi: List[Fido] = Field(default_factory=list)
    garanzie: List[Garanzia] = Field(default_factory=list)

class AnchorFields(BaseModel):
    ndg: Optional[FieldResult] = None
    denominazione: Optional[FieldResult] = None

class AnchorResponse(BaseModel):
    screen_id: str = ""
    attempt: str = ""
    fields: AnchorFields = Field(default_factory=AnchorFields)

# ============================================================
# Backward-compatible aliases
# ============================================================
RESPONSE_SCHEMA = ExtractionResponse
ANCHOR_SCHEMA = AnchorResponse
