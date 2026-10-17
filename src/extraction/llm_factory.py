"""LangChain ChatModel factory — the single provider-selection point."""

import os
import warnings
from typing import Optional

from langchain_core.language_models import BaseChatModel

from extraction.config import LLM_THINKING_LEVEL
from extraction.model_adapters import adapter_for, validate_thinking_level

_PROVIDERS = ("openai", "gemini")

# Legacy env vars — checked as fallback so existing deployments keep working.
_LEGACY_KEY_VARS = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def create_chat_model(
    provider_name: str,
    *,
    model: str,
    api_key: Optional[str] = None,
    thinking_level: Optional[str] = None,
) -> BaseChatModel:
    """Create a LangChain ChatModel for the given provider.

    The model family (src/extraction/model_adapters.py) decides how the model is
    built; thinking_level defaults to LLM_THINKING_LEVEL. Lazy imports ensure
    only the installed provider's package is loaded. Returned instances are
    thread-safe.
    """
    provider = provider_name.strip().lower()
    model = model.strip()

    key = (api_key or os.getenv("LLM_API_KEY") or "").strip()
    if not key:
        legacy_var = _LEGACY_KEY_VARS.get(provider)
        if legacy_var:
            key = (os.getenv(legacy_var) or "").strip()
            if key:
                warnings.warn(
                    f"{legacy_var} is deprecated. Use LLM_API_KEY instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
    if not key:
        raise ValueError(
            "API key required. Set LLM_API_KEY env var or pass api_key=."
        )

    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_name!r}. Available: {list(_PROVIDERS)}")

    adapter = adapter_for(model)
    if adapter.provider != provider:
        raise ValueError(
            f"Model {model!r} is a {adapter.family} model but provider is {provider!r}. "
            f"Set LLM_PROVIDER={adapter.provider} or choose a {provider} model."
        )

    level = validate_thinking_level(LLM_THINKING_LEVEL if thinking_level is None else thinking_level)
    return adapter.build(model, key, level)
