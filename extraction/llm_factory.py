"""LangChain ChatModel factory — replaces extraction/providers/ package."""

import os
from typing import Optional

from langchain_core.language_models import BaseChatModel


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

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs = {"model": model}
        if api_key:
            kwargs["api_key"] = api_key
        return ChatOpenAI(**kwargs)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY env var or pass api_key=."
            )
        return ChatGoogleGenerativeAI(model=model, google_api_key=key)

    raise ValueError(f"Unknown provider: {provider_name!r}. Available: ['openai', 'gemini']")
