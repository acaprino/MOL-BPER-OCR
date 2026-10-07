"""Rewrite the per-field debug CSV of a finished run against the current dati.csv, without calling the provider.

Usage: python rebuild_debug.py <repo_root> <input_dir>
"""
import json
import os
import sys

repo = os.path.abspath(sys.argv[1])
sys.path.insert(0, repo)
os.chdir(repo)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(repo, ".env"))
from extraction.evaluation import build_debug_report, load_ground_truth  # noqa: E402

input_dir = os.path.abspath(sys.argv[2])
gt = load_ground_truth(os.path.join(input_dir, "dati.csv"))
outputs = json.load(open(os.path.join(input_dir, "poc_outputs_improved.json"), encoding="utf-8"))
build_debug_report(outputs, gt, os.path.join(input_dir, "poc_debug_improved.csv"))
print("debug report rewritten for", len(gt), "screens")
