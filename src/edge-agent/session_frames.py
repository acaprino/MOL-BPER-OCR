"""Lossless, versioned payloads for the encrypted capture journal."""

from __future__ import annotations

import io
import json
from typing import Any

from PIL import Image


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def pack_pending(image: Image.Image, page_no: int, page_type: str, confidence: float,
                 practice_view: str = "") -> bytes:
    # PNG preserves the exact preprocessed pixels, including small identifiers.
    buffer = io.BytesIO()
    buffer.write(b"P1\n")
    buffer.write(json_bytes([page_no, page_type, confidence, practice_view]))
    buffer.write(b"\n")
    image.save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()


def _read_header(source: io.BytesIO) -> tuple[int, str, float, str]:
    if source.readline() != b"P1\n":
        raise ValueError("Formato della cattura in attesa sconosciuto.")
    header = json.loads(source.readline())
    if len(header) == 3:  # Archives predating practice selection.
        header.append("")
    page_no, page_type, confidence, view = header
    if view not in ("", "list", "detail", "selection", "unknown"):
        raise ValueError("Contesto della cattura non riconosciuto.")
    return page_no, page_type, confidence, view


def pending_metadata(data: bytes) -> tuple[int, str, float, str]:
    with io.BytesIO(data) as source:
        return _read_header(source)


def unpack_pending(data: bytes) -> tuple[Image.Image, int, str, float, str]:
    with io.BytesIO(data) as source:
        page_no, page_type, confidence, view = _read_header(source)
        with Image.open(io.BytesIO(source.read())) as image:
            return image.copy(), page_no, page_type, confidence, view
