"""Last-resort handler for an exception that escapes a Qt slot.

PyQt6 can end the process on an unhandled exception in a slot. Reporting it lets
the operator check the last saved work and export before restarting.
Top-level and free of `ui`/`extraction` imports, so it can be installed first thing.
"""

from __future__ import annotations

import sys
import time
import traceback
from types import TracebackType
from typing import Callable, Optional, Type

_MESSAGE = (
    "Si è verificato un errore imprevisto. Controlla lo stato del salvataggio, "
    "esporta i dati disponibili e riapri l’applicazione.\n\nDettaglio: {kind}: {detail}"
)


def _show_dialog(text: str) -> None:
    from PyQt6 import QtWidgets

    QtWidgets.QMessageBox.critical(None, "Edge Agent", text)


def install_excepthook(show: Optional[Callable[[str], None]] = None, min_interval: float = 5.0) -> None:
    """Log every uncaught exception to stderr (edge-agent.log in the bundle) and tell the operator.

    The dialog opens at most once per `min_interval` seconds: an error inside a paint event
    would otherwise bury the screen in dialogs. A failing dialog never raises out of the hook.
    """
    present = show or _show_dialog
    previous = sys.excepthook
    last_shown = [float("-inf")]

    def hook(exc_type: Type[BaseException], exc: BaseException, tb: Optional[TracebackType]) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        print("[UNCAUGHT] " + "".join(traceback.format_exception(exc_type, exc, tb)), file=sys.stderr, flush=True)
        now = time.monotonic()
        if now - last_shown[0] < min_interval:
            return
        last_shown[0] = now
        try:
            present(_MESSAGE.format(kind=exc_type.__name__, detail=exc))
        except Exception:  # noqa: BLE001 - the dialog is a courtesy
            pass

    sys.excepthook = hook
