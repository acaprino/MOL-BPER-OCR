"""Lossless, versioned payloads for the encrypted capture journal."""

from __future__ import annotations

import io
import json
from typing import Any

from PIL import Image


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def encode_pixels(image: Image.Image) -> bytes:
    # PNG preserves the exact preprocessed pixels, including small identifiers.
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()


def pack_pending(pixels: bytes, page_no: int, page_type: str, confidence: float,
                 view: str, context: int | None, practice: str | None) -> bytes:
    return b"P1\n" + json_bytes([page_no, page_type, confidence, view, context, practice]) + b"\n" + pixels


def _read_header(source: io.BytesIO) -> tuple[int, str, float, str, int | None, str | None]:
    if source.readline() != b"P1\n":
        raise ValueError("Formato della cattura in attesa sconosciuto.")
    header = json.loads(source.readline())
    if len(header) == 3:  # Archives predating practice selection.
        header.append("")
    if len(header) == 4:  # Captures predating immutable context ownership.
        header.extend([None, None])
    page_no, page_type, confidence, view, context, practice = header
    if view not in ("", "list", "detail", "selection", "unknown"):
        raise ValueError("Contesto della cattura non riconosciuto.")
    if context is not None and (type(context) is not int or context < 0 or not view):
        raise ValueError("Identificativo del contesto non valido.")
    if practice is not None and (context is None or not isinstance(practice, str) or not practice.isascii()
                                 or not practice.isdigit()):
        raise ValueError("Identificativo della pratica di cattura non valido.")
    return page_no, page_type, confidence, view, context, practice


def pending_metadata(data: bytes) -> tuple[int, str, float, str, int | None, str | None]:
    with io.BytesIO(data) as source:
        return _read_header(source)


def unpack_pending(data: bytes) -> tuple[Image.Image, int, str, float, str, int | None, str | None]:
    with io.BytesIO(data) as source:
        header = _read_header(source)
        with Image.open(io.BytesIO(source.read())) as image:
            return (image.copy(), *header)
