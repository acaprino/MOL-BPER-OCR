"""Consolidate captured frames into one record per banking practice.

The router recognises 9 screens but they are variants of 4 canonical pages of a
single practice: scrolled tables and open tooltips each carry only 1-6 useful
fields. Presenting one row per frame shows the operator nine mostly-empty rows
for one subject, so frames are grouped by NDG and merged field by field.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import app_paths

_SRC_DIR = str(app_paths.src_dir())
if not app_paths.is_frozen() and _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from extraction.fields import FIELD_KEYS
from extraction.normalization import is_nullish, normalize_ndg, pick_best, safe_field

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
# Operator corrections
# ============================================================

# {normalized NDG: {schema_key: corrected value, or None when the operator cleared it}}
Corrections = Mapping[str, Mapping[str, Optional[str]]]

# NDG is the practice identity (the grouping key), so it is never corrected.
CORRECTABLE_KEYS = frozenset(FIELD_KEYS) - {"ndg"}


def is_correctable(record: PracticeRecord, schema_key: str) -> bool:
    """Whether the operator may edit this cell.

    A record without an NDG is refused: when the NDG is finally read the record is
    absorbed into the first identified practice, so a correction made before would
    be orphaned.
    """
    return record.ndg is not None and schema_key in CORRECTABLE_KEYS


def _value_of(field: Any) -> Any:
    return field.get("value") if isinstance(field, dict) else None


def _has_values(fields: Iterable[Any]) -> bool:
    return any(not is_nullish(_value_of(field)) for field in fields)


def has_content(record: PracticeRecord) -> bool:
    """Whether any field of the practice holds a value.

    A session of errors only consolidates to one empty record: it is not a practice
    to count, show a total for, or warn about.
    """
    return _has_values(record.fields.values())


# ============================================================
# NDG identity
# ============================================================


def frame_ndg(result: Dict[str, Any]) -> Optional[str]:
    """Group key of a frame, from its ndg field."""
    return normalize_ndg(_value_of((result.get("fields") or {}).get("ndg")))


class PracticeCounter:
    """Count exportable practices as their frames are published in capture order."""

    def __init__(self) -> None:
        self._ndgs: set[str] = set()
        self._has_anonymous_data = False

    def add(self, result: Dict[str, Any]) -> None:
        ndg = frame_ndg(result)
        if ndg is not None:
            self._ndgs.add(ndg)
        elif not self.count:
            fields = result.get("fields") or {}
            self._has_anonymous_data = _has_values(fields.get(key) for key in FIELD_KEYS)

    @property
    def count(self) -> int:
        # The first identified practice absorbs any anonymous prefix. Corrections
        # can never clear an NDG or address an anonymous record.
        return len(self._ndgs) or int(self._has_anonymous_data)


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

    def to_record(self, corrections: Optional[Mapping[str, Optional[str]]] = None) -> PracticeRecord:
        fields = self.fields
        if corrections and self.ndg is not None:
            # The operator wins over any extracted value, applied after the frame merge
            # so a later frame cannot undo it. Copy: never alias the accumulator.
            fields = dict(self.fields)
            for key, value in corrections.items():
                if key not in CORRECTABLE_KEYS:
                    continue
                fields[key] = {
                    **fields[key],
                    "value": value,
                    "original_value": fields[key]["value"],
                    "corrected": True,
                }
        denominazione = fields["denominazione"]["value"]
        return PracticeRecord(
            ndg=self.ndg,
            denominazione=None if is_nullish(denominazione) else str(denominazione),
            fields=fields,
            source_pages=tuple(self.source_pages),
            frame_count=self.frame_count,
        )


def consolidate(
    results: Sequence[Dict[str, Any]],
    corrections: Optional[Corrections] = None,
) -> List[PracticeRecord]:
    """Group pipeline results into one record per practice.

    NDG is the key. A frame whose NDG was not read attaches to the most recent
    practice; frames arriving before any readable NDG wait in a buffer and join
    the first practice identified. A session that never reads an NDG yields a
    single record with ndg=None.

    `corrections` ({normalized NDG: {schema_key: value}}) overrides the merged
    value of a field; the extracted one stays in `original_value`.
    """
    corrections = corrections or {}
    groups: Dict[str, _Group] = {}
    order: List[str] = []
    pending: List[Dict[str, Any]] = []
    last_key: Optional[str] = None

    for result in results:
        key = frame_ndg(result)

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

    return [groups[key].to_record(corrections.get(key)) for key in order]
