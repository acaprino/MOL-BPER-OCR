"""Assign a lot delivered as practice sheets to the G8 groups, on a Modal container.

Invoke from ``src/``:
    modal run -m training.modal_lot --lot NAME --workbook ABS --zips ABS,ABS --truth-dir ABS --previous ABS --out ABS

The workbook, the delivered screenshots and the earlier truth tables go to Modal: everything that reads them runs
there, because this PC is often short of memory. Back comes the assignment manifest, written at ``--out``. It holds
no field value of the lot other than its NDGs, and no reviewer note.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import modal

from training.g8_assignment import assign_lot
from training.practice_sheets import read_practice_sheets, screen_name

ROOT = Path(__file__).resolve().parents[2]
RULE = "docs/next-ver-plan.md §5.4, regole 2 e 3"
SEAL = ("Le pratiche in conferma restano sigillate fino al congelamento del candidato: niente OCR, metriche o "
        "ispezioni per lo sviluppo sulle loro schermate o sulla loro verità.")

app = modal.App("bper-lot-assignment")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("Pillow>=10.0.0", "numpy", "openpyxl>=3.1.2", "pandas", "python-dotenv",
                 "langchain-core", "langchain-openai", "langchain-google-genai")
    .env({"PROMPTS_DIR": "/opt/prompts"})
    .add_local_dir(str(ROOT / "prompts"), "/opt/prompts")
    .add_local_python_source("training", "extraction", "prompt_store")
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _table(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))


def _delivered_screens(archives: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    """Every delivered screenshot under its screen id, hashed from the bytes and the decoded pixels."""
    from PIL import Image

    screens: dict[str, dict[str, Any]] = {}
    for archive_name, data in archives.items():
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                practice, file_name = member.split("/")
                name = screen_name(file_name)
                screen = f"{practice}__{name}"
                if screen in screens:
                    raise ValueError(f"Due file per la schermata {screen}: {member}.")
                content = archive.read(member)
                with Image.open(io.BytesIO(content)) as picture:
                    pixels = _sha256(picture.convert("RGB").tobytes())
                screens[screen] = {"path": f"data/pratiche/{practice}/{name}.png", "image_sha256": _sha256(content),
                                   "pixel_sha256": pixels, "consegna": f"{archive_name}:{member}"}
    return screens


@app.function(image=image, cpu=2.0, memory=8192, timeout=1200, retries=0)
def assign(workbook: bytes, archives: dict[str, bytes], truth: bytes, earlier_screens: bytes,
           need: dict[str, dict[str, int]]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "lotto.xlsx"
        path.write_bytes(workbook)
        records = read_practice_sheets(path)
    screens = _delivered_screens(archives)
    reviewed, delivered = {r["practice"] for r in records}, {s.split("__", 1)[0] for s in screens}
    if reviewed != delivered:
        raise ValueError(f"Pratiche senza foglio o senza schermate: {sorted(reviewed ^ delivered)}.")
    pages = {r["screen"] for r in records}
    if pages - set(screens):
        raise ValueError(f"Pagine senza schermata: {sorted(pages - set(screens))}.")
    result = assign_lot(records, screens, _table(truth), _table(earlier_screens), need)
    result["righe"] = {practice: {"nel_vocabolario": sum(r["practice"] == practice and bool(r["field"]) for r in records),
                                  "fuori_vocabolario": sum(r["practice"] == practice and not r["field"] for r in records)}
                       for practice in sorted(reviewed, key=int)}
    result["schermate"] = dict(sorted(screens.items()))
    return result


@app.local_entrypoint()
def main(lot: str, workbook: str, zips: str, truth_dir: str, previous: str, out: str, note: str = "") -> None:
    workbook_data = Path(workbook).read_bytes()
    archives = {Path(path).name: Path(path).read_bytes() for path in zips.split(",")}
    truth = Path(truth_dir)
    need = json.loads(Path(previous).read_text(encoding="utf-8"))["fabbisogno_residuo"]
    result = assign.remote(workbook_data, archives, (truth / "ground_truth.csv").read_bytes(),
                           (truth / "screens.csv").read_bytes(), need)
    manifest = {
        "lotto": lot, "regola": RULE,
        "interpretazione": ("Fabbisogno iniziale: il residuo del lotto precedente. Riduzione = numero di campi scoperti "
                            "non vuoti della pratica il cui fabbisogno nel gruppo è ancora positivo. A parità (anche zero) "
                            "i casi di parità si alternano conferma, validazione estesa, ... Una pratica con un'identità "
                            "già presente in un gruppo segue quel gruppo. Gli NDG in ndg_istituzionali sono di enti, non di "
                            "clienti, e non legano due pratiche (ADR 0024). Nessuna pratica è esclusa: le identità in comune "
                            "con v3.1 sono registrate."),
        "workbook": Path(workbook).name, "workbook_sha256": _sha256(workbook_data),
        "consegne_sha256": {name: _sha256(data) for name, data in archives.items()},
        "fabbisogno_iniziale": need, **result, "sigillo": SEAL,
    }
    if note:
        manifest["nota"] = note
    Path(out).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("gruppi", "fabbisogno_residuo", "ndg_istituzionali", "righe")},
                     ensure_ascii=False, indent=1), flush=True)
    print(json.dumps({"schermate": len(manifest["schermate"]),
                      "identita_in_comune_v3_1": manifest["isolamento_v3_1"]["identita_in_comune"],
                      "motivi": {d["pratica"]: f"{d['gruppo']}: {d['motivo']}, {d['campi_scoperti']}"
                                 for d in manifest["decisioni"]}}, ensure_ascii=False, indent=1), flush=True)
