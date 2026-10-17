from __future__ import annotations

from typing import Optional

from PIL import Image, ImageFilter, ImageOps


def _auto_scale_factor(img: Image.Image, min_dpi: int = 120) -> float:
    """Stima un fattore di scala semplice: se il lato minore è piccolo, upscalare.
    Non conosciamo il DPI reale, ma usiamo l'euristica sulle dimensioni.
    """
    w, h = img.size
    short = min(w, h)
    if short < 900:
        return 1.5
    if short < 1100:
        return 1.25
    return 1.0


def preprocess_for_ocr(
    img: Image.Image,
    *,
    scale: Optional[float] = None,
    unsharp_amount: float = 0.8,
    unsharp_radius: float = 1.2,
    unsharp_threshold: int = 2,
    contrast_stretch: bool = True,
) -> Image.Image:
    """Preprocessing leggero per migliorare l'OCR su GUI/Citrix.

    - Upscale adattivo (o forzato con `scale`)
    - Unsharp mask per nitidezza font
    - Stretch del contrasto per testo grigio/antialias
    """
    out = img

    # 1) upscale
    s = scale if (scale and scale > 0) else _auto_scale_factor(out)
    if s and abs(s - 1.0) > 1e-3:
        new_size = (max(1, int(out.width * s)), max(1, int(out.height * s)))
        out = out.resize(new_size, Image.Resampling.LANCZOS)

    # 2) unsharp
    if unsharp_amount > 0:
        out = out.filter(ImageFilter.UnsharpMask(radius=unsharp_radius, percent=int(unsharp_amount * 150), threshold=unsharp_threshold))

    # 3) contrast stretch leggero
    if contrast_stretch:
        try:
            out = ImageOps.autocontrast(out, cutoff=1)
        except Exception:
            pass

    return out


def to_png8(img: Image.Image) -> bytes:
    """Converte in PNG8 (palette) per testi: riduce dimensione mantenendo qualità alta."""
    pal = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    import io
    buf = io.BytesIO()
    pal.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def to_webp_lossless(img: Image.Image) -> bytes:
    import io
    buf = io.BytesIO()
    img.save(buf, format="WEBP", lossless=True, quality=100, method=6)
    return buf.getvalue()
