#!/usr/bin/env bash
# Run labelling one batch per process, so memory is genuinely released between them.
#
# tools/label_frames.py resumes from labels.json, so each invocation picks up where
# the previous one stopped. --limit makes it stop after N frames and exit 10 while
# work remains, 0 when done: the loop below needs no bookkeeping of its own, and a
# crash costs at most the current batch.
set -u
FRAMES="$1"; OUT="$2"; LIMIT="${3:-50}"; PY="${PY:-./.venv/Scripts/python.exe}"
while true; do
  "$PY" tools/label_frames.py --frames "$FRAMES" --out "$OUT" --limit "$LIMIT" "${@:4}"
  case $? in
    0)  echo "== completato =="; break ;;
    10) echo "== batch chiuso, riparto pulito ==" ;;
    *)  echo "== errore, mi fermo: i batch gia' salvati restano validi =="; exit 1 ;;
  esac
done
