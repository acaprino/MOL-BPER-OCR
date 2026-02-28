"""JSON schemas for structured VLM output (strict mode)."""

from typing import Dict, Any

from extraction.fields import FIELD_KEYS

# ============================================================
# JSON Schemas (strict)
# ============================================================

RESPONSE_SCHEMA: Dict[str, Any] = {
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

ANCHOR_SCHEMA: Dict[str, Any] = {
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
