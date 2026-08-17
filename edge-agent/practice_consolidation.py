"""Consolidate captured frames into one record per banking practice.

The router recognises 9 screens but they are variants of 4 canonical pages of a
single practice: scrolled tables and open tooltips each carry only 1-6 useful
fields. Presenting one row per frame shows the operator nine mostly-empty rows
for one subject, so frames are grouped by NDG and merged field by field.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import app_paths

_PROJECT_ROOT = str(app_paths.project_root())
if not app_paths.is_frozen() and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from extraction.fields import FIELD_KEYS
from extraction.normalization import is_nullish, pick_best, safe_field

# ============================================================
# Record
# ============================================================


@dataclass(frozen=True)
class PracticeRecord:
    """One banking practice, merged from every frame that showed it."""

    ndg: Optional[str]
    denominazione: Optional[str]
    fields: Dict[str, Dict[str, Any]]
    source_pages: Tuple[str, ...]
    frame_count: int


# ============================================================
# NDG identity
# ============================================================


def normalize_ndg(value: Any) -> Optional[str]:
    """Group key for an NDG, or None when it was not read.

    Deliberately not norm_number_str(): that is a quantity normalizer and reads
    the dot as a decimal separator, so "12.345" becomes "12.35" (splitting one
    practice in two) and "12345/A" becomes "12345.00" (merging two distinct
    practices). An NDG is an identifier: keep the alphanumerics, uppercase, and
    drop leading zeros only when what remains is all digits.
    """
    if is_nullish(value):
        return None
    cleaned = re.sub(r"[^0-9A-Za-z]", "", str(value)).upper()
    if cleaned.isdigit():
        cleaned = cleaned.lstrip("0") or "0"
    return cleaned or None


def _frame_ndg(result: Dict[str, Any]) -> Optional[str]:
    """Group key of a frame, from its ndg field."""
    return normalize_ndg(((result.get("fields") or {}).get("ndg") or {}).get("value"))


# ============================================================
# Consolidation
# ============================================================


class _Group:
    """Mutable accumulator; frozen into a PracticeRecord at the end."""

    def __init__(self, ndg: Optional[str]) -> None:
        self.ndg = ndg
        self.fields: Dict[str, Dict[str, Any]] = {
            key: {"value": None, "confidence": 0.0, "evidence_text": None, "section": None}
            for key in FIELD_KEYS
        }
        self.source_pages: List[str] = []
        self.frame_count = 0

    def absorb(self, result: Dict[str, Any]) -> None:
        raw = result.get("fields") or {}
        for key in FIELD_KEYS:
            # safe_field() returns a fresh dict, so pick_best never aliases the
            # caller's payload and a later frame cannot mutate an earlier choice.
            self.fields[key] = pick_best(self.fields[key], safe_field(raw, key))
        self.source_pages.append(str(result.get("_page_type") or ""))
        self.frame_count += 1

    def to_record(self) -> PracticeRecord:
        denominazione = self.fields["denominazione"]["value"]
        return PracticeRecord(
            ndg=self.ndg,
            denominazione=None if is_nullish(denominazione) else str(denominazione),
            fields=self.fields,
            source_pages=tuple(self.source_pages),
            frame_count=self.frame_count,
        )


def consolidate(results: Sequence[Dict[str, Any]]) -> List[PracticeRecord]:
    """Group pipeline results into one record per practice.

    NDG is the key. A frame whose NDG was not read attaches to the most recent
    practice; frames arriving before any readable NDG wait in a buffer and join
    the first practice identified. A session that never reads an NDG yields a
    single record with ndg=None.
    """
    groups: Dict[str, _Group] = {}
    order: List[str] = []
    pending: List[Dict[str, Any]] = []
    last_key: Optional[str] = None

    for result in results:
        key = _frame_ndg(result)

        if key is None:
            if last_key is None:
                pending.append(result)
                continue
            groups[last_key].absorb(result)
            continue

        if key not in groups:
            groups[key] = _Group(key)
            order.append(key)

        # The first identified practice adopts everything seen before it.
        for buffered in pending:
            groups[key].absorb(buffered)
        pending.clear()

        groups[key].absorb(result)
        last_key = key

    if pending:
        anonymous = _Group(None)
        for buffered in pending:
            anonymous.absorb(buffered)
        return [anonymous.to_record()]

    return [groups[key].to_record() for key in order]
