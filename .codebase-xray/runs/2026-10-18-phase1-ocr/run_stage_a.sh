#!/usr/bin/env bash
# Stage A runs of docs/next-ver-plan.md Phase 1, one heavy job at a time.
# Usage: bash run_stage_a.sh A0 A1 ...   (rerunning resumes each configuration)
set -u
ROOT="D:/Projects/poc-data-extraction"
RUNS="$ROOT/.codebase-xray/runs/2026-10-18-phase1-ocr"
cd "$ROOT/src" || exit 1
for CONFIG in "$@"; do
  OUT="$RUNS/$CONFIG-pc4"
  echo "== $CONFIG ocr start $(date -u +%FT%TZ)"
  if ! ../.venv-ocr/Scripts/python.exe -m training.ocr_runner run --config "$CONFIG" --profile pc4 \
      --examples ../data/training/ground-truth-v3.1/examples.json --screenshots ../data --out "$OUT"; then
    echo "== $CONFIG ocr FAILED $(date -u +%FT%TZ)"; continue
  fi
  echo "== $CONFIG report start $(date -u +%FT%TZ)"
  if ../.venv/Scripts/python.exe -m training.ocr_runner report --run "$OUT" \
      --workbook ../data/revisione/revisione/Revisione_ground_truth_v3_1.xlsx --screenshots ../data > "$OUT.report.txt" 2>&1; then
    echo "== $CONFIG report done $(date -u +%FT%TZ)"
  else
    echo "== $CONFIG report FAILED $(date -u +%FT%TZ)"; tail -3 "$OUT.report.txt"
  fi
done
echo "== all done $(date -u +%FT%TZ)"
