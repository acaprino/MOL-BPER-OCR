"""Image processing: normalize, crop, encode, debug save."""

import io
import os
from typing import Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter

from extraction.config import (
    CONTENT_CROP,
    CONTENT_CROP_ASPECT_TOLERANCE,
    CONTENT_CROP_CALIBRATED_ASPECT,
    CONTENT_CROP_LONG_SIDE_RANGE,
    DEBUG_SAVE_CROPS,
    DEBUG_CROP_DIR,
)


def normalize_image(img: Image.Image, long_side: int = 1800) -> Image.Image:
    w, h = img.size
    scale = long_side / max(w, h)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    img = ImageEnhance.Contrast(img).enhance(1.05)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
    return img


def screen_id_from_path(path: str) -> str:
    """Derive the screen_id (basename without extension) used as the GT join key.

    Single source of truth: the same derivation is the join key in evaluation,
    so all call sites must agree.
    """
    return os.path.splitext(os.path.basename(path))[0]


def clamp_long_side(img: Image.Image, max_side: int) -> Image.Image:
    """Downscale so the long side is at most ``max_side``. No-op if already smaller.

    Dimension-only guard (no contrast/sharpen) for the raw extract_from_image
    path, which intentionally skips normalize_image().
    """
    w, h = img.size
    longest = max(w, h)
    if max_side > 0 and longest > max_side:
        scale = max_side / longest
        img = img.resize((int(w * scale), int(h * scale)))
    return img


def select_content_crop(size: Tuple[int, int]) -> Optional[Tuple[float, float, float, float]]:
    """CONTENT_CROP if the image belongs to the calibration family, None otherwise.

    Membership means both the aspect AND the pixel size of the reference
    practice's screenshots (data/dataset/pratiche/51350695). Aspect alone is not identity: 1280x1024 (5:4) sits 0.09% from
    848/679, so a full-screen legacy grab would pass an aspect-only gate and
    lose its left columns exactly as in the measured 1536x1032 case (see the
    comment on CONTENT_CROP in config.py).

    None means: send the full image. This gate is only consulted on the file
    path (extract_from_screen); the live path never crops, because no operator
    window is ever the reference rendered at 848px (ADR 0010). A future second
    reference family adds a calibration entry here, not a new consumer.
    """
    width, height = size
    if height <= 0:
        return None
    lo, hi = CONTENT_CROP_LONG_SIDE_RANGE
    if not (lo <= max(width, height) <= hi):
        return None
    deviation = abs(width / height - CONTENT_CROP_CALIBRATED_ASPECT) / CONTENT_CROP_CALIBRATED_ASPECT
    if deviation <= CONTENT_CROP_ASPECT_TOLERANCE:
        return CONTENT_CROP
    return None


def crop_relative(img: Image.Image, box: Tuple[float, float, float, float]) -> Image.Image:
    w, h = img.size
    l = int(box[0] * w)
    t = int(box[1] * h)
    r = int(box[2] * w)
    b = int(box[3] * h)
    return img.crop((l, t, r, b))


def img_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_debug_crop(img: Image.Image, screen_id: str, name: str) -> None:
    if not DEBUG_SAVE_CROPS:
        return
    os.makedirs(DEBUG_CROP_DIR, exist_ok=True)
    out_path = os.path.join(DEBUG_CROP_DIR, f"{screen_id}__{name}.png")
    img.save(out_path)
