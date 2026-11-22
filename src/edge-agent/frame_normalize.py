"""Riporta un frame catturato a schermo intero sull'area della finestra applicativa.

Il classificatore pagina confronta il frame con prototipi costruiti da screenshot
di *finestra* (le 9 schermate di data/dataset/pratiche/51350695). La cattura invece prende il
monitor intero, e le ROI del classificatore sono relative: sullo schermo pieno
la stessa ROI cade su contenuto diverso e la similarita' coseno crolla su un
prototipo arbitrario. Normalizzare l'inquadratura prima del routing e' quello
che rimette query e prototipi nella stessa distribuzione.

Due strategie, in ordine di affidabilita':
  1. il rettangolo della finestra dal sistema operativo (esatto);
  2. il rettangolo dedotto dal contenuto, quando il desktop attorno alla
     finestra e' uniforme (approssimato, ma non richiede API di sistema).
Se nessuna delle due conclude, il frame passa invariato: peggiorare
l'inquadratura e' peggio che lasciarla come e'.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageChops

# Rect in coordinate dello schermo virtuale, come le restituisce GetWindowRect.
Rect = Tuple[int, int, int, int]

# Strategia che ha prodotto l'inquadratura, riportata da normalize_frame().
# UNCHANGED non e' un dettaglio: significa che al classificatore arriva un frame
# che sappiamo fuori distribuzione, la condizione che faceva riconoscere 1 pagina
# su 9. Va detta a voce, non lasciata deducibile dai punteggi.
WINDOW_RECT = "window-rect"
CONTENT_RECT = "content-rect"
UNCHANGED = "unchanged"

# Scostamento massimo di luminanza perche' due pixel contino come stesso colore.
_COLOR_TOLERANCE = 24

# Sotto questa dimensione un ritaglio non e' una finestra applicativa.
_MIN_CROP_SIDE = 16

# Margine minimo di sfondo su ogni lato perche' si possa parlare di "finestra
# dentro un desktop": senza margine la finestra riempie il monitor e il frame
# gia' e' l'applicativo.
_MIN_DESKTOP_MARGIN = 8


def crop_to_rect(img: Image.Image, monitor: Dict[str, int], window_rect: Optional[Rect]) -> Image.Image:
    """Ritaglia il frame sul rettangolo della finestra.

    `monitor` e' il dict di mss (left/top/width/height in coordinate dello
    schermo virtuale); `window_rect` e' (left, top, right, bottom) nelle stesse
    coordinate. Se l'intersezione col monitor e' vuota o degenere il frame torna
    invariato: una finestra su un altro monitor non deve produrre un ritaglio.
    """
    if window_rect is None:
        return img

    left, top, right, bottom = window_rect
    x1 = max(0, left - int(monitor.get("left", 0)))
    y1 = max(0, top - int(monitor.get("top", 0)))
    x2 = min(img.width, right - int(monitor.get("left", 0)))
    y2 = min(img.height, bottom - int(monitor.get("top", 0)))

    if x2 - x1 < _MIN_CROP_SIDE or y2 - y1 < _MIN_CROP_SIDE:
        return img

    return img.crop((x1, y1, x2, y2))


def detect_app_rect(img: Image.Image, *, tolerance: int = _COLOR_TOLERANCE) -> Optional[Rect]:
    """Rettangolo della finestra dedotto dallo sfondo uniforme che la circonda.

    Restituisce None quando i quattro angoli non concordano (c'e' altro sul
    desktop, o la finestra e' massimizzata) oppure quando il contenuto tocca un
    bordo del frame: in entrambi i casi non c'e' uno sfondo su cui basarsi.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    if w < _MIN_CROP_SIDE or h < _MIN_CROP_SIDE:
        return None

    corners = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((w - 1, 0)),
        rgb.getpixel((0, h - 1)),
        rgb.getpixel((w - 1, h - 1)),
    ]
    reference = corners[0]
    for corner in corners[1:]:
        if max(abs(a - b) for a, b in zip(corner, reference)) > tolerance:
            return None

    background = Image.new("RGB", rgb.size, reference)
    mask = ImageChops.difference(rgb, background).convert("L").point(
        lambda v: 255 if v > tolerance else 0
    )
    bbox = mask.getbbox()
    if bbox is None:
        return None

    x1, y1, x2, y2 = bbox
    if x2 - x1 < _MIN_CROP_SIDE or y2 - y1 < _MIN_CROP_SIDE:
        return None
    margins = (x1, y1, w - x2, h - y2)
    if min(margins) < _MIN_DESKTOP_MARGIN:
        return None

    return bbox


def select_window_rect(
    title_substring: str,
    windows: Iterable[Dict[str, Any]],
    own_pid: int,
) -> Optional[Rect]:
    """Sceglie fra le finestre candidate quella che inquadra l'applicativo.

    Pura di proposito: l'enumerazione di sistema sta in find_window_rect(), qui
    resta la sola decisione, che e' la parte che puo' sbagliare in silenzio.

    Due regole, entrambe nate da difetti osservati:

    1. Le finestre del nostro stesso processo sono escluse. L'agent intitola la
       propria finestra "BPER Edge Agent" (ui/main_window.py) e config.ini cerca
       "BPER": senza questa esclusione l'agent trova se stesso, e siccome un
       ritaglio riuscito ferma normalize_frame() prima del ripiego, a router ed
       estrazione arriva uno screenshot dell'agent.
    2. Fra piu' candidate vince l'area maggiore, non l'ordine di enumerazione.
       L'ordine non e' una prova di niente: una finestra vecchia o in secondo
       piano poteva vincere per caso. La sessione in cui l'operatore lavora e'
       quella grande. E' un arbitraggio, non una validazione: non dimostra che
       la finestra scelta contenga davvero l'applicativo.
    """
    needle = (title_substring or "").strip().lower()
    if not needle:
        return None

    best: Optional[Rect] = None
    best_area = 0
    for win in windows:
        title = str(win.get("title") or "")
        if needle not in title.lower():
            continue
        if win.get("pid") == own_pid:
            continue
        rect = win.get("rect")
        if not rect:
            continue
        left, top, right, bottom = rect
        area = max(0, right - left) * max(0, bottom - top)
        if area <= 0:
            continue
        if area > best_area:
            best, best_area = (left, top, right, bottom), area

    return best


def _enumerate_windows() -> List[Dict[str, Any]]:
    """Finestre visibili con titolo: {title, pid, rect}. Solo Windows."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    out: List[Dict[str, Any]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _visit(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append({
            "title": buffer.value,
            "pid": int(pid.value),
            "rect": (rect.left, rect.top, rect.right, rect.bottom),
        })
        return True  # enumerazione completa: la scelta e' di select_window_rect()

    user32.EnumWindows(_visit, 0)
    return out


def find_window_rect(title_substring: str) -> Optional[Rect]:
    """Rect della finestra visibile che meglio corrisponde alla sottostringa.

    Solo Windows, via user32 con ctypes: nessuna dipendenza aggiuntiva. Fuori da
    Windows, senza sottostringa o in caso di qualunque errore restituisce None,
    e la normalizzazione ripiega sul rilevamento da contenuto.
    """
    if not (title_substring or "").strip() or sys.platform != "win32":
        return None
    try:
        return select_window_rect(title_substring, _enumerate_windows(), os.getpid())
    except Exception:  # noqa: BLE001 — la cattura non deve dipendere da user32
        return None


def normalize_frame(
    img: Image.Image,
    monitor: Dict[str, int],
    window_rect_provider: Callable[[], Optional[Rect]],
) -> Tuple[Image.Image, str]:
    """Frame ritagliato sull'applicativo: finestra dal sistema, poi contenuto.

    Restituisce anche quale strategia ha agito (WINDOW_RECT / CONTENT_RECT /
    UNCHANGED). Il chiamante deve poterlo dire: UNCHANGED lascia passare un frame
    a schermo intero, e le coordinate relative a valle cadono su contenuto
    diverso da quello su cui sono tarate.
    """
    try:
        window_rect = window_rect_provider()
    except Exception:  # noqa: BLE001 — un provider di sistema non deve fermare la cattura
        window_rect = None

    if window_rect is not None:
        cropped = crop_to_rect(img, monitor, window_rect)
        if cropped is not img:
            return cropped, WINDOW_RECT

    content_rect = detect_app_rect(img)
    if content_rect is not None:
        return img.crop(content_rect), CONTENT_RECT

    return img, UNCHANGED
