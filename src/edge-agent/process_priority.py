"""Optional Windows CPU scheduling priority for the desktop process."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes

_ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000


def apply_process_priority() -> None:
    """Request above-normal priority only when the operator opts in."""
    setting = os.getenv("EDGE_AGENT_PRIORITY", "normal").strip().lower()
    if setting != "above_normal" or sys.platform != "win32":
        return

    try:
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetPriorityClass.restype = wintypes.BOOL
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), _ABOVE_NORMAL_PRIORITY_CLASS):
            logging.getLogger(__name__).warning("Windows declined above-normal process priority")
    except OSError as exc:
        logging.getLogger(__name__).warning("Unable to set above-normal process priority: %s", exc)
