"""Turn the per-practice transcriptions into the ground-truth CSV the CLI evaluates against.

Usage: python -I assemble_gt.py <gt_json_dir> <source_root> <out_dir> [--check-only]

One place for every convention, so a convention change is one edit:
- a row exists only for a field that is on screen in that screenshot (same as the 9-screen draft);
- two deliberate blanks: "Tipo" on an Elenco whose Tipo column is out of view, and the unused
  soggetti slots up to 4;
- off-topic screenshots get no rows and are not copied to the run folder.
"""
import csv
import glob
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

Row = Tuple[str, str, str, str]  # screen_id, gt_key, value, note

TOOLTIP_BMB = "tooltip su valore campo Descrizione: BMB"
TOOLTIP_EVIDENZE_B = "tooltip su valore campo Evidenze: B"
TOOLTIP_BY_DESCRIZIONE = {
    "M.CONSAP>=80%": "tooltip su valore campo Descrizione (riga 1): M. CONSAP >= 80%",
    "CONSAPDRBIS": "tooltip su valore campo Descrizione (riga 1): CONSAP DR BIS",
    "IPOTECAIGR.": "tooltip su valore campo Descrizione (riga 2): IPOTECA I GR.",
}
SCHEMA_COLUMNS = {"NDG", "Denom.", "Tipo", "Stato", "Fase", "Creazione"}
SCHEDA_KEYS = [
    ("professione_principale", "Professione principale"),
    ("numero_mensilita", "Numero mensilità"),
    ("retribuzione_annua_netta", "Retribuzione annua netta"),
    ("tipo_contratto", "Tipo contratto"),
    ("datore_anagrafica", "DATORE DI LAVORO ANAGRAFICA"),
    ("rating_ufficiale", "RATING UFFICIALE"),
    ("score_cgs", "SCORE CGS"),
    ("nr_altri_componenti_nucleo", "Nr altri componenti nucleo familiare"),
    ("di_cui_percepiscono_reddito", "Di cui percepiscono reddito"),
    ("importo_totale_annuo_nucleo", "Importo totale annuo altri componenti nucleo familiare"),
]


def compact(text: Optional[str]) -> str:
    return re.sub(r"\s+", "", text or "").upper()


def one_line(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def screen_id(practice: str, stem: str) -> str:
    return f"{practice}__{stem}"


def header_rows(sid: str, header: Optional[Dict[str, Any]], *, with_tipo: bool = True) -> List[Row]:
    rows: List[Row] = []
    header = header or {}
    if header.get("ndg") is not None:
        rows.append((sid, "NDG", one_line(header["ndg"]), ""))
    if header.get("denominazione") is not None:
        rows.append((sid, "DENOMINAZIONE", one_line(header["denominazione"]), ""))
    if with_tipo and header.get("tipo_pratica") is not None:
        rows.append((sid, "Tipo", one_line(header["tipo_pratica"]), ""))
    if with_tipo and header.get("filiale_relazione") is not None:
        rows.append((sid, "Filiale relazione", one_line(header["filiale_relazione"]), ""))
    return rows


def elenco_rows(sid: str, shot: Dict[str, Any], out_of_schema: List[str]) -> List[Row]:
    rows: List[Row] = []
    el = shot.get("elenco") or {}
    cols = [c.strip() for c in el.get("columns_visible") or []]
    row = {k.strip(): v for k, v in (el.get("row") or {}).items()}

    def cell(name: str) -> Optional[str]:
        if name not in cols:
            return None
        value = row.get(name)
        return None if value is None else one_line(value)

    ndg = cell("NDG")
    if ndg is not None:
        rows.append((sid, "NDG", ndg, ""))
    den = cell("Denom.")
    if den is not None:
        note = "troncato a schermo con i puntini: convenzione da confermare" if den.endswith("...") else ""
        rows.append((sid, "DENOMINAZIONE", den, note))
    tipo = cell("Tipo")
    rows.append((sid, "Tipo", tipo or "", "" if tipo else "colonna Tipo non a schermo: un valore estratto conta come invenzione"))
    for name in ("Stato", "Fase", "Creazione"):
        value = cell(name)
        if value is not None:
            rows.append((sid, name, value, ""))
    if "Evidenze" in cols:
        letters = [i for i in (el.get("evidenze_icons") or []) if re.fullmatch(r"[A-Z]{1,3}", str(i).strip())]
        note = "più codici letterali nella cella: formato da confermare" if len(letters) > 1 else ""
        rows.append((sid, "Evidenze", " ".join(letters), note))

    tip = shot.get("tooltip")
    if tip and tip.get("text"):
        column = (tip.get("anchor_column") or "").strip().lower()
        value = compact(tip.get("anchor_cell_value"))
        if column == "tipo" and value == "BMB":
            rows.append((sid, TOOLTIP_BMB, one_line(tip["text"]), ""))
        elif column == "evidenze" and value == "B":
            rows.append((sid, TOOLTIP_EVIDENZE_B, one_line(tip["text"]), ""))
        else:
            out_of_schema.append(f"{sid}: Elenco, colonna {tip.get('anchor_column')!r}, valore {tip.get('anchor_cell_value')!r} -> {one_line(tip['text'])!r}")
    return rows


def soggetti_rows(sid: str, shot: Dict[str, Any]) -> List[Row]:
    rows = header_rows(sid, shot.get("header"))
    people = shot.get("soggetti") or []
    extra = f"{len(people)} soggetti a schermo: lo schema ne tiene 4" if len(people) > 4 else ""
    for i in range(4):
        person = people[i] if i < len(people) else {}
        note = extra if i == 0 else ""
        rows.append((sid, f"NDG {i + 1}", one_line(person.get("ndg")), note))
        rows.append((sid, f"DENOMINAZIONE {i + 1}", one_line(person.get("denominazione")), ""))
        rows.append((sid, f"RUOLO {i + 1}", one_line(person.get("ruolo")), ""))
    return rows


def fidi_rows(sid: str, shot: Dict[str, Any], out_of_schema: List[str]) -> List[Row]:
    rows = header_rows(sid, shot.get("header"))
    fidi = shot.get("fidi") or []
    visible = shot.get("fidi_table_visible", bool(fidi))
    if visible and fidi:
        first = fidi[0]
        note = f"{len(fidi)} fidi a schermo: lo schema valuta solo la prima riga" if len(fidi) > 1 else ""
        for key, label in (("n_fido", "n° FIDO"), ("rapporto", "Rapporto"), ("descrizione", "Descrizione"),
                           ("scadenza", "Scadenza"), ("importo", "Importo (€)"), ("tipo_op", "Tipo Op.")):
            if first.get(key) is not None:
                rows.append((sid, label, one_line(first[key]), note if key == "n_fido" else ""))
    tip = shot.get("tooltip")
    if tip and tip.get("text"):
        label = TOOLTIP_BY_DESCRIZIONE.get(compact(tip.get("anchor_cell_value")))
        if label and (tip.get("anchor_column") or "").strip().lower() == "descrizione":
            rows.append((sid, label, one_line(tip["text"]), ""))
        else:
            out_of_schema.append(f"{sid}: {tip.get('anchor_table')}, riga {tip.get('anchor_row')}, valore {tip.get('anchor_cell_value')!r} -> {one_line(tip['text'])!r}")
    return rows


def note_rows(sid: str, shot: Dict[str, Any], problems: List[str]) -> List[Row]:
    rows = header_rows(sid, shot.get("header"))
    note = shot.get("note") or {}
    text = one_line(note.get("text"))
    tab = shot.get("active_tab")
    if tab not in (None, "Note da Richiesta"):
        problems.append(f"{sid}: tab attivo {tab!r}, non 'Note da Richiesta': nota non messa in ground truth")
        return rows
    if text:
        flags = []
        if note.get("starts_at_beginning") is False:
            flags.append("inizio della nota fuori schermo")
        if note.get("cut_at_bottom"):
            flags.append("fine della nota fuori schermo")
        rows.append((sid, "Note della richiesta", text, "; ".join(flags)))
    return rows


def scheda_rows(sid: str, shot: Dict[str, Any]) -> List[Row]:
    rows = header_rows(sid, shot.get("header"), with_tipo=False)
    scheda = shot.get("scheda") or {}
    for key, label in SCHEDA_KEYS:
        if key in scheda and scheda[key] is not None:
            rows.append((sid, label, one_line(scheda[key]), ""))
    if scheda.get("professione_dal") is not None:
        other = scheda.get("datore_dal")
        rows.append((sid, "DAL", one_line(scheda["professione_dal"]),
                     f"ambiguo: a schermo c'è anche il DAL del datore di lavoro ({other}); scelto quello accanto a Professione principale"))
    if scheda.get("ultima_validazione") is not None:
        rows.append((sid, "Ultima validazione scheda privati", one_line(scheda["ultima_validazione"]),
                     "trascritto come a schermo: il suffisso relativo cambia ogni giorno, convenzione da confermare"))
    note = shot.get("note_scheda")
    if note and note.get("text") and note.get("reliable", True):
        rows.append((sid, "Note Scheda Privati", one_line(note["text"]), "il riquadro mostra poche righe per volta"))
    return rows


def consistency(practice: str, shots: Dict[str, Dict[str, Any]], problems: List[str]) -> None:
    seen: Dict[str, Counter] = defaultdict(Counter)
    where: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    def add(field: str, value: Optional[str], stem: str) -> None:
        if value is None:
            return
        value = one_line(value)
        seen[field][value] += 1
        where[(field, value)].append(stem)

    notes_text = ""
    for stem, shot in shots.items():
        header = shot.get("header") or {}
        if shot.get("kind") != "scheda":
            for key in ("ndg", "denominazione", "tipo_pratica", "n_pratica", "filiale_relazione"):
                add(f"header.{key}", header.get(key), stem)
        el = shot.get("elenco") or {}
        cols = el.get("columns_visible") or []
        for col, value in (el.get("row") or {}).items():
            # Only the columns the schema reads: the others are routinely clipped by the pinned columns.
            if col in cols and col.strip() in SCHEMA_COLUMNS:
                add(f"elenco.{col.strip()}", value, stem)
        if el and "Evidenze" in cols:
            letters = [i for i in map(str, el.get("evidenze_icons") or []) if re.fullmatch(r"[A-Z]{1,3}", i.strip())]
            add("elenco.letters", " ".join(letters), stem)
        for i, fido in enumerate([] if shot.get("kind_note") else shot.get("fidi") or []):
            for key, value in fido.items():
                add(f"fidi[{i}].{key}", value, stem)
        notes_text += " " + ((shot.get("note") or {}).get("text") or "")

    for field, counter in sorted(seen.items()):
        if len(counter) > 1:
            detail = "; ".join(f"{v!r} in {','.join(where[(field, v)])}" for v in counter)
            problems.append(f"{practice}: {field} letto in modi diversi -> {detail}")

    def only(field: str) -> Optional[str]:
        counter = seen.get(field)
        return counter.most_common(1)[0][0] if counter else None

    el_ndg, hd_ndg = only("elenco.NDG"), only("header.ndg")
    if el_ndg and hd_ndg and el_ndg.lstrip("0") != hd_ndg.lstrip("0"):
        problems.append(f"{practice}: NDG in Elenco {el_ndg} diverso dalla testata {hd_ndg}")
    n_pratica = only("header.n_pratica")
    if n_pratica and n_pratica != practice:
        problems.append(f"{practice}: N° Pratica in testata = {n_pratica}, diverso dal nome della cartella")
    rapporti = [compact(v) for field, counter in seen.items() if field.endswith(".rapporto") for v in counter]
    fics = re.search(r"FICS:\s*\d+/(\d+)", notes_text)
    if rapporti and fics and not any(r.endswith(fics.group(1)) for r in rapporti):
        problems.append(f"{practice}: nessun rapporto dei fidi termina con il numero FICS della nota ({fics.group(1)})")
    # With a single fido, its amount (small font) must equal the Elenco amount (large font).
    elenco_amounts = {one_line(v) for s in shots.values()
                      for v in [((s.get("elenco") or {}).get("row") or {}).get("Importo €")] if v}
    fidi_tables = [s.get("fidi") or [] for s in shots.values() if s.get("kind") == "fidi"]
    longest = max(fidi_tables, key=len, default=[])
    if len(longest) == 1 and len(elenco_amounts) == 1:
        amounts = {one_line(t[0].get("importo")) for t in fidi_tables if t and t[0].get("importo")}
        if amounts and amounts != elenco_amounts:
            problems.append(f"{practice}: importo del fido {sorted(amounts)} diverso dall'Importo in Elenco {sorted(elenco_amounts)}")
    for stem, shot in shots.items():
        people = shot.get("soggetti") or []
        if people and hd_ndg and one_line(people[0].get("ndg")) != hd_ndg:
            problems.append(f"{practice}: primo soggetto {people[0].get('ndg')} diverso dall'NDG di testata {hd_ndg}")


def main(json_dir: str, source_root: str, out_dir: str, check_only: bool) -> None:
    rows: List[Row] = []
    problems: List[str] = []
    out_of_schema: List[str] = []
    uncertain: List[str] = []
    offtopic: List[str] = []
    in_scope: List[Tuple[str, str]] = []
    kinds: Counter = Counter()

    for path in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        data = json.load(open(path, encoding="utf-8"))
        practice = str(data["pratica"])
        shots = data["screenshots"]
        on_disk = {os.path.splitext(f)[0] for f in os.listdir(os.path.join(source_root, practice))}
        if set(shots) != on_disk:
            problems.append(f"{practice}: file trascritti diversi da quelli su disco: mancano {sorted(on_disk - set(shots))}, in più {sorted(set(shots) - on_disk)}")
        consistency(practice, shots, problems)
        for stem, shot in shots.items():
            sid = screen_id(practice, stem)
            kind = shot.get("kind")
            kinds[kind] += 1
            for item in shot.get("uncertain") or []:
                uncertain.append(f"{sid}: {item}")
            if shot.get("kind_note"):
                uncertain.append(f"{sid}: {shot['kind_note']}")
            if kind == "offtopic":
                offtopic.append(f"{sid}: {shot.get('description')}")
                continue
            before = len(rows)
            if kind == "elenco":
                rows += elenco_rows(sid, shot, out_of_schema)
            elif kind == "soggetti":
                rows += soggetti_rows(sid, shot)
            elif kind == "fidi":
                rows += fidi_rows(sid, shot, out_of_schema)
            elif kind == "note":
                rows += note_rows(sid, shot, problems)
            elif kind == "scheda":
                rows += scheda_rows(sid, shot)
            else:
                problems.append(f"{sid}: tipo pagina sconosciuto {kind!r}")
                continue
            if len(rows) == before:
                problems.append(f"{sid}: nessuna riga di ground truth prodotta")
            in_scope.append((practice, stem))

    print(f"screenshots by kind: {dict(kinds)}")
    print(f"in scope: {len(in_scope)}  ground-truth rows: {len(rows)}  blank rows: {sum(1 for r in rows if not r[2])}")
    print(f"rows per field: {dict(Counter(r[1] for r in rows).most_common())}")
    for title, items in (("PROBLEMS", problems), ("TOOLTIP FUORI SCHEMA", out_of_schema), ("UNCERTAIN", uncertain), ("OFFTOPIC", offtopic)):
        print(f"\n== {title} ({len(items)})")
        for item in items:
            print("  " + item)
    if check_only:
        return

    run_dir = os.path.join(out_dir, "input")
    os.makedirs(run_dir, exist_ok=True)
    for practice, stem in in_scope:
        shutil.copyfile(os.path.join(source_root, practice, stem + ".png"),
                        os.path.join(run_dir, screen_id(practice, stem) + ".png"))
    with open(os.path.join(run_dir, "dati.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["Fotogramma", "Denominazione da attribuire", "Valore rilevato", "Nota"])
        writer.writerows(rows)
    json.dump({"problems": problems, "tooltip_fuori_schema": out_of_schema, "uncertain": uncertain, "offtopic": offtopic},
              open(os.path.join(out_dir, "controlli.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote {len(in_scope)} images and dati.csv to {run_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], "--check-only" in sys.argv)
