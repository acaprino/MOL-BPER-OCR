"""Lossless, versioned payloads for the encrypted capture journal."""

from __future__ import annotations

import io
import json
from typing import Any

from PIL import Image


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def pack_pending(image: Image.Image, page_no: int, page_type: str, confidence: float) -> bytes:
    # PNG preserves the exact preprocessed pixels, including small identifiers.
    buffer = io.BytesIO()
    buffer.write(b"P1\n")
    buffer.write(json_bytes([page_no, page_type, confidence]))
    buffer.write(b"\n")
    image.save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()


def unpack_pending(data: bytes) -> tuple[Image.Image, int, str, float]:
    with io.BytesIO(data) as source:
        if source.readline() != b"P1\n":
            raise ValueError("Formato della cattura in attesa sconosciuto.")
        page_no, page_type, confidence = json.loads(source.readline())
        with Image.open(io.BytesIO(source.read())) as image:
            return image.copy(), page_no, page_type, confidence
