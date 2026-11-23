"""Avvia il simulatore BPER su loopback oppure esportalo in un unico file HTML."""

import argparse
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bper_simulator_catalog import DEFAULT_DB, catalog_schede, ensure_database, read_catalog
from bper_simulator_data import SITE_ORIGINS, reference_practice, site_reference_png
from bper_simulator_truth import practice_truth_csv, practice_truth_record_csv

SIMULATOR_DIR = Path(__file__).resolve().parent / "site"
# Scheda Privati is a separate application; its real URL is /schede/SchedaPrivati/#/schede/<ndg>/<id>.
SCHEDA_PAGE = "/schede/SchedaPrivati/"
REFERENCE_ROUTES = {f"/reference/{step}.png": step for step in SITE_ORIGINS}
ROUTES = {
    "/": (SIMULATOR_DIR / "index.html", "text/html; charset=utf-8"),
    **{
        f"/{name}.js": (SIMULATOR_DIR / f"{name}.js", "text/javascript; charset=utf-8")
        for name in ("app", "list", "detail", "docs", "home", "search", "loading", "pef-extra")
    },
    **{
        f"/{name}.css": (SIMULATOR_DIR / f"{name}.css", "text/css; charset=utf-8")
        for name in ("app", "list", "detail", "docs", "home", "search", "loading", "pef-extra")
    },
    SCHEDA_PAGE: (SIMULATOR_DIR / "scheda" / "index.html", "text/html; charset=utf-8"),
    SCHEDA_PAGE + "scheda.css": (SIMULATOR_DIR / "scheda" / "scheda.css", "text/css; charset=utf-8"),
    SCHEDA_PAGE + "scheda.js": (SIMULATOR_DIR / "scheda" / "scheda.js", "text/javascript; charset=utf-8"),
}


class SimulatorServer(ThreadingHTTPServer):
    # Chrome opens six connections per page and tests run pages side by side: past the standard queue of 5 Windows
    # refuses a connection, and a script of the page goes missing.
    request_queue_size = 64
    db_path: Path
    include_reference: bool
    include_archive: bool
    include_test: bool
    profiles: list[Path]


class SimulatorHandler(BaseHTTPRequestHandler):
    server: SimulatorServer

    def do_GET(self) -> None:
        self._serve_file()

    def do_HEAD(self) -> None:
        self._serve_file()

    def _serve_file(self) -> None:
        # Reject foreign DNS names even if a browser resolves them to loopback.
        host = self.headers.get("Host", "").partition(":")[0].lower()
        if host not in ("127.0.0.1", "localhost"):
            self.send_error(403)
            return
        request_path = self.path.partition("?")[0]
        if request_path == "/api/practices.json" or (
            request_path.startswith(("/api/truth/", "/api/truth-practice/")) and request_path.endswith(".csv")
        ) or (request_path.startswith("/api/scheda/") and request_path.endswith(".json")):
            try:
                catalog = read_catalog(self.server.db_path, self.server.include_reference,
                                       include_archive=self.server.include_archive,
                                       include_test=self.server.include_test, profiles=self.server.profiles)
                if request_path == "/api/practices.json":
                    body = json.dumps(catalog, ensure_ascii=False).encode("utf-8")
                    content_type = "application/json; charset=utf-8"
                elif request_path.startswith("/api/scheda/"):
                    # Only a dictionary lookup: the NDG never becomes a file path.
                    scheda = catalog_schede(catalog).get(request_path.removeprefix("/api/scheda/").removesuffix(".json"))
                    if scheda is None:
                        self.send_error(404)
                        return
                    body = json.dumps(scheda, ensure_ascii=False).encode("utf-8")
                    content_type = "application/json; charset=utf-8"
                else:
                    # Per screen (/api/truth/) or one row per field of the practice (/api/truth-practice/).
                    per_screen = request_path.startswith("/api/truth/")
                    key = request_path.rpartition("/")[2].removesuffix(".csv")
                    practice = next((p for p in catalog["practices"] if p["key"] == key), None)
                    if practice is None:
                        self.send_error(404)
                        return
                    render = practice_truth_csv if per_screen else practice_truth_record_csv
                    body = render(practice).encode("utf-8-sig")
                    content_type = "text/csv; charset=utf-8"
            except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
                self.log_error("Invalid synthetic database or Scheda Privati: %s", exc)
                self.send_error(500)
                return
        elif self.server.include_reference and request_path == "/reference/practice.json":
            try:
                body = json.dumps(reference_practice(), ensure_ascii=False).encode("utf-8")
            except (OSError, ValueError, KeyError) as exc:
                self.log_error("Invalid reference practice: %s", exc)
                self.send_error(500)
                return
            content_type = "application/json; charset=utf-8"
        elif self.server.include_reference and request_path in REFERENCE_ROUTES:
            try:
                body = site_reference_png(REFERENCE_ROUTES[request_path])
            except FileNotFoundError:
                self.send_error(404)
                return
            except (ImportError, OSError) as exc:
                self.log_error("Cannot generate website reference: %s", exc)
                self.send_error(500)
                return
            content_type = "image/png"
        else:
            route = ROUTES.get(request_path)
            if route is None:
                self.send_error(404)
                return
            path, content_type = route
            try:
                body = path.read_bytes()
            except FileNotFoundError:
                self.send_error(404)
                return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        if self.command == "GET":
            self.wfile.write(body)


def create_server(port: int = 8765, *, db_path: Path = DEFAULT_DB, include_reference: bool = False,
                  include_archive: bool = False, include_test: bool = False,
                  profiles: Sequence[Path] = ()) -> SimulatorServer:
    ensure_database(db_path)
    # An invalid profile file, or one reusing a key of the catalogue, stops the start instead of every request.
    read_catalog(db_path, include_reference, include_archive=include_archive, include_test=include_test,
                 profiles=profiles)
    server = SimulatorServer(("127.0.0.1", port), SimulatorHandler)
    server.db_path = db_path
    server.include_reference = include_reference
    server.include_archive = include_archive
    server.include_test = include_test
    server.profiles = list(profiles)
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, metavar="FILE",
                        help=f"Database SQLite sintetico, creato al primo avvio (predefinito: {DEFAULT_DB})")
    parser.add_argument("--include-reference", action="store_true",
                        help="Includi anche la pratica di riferimento e i ritagli originali del sito")
    parser.add_argument("--include-archive", action="store_true",
                        help="Includi le pratiche reali dell'archivio data/dataset (addestramento e controllo)")
    parser.add_argument("--include-test", action="store_true",
                        help="Includi anche le pratiche con ruolo test. Restano chiuse fino a un candidato congelato "
                             "(ADR 0027): per averle servono --include-archive e questo flag, scelti apposta")
    parser.add_argument("--profiles", type=Path, action="append", default=[], metavar="FILE",
                        help="File di profili di pratiche da aggiungere al catalogo (ripetibile)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--port", type=int, default=8765, help="Porta locale (predefinita 8765)")
    mode.add_argument("--export", type=Path, metavar="FILE", help="Salva il simulatore come HTML offline")
    args = parser.parse_args()
    db = args.db or DEFAULT_DB
    if args.db is None:
        # Only the launcher's default file is replaced when it is of an older version. A named one is
        # checked, and refused, by the export or the server below.
        try:
            backup = ensure_database(db, replace_older=True)
        except (OSError, sqlite3.Error, ValueError) as exc:
            parser.exit(1, f"Impossibile usare il database del simulatore: {exc}\n")
        if backup is not None:
            print(f"Database di una versione precedente conservato in {backup}; creato un nuovo {db.name}.")
    if args.export is not None:
        from bper_simulator_export import export_simulator

        try:
            export_simulator(args.export, db_path=db, include_reference=args.include_reference,
                             include_archive=args.include_archive, include_test=args.include_test,
                             profiles=args.profiles)
        except (ImportError, OSError, ValueError, sqlite3.Error) as exc:
            parser.exit(1, f"Impossibile esportare il simulatore: {exc}\n")
        print(f"Simulatore esportato in {args.export.resolve()}")
        return
    if not 0 <= args.port <= 65535:
        parser.error("La porta deve essere compresa tra 0 e 65535.")
    try:
        server = create_server(args.port, db_path=db, include_reference=args.include_reference,
                               include_archive=args.include_archive, include_test=args.include_test,
                               profiles=args.profiles)
    except (OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(1, f"Impossibile avviare il simulatore: {exc}\n")
    with server:
        print(f"Simulatore BPER: http://127.0.0.1:{server.server_port}/  (Ctrl+C per uscire)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
