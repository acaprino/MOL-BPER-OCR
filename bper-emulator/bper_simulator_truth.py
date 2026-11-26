"""Ground truth for native, single-practice captures at the nine numbered site views and at the
capture states of the practice's Scheda Privati page."""
import csv
from io import StringIO
import json
import math
from pathlib import Path
from runpy import run_path


# The standalone simulator does not install the extraction or training packages.
# Resolve the project's stdlib-only reader without modifying the caller's sys.path.
_schema = Path(__file__).resolve().parents[1] / "src" / "training" / "schema.py"
CSV_LABELS = {key: label.strip() for label, key in run_path(str(_schema))["vocabulary"]()[1].items()}
FINANCIAL_TOOLTIPS = (
    "tooltip_descrizione_m_consap", "tooltip_descrizione_consap_dr_bis", "tooltip_descrizione_ipoteca",
)
CREDIT_FIELDS = {
    "n_fido": "id", "rapporto": "account", "descrizione": "description",
    "scadenza": "due", "importo_euro": "amount", "tipo_op": "operation",
}
# Scheda Privati at the 1903 x 945 page viewport of the reference screenshots, as the real archive
# transcribes them (data/dataset/valori.csv, 52062600/scheda-privati-0K): the top of the page, then the
# page scrolled to the family block and the note box.
SCHEDA_TOP_FIELDS = (
    "ndg", "denominazione", "ultima_validazione_scheda", "professione_principale", "dal", "numero_mensilita",
    "retribuzione_annua_netta", "tipo_contratto", "datore_di_lavoro_anagrafica", "rating_ufficiale", "score_cgs",
)
SCHEDA_BOTTOM_FIELDS = (
    "datore_di_lavoro_anagrafica", "rating_ufficiale", "score_cgs", "nr_altri_componenti_nucleo",
    "di_cui_percepiscono_reddito", "importo_totale_annuo_nucleo",
)
SCHEDA_PAGE_SCROLL = 662  # page scroll of the real screenshots 02-05 (measure_scheda.SHOTS)
# A USCITE CONTINUATIVE row of scheda.css (.sp-outgoing): each one lengthens the page by this height.
OUTGOING_ROW_PX = 90
# Top of each employer field's value box below the top of the viewport, at SCHEDA_PAGE_SCROLL on a page without
# outgoing rows; each row moves it OUTGOING_ROW_PX higher, and a box no longer wholly in the viewport leaves the truth.
# Measured in headless Chrome (1920 x 945 viewport) on sim-002 at ?scroll=662: the input's top minus the top of
# .sp-main, rounded; the heights in scheda.css give the same 18, 150 and 147.
EMPLOYER_TOP_PX = {"datore_di_lavoro_anagrafica": 18, "rating_ufficiale": 150, "score_cgs": 147}
# The note textarea of scheda.css: border-box height with a 1 px bottom border, top padding, line box.
NOTE_BOX_PX, NOTE_PADDING_PX, NOTE_LINE_PX = 95, 3, 21
# shortcut: assumes each note line renders as one line box; at ~1590 px of text 170 characters fit with a
# wide fallback font. Measure the wrapping in the browser if longer lines are needed.
NOTE_LINE_CHARS = 170
# Screen 9 at 842 x 617: the request note (8.6 px Arial, 9.85 px lines, 586 px wide) has 26 lines above the bottom
# of the detail window. shortcut: lines are estimated at 135 characters (the archive's notes render 120-152 per
# line); a note near 26 * 135 characters may be misjudged: run audit_truth.cjs on new profiles, and measure the
# wrap (glyph widths) if one is.
REQUEST_NOTE_LINES, REQUEST_NOTE_LINE_CHARS = 26, 135


# The list shows a name of up to 127 px (12 px Segoe UI) whole and cuts a wider one with an ellipsis (list.js
# nameLimit, kept in list_font_metrics.json as innerWidth). A name's width is the sum of Chrome's glyph advances plus
# its pair kerning, measured by measure_list_font.cjs into list_font_metrics.json; calibrated against the audit
# (audit_truth.cjs): on the 64 synthetic practices it cuts exactly the 11 names Chrome cuts (126.18 px fits,
# 127.25 px is cut), and the archive's nearest name is 2.9 px from the edge.
# shortcut: Windows' Segoe UI as Chrome draws it, unknown characters taken at the mean advance; re-measure when
# list.css or list.js change the list's columns or font, or when audit_truth.cjs flags a list name.
LIST_FONT = json.loads(Path(__file__).with_name("list_font_metrics.json").read_text(encoding="utf-8"))
_MEAN_ADVANCE = sum(LIST_FONT["advance"].values()) / len(LIST_FONT["advance"])


def _list_width(name: str) -> float:
    advance, kerning = LIST_FONT["advance"], LIST_FONT["kerning"]
    return sum(advance.get(c, _MEAN_ADVANCE) for c in name) + sum(kerning.get(a + b, 0.0) for a, b in zip(name, name[1:]))


def list_name_fits(name: str) -> bool:
    """Whether the list's Denom. cell shows the name whole; a cut name is not asserted on the list screens."""
    return _list_width(name) <= LIST_FONT["innerWidth"]


# The list sizes its columns to their content, and its identity columns (ABI, NDG, Denom.) stay in view while they fit
# beside the scrolled ones (list.js scroller): at the end of the scroll (screen 3) how far they have gone depends on
# the width of Denom. This replays that geometry with what measure_list_font.cjs measured on the demo practice at
# 842 x 617 (LIST_FONT["end"], reference px): the container, the columns right of Denom., the identity columns besides
# the name, the label's width, where the NDG and the name start, and how far they stick left once scrolled.
# Two things widen a row besides its name: the checkbox of a row whose state is in end["selectable"] (NDG and what
# follows move right) and an Evidenze cell whose marks need more than the column's label (end["evidenceLabel"]).
# shortcut: end-of-scroll geometry measured on the demo practice (other columns label-sized, 8-digit NDG), re-measure when audit_truth.cjs flags screen 3
def list_end_shows(name: str, checkbox: bool = False, slots: int = 1) -> tuple[bool, bool]:
    """Whether the list scrolled to its end (screen 3) still shows the NDG whole, and the name whole."""
    end = LIST_FONT["end"]
    fits = list_name_fits(name)
    shift = end["checkbox"] if checkbox else 0.0
    # Chrome lays the columns out in 1/64 px units: where the identity columns stick turns on half a pixel.
    pinned = round((end["pinned"] + shift + (max(_list_width(name), end["label"]) if fits else end["label"])) * 64) / 64
    evidence = max(end["evidenceLabel"], end["chip"] + slots * end["slot"])
    scroll = math.floor(pinned + end["rest"] - end["evidence"] + evidence - end["view"])
    beyond = max(0.0, scroll - (end["view"] - 1 - pinned + end["settle"][1]))

    def starts_inside(left: float, settle: float) -> bool:
        # list.js keeps the pinned cells on whole pixels (Math.round); the audit allows half a pixel.
        return left + math.floor(0.5 - beyond - settle) >= -0.5

    return (starts_inside(end["ndg"] + shift, end["settle"][0]),
            fits and starts_inside(end["name"] + shift, end["settle"][1]))


def list_start_shows(name: str, checkbox: bool = False, slots: int = 1) -> set[str]:
    """Which of Stato, Fase and Creazione the list shows at the capture window's start offset (screen 1): those the
    pinned Evidenze, which an invented practice's marks may widen, leaves readable. As audit_truth.cjs judges it, a
    text is readable while the point at 85% of its width is not covered."""
    # shortcut: the texts' widths are the demo practice's (a date is always as wide; Stato and Fase codes nearly), re-measure when audit_truth.cjs flags screen 1
    end = LIST_FONT["end"]
    shift = end["checkbox"] if checkbox else 0.0
    column = max(_list_width(name), end["label"]) if list_name_fits(name) else end["label"]
    wall = end["view"] - end["actions"] - max(end["evidenceLabel"], end["chip"] + slots * end["slot"])
    return {field for field, (left, width) in end["columns"].items()
            if left + shift + column - end["start"] + 0.85 * width < wall}


def _draw(text: str) -> float:
    """FNV-1a of the text as a fraction of 2**32, as list.js draws it."""
    value = 0x811C9DC5
    for character in text:
        value = ((value ^ ord(character)) * 0x01000193) & 0xFFFFFFFF
    return value / 2**32


def evidence_slots(practice: dict) -> int:
    """How many marks the list's Evidenze cell draws: one per code, plus the other marks list.js picks from an
    invented practice's key (end["markShare"]), at most end["maxMarks"] in all; a real practice's other marks are
    unknown and not drawn."""
    count = len(practice.get("evidence", "").split())
    if practice.get("role") == "sintetica":
        share = LIST_FONT["end"]["markShare"]
        drawn = sum(1 for mark in share if _draw(f"{practice['key']}|{mark}") < share[mark])
        count += min(drawn, max(0, LIST_FONT["end"]["maxMarks"] - count))
    return count


def request_note_fits(note: str) -> bool:
    """Whether the whole request note shows on screen 9; a note cut by the window is not asserted there."""
    lines = note.split("\n")
    return sum(max(1, -(-len(line) // REQUEST_NOTE_LINE_CHARS)) for line in lines) <= REQUEST_NOTE_LINES


def _tooltip_targets(practice: dict) -> dict[int, tuple[str | None, str]]:
    targets = {}
    evidence = practice["evidence"]
    text = practice["evidenceTooltip"]
    if evidence and text and text.strip():
        # Codes stand side by side ("B V"); the tooltip shown is the B code's.
        targets[3] = ("tooltip_evidenze_b" if "B" in evidence.split() else None, text)
    for start, rows in ((6, practice["fidi"][:1]), (7, practice["guarantees"][:2])):
        for step, row in enumerate(rows, start):
            text = row.get("tooltip")
            if row.get("description") and text and text.strip():
                targets[step] = (row.get("tooltipField"), text)
    return targets


# The capture states each PEF page offers; a practice without a page (profile "pages") has none of its states.
PAGE_STEPS = {"elenco": (1, 2, 3), "soggetti": (4,), "gestione-fidi": (5, 6, 7, 8), "note": (9,)}


def available_steps(practice: dict) -> list[int]:
    """Canonical capture states actually reachable for this dossier."""
    pages = practice.get("pages", PAGE_STEPS)
    allowed = {step for page in pages for step in PAGE_STEPS[page]}
    return sorted({1, 2, 4, 5, 9, *_tooltip_targets(practice)} & allowed)


def _note_views(note: str) -> list[tuple[int, str]]:
    """Scroll offsets of the note box in the bottom states, with the text fully visible at each.

    State j scrolls the box so that paragraph j and the next one sit in it, centred, within the box's scroll
    range; the states stop once the last paragraph is fully visible. A line counts only when its whole line
    box is inside the box: the real transcriptions leave out partly hidden paragraphs.
    """
    lines = note.split("\n")  # a trailing newline is one more (empty) line, as the textarea renders it
    client = NOTE_BOX_PX - 1

    def top(index: int) -> int:
        return NOTE_PADDING_PX + index * NOTE_LINE_PX

    limit = max(0, top(len(lines)) - client)
    margin = (client - 4 * NOTE_LINE_PX) // 2
    starts = [index for index, line in enumerate(lines) if line.strip()]
    views = []
    for start in starts or [0]:
        scroll = min(max(0, top(start) - margin), limit)
        shown = [i for i in range(len(lines)) if top(i) >= scroll and top(i + 1) <= scroll + client]
        views.append((scroll, "\n".join(lines[shown[0]:shown[-1] + 1]).strip("\n") if shown else ""))
        if not starts or starts[-1] in shown:
            break
    return views


def _scheda_captures(scheda: dict) -> list[tuple[dict, dict[str, str]]]:
    values = {"ndg": scheda["ndg"], "denominazione": scheda["name"], **scheda["fields"]}
    positions = [((0, 0), {key: values[key] for key in SCHEDA_TOP_FIELDS})]
    # The outgoing rows lengthen the page: the bottom states scroll past them, and the employer value boxes they push
    # above the viewport leave the truth.
    shift = len(scheda["details"]["outgoings"]) * OUTGOING_ROW_PX
    bottom = {key: values[key] for key in SCHEDA_BOTTOM_FIELDS
              if key not in EMPLOYER_TOP_PX or EMPLOYER_TOP_PX[key] >= shift}
    for note_scroll, text in _note_views(values["note_scheda_privati"]):
        positions.append(((SCHEDA_PAGE_SCROLL + shift, note_scroll), {**bottom, "note_scheda_privati": text}))
    return [({"name": f"scheda-privati-{n:02d}", "scroll": page, "noteScroll": note}, shown)
            for n, ((page, note), shown) in enumerate(positions, 1)]


def scheda_states(scheda: dict) -> list[dict]:
    """Capture states of a Scheda Privati page, named like the screenshots of the real archive.

    scheda-privati-01 is the top of the page. Every later state is the page at its end, SCHEDA_PAGE_SCROLL plus
    OUTGOING_ROW_PX per outgoing row (so the family block and the note box stay where they are), with the note box
    scrolled by one paragraph (see _note_views), so a note of n one-line paragraphs gives max(1, n - 1) of them.
    An employer field stays in their truth only while its value box is wholly in the viewport: EMPLOYER_TOP_PX minus
    the rows' height is not negative. The page's ?scroll= and ?noteScroll= reproduce each state.
    """
    return [state for state, _ in _scheda_captures(scheda)]


SCHEDA_KEYS = (
    "professione_principale", "dal", "numero_mensilita", "retribuzione_annua_netta", "tipo_contratto",
    "datore_di_lavoro_anagrafica", "rating_ufficiale", "score_cgs", "nr_altri_componenti_nucleo",
    "di_cui_percepiscono_reddito", "importo_totale_annuo_nucleo", "note_scheda_privati", "ultima_validazione_scheda",
)


def practice_truth_record(practice: dict) -> dict[str, str]:
    """The practice's value of each extracted field, as one consolidated row per practice.

    One value per field: the header's NDG and name (a Scheda Privati of another holder keeps its own on its
    page), Tipo Pratica (else the list's code), the first credit line, a tooltip from the row whose field it
    fills, the B tooltip only for a B evidence; the 13 Scheda Privati fields when there is a scheda. A practice
    whose provenance lists the fields it states (an archive practice) gives only those: the others are unknown.
    """
    first = next(iter(practice["fidi"]), {})
    values = {
        "ndg": practice["ndg"], "denominazione": practice["name"],
        "tipo": practice["type"] or practice.get("typeCode") or "", "stato": practice["state"],
        "fase": practice["phase"], "creazione": practice["created"], "evidenze": practice["evidence"],
        "filiale_relazione": " - ".join(part for part in (practice["branch"], practice["branchName"]) if part),
        **{field: first.get(prop, "") for field, prop in CREDIT_FIELDS.items()},
        "note_della_richiesta": practice["notes"], "tooltip_descrizione_bmb": practice.get("typeName") or "",
        "tooltip_evidenze_b": practice["evidenceTooltip"] if "B" in practice["evidence"].split() else "",
        **dict.fromkeys(FINANCIAL_TOOLTIPS, ""),
    }
    for row in reversed([*practice["fidi"], *practice["guarantees"]]):
        if row.get("tooltipField"):
            values[row["tooltipField"]] = row.get("tooltip", "")
    for index in range(4):
        subject = practice["subjects"][index] if index < len(practice["subjects"]) else {}
        for field, prop in (("ndg", "ndg"), ("denominazione", "name"), ("ruolo", "role")):
            values[f"{field}_{index + 1}"] = subject.get(prop, "")
    if practice.get("scheda"):
        values.update(practice["scheda"]["fields"])
    stated = (practice.get("provenance") or {}).get("stated")
    return {key: values[key].strip() for key in CSV_LABELS if key in values and (stated is None or key in stated)}


def practice_truth_record_csv(practice: dict) -> str:
    """practice_truth_record as CSV: Chiave;Campo;Valore with the evaluator's labels as Campo."""
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(("Chiave", "Campo", "Valore"))
    writer.writerows((key, CSV_LABELS[key], value) for key, value in practice_truth_record(practice).items())
    return output.getvalue()


def practice_truth_csv(practice: dict) -> str:
    """Return evaluator CSV for screen N.png at each available canonical state (available_steps: only the
    practice's pages), then for scheda-privati-0K.png at each state of its Scheda Privati when it has one."""
    targets = _tooltip_targets(practice)
    identity = {"ndg": practice["ndg"], "denominazione": practice["name"]}
    list_identity = identity if list_name_fits(practice["name"]) else {"ndg": practice["ndg"]}
    list_fields = {**list_identity, "evidenze": practice["evidence"], "tooltip_evidenze_b": ""}
    detail = {
        **identity, "tipo": practice["type"],
        "filiale_relazione": " - ".join(part for part in (practice["branch"], practice["branchName"]) if part),
    }
    subjects = {}
    for index in range(4):
        row = practice["subjects"][index] if index < len(practice["subjects"]) else {}
        for field, prop in (("ndg", "ndg"), ("denominazione", "name"), ("ruolo", "role")):
            subjects[f"{field}_{index + 1}"] = row.get(prop, "")

    # The scalar credit contract uses FIDI row one, even on a multi-credit dossier.
    first = next(iter(practice["fidi"]), {})
    credit = {field: first.get(prop, "") for field, prop in CREDIT_FIELDS.items()}
    financial = {**detail, **credit, **dict.fromkeys(FINANCIAL_TOOLTIPS, "")}
    checkbox, slots = practice["state"] in LIST_FONT["end"]["selectable"], evidence_slots(practice)
    started = list_start_shows(practice["name"], checkbox, slots)
    screens = {
        1: {**list_fields, **{field: value for field, value in (
            ("stato", practice["state"]), ("fase", practice["phase"]), ("creazione", practice["date"])) if field in started}},
        # At the middle scroll position Creazione still shows (audit_truth.cjs; the reference's truth lists it).
        2: {**list_fields, "creazione": practice["date"]},
        4: {**detail, **subjects},
        5: financial,
        9: {**detail, **({"note_della_richiesta": practice["notes"]} if request_note_fits(practice["notes"]) else {})},
    }
    ndg_at_end, name_at_end = list_end_shows(practice["name"], checkbox, slots)
    list_end = {**({"ndg": practice["ndg"]} if ndg_at_end else {}),
                **({"denominazione": practice["name"]} if name_at_end else {})}
    for step, (field, text) in targets.items():
        # The far-right list view keeps of the identity columns what still fits (list_end_shows).
        values = {**list_end, "evidenze": practice["evidence"], "tooltip_evidenze_b": ""} if step == 3 else financial.copy()
        if field is not None:
            values[field] = text
        screens[step] = values

    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("Fotogramma", "Denominazione da attribuire", "Valore rilevato"))
    steps = available_steps(practice)
    for step, values in sorted(screens.items()):
        if step in steps:
            writer.writerows((f"screen {step}", CSV_LABELS[key], value) for key, value in values.items())
    for state, values in _scheda_captures(practice["scheda"]) if practice.get("scheda") else ():
        writer.writerows((state["name"], CSV_LABELS[key], value) for key, value in values.items())
    return output.getvalue()
