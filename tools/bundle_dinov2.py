"""Put the DINOv2 model in a package, so the edge-agent recognises pages offline from the first start (ADR 0031).

    python tools/bundle_dinov2.py dist/EdgeAgent/torch-cache

The packaged app points TORCH_HOME at its own torch-cache folder. With the pinned hub repo and the
weights already there, torch.hub loads them without touching the network. This copies both from this
machine's torch cache, lets torch.hub download only what is missing, loads the model once from the
package to prove it is complete, and refuses weights whose SHA-256 differs from DINOV2_WEIGHTS_SHA256.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "edge-agent"))
from page_classifier import (  # noqa: E402
    DINOV2_HUB_REPO,
    DINOV2_MODEL_NAME,
    DINOV2_WEIGHTS_FILENAME,
    DINOV2_WEIGHTS_SHA256,
)


def repo_dirname(hub_repo: str = DINOV2_HUB_REPO) -> str:
    """The folder torch.hub caches an owner/name:ref repo in."""
    owner_name, ref = hub_repo.split(":")
    owner, name = owner_name.split("/")
    return f"{owner}_{name}_{ref.replace('/', '_')}"


def copy_cached(source_hub: Path, target_hub: Path) -> None:
    """Copy the pinned repo and the weights from a torch hub cache, where it has them."""
    repo = source_hub / repo_dirname()
    if repo.is_dir() and not (target_hub / repo.name).exists():
        shutil.copytree(repo, target_hub / repo.name, ignore=shutil.ignore_patterns("__pycache__", ".git"))
    weights = source_hub / "checkpoints" / DINOV2_WEIGHTS_FILENAME
    target = target_hub / "checkpoints" / DINOV2_WEIGHTS_FILENAME
    if weights.is_file() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(weights, target)


def verify(target_hub: Path, expected_sha256: str = DINOV2_WEIGHTS_SHA256) -> None:
    """The bundle holds the pinned repo and the expected weights, or nothing is shipped."""
    if not (target_hub / repo_dirname()).is_dir():
        raise FileNotFoundError(f"Repo DINOv2 assente nel pacchetto: {target_hub / repo_dirname()}")
    digest = hashlib.sha256()
    with (target_hub / "checkpoints" / DINOV2_WEIGHTS_FILENAME).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != expected_sha256:
        raise ValueError(f"I pesi DINOv2 nel pacchetto hanno un altro SHA-256: {digest.hexdigest()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("torch_home", type=Path, help="the package's torch-cache folder")
    target_hub = parser.parse_args().torch_home / "hub"
    target_hub.mkdir(parents=True, exist_ok=True)
    source_hub = Path(os.environ.get("TORCH_HOME") or Path.home() / ".cache" / "torch") / "hub"
    copy_cached(source_hub, target_hub)

    import torch

    torch.hub.set_dir(str(target_hub))
    torch.hub.load(DINOV2_HUB_REPO, DINOV2_MODEL_NAME)  # from the package; downloads only what is missing
    for cache in (target_hub / repo_dirname()).rglob("__pycache__"):
        shutil.rmtree(cache)  # compiled by this load, not part of the model
    verify(target_hub)
    print(f"[OK] DINOv2 nel pacchetto: {target_hub}")


if __name__ == "__main__":
    main()
