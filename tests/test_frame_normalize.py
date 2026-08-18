"""Frame normalization: bring a full-monitor grab back to the app window."""

from PIL import Image

from frame_normalize import (
    CONTENT_RECT,
    UNCHANGED,
    WINDOW_RECT,
    crop_to_rect,
    detect_app_rect,
    normalize_frame,
    select_window_rect,
)

# mss reports monitors as left/top/width/height in virtual-screen coordinates.
MONITOR = {"left": 0, "top": 0, "width": 800, "height": 600}
MONITOR_SECOND = {"left": 1920, "top": 0, "width": 800, "height": 600}

DESKTOP = (32, 34, 38)


def _desktop_with_window(win: Image.Image, at: tuple[int, int]) -> Image.Image:
    frame = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), DESKTOP)
    frame.paste(win, at)
    return frame


def test_crop_to_rect_maps_virtual_screen_coordinates_to_monitor_local_ones():
    frame = Image.new("RGB", (800, 600), "black")
    frame.paste(Image.new("RGB", (200, 100), "white"), (300, 250))

    cropped = crop_to_rect(frame, MONITOR_SECOND, (1920 + 300, 250, 1920 + 500, 350))

    assert cropped.size == (200, 100)
    assert cropped.getpixel((0, 0)) == (255, 255, 255)


def test_crop_to_rect_keeps_the_frame_when_the_window_is_on_another_monitor():
    frame = Image.new("RGB", (800, 600), "black")

    cropped = crop_to_rect(frame, MONITOR, (1920, 0, 2500, 400))

    assert cropped.size == frame.size


def test_crop_to_rect_clamps_a_window_hanging_off_the_monitor_edge():
    frame = Image.new("RGB", (800, 600), "black")

    cropped = crop_to_rect(frame, MONITOR, (-50, -20, 300, 200))

    assert cropped.size == (300, 200)


def test_detect_app_rect_finds_a_window_on_a_uniform_desktop():
    win = Image.new("RGB", (420, 300), "white")

    rect = detect_app_rect(_desktop_with_window(win, (120, 80)))

    assert rect == (120, 80, 540, 380)


def _maximized_app() -> Image.Image:
    """A window filling the monitor: no desktop ring, the frame *is* the app."""
    frame = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), "white")
    frame.paste(Image.new("RGB", (MONITOR["width"], 60), (10, 40, 90)), (0, 0))
    return frame


def test_detect_app_rect_gives_up_when_the_app_fills_the_frame():
    assert detect_app_rect(_maximized_app()) is None


def test_normalize_frame_prefers_the_window_rect_over_content_detection():
    win = Image.new("RGB", (420, 300), "white")
    frame = _desktop_with_window(win, (120, 80))

    normalized, strategy = normalize_frame(
        frame, MONITOR, window_rect_provider=lambda: (200, 100, 400, 250)
    )

    assert normalized.size == (200, 150)
    assert strategy == WINDOW_RECT


def test_normalize_frame_falls_back_to_content_detection_without_a_window_rect():
    win = Image.new("RGB", (420, 300), "white")
    frame = _desktop_with_window(win, (120, 80))

    normalized, strategy = normalize_frame(frame, MONITOR, window_rect_provider=lambda: None)

    assert normalized.size == (420, 300)
    assert strategy == CONTENT_RECT


def test_normalize_frame_keeps_the_frame_when_nothing_can_be_located():
    """The give-up branch must be nameable.

    It hands the classifier a frame that is known to be out of distribution,
    which is the exact condition that made recognition score 1 page out of 9.
    Silently returning the frame leaves that diagnosable only by reading the
    scores, so the caller has to be able to say which branch ran.
    """
    frame = _maximized_app()

    normalized, strategy = normalize_frame(frame, MONITOR, window_rect_provider=lambda: None)

    assert normalized.size == frame.size
    assert strategy == UNCHANGED


def test_normalize_frame_survives_a_window_rect_provider_that_raises():
    win = Image.new("RGB", (420, 300), "white")
    frame = _desktop_with_window(win, (120, 80))

    def boom():
        raise OSError("user32 unavailable")

    normalized, strategy = normalize_frame(frame, MONITOR, window_rect_provider=boom)

    assert normalized.size == (420, 300)
    assert strategy == CONTENT_RECT


# ---------------------------------------------------------------- window selection

def _win(title: str, pid: int, rect: tuple) -> dict:
    return {"title": title, "pid": pid, "rect": rect}


OWN_PID = 4242


def test_window_selection_never_returns_our_own_window():
    """The agent titles its own window "BPER Edge Agent".

    With `window_title_contains = BPER` the agent is a permanent match for itself,
    so a title-only search hands routing and extraction a screenshot of the agent.
    Nothing downstream can recover from that, because a successful crop stops
    normalize_frame() before the content fallback runs.
    """
    windows = [
        _win("BPER Edge Agent", OWN_PID, (0, 0, 900, 700)),
        _win("Nuova PEF 3.0 - BPER - Google Chrome", 99, (100, 50, 1400, 900)),
    ]

    assert select_window_rect("BPER", windows, own_pid=OWN_PID) == (100, 50, 1400, 900)


def test_window_selection_gives_up_when_only_our_own_window_matches():
    windows = [_win("BPER Edge Agent", OWN_PID, (0, 0, 900, 700))]

    assert select_window_rect("BPER", windows, own_pid=OWN_PID) is None


def test_window_selection_arbitrates_by_area_instead_of_enumeration_order():
    """Enumeration order is not evidence of which window holds the application.

    Taking the first hit made a stale or background window win by accident; the
    session the operator works in is the large one.
    """
    windows = [
        _win("BPER notes.txt - Notepad", 7, (0, 0, 400, 300)),
        _win("BPER - Remote Desktop Connection", 8, (200, 100, 1720, 980)),
    ]

    assert select_window_rect("BPER", windows, own_pid=OWN_PID) == (200, 100, 1720, 980)


def test_window_selection_returns_none_when_nothing_matches():
    windows = [_win("Spotify", 7, (0, 0, 400, 300))]

    assert select_window_rect("BPER", windows, own_pid=OWN_PID) is None


def test_window_selection_ignores_degenerate_rectangles():
    # A minimized or zero-area window matches the title but frames nothing.
    windows = [
        _win("BPER - Remote Desktop Connection", 8, (0, 0, 0, 0)),
        _win("BPER - Google Chrome", 9, (10, 10, 800, 600)),
    ]

    assert select_window_rect("BPER", windows, own_pid=OWN_PID) == (10, 10, 800, 600)
