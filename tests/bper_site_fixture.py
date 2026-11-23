"""Reference assets of the simulator: the site pixels of the source PNGs, the Scheda Privati fixture, and the
identities of the real archive that the gates must keep out of default responses."""

import csv
from io import BytesIO
import json
from pathlib import Path
import re

from PIL import Image

from bper_synthetic_db import FUND_NAME
from tools.reference_screens import reference_screens

REPO = Path(__file__).resolve().parents[1]
SCHEDA_FIXTURE = REPO / "bper-emulator" / "site" / "scheda" / "reference.json"
ARCHIVE = REPO / "data" / "dataset"
ALL_ROLES = frozenset({"addestramento", "controllo", "test"})


def assert_site_pixels(step: int, png: bytes) -> None:
    left = 4 if step in (8, 9) else 3
    top = 59 if step in (1, 4) else 60
    with Image.open(reference_screens()[f"screen {step}"]) as source, Image.open(BytesIO(png)) as result:
        expected = source.crop((left, top, left + 842, top + 617))
        assert result.size == expected.size
        assert result.convert("RGBA").tobytes() == expected.convert("RGBA").tobytes()


def reference_scheda() -> dict:
    """The Scheda Privati fixture of practice 52062600, read from its file."""
    return json.loads(SCHEDA_FIXTURE.read_text(encoding="utf-8"))


def scheda_personal_values() -> list[str]:
    """The real customer's name, NDG, scheda number and employer, the staff names and branch of the fixture."""
    scheda = reference_scheda()
    return [scheda["name"], scheda["ndg"], scheda["schedaId"], scheda["fields"]["datore_di_lavoro_anagrafica"],
            scheda["operator"]["name"], scheda["lastChange"]["user"], scheda["lastValidation"]["user"],
            scheda["lastChange"]["branch"]]


def fictitious_profile(key: str = "fittizia-001", role: str = "sintetica") -> dict:
    """A valid profile with invented values: a synthetic practice under another key and role."""
    from copy import deepcopy

    from bper_synthetic_db import synthetic_practices
    profile = deepcopy(synthetic_practices()[1])
    profile.update(key=key, role=role)
    return profile


def write_profiles(path: Path, profiles: list[dict]) -> Path:
    from bper_profiles import FORMAT
    path.write_text(json.dumps({"format": FORMAT, "profiles": profiles}, ensure_ascii=False), encoding="utf-8")
    return path


def squash(text: str) -> str:
    return " ".join(text.split()).lower()


def _ndg(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits.lstrip("0") or "0"


def archive_identities(roles: frozenset[str] | set[str]) -> dict[str, set[str]]:
    """NDGs (digits without leading zeros), names (squashed, 8+ characters) and 40-character note windows that
    the archive authored for the practices of these roles. Kept as sets so a failure reports only counts."""
    with (ARCHIVE / "pratiche.csv").open(encoding="utf-8-sig", newline="") as source:
        chosen = {row["Pratica"] for row in csv.DictReader(source, delimiter=";") if row["Ruolo"] in roles}
    found: dict[str, set[str]] = {"ndg": set(), "name": set(), "note": set()}
    with (ARCHIVE / "valori.csv").open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source, delimiter=";"):
            value, key, label = row["Valore"].strip(), row["Chiave"], row["Campo"]
            if row["Schermata"].split("/")[0] not in chosen or not value or row["Esito"] in ("VUOTO", "NON VISIBILE"):
                continue
            if key.startswith("ndg") or label.endswith(": NDG"):
                # A guarantee cell may list several NDGs.
                found["ndg"] |= {_ndg(token) for token in re.findall(r"\d{6,}", value)}
            elif key.startswith(("denominazione", "datore_di_lavoro")) or label.endswith(": Denominazione"):
                # The guarantee fund is an institution of the real practices that the synthetic ones also name.
                if len(squash(value)) >= 8 and squash(value) != squash(FUND_NAME):
                    found["name"].add(squash(value))
            elif key in ("note_della_richiesta", "note_scheda_privati"):
                text = squash(value)
                found["note"] |= {text[i:i + 40] for i in range(0, max(1, len(text) - 39), 40)}
    # Full names only: the list shows a name cut to its first characters, and such a prefix of a real name may
    # start a synthetic one too (or the fund's name) without naming anybody.
    names = found["name"] | {squash(FUND_NAME)}
    found["name"] = {n for n in found["name"] if not any(o != n and o.startswith(n.rstrip(". …")) for o in names)}
    return found


def sealed_only() -> dict[str, set[str]]:
    """Identities only the test practices carry. A note window that the training or control notes contain
    anywhere is left out too: the notes share template sentences ("Dettaglio importi mutuo", ...)."""
    opened = archive_identities({"addestramento", "controllo"})
    sealed = archive_identities({"test"})
    with (ARCHIVE / "pratiche.csv").open(encoding="utf-8-sig", newline="") as source:
        open_practices = {row["Pratica"] for row in csv.DictReader(source, delimiter=";") if row["Ruolo"] != "test"}
    with (ARCHIVE / "valori.csv").open(encoding="utf-8-sig", newline="") as source:
        open_notes = "\n".join(squash(row["Valore"]) for row in csv.DictReader(source, delimiter=";")
                               if row["Schermata"].split("/")[0] in open_practices
                               and row["Chiave"] in ("note_della_richiesta", "note_scheda_privati"))
    return {"ndg": sealed["ndg"] - opened["ndg"], "name": sealed["name"] - opened["name"],
            "note": {window for window in sealed["note"] if window not in open_notes}}


def strings(body: str) -> str:
    """The text of a response: every string of a JSON document joined by newlines, or the body itself."""
    try:
        document = json.loads(body)
    except ValueError:
        return body
    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(document)
    return "\n".join(out)


def leaks(text: str, identities: dict[str, set[str]]) -> dict[str, int]:
    """How many of the identities occur in the text: NDGs as whole digit runs, names and notes as squashed text."""
    tokens = {_ndg(token) for token in re.findall(r"\d{6,}", text)}
    flat = squash(text)
    return {"ndg": len(identities["ndg"] & tokens),
            "name": sum(name in flat for name in identities["name"]),
            "note": sum(window in flat for window in identities["note"])}
