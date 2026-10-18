"""Re-download one finished run's cpu_model from the Modal volume, as modal_train.main() does."""
import hashlib, json, sys
from pathlib import Path, PurePosixPath
import modal

run = Path(sys.argv[1])
result = json.loads((run / "result.json").read_text(encoding="utf-8"))
volume = modal.Volume.from_name("bper-lilt-spike")
model_dir = run / "cpu_model"
model_dir.mkdir(exist_ok=True)
for filename in result["model_files"]:
    assert PurePosixPath(filename).name == filename and "\\" not in filename
    target = model_dir / filename
    target.unlink(missing_ok=True)
    with target.open("xb") as stream:
        for block in volume.read_file(str(PurePosixPath(result["remote_model_dir"]) / filename)):
            stream.write(block)
    print("got", filename, target.stat().st_size, flush=True)

def sha(p):
    d = hashlib.sha256()
    with p.open("rb") as s:
        for b in iter(lambda: s.read(1 << 20), b""):
            d.update(b)
    return d.hexdigest()

(run / "download_manifest.json").write_text(json.dumps({
    "volume": "bper-lilt-spike", "remote_model_dir": result["remote_model_dir"],
    "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)} for p in model_dir.iterdir()},
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("manifest written")
