"""Build a self-contained copy of the local capture simulator."""

from base64 import b64encode
from collections.abc import Sequence
import json
from pathlib import Path
import re

from bper_simulator_catalog import DEFAULT_DB, catalog_schede, ensure_database, read_catalog
from bper_simulator_data import REFERENCE_CSV, SITE_ORIGINS, reference_practice, site_reference_png
from bper_simulator_truth import CSV_LABELS, practice_truth_csv, practice_truth_record_csv
from serve_bper_simulator import ROUTES, SCHEDA_PAGE


# Only process tags in the source template, never text in an inlined asset.
RESOURCE_TAG = re.compile(
    r'<link\s+rel="stylesheet"\s+href="(?P<css>/[\w/-]+\.css)"\s*/?>'
    r'|<script\s+(?:defer\s+)?src="(?P<js>/[\w/-]+\.js)"\s*>\s*</script>'
    r'|</body>'
)


def inline_page(url: str, scripts: list[str]) -> str:
    """Return the page served at `url` with its own styles and scripts inlined after `scripts`."""
    scripts = list(scripts)

    def inline(match: re.Match[str]) -> str:
        if asset := match.group("css"):
            return "<style>\n" + ROUTES[asset][0].read_text(encoding="utf-8") + "\n</style>"
        if asset := match.group("js"):
            source = ROUTES[asset][0].read_text(encoding="utf-8")
            if "</script" in source.lower():
                raise ValueError(f"{asset} contains an unsafe inline script terminator")
            scripts.append(f"<script>\n{source}\n</script>")
            return ""
        # Inline scripts have no defer behavior. Start once the body exists.
        return "\n".join([*scripts, "</body>"])

    return RESOURCE_TAG.sub(inline, ROUTES[url][0].read_text(encoding="utf-8"))


def export_simulator(path: Path, *, db_path: Path = DEFAULT_DB, include_reference: bool = False,
                     include_archive: bool = False, include_test: bool = False, profiles: Sequence[Path] = ()) -> None:
    """Inline the site and an evaluable snapshot of the catalogue (see read_catalog for the flags)."""
    if path.resolve() == db_path.resolve() or (path.exists() and db_path.exists() and path.samefile(db_path)):
        raise ValueError("Il file HTML e il database devono avere percorsi distinti.")
    ensure_database(db_path)
    catalog = read_catalog(db_path, include_reference, include_archive=include_archive,
                           include_test=include_test, profiles=profiles)
    payload = {
        **catalog,
        "truth": {practice["key"]: practice_truth_csv(practice) for practice in catalog["practices"]},
        "practiceTruth": {practice["key"]: practice_truth_record_csv(practice) for practice in catalog["practices"]},
        # The truth's field labels, so that audit_truth.cjs reads the truth rows by field.
        "fieldLabels": CSV_LABELS,
        # app.js swaps in this page when the file is opened at #/schede/<ndg>/<id>.
        "schedaPage": inline_page(SCHEDA_PAGE, []),
        "schede": catalog_schede(catalog),
    }
    if include_reference:
        payload["practice"] = reference_practice()
        payload["referenceTruth"] = REFERENCE_CSV.read_text(encoding="utf-8-sig")
        payload["screens"] = {
            str(step): "data:image/png;base64," + b64encode(site_reference_png(step)).decode("ascii")
            for step in SITE_ORIGINS
        }
    # A literal </script> in a practice note would end the data script early.
    config = json.dumps(payload, separators=(",", ":")).replace("<", r"\u003c")
    result = inline_page("/", [f"<script>window.BperOffline = {config};</script>"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result, encoding="utf-8")
