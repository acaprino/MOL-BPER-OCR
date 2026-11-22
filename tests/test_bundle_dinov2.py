"""The DINOv2 model a package ships, so page recognition works offline from the first start (ADR 0031)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from page_classifier import DINOV2_WEIGHTS_FILENAME
from tools.bundle_dinov2 import copy_cached, repo_dirname, verify


def _hub(root: Path, weights: bytes = b"weights") -> Path:
    """A torch hub cache holding the pinned repo and the weights."""
    (root / repo_dirname()).mkdir(parents=True)
    (root / repo_dirname() / "hubconf.py").write_text("dependencies = []\n", encoding="utf-8")
    (root / "checkpoints").mkdir()
    (root / "checkpoints" / DINOV2_WEIGHTS_FILENAME).write_bytes(weights)
    return root


def test_repo_folder_is_the_one_torch_hub_caches_for_the_pinned_commit() -> None:
    assert repo_dirname() == "facebookresearch_dinov2_7764ea0f912e53c92e82eb78a2a1631e92725fc8"


def test_the_pinned_repo_and_the_weights_are_copied_from_a_local_cache(tmp_path: Path) -> None:
    target = tmp_path / "package" / "hub"
    copy_cached(_hub(tmp_path / "cache"), target)

    assert (target / repo_dirname() / "hubconf.py").is_file()
    assert (target / "checkpoints" / DINOV2_WEIGHTS_FILENAME).read_bytes() == b"weights"


def test_weights_with_the_expected_checksum_are_accepted(tmp_path: Path) -> None:
    hub = _hub(tmp_path)
    verify(hub, expected_sha256=hashlib.sha256(b"weights").hexdigest())


def test_weights_with_another_checksum_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        verify(_hub(tmp_path), expected_sha256="0" * 64)


def test_a_bundle_without_the_repo_is_refused(tmp_path: Path) -> None:
    hub = _hub(tmp_path)
    (hub / repo_dirname() / "hubconf.py").unlink()
    (hub / repo_dirname()).rmdir()
    with pytest.raises(FileNotFoundError):
        verify(hub, expected_sha256=hashlib.sha256(b"weights").hexdigest())
