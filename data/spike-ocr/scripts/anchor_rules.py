"""Throwaway spike: extract the BPER fields from OCR boxes with text anchors, no model.

Read first, crop after: the whole screenshot is OCR'd once (RapidOCR boxes), then
each field is located relative to a text anchor ("NDG:", "Filiale relazione:",
the column headers of each table). Thresholds scale with the median text height,
so the same rules run on the 848 px references and the ~1890 px live frames.
"""

import re
from dataclasses import dataclass
from statistics import median
from typing import Dict, List, Optional, Tuple


@dataclass
class Box:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def to_boxes(lines: List[dict]) -> List[Box]:
    out = []
    for ln in lines:
        xs = [p[0] for p in ln["box"]]
        ys = [p[1] for p in ln["box"]]
        out.append(Box(ln["text"].strip(), min(xs), min(ys), max(xs), max(ys)))
    return [b for b in out if b.text]


def rows_of(boxes: List[Box], tol: float) -> List[List[Box]]:
    """Group boxes into visual lines: same line when their vertical centers are within tol."""
    rows: List[List[Box]] = []
    for b in sorted(boxes, key=lambda b: b.cy):
        if rows and abs(median([x.cy for x in rows[-1]]) - b.cy) <= tol:
            rows[-1].append(b)
        else:
            rows.append([b])
    return [sorted(r, key=lambda b: b.x0) for r in rows]


def line_text(row: List[Box]) -> str:
    return " ".join(b.text for b in row)


def find(boxes: List[Box], pattern: str) -> List[Box]:
    rx = re.compile(pattern, re.I)
    return [b for b in boxes if rx.search(b.text)]


# ============================================================ page family

def page_family(boxes: List[Box]) -> str:
    n = {norm(b.text) for b in boxes}
    joined = " ".join(b.text.lower() for b in boxes)
    if "notaallistruttoria" in "".join(n) or "nota all'istruttoria" in joined:
        return "other"
    if any("notadellarichiesta" in t for t in n):
        return "note"
    if any(t == "fidi" for t in n) and any(t == "garanzie" for t in n):
        return "fidi"
    if any(t.startswith("ruolo") for t in n) and any("faseddirecupero" in t or "fasedirecupero" in t for t in n):
        return "soggetti"
    if any("filtriattivi" in t for t in n) or "risultati" in joined:
        return "list"
    return "other"


# ============================================================ helpers for tables

def header_columns(row: List[Box], names: Dict[str, str]) -> List[Tuple[str, Box]]:
    """Map header boxes to schema keys; names maps a normalized header (or its visible suffix) to a key."""
    cols = []
    for b in row:
        t = norm(b.text)
        for header, key in names.items():
            if len(t) >= 3 and (t == header or header.endswith(t) or t.startswith(header)):
                cols.append((key, b))
                break
    return cols


def column_of(b: Box, cols: List[Tuple[str, Box]]) -> Optional[str]:
    """Nearest header by horizontal center, within the band between neighbouring headers."""
    if not cols:
        return None
    best = min(cols, key=lambda kb: abs(kb[1].cx - b.cx))
    return best[0]


def join_cells(cells: List[Box]) -> str:
    return " ".join(c.text for c in sorted(cells, key=lambda c: (round(c.cy), c.x0))).strip()


# ============================================================ extraction per family

def detail_header(boxes: List[Box], rows: List[List[Box]], fields: Dict[str, str]) -> None:
    for b in boxes:
        m = re.search(r"NDG:?\s*(\d{6,})\s*-\s*(.+)$", b.text)
        if m and "ndg" not in fields:
            fields["ndg"], fields["denominazione"] = m.group(1), m.group(2).strip()
    for row in rows:
        text = line_text(row)
        m = re.search(r"Tipo Pratica:?\s*(.+?)\s*-\s*N", text)
        if m and "tipo" not in fields:
            fields["tipo"] = m.group(1).strip()
        m = re.search(r"Filiale relazione:?\s*(.+)$", text)
        if m and "filiale_relazione" not in fields:
            # Stop at the next label on the same visual line, if any.
            fields["filiale_relazione"] = re.split(r"\s{2,}|[A-Z][a-z]+ [a-z]+:", m.group(1))[0].strip()


LIST_HEADERS = {
    "abi": "_abi", "ndg": "ndg", "denom": "denominazione", "tipo": "tipo", "importo": "_importo",
    "stato": "stato", "fase": "fase", "creazione": "creazione", "dataassdel": "_data_ass", "assegnata": "_assegnata",
    "dest": "_dest", "delib": "_delib", "dr": "_dr", "area": "_area", "filiale": "_filiale", "evidenze": "evidenze",
}


def extract_list(boxes: List[Box], rows: List[List[Box]], fields: Dict[str, str]) -> None:
    header_idx = next((i for i, r in enumerate(rows)
                       if len(header_columns(r, LIST_HEADERS)) >= 4 and "risultato" not in line_text(r).lower()), None)
    if header_idx is None or header_idx + 1 >= len(rows):
        return
    cols = header_columns(rows[header_idx], LIST_HEADERS)
    data = rows[header_idx + 1]
    if "nessun" in line_text(data).lower():
        return
    for b in data:
        key = column_of(b, cols)
        if not key or key.startswith("_"):
            continue
        value = b.text
        if key == "evidenze":
            m = re.match(r"^([A-Z])\b", value)
            if not m:
                continue
            value = m.group(1)
        fields.setdefault(key, value)
    # A tooltip floats between the data row and the next block (the export button line).
    stop_idx = next((i for i in range(header_idx + 2, len(rows)) if "esporta" in line_text(rows[i]).lower()), None)
    for r in rows[header_idx + 2: stop_idx]:
        for b in r:
            if len(b.text) > 3 and not re.fullmatch(r"[\d/.,\s]+", b.text):
                fields.setdefault("tooltip_evidenze_b", b.text)


SOGGETTI_HEADERS = {"ndg": "ndg", "denominazione": "denominazione", "ruolo": "ruolo",
                    "fasedirecuperoinserimento": "_fase", "privacy": "_privacy", "qav": "_qav", "azioni": "_azioni"}


def extract_soggetti(boxes: List[Box], rows: List[List[Box]], fields: Dict[str, str], tol: float) -> None:
    header_idx = next((i for i, r in enumerate(rows) if len(header_columns(r, SOGGETTI_HEADERS)) >= 3), None)
    if header_idx is None:
        return
    cols = [c for c in header_columns(rows[header_idx], SOGGETTI_HEADERS)]
    below = [b for r in rows[header_idx + 1:] for b in r
             if not re.search(r"avvia step|refresh|procedi", b.text, re.I)]
    anchors = sorted([b for b in below if column_of(b, cols) == "ndg" and re.fullmatch(r"\d{6,}", b.text)],
                     key=lambda b: b.cy)
    for i, a in enumerate(anchors[:4], start=1):
        top = a.cy - 2.2 * tol
        bottom = anchors[i].cy - 2.2 * tol if i < len(anchors) else a.cy + 2.2 * tol
        cells = [b for b in below if top <= b.cy < bottom]
        fields[f"ndg_{i}"] = a.text
        fields[f"denominazione_{i}"] = join_cells([c for c in cells if column_of(c, cols) == "denominazione"])
        fields[f"ruolo_{i}"] = join_cells([c for c in cells if column_of(c, cols) == "ruolo"])


FIDI_HEADERS = {"nfido": "n_fido", "rapporto": "rapporto", "descrizione": "descrizione", "scadenza": "scadenza",
                "importo": "importo_euro", "tipoop": "tipo_op", "ndg": "_ndg"}
TOOLTIP_RX = r"^\s*\d{2,6}\s*-\s*\S"


def extract_fidi(boxes: List[Box], rows: List[List[Box]], fields: Dict[str, str], tol: float) -> None:
    fidi_top = next((b for b in boxes if norm(b.text) == "fidi"), None)
    gar_top = next((b for b in boxes if norm(b.text) == "garanzie"), None)
    tot_gar = next((b for b in boxes if "totalegaranzieproposte" in norm(b.text)), None)
    if not (fidi_top and gar_top):
        return
    header_idx = next((i for i, r in enumerate(rows)
                       if r[0].cy > fidi_top.cy and len(header_columns(r, FIDI_HEADERS)) >= 4), None)
    if header_idx is None:
        return
    header = rows[header_idx]
    fido_headers = [b for b in header if norm(b.text) == "nfido"]
    right_limit = fido_headers[1].x0 if len(fido_headers) > 1 else float("inf")
    cols = [(k, b) for k, b in header_columns(header, FIDI_HEADERS) if b.x1 <= right_limit]
    bottom = tot_gar.cy if tot_gar else gar_top.cy
    body = [b for r in rows[header_idx + 1:] for b in r
            if b.cy < bottom and b.x1 <= right_limit and not re.search(TOOLTIP_RX, b.text)]
    anchors = sorted([b for b in body if re.fullmatch(r"F\d+", b.text)], key=lambda b: b.cy)
    if anchors:
        a = anchors[0]
        top = a.cy - 2.2 * tol
        end = anchors[1].cy - 2.2 * tol if len(anchors) > 1 else bottom
        cells = [b for b in body if top <= b.cy < end]
        fields["n_fido"] = a.text
        for key in ("rapporto", "descrizione", "scadenza", "importo_euro", "tipo_op"):
            value = join_cells([c for c in cells if column_of(c, cols) == key])
            if value:
                fields[key] = value
    # Tooltips: "code - description" text floating over the tables. Its row decides the field.
    g_rows = sorted([b for b in boxes if re.fullmatch(r"G\d+", b.text) and b.cy > gar_top.cy], key=lambda b: b.cy)
    for t in find(boxes, TOOLTIP_RX):
        if t.cy < gar_top.cy:
            fields.setdefault("tooltip_descrizione_m_consap", t.text)
        else:
            above = [g for g in g_rows if g.y0 <= t.y0]
            row = len(above) if above else 1
            key = "tooltip_descrizione_consap_dr_bis" if row <= 1 else "tooltip_descrizione_ipoteca"
            fields.setdefault(key, t.text)


def extract_note(boxes: List[Box], rows: List[List[Box]], fields: Dict[str, str]) -> None:
    head = next((b for b in boxes if "notadellarichiesta" in norm(b.text)), None)
    if not head:
        return
    stop = min([b.cy for b in boxes if re.search(r"^(procedi|avvia step)", b.text, re.I) and b.cy > head.cy],
               default=float("inf"))
    parts = []
    for r in rows:
        if head.cy < r[0].cy < stop:
            text = line_text([b for b in r if b.x0 >= head.x0 - 3 * head.h])
            if text and not re.search(r"\(\d+\)\s*del\s*\d{2}/\d{2}/\d{4}", text):
                parts.append(text)
    if parts:
        fields["note_della_richiesta"] = " ".join(parts)


def extract(lines: List[dict]) -> Tuple[str, Dict[str, str]]:
    boxes = to_boxes(lines)
    if not boxes:
        return "other", {}
    tol = 0.5 * median(b.h for b in boxes)
    rows = rows_of(boxes, tol)
    family = page_family(boxes)
    fields: Dict[str, str] = {}
    if family in ("soggetti", "fidi", "note"):
        detail_header(boxes, rows, fields)
    if family == "list":
        extract_list(boxes, rows, fields)
    elif family == "soggetti":
        extract_soggetti(boxes, rows, fields, tol)
    elif family == "fidi":
        extract_fidi(boxes, rows, fields, tol)
    elif family == "note":
        extract_note(boxes, rows, fields)
    return family, {k: v for k, v in fields.items() if v}
