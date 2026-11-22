"""Compare rendered reference assets with the page area measured in the source PNGs."""

from io import BytesIO
from pathlib import Path

from PIL import Image

from tools.reference_screens import reference_screens


def assert_site_pixels(step: int, png: bytes) -> None:
    left = 4 if step in (8, 9) else 3
    top = 59 if step in (1, 4) else 60
    with Image.open(reference_screens()[f"screen {step}"]) as source, Image.open(BytesIO(png)) as result:
        expected = source.crop((left, top, left + 842, top + 617))
        assert result.size == expected.size
        assert result.convert("RGBA").tobytes() == expected.convert("RGBA").tobytes()
