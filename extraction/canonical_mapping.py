"""Canonical mapping helpers for backend/UI/export integration."""

from typing import Any, Dict, List, Tuple

from extraction.fields import get_canonical_field_metadata
from extraction.page_definitions import PAGE_SHEET_ORDER

def _canonical_entry_sort_key(entry: Dict[str, Any]) -> Tuple[int, str, str]:
    """Return a stable sort key for canonical field entries."""
    page_key = entry.get("page_key")
    try:
        page_index = PAGE_SHEET_ORDER.index(page_key)
    except ValueError:
        page_index = len(PAGE_SHEET_ORDER)

    display_name = str(entry.get("display_name") or "")
    schema_key = str(entry.get("schema_key") or "")
    return (page_index, display_name, schema_key)

def build_canonical_field_entries(fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert extracted field payloads into canonical backend entries."""
    entries: List[Dict[str, Any]] = []

    for schema_key, payload in (fields or {}).items():
        if not isinstance(payload, dict):
            continue

        metadata = get_canonical_field_metadata(schema_key)
        entries.append(
            {
                "schema_key": metadata["schema_key"],
                "display_name": metadata["display_name"],
                "page_key": metadata["page_key"],
                "page_name": metadata["page_name"],
                "value": payload.get("value"),
                "confidence": payload.get("confidence"),
                "evidence_text": payload.get("evidence_text"),
                "section": payload.get("section"),
            }
        )

    return sorted(entries, key=_canonical_entry_sort_key)
