from functools import lru_cache

from ..config import get_settings
from .base import LLMClient
from .mock import MockLLMClient


@lru_cache
def get_llm_client() -> LLMClient:
    """LangChain-backed client when a provider is configured, else the
    deterministic MockLLM so the app runs with zero API keys."""
    if get_settings().llm_provider:
        from .langchain_client import LangChainClient

        return LangChainClient()
    return MockLLMClient()
