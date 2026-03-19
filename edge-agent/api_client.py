"""Client per le comunicazioni con l'API REST del sistema OCR / IE / RAG."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
from PyQt6 import QtWidgets


class APIClient:
    """
    Client HTTP minimale per interagire con l'API REST.

    Contratto allineato a api.py:

        GET  /healthz
        POST /jobs/start
        POST /jobs/{job_id}/frames
        POST /jobs/{job_id}/requeue
        GET  /jobs/{job_id}/docs
        GET  /jobs/{job_id}/docs/{doc_id}/objects
        GET  /jobs/{job_id}/docs/{doc_id}/objects/{object_id}
        GET  /jobs/{job_id}/docs/{doc_id}/links
        GET  /jobs/{job_id}/docs/{doc_id}/manifest
        GET  /jobs
        GET  /exports/csv?job_id=...
    """

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        """
        Args:
            base_url: URL base dell'API, es. "http://localhost:8081".
            timeout:  Timeout predefinito per le richieste (secondi).
        """
        self.base_url: str = (base_url or "").rstrip("/")
        self.timeout: int = int(timeout)
        self._session = requests.Session()

    # ------------------------------------------------------------------ helper HTTP

    def _make_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _show_error(self, message: str) -> None:
        try:
            QtWidgets.QMessageBox.critical(
                None,
                "Errore API",
                message,
            )
        except Exception:
            # Evita crash se non c'è un QApplication attivo
            pass

    def _get(
            self,
            path: str,
            params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        url = self._make_url(path)
        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            if not resp.content:
                return {}
            return resp.json()
        except requests.RequestException as e:
            self._show_error(f"Errore richiesta GET {url}: {e}")
            return None
        except ValueError:
            self._show_error(f"Risposta non valida (non JSON) da {url}")
            return None

    def _post(
        self,
        path: str,
            json: Optional[Dict[str, Any]] = None,
            data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        url = self._make_url(path)
        try:
            resp = self._session.post(
                url,
                json=json,
                data=data,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError:
                return {}
        except requests.RequestException as e:
            self._show_error(f"Errore richiesta POST {url}: {e}")
            return None

    # ------------------------------------------------------------------ API “jobs”

    def healthz(self) -> bool:
        """
        Controllo di salute base: GET /healthz.

        Returns:
            True se l'API risponde 2xx, False altrimenti.
        """
        data = self._get("/healthz")
        return bool(data)

    def start_job(self) -> Optional[str]:
        """
        Avvia un nuovo job lato backend.

        api.py → POST /jobs/start
        ritorna: {"job_id": "<uuid>"}
        """
        data = self._post("/jobs/start")
        if not data:
            return None

        job_id = data.get("job_id")
        if not job_id:
            self._show_error("La risposta di /jobs/start non contiene job_id.")
            return None

        return str(job_id)

    def get_jobs(self) -> List[str]:
        """
        Ottiene la lista di tutti i job disponibili.

        api.py → GET /jobs ritorna:
            {"jobs": [{"job_id": "...", "document_count": ..., ...}, ...], "total": N}
        """
        data = self._get("/jobs")
        if not data:
            return []

        jobs = data.get("jobs", [])
        result: List[str] = []

        for item in jobs:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict) and "job_id" in item:
                result.append(str(item["job_id"]))

        return result

    def requeue_job(self, job_id: str) -> bool:
        """
        Riaccoda un job per rielaborazione lato backend.

        api.py → POST /jobs/{job_id}/requeue
        """
        if not job_id:
            self._show_error("Job ID non valido per requeue.")
            return False

        data = self._post(f"/jobs/{job_id}/requeue")
        return data is not None

    def export_csv(self, job_id: str, schema: str = "flat") -> Optional[str]:
        """
        Scarica l'export CSV dei risultati di un job.

        api.py → GET /exports/csv?job_id=...&schema=...

        Returns:
            Contenuto CSV come stringa oppure None in caso di errore.
        """
        if not job_id:
            self._show_error("Job ID non valido per export CSV.")
            return None

        url = self._make_url("/exports/csv")
        try:
            resp = self._session.get(
                url, params={"job_id": job_id, "schema": schema}, timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            self._show_error(f"Errore export CSV da {url}: {e}")
            return None

    def export_xlsx(self, job_id: str, schema: str = "flat") -> Optional[bytes]:
        """
        Scarica l'export Excel (xlsx) dei risultati di un job.

        api.py → GET /exports/xlsx?job_id=...&schema=...

        Returns:
            Bytes del file XLSX oppure None in caso di errore.
        """
        if not job_id:
            self._show_error("Job ID non valido per export Excel.")
            return None

        url = self._make_url("/exports/xlsx")
        try:
            resp = self._session.get(
                url, params={"job_id": job_id, "schema": schema}, timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            self._show_error(f"Errore export Excel da {url}: {e}")
            return None

    # ------------------------------------------------------------------ API “documents”

    def get_job_documents(self, job_id: str) -> List[str]:
        """
        Ottiene la lista di documenti associati a un job.

        api.py → GET /jobs/{job_id}/docs
        ritorna: {"job_id": job_id, "docs": [...]}
        """
        if not job_id:
            self._show_error("Job ID non valido per il recupero documenti.")
            return []

        data = self._get(f"/jobs/{job_id}/docs")
        if not data:
            return []

        docs = data.get("docs", [])
        result: List[str] = []

        for item in docs:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                for key in ("doc_id", "id", "document_id"):
                    if key in item:
                        result.append(str(item[key]))
                        break

        return result

    def get_document_objects(
            self,
            job_id: str,
            doc_id: str,
            search_query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Ottiene la lista di oggetti (entità estratte) per un documento.

        api.py → GET /jobs/{job_id}/docs/{doc_id}/objects
        ritorna: { "items": [...], "total": ..., "page": ..., "size": ... }
        """
        if not job_id or not doc_id:
            self._show_error("Job ID o Document ID non validi per gli oggetti.")
            return []

        params: Dict[str, Any] = {}
        if search_query:
            params["q"] = search_query

        data = self._get(f"/jobs/{job_id}/docs/{doc_id}/objects", params=params)
        if not data:
            return []

        items = data.get("items", [])
        if isinstance(items, list):
            return items
        return []

    def get_object_detail(
            self,
            job_id: str,
            doc_id: str,
            object_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Ottiene il dettaglio di un singolo oggetto.

        api.py → GET /jobs/{job_id}/docs/{doc_id}/objects/{object_id}
        """
        if not (job_id and doc_id and object_id):
            self._show_error("Parametri non validi per il dettaglio oggetto.")
            return None

        return self._get(f"/jobs/{job_id}/docs/{doc_id}/objects/{object_id}")

    def get_document_links(
            self,
            job_id: str,
            doc_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Ottiene i collegamenti / relazioni per un documento.

        api.py → GET /jobs/{job_id}/docs/{doc_id}/links
        ritorna: {"job_id", "doc_id", "links": [...]}
        """
        if not (job_id and doc_id):
            self._show_error("Parametri non validi per i link documento.")
            return None

        return self._get(f"/jobs/{job_id}/docs/{doc_id}/links")

    def get_document_manifest(
            self,
            job_id: str,
            doc_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Ottiene il manifest del documento.

        api.py → GET /jobs/{job_id}/docs/{doc_id}/manifest
        ritorna direttamente il JSON del manifest.
        """
        if not (job_id and doc_id):
            self._show_error("Parametri non validi per il manifest documento.")
            return None

        return self._get(f"/jobs/{job_id}/docs/{doc_id}/manifest")

    def get_page_fixed_fields(
        self,
        job_id: str,
        doc_id: str,
        page_no: int,
        page_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Ottiene i campi fissi BPER per una pagina del documento.

        API → GET /jobs/{job_id}/docs/{doc_id}/pages/{page_no}/fixed_fields?page_type=...
        """
        if not (job_id and doc_id):
            self._show_error("Parametri non validi per i fixed fields della pagina.")
            return None
        params: Dict[str, Any] = {}
        if page_type:
            params["page_type"] = page_type
        return self._get(
            f"/jobs/{job_id}/docs/{doc_id}/pages/{page_no}/fixed_fields",
            params=params or None,
        )

    # ------------------------------------------------------------------ Utility: rerun IE
    def rerun_ie(self, job_id: str, delete_outputs: bool = False) -> Optional[Dict[str, Any]]:
        """
        Forza il worker IE a rielaborare i TXT già presenti per il job indicato.

        API → POST /jobs/{job_id}/ie-rerun?delete_outputs=false|true
        """
        if not job_id:
            self._show_error("Job ID non valido per il rerun IE.")
            return None
        path = f"/jobs/{job_id}/ie-rerun"
        params = {"delete_outputs": str(bool(delete_outputs)).lower()}
        url = self._make_url(path)
        try:
            resp = self._session.post(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            if not resp.content:
                return {}
            return resp.json()
        except requests.RequestException as e:
            self._show_error(f"Errore nel rerun IE {url}: {e}")
            return None

    def process_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Invia la richiesta di processamento intelligente per il job.

        API → POST /jobs/{job_id}/process
        """
        if not job_id:
            self._show_error("Job ID non valido per il processamento.")
            return None
        return self._post(f"/jobs/{job_id}/process")
