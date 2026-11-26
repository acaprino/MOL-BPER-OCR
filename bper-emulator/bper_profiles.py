"""The practice profile: the one shape every source of the emulator's catalogue produces.

A profile is a JSON object describing one practice as the emulator's pages show it. The SQLite seed
(bper_synthetic_db), the archive importer (bper_archive) and profile files all produce it; a profile file is

    {"format": "bper-emulator-profiles/1", "profiles": [<profile>, ...]}

and joins the catalogue with ``--profiles FILE`` (see load_profiles), without code changes. Every value is a
display string, exactly as the page shows it ("" for an empty cell), unless noted:

    key                 practice key, [a-z0-9][a-z0-9_-]*: URL parameter and capture folder name
    role                sintetica (invented), addestramento, controllo or test (the archive's roles, ADR 0027)
    number, ndg, name   practice number, main NDG and name of the header
    type, typeCode, typeName   Tipo Pratica of the detail header; Tipo cell of the list and its tooltip
    state, phase, date, created, assigned, evidence, evidenceTooltip   list row: Stato, Fase, Creazione,
                        Data Ass./Del., Evidenze and its tooltip ("" for no tooltip)
    branch, branchName  Filiale relazione "<branch> - <branchName>"
    abi, assignee, assigneeName, operatorId, operatorName, officeCode, noteAuthor, scenario
                        list and header details outside the 45 extracted fields; scenario is free text
    subjects            [{ndg, name, role}] the Elenco Soggetti rows, in order
    fidi                [{id, account, description, due, amount, operation, tooltip, tooltipField}]
    guarantees          [{id, creditId, description, ndgName, amount, operation, tooltip, tooltipField}]
                        tooltipField: the extracted field a description tooltip fills, or null
    creditTotal, guaranteeTotal   the totals under the two tables
    notes               Note della richiesta, with its line breaks
    pages               the PEF pages this practice has: elenco, soggetti, gestione-fidi, note
    scheda              the Scheda Privati page (schema in site/scheda/scheda.js) or null for none
    provenance          {source, filler, stated}: where the values come from; the dotted paths of values that
                        are stand-ins rather than the source's data ("operatorName", "scheda.details", ...); and the
                        extracted fields whose value the source states, possibly empty (null: every field)

The catalogue adds availableSteps and schedaStates when it serves a profile; they are not part of it.
"""

import csv
import json
from pathlib import Path
import re
from typing import Any

from bper_synthetic_db import FUND_NAME

FORMAT ="bper-emulator-profiles/1"
ROLES = ("sintetica", "addestramento", "controllo", "test")
PAGES = ("elenco", "soggetti", "gestione-fidi", "note")
TOOLTIP_FIELDS = (
    "tooltip_descrizione_m_consap", "tooltip_descrizione_consap_dr_bis", "tooltip_descrizione_ipoteca",
)
SCHEDA_FIELDS = (
    "professione_principale", "dal", "numero_mensilita", "retribuzione_annua_netta", "tipo_contratto",
    "datore_di_lavoro_anagrafica", "rating_ufficiale", "score_cgs", "nr_altri_componenti_nucleo",
    "di_cui_percepiscono_reddito", "importo_totale_annuo_nucleo", "note_scheda_privati", "ultima_validazione_scheda",
)
ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "dataset"

# The shape: a type, a dict of shapes, a one-element list (every item has that shape) or a tuple of choices.
_TOOLTIP_FIELD = (str, None)
_STAFF = {"user": str, "branch": str, "bank": str}
_SCHEDA = {
    "ndg": str, "schedaId": str, "name": str, "operator": {"code": str, "name": str},
    "lastChange": {"when": str, **_STAFF}, "lastValidation": _STAFF,
    "fields": {key: str for key in SCHEDA_FIELDS},
    "details": {"employerNdg": str, "employerFrom": str, "employerTo": str, "employerRegistered": bool,
                "incomeChanneled": str, "creditCardBalance": str, "housing": str, "housingFrom": str,
                "outgoings": [{"description": str, "annualAmount": str, "due": str, "residual": str}]},
}
SHAPE = {
    "key": str, "role": str, "number": str, "ndg": str, "name": str,
    "type": str, "typeCode": str, "typeName": str,
    "state": str, "phase": str, "date": str, "created": str, "assigned": str, "evidence": str, "evidenceTooltip": str,
    "branch": str, "branchName": str,
    "abi": str, "assignee": str, "assigneeName": str, "operatorId": str, "operatorName": str, "officeCode": str,
    "noteAuthor": str, "scenario": str,
    "subjects": [{"ndg": str, "name": str, "role": str}],
    "fidi": [{"id": str, "account": str, "description": str, "due": str, "amount": str, "operation": str,
              "tooltip": str, "tooltipField": _TOOLTIP_FIELD}],
    "guarantees": [{"id": str, "creditId": str, "description": str, "ndgName": str, "amount": str,
                    "operation": str, "tooltip": str, "tooltipField": _TOOLTIP_FIELD}],
    "creditTotal": str, "guaranteeTotal": str, "notes": str,
    "pages": [str],
    "scheda": (_SCHEDA, None),
    "provenance": {"source": str, "filler": [str], "stated": ([str], None)},
}


def _shape_problems(value: Any, shape: Any, path: str) -> list[str]:
    def at(key: Any) -> str:
        return f"{path}.{key}" if path else str(key)

    if isinstance(shape, tuple):  # a shape or null
        return [] if value is None else _shape_problems(value, shape[0], path)
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            return [f"{path or 'profilo'}: atteso un oggetto"]
        problems = [f"{at(key)}: mancante" for key in shape if key not in value]
        problems += [f"{at(key)}: campo sconosciuto" for key in value if key not in shape]
        for key, inner in shape.items():
            if key in value:
                problems += _shape_problems(value[key], inner, at(key))
        return problems
    if isinstance(shape, list):
        if not isinstance(value, list):
            return [f"{path}: attesa una lista"]
        return [problem for n, item in enumerate(value) for problem in _shape_problems(item, shape[0], at(n))]
    if type(value) is not shape:  # bool is an int: only the exact type passes
        return [f"{path}: atteso {shape.__name__}, trovato {type(value).__name__}"]
    return []


def validate_profile(profile: Any) -> list[str]:
    """The problems of one profile, each naming its dotted path; empty when the profile is valid."""
    problems = _shape_problems(profile, SHAPE, "")
    if not isinstance(profile, dict):
        return problems
    if isinstance(profile.get("key"), str) and not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", profile["key"]):
        problems.append("key: solo minuscole, cifre, '-' e '_'")
    if isinstance(profile.get("role"), str) and profile["role"] not in ROLES:
        problems.append(f"role: uno fra {', '.join(ROLES)}")
    pages = profile.get("pages")
    if isinstance(pages, list) and (set(pages) - set(PAGES) or len(set(pages)) != len(pages)):
        problems.append(f"pages: pagine distinte fra {', '.join(PAGES)}")
    for table in ("fidi", "guarantees"):
        for n, row in enumerate(profile.get(table) or []):
            if isinstance(row, dict) and row.get("tooltipField") not in (None, *TOOLTIP_FIELDS):
                problems.append(f"{table}.{n}.tooltipField: uno fra {', '.join(TOOLTIP_FIELDS)} o null")
    return problems


def _ndg(value: str) -> str:
    """An NDG as an identity, as extraction.normalization.normalize_ndg compares it."""
    cleaned = re.sub(r"[^0-9A-Za-z]", "", value).upper()
    return (cleaned.lstrip("0") or "0") if cleaned.isdigit() else cleaned


def _name(value: str) -> str:
    return " ".join(value.upper().split())


def archive_identities(archive: Path = ARCHIVE) -> tuple[set[str], set[str]]:
    """NDGs and names of the real archive, normalized; empty when the archive is not there."""
    ndgs: set[str] = set()
    names: set[str] = set()
    path = Path(archive) / "valori.csv"
    if not path.exists():
        return ndgs, names
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source, delimiter=";"):
            value, key, label = row["Valore"].strip(), row["Chiave"], row["Campo"]
            if not value:
                continue
            if key.startswith("ndg") or label.endswith(": NDG"):
                ndgs |= {_ndg(token) for token in value.split()}  # a guarantee cell may list several NDGs
            elif key.startswith(("denominazione", "datore_di_lavoro")) or label.endswith(": Denominazione"):
                names.add(_name(value))
    return ndgs, names


def _identities(profile: dict) -> tuple[set[str], set[str]]:
    scheda = profile.get("scheda") or {}
    ndgs = {profile["ndg"], *(s["ndg"] for s in profile["subjects"]), scheda.get("ndg", "")}
    names = {profile["name"], *(s["name"] for s in profile["subjects"]), scheda.get("name", ""),
             (scheda.get("fields") or {}).get("datore_di_lavoro_anagrafica", "")}
    return {_ndg(n) for n in ndgs if n.strip()}, {_name(n) for n in names if n.strip()}


def check_profiles(profiles: list[Any], *, archive: Path | None = ARCHIVE, source: str = "profili") -> None:
    """Refuse invalid profiles, two under one key, and a sintetica one carrying an NDG or a name of the real
    archive. The message names the profile and the path, never the colliding value."""
    problems = [f"{p.get('key', n) if isinstance(p, dict) else n}: {problem}"
                for n, p in enumerate(profiles) for problem in validate_profile(p)]
    keys = [p["key"] for p in profiles if isinstance(p, dict) and isinstance(p.get("key"), str)]
    problems += [f"{key}: chiave ripetuta" for key in sorted({k for k in keys if keys.count(k) > 1})]
    if not problems and archive is not None:
        # The guarantee fund is a real institution that invented practices may name, as real ones do.
        real_ndgs, real_names = archive_identities(archive)
        for profile in profiles:
            if profile["role"] == "sintetica":
                ndgs, names = _identities(profile)
                if ndgs & real_ndgs or names & real_names - {_name(FUND_NAME)}:
                    problems.append(f"{profile['key']}: è sintetica ma usa un NDG o un nome dell'archivio reale")
    if problems:
        raise ValueError(f"{source}: " + "; ".join(problems))


def load_profiles(path: Path, *, archive: Path | None = ARCHIVE) -> list[dict]:
    """Read and check a profile file (see the module docstring); raise ValueError naming the file."""
    path = Path(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("format") != FORMAT or not isinstance(document.get("profiles"), list):
        raise ValueError(f"{path.name}: atteso {{\"format\": \"{FORMAT}\", \"profiles\": [...]}}")
    check_profiles(document["profiles"], archive=archive, source=path.name)
    return document["profiles"]
