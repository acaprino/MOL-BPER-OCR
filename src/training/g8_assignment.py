"""Assign reviewed practices to the G8 groups (docs/next-ver-plan.md §5.4, rules 2 and 3).

The rule looks only at which fields have a value and at the identities a practice holds: no OCR and no model.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from typing import Any

Identity = tuple[str, str]

TIE_ORDER = ("conferma", "validazione_estesa")
# NDGs of institutions, not of clients. The Fondo di garanzia per la prima casa guarantees first-home mortgages and
# is a subject of a large share of the practices: finding it in two of them says nothing about the two (ADR 0024).
INSTITUTIONAL_NDGS = frozenset({"11153238"})
# The groups of the truth tables an identity must not cross; a v3.1 split in common is only recorded.
G8_GROUPS = {"val_ext": "validazione_estesa", "conferma": "conferma"}


def assign_practices(filled: Mapping[str, Collection[str]], identities: Mapping[str, Collection[Identity]],
                     need: Mapping[str, Mapping[str, int]],
                     bound: Mapping[Identity, str] | None = None) -> dict[str, Any]:
    """Examine the practices by increasing number and give each one to a group.

    A practice holding an identity already in a group follows that group, because the two groups must share none.
    Any other goes to the group whose need it reduces most; at parity, also with no reduction at all, the ties
    alternate starting from the confirmation group.
    """
    remaining = {group: dict(counts) for group, counts in need.items()}
    uncovered = {field for counts in need.values() for field in counts}
    owners = dict(bound or {})
    decisions: list[dict[str, Any]] = []
    ties = 0
    for practice in sorted(filled, key=int):
        fields = sorted(set(filled[practice]) & uncovered)
        gain = {group: sum(counts.get(field, 0) > 0 for field in fields) for group, counts in remaining.items()}
        held = {owners[identity] for identity in identities[practice] if identity in owners}
        if len(held) > 1:
            raise ValueError(f"La pratica {practice} ha identità in comune con entrambi i gruppi.")
        if held:
            group, reason = held.pop(), "identità già presente nel gruppo"
        elif gain["validazione_estesa"] != gain["conferma"]:
            group, reason = max(gain, key=gain.__getitem__), "riduce di più il fabbisogno scoperto"
        else:
            group, ties = TIE_ORDER[ties % 2], ties + 1
            reason = ("parità" if gain["conferma"] else "nessuna riduzione") + ", alternanza a partire dalla conferma"
        for field in fields:
            if remaining[group].get(field, 0) > 0:
                remaining[group][field] -= 1
        owners.update(dict.fromkeys(identities[practice], group))
        decisions.append({"pratica": practice, "gruppo": group, "campi_scoperti": fields, "riduzione": gain,
                          "motivo": reason})
    return {"gruppi": {group: [d["pratica"] for d in decisions if d["gruppo"] == group] for group in need},
            "decisioni": decisions,
            "fabbisogno_residuo": {group: {field: count for field, count in counts.items() if count}
                                   for group, counts in remaining.items()}}


def _transcribed_ndgs(records: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Each (practice, NDG) read in the NDG fields of the lot."""
    from extraction.normalization import normalize_ndg

    found = []
    for record in records:
        field = record["field"] or ""
        if (field == "ndg" or field.startswith("ndg_")) and record["outcome"] == "TRASCRITTO":
            if ndg := normalize_ndg(record["value"]):
                found.append((record["practice"], ndg))
    return found


def _lot_identities(records: Iterable[Mapping[str, Any]],
                    screens: Mapping[str, Mapping[str, str]]) -> dict[str, set[Identity]]:
    """What must stay in one group: the practice, the NDGs of its clients and its images."""
    identities: dict[str, set[Identity]] = {record["practice"]: {("pratica", record["practice"])} for record in records}
    for practice, ndg in _transcribed_ndgs(records):
        if ndg not in INSTITUTIONAL_NDGS:
            identities[practice].add(("NDG", ndg))
    for screen, digests in screens.items():
        identities[screen.split("__", 1)[0]] |= {("immagine", digests["image_sha256"]),
                                                 ("pixel", digests["pixel_sha256"])}
    return identities


def _earlier_identities(truth_rows: Iterable[Mapping[str, str]], screen_rows: Iterable[Mapping[str, str]],
                        ) -> tuple[dict[Identity, str], dict[Identity, str]]:
    """The identities of the earlier lots: those in a G8 group, and those in a v3.1 practice."""
    from extraction.normalization import normalize_ndg

    bound: dict[Identity, str] = {}
    recorded: dict[Identity, str] = {}

    def note(identity: Identity, practice: str, group: str) -> None:
        if group in G8_GROUPS:
            bound[identity] = G8_GROUPS[group]
        else:
            recorded[identity] = practice

    for row in truth_rows:
        note(("pratica", row["Pratica"]), row["Pratica"], row["Gruppo"])
        name = row["Denominazione da attribuire"]
        if (name == "NDG" or name.startswith("NDG ")) and row["Esito"] == "TRASCRITTO":
            identity = normalize_ndg(row["Valore rilevato"])
            if identity and identity not in INSTITUTIONAL_NDGS:
                note(("NDG", identity), row["Pratica"], row["Gruppo"])
    for row in screen_rows:
        note(("immagine", row["SHA256 immagine"]), row["Pratica"], row["Gruppo"])
        note(("pixel", row["SHA256 pixel"]), row["Pratica"], row["Gruppo"])
    return bound, recorded


def assign_lot(records: Iterable[Mapping[str, Any]], screens: Mapping[str, Mapping[str, str]],
               truth_rows: Iterable[Mapping[str, str]], screen_rows: Iterable[Mapping[str, str]],
               need: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    """Assign a lot given the truth tables of the earlier ones."""
    records = list(records)
    identities = _lot_identities(records, screens)
    bound, recorded = _earlier_identities(truth_rows, screen_rows)
    filled = {practice: {record["field"] for record in records if record["practice"] == practice
                         and record["field"] and record["value"] is not None} for practice in identities}
    result = assign_practices(filled, identities, need, bound)
    shared = {practice: [{"tipo": kind, "valore": value, "v3_1": recorded[(kind, value)]}
                         for kind, value in sorted(held) if (kind, value) in recorded]
              for practice, held in identities.items()}
    result["isolamento_v3_1"] = {"controlli": ["pratica", "NDG", "immagine", "pixel"],
                                 "esito": "registrato, non esclude",
                                 "identita_in_comune": {practice: found for practice, found in shared.items() if found}}
    ndgs = _transcribed_ndgs(records)
    result["ndg_istituzionali"] = {ndg: sorted({practice for practice, found in ndgs if found == ndg}, key=int)
                                   for ndg in sorted(INSTITUTIONAL_NDGS)}
    result["ndg"] = {practice: sorted({found for owner, found in ndgs if owner == practice}) for practice in identities}
    return result
