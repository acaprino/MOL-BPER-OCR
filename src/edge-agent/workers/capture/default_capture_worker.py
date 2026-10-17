"""Worker di cattura generico (senza riconoscimento pagine)."""

from __future__ import annotations

import io
import uuid
from typing import Optional

import requests
from PIL import Image
from PyQt6 import QtCore

from .base_capture_worker import BaseCaptureWorker


class DefaultCaptureWorker(BaseCaptureWorker):
    """
    Worker di default:

        - cattura screenshot full-screen
        - invia ogni frame al backend
        - non applica alcuna logica di riconoscimento pagina

    Usa l'endpoint:
        POST /jobs/{job_id}/frames
        form-data: file=<PNG>, page=0
    """

    def __init__(self, config, job_id_getter, parent: Optional[QtCore.QObject] = None):
        super().__init__(config, job_id_getter, parent)

    # ------------------------------------------------------------------ core loop

    def _capture_once(self) -> None:
        """
        Implementazione per il worker generico:

            - legge il job_id corrente
            - cattura screenshot
            - lo invia all'API come page=0
        """
        job_id = self.job_id_getter()
        if not job_id:
            # Nessun job attivo: non ha senso caricare frame
            return

        # Cattura screenshot
        img = self._capture_screenshot()
        if img is None:
            return

        # Serializza in PNG in memoria
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        filename = f"frame-{uuid.uuid4().hex}.png"
        files = {"file": (filename, buf, "image/png")}
        data = {"page": "0"}

        base_url = self.config.api_base.rstrip("/")
        url = f"{base_url}/jobs/{job_id}/frames"

        try:
            resp = requests.post(url, files=files, data=data, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
            return

        self.tick.emit(f"📸 Frame caricato: {filename}")

    # ------------------------------------------------------------------ helper screenshot

    def _capture_screenshot(self) -> Optional[Image.Image]:
        """
        Cattura screenshot full-screen.

        Se vuoi filtrare per finestra / titolo, puoi estendere questa funzione.
        """
        try:
            import pyscreenshot as ImageGrab  # type: ignore[import]

            img = ImageGrab.grab()
            return img.convert("RGB")
        except Exception as exc:  # noqa: BLE001
            self.on_error(exc)
            return None
