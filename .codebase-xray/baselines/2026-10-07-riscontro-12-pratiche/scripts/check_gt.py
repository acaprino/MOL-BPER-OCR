"""Load the assembled CSV through the project's own loader and confirm every key joins the schema."""
import os
import sys

repo, input_dir = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
sys.path.insert(0, repo)
os.chdir(repo)
from dotenv import load_dotenv

load_dotenv()
from extraction.evaluation import load_ground_truth
from extraction.fields import CSV_TO_SCHEMA

gt = load_ground_truth(os.path.join(input_dir, "dati.csv"))
images = {os.path.splitext(f)[0] for f in os.listdir(input_dir) if f.lower().endswith(".png")}
rows = sum(len(v) for v in gt.values())
unknown = sorted({k for kv in gt.values() for k in kv if k not in CSV_TO_SCHEMA})
print(f"screens in csv={len(gt)} images={len(images)} rows={rows}")
print("screens without image:", sorted(set(gt) - images))
print("images without rows:", sorted(images - set(gt)))
print("keys not in CSV_TO_SCHEMA:", unknown)
longest = max((len(str(v)), s, k) for s, kv in gt.items() for k, v in kv.items())
print("longest value:", longest)
