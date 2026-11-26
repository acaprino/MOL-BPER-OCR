"""Page decisions from the shipped catalog, with only the provider response faked."""

import json
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

import app_paths
import llm_router
from llm_router import LLMPageRouter, RouterResult


CATALOG = app_paths.templates_dir() / "prompts.json"
SEARCH = "Risultato ricerca"
NOTES = "Note da Richiesta"
GUARANTEE = "Gestione Fidi e Garanzie - Tooltip Descrizione Garanzie"
CONSAP = f"{GUARANTEE} (riga 1)"
MORTGAGE = f"{GUARANTEE} (riga 2)"
OTHER = "Altro / Non riconosciuto"


@pytest.fixture
def route_reply(monkeypatch: pytest.MonkeyPatch) -> Callable[..., RouterResult]:
    client = Mock()
    monkeypatch.setattr(llm_router, "OpenAI", lambda **kwargs: client)
    router = LLMPageRouter(CATALOG, api_key="test")
    image = Image.new("RGB", (80, 60))

    def route(page: str, confidence: object = 0.95, evidence: object = None) -> RouterResult:
        response = {"page_type": page, "confidence": confidence, "reason": "Riscontro visivo"}
        if evidence is not None:
            response["evidence"] = evidence
        message = SimpleNamespace(content=json.dumps(response))
        client.chat.completions.create.return_value.choices = [SimpleNamespace(message=message)]
        return router.route(image)

    return route


@pytest.mark.parametrize("confidence", [0.59, 95, "NaN", True])
def test_unusable_confidence_abstains(route_reply: Callable[..., RouterResult], confidence: object) -> None:
    assert route_reply(SEARCH, confidence).page_type == OTHER


def test_confidence_floor_is_inclusive(route_reply: Callable[..., RouterResult]) -> None:
    assert route_reply(SEARCH, 0.60).page_type == SEARCH


def test_uncatalogued_label_is_an_abstention(route_reply: Callable[..., RouterResult]) -> None:
    assert route_reply("Gestione Documentale").page_type == OTHER


@pytest.mark.parametrize("heading", ["Gestione Documentale", "Nota all'istruttoria", "Note da Richiesta", None])
def test_notes_requires_its_content_heading(route_reply: Callable[..., RouterResult], heading: str | None) -> None:
    # The tab named "Note da Richiesta" is also visible beside the active istruttoria tab.
    assert route_reply(NOTES, evidence=heading).page_type == OTHER


def test_collapsed_notes_heading_suffices(route_reply: Callable[..., RouterResult]) -> None:
    assert route_reply(NOTES, evidence="Nota della richiesta").page_type == NOTES


@pytest.mark.parametrize("page, text", [
    (CONSAP, "55-IPOTECA DI PRIMO GRADO"),  # The curated tooltip-3a has a mortgage in row 1.
    (MORTGAGE, "457-IMP. FID. F.DO 1 CASA DR SOSTEGNI BIS"),
    (MORTGAGE, None),
])
def test_guarantee_row_alone_cannot_decide(route_reply: Callable[..., RouterResult], page: str, text: str | None) -> None:
    assert route_reply(page, evidence=text).page_type == OTHER


@pytest.mark.parametrize("page, text", [
    (CONSAP, "457 - IMP. FID. F.DO 1 CASA DR SOSTEGNI BIS"),
    (MORTGAGE, "55–Ipoteca di primo grado"),
])
def test_guarantee_accepts_its_visible_tooltip(route_reply: Callable[..., RouterResult], page: str, text: str) -> None:
    assert route_reply(page, evidence=text).page_type == page


def test_unconfigured_router_explains_why_it_cannot_recognize_a_page() -> None:
    result = LLMPageRouter(CATALOG, api_key="").route(Image.new("RGB", (80, 60)))

    assert result.page_type is None
    assert "API key" in (result.reason or "")
