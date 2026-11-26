"""Consolidate captured frames into one record per banking practice.

The router recognises 9 screens but they are variants of 4 canonical pages of a
single practice: scrolled tables and open tooltips each carry only 1-6 useful
fields. Presenting one row per frame shows the operator nine mostly-empty rows
for one subject. Live frames follow the selected PEF number. Historical frames
use their original NDG grouping. Both merge the same fields.
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
    practice_number: Optional[str] = None

    @property
    def edit_key(self) -> Optional[str]:
        return f"pef:{self.practice_number}" if self.practice_number else self.ndg


# ============================================================
# Operator corrections
# ============================================================

# {practice edit key: {schema_key: corrected value, or None when the operator cleared it}}
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


def correction_key(value: str | None) -> Optional[str]:
    if isinstance(value, str) and value.startswith("pef:") and value[4:].isascii() and value[4:].isdigit():
        return value
    return normalize_ndg(value)


class SelectedPracticeFlow:
    """Assign captures to the opened PEF in capture order, including failed slots."""

    def __init__(self) -> None:
        self.number: str | None = None
        self.browsing = False
        self.awaiting_identity = False
        self._opened: set[str] = set()
        self._list_rows: dict[str, list[tuple[int, dict]]] = {}
        self._pending: list[tuple[int, dict]] = []
        self._ndg: str | None = None

    def accept(self, frame: dict, sequence: int) -> list[tuple[str, int, dict]]:
        view = frame["_practice_view"]
        if view == "unknown":
            return []
        number = frame.get("_practice_number")
        success = frame.get("_status") != "ERROR" and not frame.get("_practice_context_conflict")
        if view == "list":
            self.browsing = True
            self.awaiting_identity = False
            self._pending.clear()
            if number and success:
                if number in self._opened:
                    return [(number, sequence, frame)]
                self._list_rows.setdefault(number, []).append((sequence, frame))
            return []

        ndg = frame_ndg(frame)
        if view == "selection" or self.browsing or (ndg and self._ndg and ndg != self._ndg):
            self.number = self._ndg = None
            self._pending.clear()
        self.browsing = False
        self.awaiting_identity = not number or not success
        if not success:
            return []
        if not number:
            if ndg:
                self._ndg = ndg
            self._pending.append((sequence, frame))
            return []
        if self.number and number != self.number:
            # A fast switch can entirely escape sampling. The intervening
            # anonymous frames could belong to either file.
            self._pending.clear()
        if number != self.number:
            self._ndg = None
        self.number = number
        if ndg:
            self._ndg = ndg
        self._opened.add(number)
        earlier = self._list_rows.pop(number, []) + self._pending
        self._pending = []
        return [(number, seq, row) for seq, row in earlier] + [(number, sequence, frame)]


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

    def __init__(self, ndg: Optional[str], practice_number: Optional[str] = None) -> None:
        self.ndg = ndg
        self.practice_number = practice_number
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
        # Each published row keeps its own field choices across later captures.
        fields = dict(self.fields)
        if corrections and self.ndg is not None:
            # The operator wins over any extracted value, applied after the frame merge
            # so a later frame cannot undo it. Copy: never alias the accumulator.
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
            practice_number=self.practice_number,
        )


class PracticeEngine:
    """Fold the contiguous capture prefix into stable, independently editable rows."""

    def __init__(self) -> None:
        self._groups: dict[Optional[str], _Group] = {}
        self._rows: dict[Optional[str], PracticeRecord] = {}
        self._last_ndg: Optional[str] = None
        self._flow = SelectedPracticeFlow()

    def merge(self, frames: Iterable[dict], corrections: Corrections) -> set[int]:
        assigned_slots: set[int] = set()
        touched: set[Optional[str]] = set()
        for frame in frames:
            if frame.get("_practice_view"):
                for number, sequence, assigned in self._flow.accept(frame, frame.get("_capture_sequence", 0)):
                    assigned_slots.add(sequence)
                    key = f"pef:{number}"
                    if key not in self._groups:
                        self._groups[key] = _Group(None, number)
                    group = self._groups[key]
                    group.absorb(assigned)
                    group.ndg = normalize_ndg(_value_of(group.fields["ndg"]))
                    touched.add(key)
                continue
            ndg = frame_ndg(frame)
            if ndg is not None:
                if None in self._groups:
                    prefix = self._groups.pop(None)
                    prefix.ndg = ndg
                    self._groups[ndg] = prefix
                    self._rows.pop(None, None)
                    touched.discard(None)
                self._last_ndg = ndg
            key = self._last_ndg
            if key not in self._groups:
                self._groups[key] = _Group(key)
            self._groups[key].absorb(frame)
            touched.add(key)
        for key in touched:
            self.refresh(key, corrections)
        return assigned_slots

    def refresh(self, key: Optional[str], corrections: Corrections) -> None:
        if key in self._groups:
            edits = corrections.get(key) if key is not None else None
            self._rows[key] = self._groups[key].to_record(edits)

    def records(self, *, exportable_only: bool = False) -> tuple[PracticeRecord, ...]:
        return tuple(self._rows[key] for key in self._groups
                     if not exportable_only or self._rows[key].ndg or has_content(self._rows[key]))


def consolidate(
    results: Sequence[Dict[str, Any]],
    corrections: Optional[Corrections] = None,
) -> List[PracticeRecord]:
    """Group pipeline results into one record per practice.

    Live frames use the selected file number. In legacy archives NDG is the key.
    A legacy frame whose NDG was not read attaches to the most recent
    practice; frames arriving before any readable NDG wait in a buffer and join
    the first practice identified. A session that never reads an NDG yields a
    single record with ndg=None.

    `corrections` ({practice edit key: {schema_key: value}}) overrides the merged
    value of a field; the extracted one stays in `original_value`.
    """
    engine = PracticeEngine()
    engine.merge(results, corrections or {})
    return list(engine.records())
