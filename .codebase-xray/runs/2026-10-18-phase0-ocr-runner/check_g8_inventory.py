"""Recompute the corpus inventory that docs/next-ver-plan.md section 5.4 states.

Usage: python -I check_g8_inventory.py <repo_root> <plan.md>
Exits 1 if any check fails.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

root, plan_path = Path(sys.argv[1]), Path(sys.argv[2])
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


manifest = json.loads((root / "data/pratiche/manifest.json").read_text(encoding="utf-8"))
practices = manifest["practices"]
privati = {p["practice"]: [s for s in p["screens"] if s.startswith("Scheda_Privati")] for p in practices}
privati = {k: v for k, v in privati.items() if v}
check("Scheda Privati screens only in 52062600, 5 of them", privati == {"52062600": [f"Scheda_Privati_{i}.png" for i in range(1, 6)]},
      str(privati))
lotto = [p for p in practices if p["batch"] == "lotto-2026-08-21"]
check("lotto 2026-08-21: 10 practices, 34 in-scope screens, no reviewed split",
      (len(lotto), sum(p["in_scope_count"] for p in lotto), {p.get("ground_truth_split") for p in lotto}) == (10, 34, {None}),
      str((len(lotto), sum(p["in_scope_count"] for p in lotto))))
check("lotto has no Scheda Privati screen", not any(s.startswith("Scheda_Privati") for p in lotto for s in p["screens"]))

PRIVATI_FIELDS = {"dal", "datore_di_lavoro_anagrafica", "di_cui_percepiscono_reddito", "importo_totale_annuo_nucleo",
                  "note_scheda_privati", "nr_altri_componenti_nucleo", "numero_mensilita", "professione_principale",
                  "rating_ufficiale", "retribuzione_annua_netta", "score_cgs", "tipo_contratto", "ultima_validazione_scheda"}
CONSAP = {"tooltip_descrizione_m_consap", "tooltip_descrizione_consap_dr_bis"}
positives: dict[str, set[tuple[str, str]]] = defaultdict(set)
with open(root / "data/training/ground-truth-v3.1/alignment_report.csv", encoding="utf-8-sig", newline="") as fh:
    for row in csv.DictReader(fh, delimiter=";"):
        if row["expected"].strip():
            positives[row["field"]].add((row["practice"], row["split"]))
check("all 13 Scheda Privati fields have positives, only in 52062600 (train)",
      all(positives[f] == {("52062600", "train")} for f in PRIVATI_FIELDS), str({f: sorted(positives[f]) for f in PRIVATI_FIELDS}))
check("CONSAP tooltips have positives only in 52067184 and 52068422 (train)",
      all(positives[f] == {("52067184", "train"), ("52068422", "train")} for f in CONSAP), str({f: sorted(positives[f]) for f in CONSAP}))

fixture = (root / "tests/fixtures/frames/no-tooltip/manifest.json").read_text(encoding="utf-8")
cited = set(re.findall(r"5[12]\d{6}", fixture))
check("page-classifier fixture cites 51788077, 51800301, 52032077", {"51788077", "51800301", "52032077"} <= cited, str(sorted(cited)))

plan = plan_path.read_text(encoding="utf-8")
check("plan has section 5.4", "### 5.4 Piano di Raccolta per G8" in plan)
check("plan cites the fixture directory and commit", "tests/fixtures/frames/no-tooltip/" in plan and "7b70bf7" in plan)
check("plan has 17 em dashes (none added)", plan.count("—") == 17, str(plan.count("—")))

for name, ok, detail in results:
    print("PASS" if ok else "FAIL", name, "" if ok else f"-> {detail}")
print(f"{sum(ok for _, ok, _ in results)}/{len(results)} checks passed")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
