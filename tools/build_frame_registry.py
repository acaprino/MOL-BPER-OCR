"""Build the frame registry: every reference frame mapped to its cluster.

The registry is the index over tests/fixtures/frames. For each frame it records
which cluster it belongs to, who proposed that, and the rectangle the application
area was found at, so the crop is reproducible from the committed frame and does
not need committing itself.

Clusters are not just the nine process pages. The negatives split three ways
because they are not equally hard, and a rejection threshold calibrated on the
easy ones is worth nothing against the hard ones:

    1..9         a page of the BPER P1 process (see processes/bper-p1.json)
    altro-bper   BPER Gestione Pratiche, outside process P1 (e.g. Gestione
                 Documentale, reached from the navigator's Funzioni). The hard
                 negative: same application, same styling, must still be refused.
    altro-app    a different application entirely (qtask underwriting, iSpace,
                 browser chrome)
    altro-nulla  black frame, transition, popup: no usable content

Two proposals are kept per frame rather than one verdict. `gemini` is the batch
labelling run; `claude` is an independent review by a different model family,
which is what makes agreement meaningful. Neither is human ground truth, and the
registry says so rather than implying otherwise.

    python tools/build_frame_registry.py --labels <labels.json> --review <review.json>
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Optional

FRAMES = Path("tests/fixtures/frames")
VIDEO_DIRS = {
    "raw_v1": "20250919-parte02",
    "raw_v2": "bpimutui-surroga",
    "raw_v3": "20250925-controllo-schermo",
}

# gemini answered with page names; the registry speaks cluster ids
NAME_TO_CLUSTER = {
    "Risultato ricerca": "1",
    "Risultato ricerca - Colonne estese": "2",
    "Risultato ricerca - Tooltip mostrata": "3",
    "Elenco Soggetti": "4",
    "Gestione Fidi e Garanzie": "5",
    "Gestione Fidi e Garanzie - Tooltip Descrizione Fidi": "6",
    "Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 1)": "7",
    "Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 2)": "8",
    "Note da Richiesta": "9",
}


PAGE_NAMES = {v: k for k, v in NAME_TO_CLUSTER.items()}


def _cluster_from_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return NAME_TO_CLUSTER.get(name, "altro")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True, help="labels.json from the batch labelling run")
    ap.add_argument("--review", default="", help="review json with the independent pass")
    ap.add_argument("--out", default=str(FRAMES / "registry.json"))
    args = ap.parse_args()

    labels = {r["file"]: r for r in json.loads(Path(args.labels).read_text(encoding="utf-8"))
              if r.get("file")}

    review: Dict[str, str] = {}
    if args.review and Path(args.review).exists():
        blob = json.loads(Path(args.review).read_text(encoding="utf-8"))
        for sheet in blob.get("sheets", {}).values():
            for stem, cluster in sheet.items():
                review[f"{stem}.jpg"] = cluster

    entries = []
    for crop_name in sorted(labels):
        rec = labels[crop_name]
        stem = Path(crop_name).stem
        folder = VIDEO_DIRS.get(rec.get("video", ""), "")
        reviewed = review.get(crop_name)
        cluster = reviewed or _cluster_from_name(rec.get("label"))
        is_page = cluster in PAGE_NAMES
        entries.append({
            "frame": f"{folder}/{stem}.jpg" if folder else f"{stem}.jpg",
            "video": folder,
            "cluster": cluster,
            "process": "bper-p1" if is_page else None,
            "step": int(cluster) if is_page else None,
            "step_name": PAGE_NAMES.get(cluster),
            "reviewed": reviewed is not None,
            "proposals": {
                "gemini": _cluster_from_name(rec.get("label")),
                "claude": reviewed,
            },
            "app_rect": rec.get("rect"),
            "localization_score": rec.get("loc_score"),
        })

    reviewed_n = sum(1 for e in entries if e["reviewed"])
    # Agreement is measured at two granularities on purpose. gemini answers "altro"
    # where the review answers altro-bper / altro-app / altro-nulla: that is the same
    # judgement at a finer grain, not a disagreement, and comparing the strings
    # directly understates agreement badly (23/24 read as 4/24 on the first sheet).
    coarse = lambda c: "altro" if c and c.startswith("altro") else c
    agree_coarse = sum(1 for e in entries if e["reviewed"]
                       and coarse(e["proposals"]["gemini"]) == coarse(e["proposals"]["claude"]))
    agree_exact = sum(1 for e in entries if e["reviewed"]
                      and e["proposals"]["gemini"] == e["proposals"]["claude"])

    registry = {
        "process": "bper-p1",
        "frames_dir": str(FRAMES).replace("\\", "/"),
        "clusters": {
            "1": "Risultato ricerca", "2": "Risultato ricerca - Colonne estese",
            "3": "Risultato ricerca - Tooltip mostrata", "4": "Elenco Soggetti",
            "5": "Gestione Fidi e Garanzie",
            "6": "Gestione Fidi e Garanzie - Tooltip Descrizione Fidi",
            "7": "Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 1)",
            "8": "Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie (riga 2)",
            "9": "Note da Richiesta",
            "altro-bper": "BPER Gestione Pratiche, fuori dal processo P1",
            "altro-app": "applicativo diverso",
            "altro-nulla": "nero, transizione, popup",
            "altro": "negativo non ancora suddiviso (proposta batch, non rivista)",
        },
        "review_status": {
            "total": len(entries),
            "reviewed": reviewed_n,
            "pending": len(entries) - reviewed_n,
            "agreement_page_vs_altro": f"{agree_coarse}/{reviewed_n}" if reviewed_n else "n/a",
            "agreement_exact_string": f"{agree_exact}/{reviewed_n}" if reviewed_n else "n/a",
            "caveat": "Nessuna etichetta e' verita' umana. 'cluster' riporta la revisione "
                      "indipendente dove esiste, altrimenti la proposta batch.",
        },
        "cluster_counts": dict(Counter(e["cluster"] for e in entries).most_common()),
        "frames": entries,
    }

    out = Path(args.out)
    out.write_text(json.dumps(registry, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(entries)} frame -> {out}")
    print(f"rivisti: {reviewed_n}, in attesa: {len(entries)-reviewed_n}")
    for k, v in registry["cluster_counts"].items():
        print(f"  {v:4}  {k}")
    print(f"accordo pagina-vs-altro: {registry['review_status']['agreement_page_vs_altro']}, "
          f"stringa esatta: {registry['review_status']['agreement_exact_string']}")


if __name__ == "__main__":
    main()
