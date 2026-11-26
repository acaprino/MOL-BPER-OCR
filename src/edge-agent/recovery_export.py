"""Offline emergency workbooks from the same recovered sessions used by the GUI."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from local_extraction_client import LocalExtractionClient


def _export_session(client: LocalExtractionClient, job: str, index: int, destination: Path,
                    report: TextIO) -> None:
    accepted, published = client.capture_counts(job)
    pending = client.pending_capture_sequences(job)
    has_draft = client.get_cell_draft(job) is not None
    state = "PARZIALE" if pending or has_draft else "COMPLETA"
    report.write(f"\n{client.session_label(job)} — {state}\n")
    report.write(f"Fotogrammi in ordine disponibili per l'Excel: {published} su {accepted}\n")
    numbers = ", ".join(str(sequence + 1) for sequence in pending)
    report.write(f"Fotogrammi da elaborare: {numbers or 'nessuno'}\n")
    report.write(f"Risultati completati dopo il primo fotogramma in attesa: "
                 f"{accepted - published - len(pending)}\n")
    report.write(f"Bozza da confermare: {'presente' if has_draft else 'assente'}\n")
    if client.practice_count(job):
        suffix = "-PARZIALE" if state == "PARZIALE" else ""
        workbook = destination / f"sessione-{index:03}{suffix}.xlsx"
        count = client.export_workbook(job, str(workbook))
        report.write(f"Pratiche esportate: {count} ({workbook.name})\n")
    else:
        report.write("Nessuna pratica con dati disponibili per l'Excel.\n")


def export_recovery(source_directory: Path, destination: Path) -> None:
    """Write an operator-readable report and one workbook for each exportable session."""
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    report_path = destination / "riepilogo.txt"
    with report_path.open("x", encoding="utf-8-sig") as report:
        report.write("Esportazione di emergenza BPER\n"
                     "I fotogrammi sono numerati da 1 in ordine di cattura.\n"
                     "Ogni Excel include i dati consecutivi già elaborati e le correzioni confermate.\n"
                     "Riapri l'Edge Agent per elaborare i fotogrammi in attesa o confermare una bozza.\n")
        try:
            client = LocalExtractionClient(recovery_dir=source_directory, export_only=True)
            try:
                if not client.recovered_jobs:
                    report.write("\nL'archivio non contiene sessioni con fotogrammi acquisiti.\n")
                for index, job in enumerate(client.recovered_jobs, start=1):
                    _export_session(client, job, index, destination, report)
                    report.flush()
            finally:
                client.shutdown()
        except Exception as exc:
            report.write(f"\nEsportazione interrotta. {exc}\n")
            raise
        report.write("\nEsportazione di emergenza terminata.\n")
    print(f"Esportazione di emergenza terminata. Riepilogo: {report_path}")
