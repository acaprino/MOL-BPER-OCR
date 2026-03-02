"""LangChain ChatModel factory — replaces extraction/providers/ package."""

import os
import warnings
from typing import Optional

from langchain_core.language_models import BaseChatModel

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
) -> BaseChatModel:
    """Create a LangChain ChatModel for the given provider.

    Lazy imports ensure only the installed provider's package is loaded.
    Returned instances are thread-safe.
    """
    provider = provider_name.lower()

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

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if model.startswith("gemini"):
            raise ValueError(
                f"Model {model!r} looks like a Gemini model but provider is 'openai'. "
                f"Set LLM_PROVIDER=gemini or choose an OpenAI model."
            )
        return ChatOpenAI(model=model, api_key=key)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if model.startswith("gpt-"):
            raise ValueError(
                f"Model {model!r} looks like an OpenAI model but provider is 'gemini'. "
                f"Set LLM_MODEL to a Gemini model (e.g. 'gemini-3-flash-preview')."
            )
        kwargs = {}
        thinking_level = os.getenv("LLM_THINKING_LEVEL", "").strip().lower()
        if thinking_level in ("low", "medium", "high"):
            kwargs["thinking_level"] = thinking_level
        return ChatGoogleGenerativeAI(model=model, google_api_key=key, **kwargs)

    raise ValueError(f"Unknown provider: {provider_name!r}. Available: ['openai', 'gemini']")
