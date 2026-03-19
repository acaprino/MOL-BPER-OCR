from __future__ import annotations

"""
llm_router.py

Router di pagina ed estrazione campi basato su:
 - MLPageRouter: wrappa il classificatore a prototipi esistente
 - LLMPageRouter: usa OpenAI Vision per routing + estrazione

Nota: L'LLMPageRouter è implementato in modo resiliente: se manca API key o
fallisce la chiamata, ritorna (None, 0.0, {}).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image

try:
    from openai import OpenAI  # type: ignore
except Exception:  # noqa: BLE001
    OpenAI = None  # type: ignore


@dataclass
class RouterResult:
    page_type: Optional[str]
    confidence: float
    fields: Dict[str, Any]
    # opzionali: per spiegare mismatch/diagnostica
    reason: Optional[str] = None
    expected: Optional[str] = None


class PageRouter:
    def route(self, image: Image.Image) -> RouterResult:
        raise NotImplementedError


class MLPageRouter(PageRouter):
    """Wrapper del classificatore a prototipi esistente."""

    def __init__(self, templates_dir: Path) -> None:
        # Import lazily per non forzare torch su ambienti senza supporto
        from page_classifier import BPERPagePrototypeClassifier  # type: ignore

        self.classifier = BPERPagePrototypeClassifier(
            templates_dir=templates_dir,
            crop_roi=(0.0, 0.12, 1.0, 0.30),
            similarity_threshold=0.70,
            device="cpu",
        )

    def route(self, image: Image.Image) -> RouterResult:
        label, score = self.classifier.classify(image)
        return RouterResult(page_type=label, confidence=float(score or 0.0), fields={})


class LLMPageRouter(PageRouter):
    """
    Router LLM (OpenAI Vision). Legge un file prompts.json con definizione delle pagine
    e dei campi da estrarre e costruisce un prompt strutturato con richiesta
    di output JSON.
    """

    def __init__(
            self,
            prompts_path: Path,
            *,
            provider: str = "openai",
            base_url: str = "https://api.openai.com/v1",
            model: str = "gpt-4o-mini",
            api_key: str = "",
            timeout: int = 60,
    ) -> None:
        self.prompts_path = Path(prompts_path)
        self.provider = provider
        self.base_url = base_url
        self.model = model
        self.api_key = api_key or ""
        self.timeout = int(timeout)
        self._spec: Dict[str, Any] = {}
        self._load_spec()

        self._client = None
        self._last_debug: Dict[str, Any] = {}
        self._expected_page: Optional[str] = None
        if OpenAI is not None and self.api_key:
            try:
                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except Exception:  # noqa: BLE001
                self._client = None

    def _load_spec(self) -> None:
        try:
            if self.prompts_path.exists():
                self._spec = json.loads(self.prompts_path.read_text(encoding="utf-8"))
            else:
                self._spec = {"pages": [], "fields": {}}
        except Exception:  # noqa: BLE001
            self._spec = {"pages": [], "fields": {}}

    def _build_system_prompt(self) -> str:
        pages = [p.get("name") for p in self._spec.get("pages", []) if p.get("name")]
        expected_txt = (
            f" La pagina attesa è '{self._expected_page}'. Conferma se l'immagine corrisponde davvero;"
            " in caso contrario, indica quale pagina è realmente e spiega brevemente il motivo in 'reason'."
            if self._expected_page else ""
        )
        return (
            "Sei un assistente che classifica schermate dell'app BPER. "
            "Identifica la pagina tra queste: " + ", ".join(pages) + ". "
            "Rispondi solo JSON con chiavi: page_type (string), confidence (0..1), reason (string opzionale)."
            + expected_txt
        )

    def _build_user_prompt(self) -> str:
        lines = ["Istruzioni per il riconoscimento pagina:"]
        if self._expected_page:
            lines.append(f"PAGINA ATTESA: {self._expected_page}")
        for p in self._spec.get("pages", []):
            name = p.get("name", "")
            hints = p.get("hints", "")
            lines.append(f"- {name}: {hints}")
        lines.append("Formato di risposta: JSON puro, senza testo extra.")
        return "\n".join(lines)

    def set_expected_page(self, name: Optional[str]) -> None:
        """Suggerisce al router qual è la prossima pagina attesa per aumentare la precisione."""
        self._expected_page = name

    def get_page_hints(self, name: str) -> Optional[str]:
        """Ritorna gli hints per una pagina dal file prompts.json, se presenti."""
        try:
            for p in self._spec.get("pages", []):
                if p.get("name") == name:
                    return p.get("hints")
        except Exception:
            pass
        return None

    def route(self, image: Image.Image) -> RouterResult:
        # Se manca client (niente API key o import fallito), fallback nullo
        if self._client is None:
            self._last_debug = {
                "error": "LLM client non inizializzato (manca API key o import OpenAI fallito)",
            }
            return RouterResult(None, 0.0, {})

        # Prepara immagini per la richiesta:
        #  - downscale lato lungo a 1280px per ridurre latenza/costi
        #  - aggiungi anche una ROI (header/tab) per aiutare il routing
        import base64
        import io

        def _downscale(img: Image.Image, max_side: int = 1280) -> Image.Image:
            w, h = img.size
            scale = min(1.0, float(max_side) / float(max(w, h)))
            if scale >= 1.0:
                return img
            new_size = (int(w * scale), int(h * scale))
            return img.resize(new_size, Image.Resampling.LANCZOS)

        full_img = _downscale(image)
        # ROI: fascia alta ~12%-30% dell'altezza
        try:
            w, h = image.size
            y1, y2 = int(0.12 * h), int(0.30 * h)
            roi = image.crop((0, y1, w, max(y1 + 1, y2)))
            roi = _downscale(roi)
        except Exception:
            roi = None

        def _to_data_url(img: Image.Image) -> str:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"

        full_url = _to_data_url(full_img)
        roi_url = _to_data_url(roi) if roi is not None else None

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt()

        # Piccolo retry/backoff per 429/timeout/transienti
        import time
        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                content_items = [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": full_url}},
                ]
                if roi_url:
                    content_items.append({"type": "image_url", "image_url": {"url": roi_url}})

                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content_items},
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                    timeout=self.timeout,
                )
                content = resp.choices[0].message.content if resp and resp.choices else ""
                data = {}
                try:
                    data = json.loads(content or "{}")
                except Exception:  # noqa: BLE001
                    # alcuni modelli potrebbero incapsulare il JSON in testo, prova a individuarlo
                    import re

                    m = re.search(r"\{[\s\S]*\}", content or "")
                    if m:
                        data = json.loads(m.group(0))

                page_type = data.get("page_type") if isinstance(data, dict) else None
                confidence = float(data.get("confidence", 0.0)) if isinstance(data, dict) else 0.0
                reason = data.get("reason") if isinstance(data, dict) else None
                # salva debug
                self._last_debug = {
                    "provider": self.provider,
                    "model": self.model,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response_text": content,
                    "parsed": {
                        "page_type": page_type,
                        "confidence": confidence,
                        "reason": reason,
                        "expected": self._expected_page,
                    },
                }
                return RouterResult(page_type, confidence, {}, reason=reason, expected=self._expected_page)
            except Exception as e:  # noqa: BLE001
                last_exc = e
                # backoff semplice
                time.sleep(0.5 * (attempt + 1))
        # fallito dopo i tentativi
        self._last_debug = {
            "provider": self.provider,
            "model": self.model,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "error": str(last_exc) if last_exc else "unknown error",
        }
        return RouterResult(None, 0.0, {}, reason=str(last_exc) if last_exc else None, expected=self._expected_page)

    def get_last_debug(self) -> Dict[str, Any]:
        """Ritorna i dettagli dell'ultimo scambio (prompt/risposta/parsed)."""
        return dict(self._last_debug)
