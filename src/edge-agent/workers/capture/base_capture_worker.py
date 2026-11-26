from __future__ import annotations

import threading
import time
from typing import Optional, Callable

from PyQt6 import QtCore


class BaseCaptureWorker(QtCore.QThread):
    """
    Base class per tutti i worker di cattura screenshot.

    Non può essere una ABC vera (QThread non supporta ABCMeta), quindi i metodi
    “astratti” usano raise NotImplementedError.
    """

    tick = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(Exception)
    # Emesso con stringa JSON contenente dettagli debug LLM (prompt/risposta/parsed)
    llm_debug = QtCore.pyqtSignal(str)

    def __init__(
        self,
            config,
        job_id_getter: Callable[[], Optional[str]],
            parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.job_id_getter = job_id_getter

        self._stop_event = threading.Event()
        self._capture_fps = config.fps or 1

    # =====================================================================
    # Main loop
    # =====================================================================

    def run(self) -> None:
        """
        Loop principale del thread di cattura.

        Chiama _capture_once() n volte al secondo (fps configurato).
        """
        delay = 1.0 / float(self._capture_fps)

        self.tick.emit(f"[Worker] Avviato (FPS={self._capture_fps})")

        try:
            while not self._stop_requested:
                t0 = time.monotonic()
                try:
                    self._capture_once()
                except Exception as exc:  # noqa: BLE001
                    self.error.emit(exc)
                remaining = delay - (time.monotonic() - t0)
                if remaining > 0:
                    self._stop_event.wait(remaining)
        finally:
            self.tick.emit("[Worker] Terminato.")

    # =====================================================================
    # API chiamate dal thread principale
    # =====================================================================

    def start_capture(self) -> None:
        if not self.isRunning():
            self.start()

    @property
    def _stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def stop(self) -> None:
        self._stop_event.set()

    # =====================================================================
    # Metodi da implementare nei worker specifici
    # =====================================================================

    def _capture_once(self) -> None:
        """
        Metodo chiamato n volte al secondo dal loop.

        Ogni worker deve implementarlo.
        """
        raise NotImplementedError("_capture_once() must be implemented by subclasses")

    # Utility: logging
    def _log(self, msg: str) -> None:
        self.tick.emit(msg)

    # Utility: gestione errori non fatali
    def on_error(self, exc: Exception) -> None:
        """
        Gestione centralizzata degli errori non fatali emersi nei worker.

        Emette il segnale Qt `error` così l'UI può decidere come mostrarli.
        """
        try:
            self.error.emit(exc)
        except Exception:
            # Evita qualsiasi propagazione nel thread del worker
            pass
