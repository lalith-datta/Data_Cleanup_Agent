import json
import re

from ..config import get_settings
from .base import LLMClient, MappingSuggestion

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "groq": "llama-3.1-8b-instant",
    "google-genai": "gemini-2.0-flash",
    "ollama": "llama3.1:8b",
}

_PROMPT = """You map a source spreadsheet column to a target schema field for an
employee data migration.

Source column: {source_column}
Sample values: {samples}
Candidate target fields: {candidates}

Pick the single best target field, or null if none fits semantically.
Respond with STRICT JSON only, no prose:
{{"target_field": "<one of the candidates or null>", "confidence": <0.0-1.0>, "rationale": "<one line>"}}"""


class LangChainClient(LLMClient):
    """Provider-agnostic via LangChain init_chat_model. Provider, model and
    key all come from env — swap OpenAI/Anthropic/Groq/Gemini/Ollama with no
    code change."""

    def __init__(self) -> None:
        s = get_settings()
        self.provider = s.llm_provider
        self.model_name = s.llm_model or DEFAULT_MODELS.get(self.provider, "")
        self._model = None

    def _get_model(self):
        if self._model is None:
            from langchain.chat_models import init_chat_model

            s = get_settings()
            # A misconfigured/unreachable provider (e.g. LLM_PROVIDER=ollama
            # with no daemon running) must fail fast, not eat the library's
            # default multi-second timeout on every ambiguous column — the
            # caller already treats a failure as "escalate", so bounding
            # this tightly only ever trades a slow wrong answer for a
            # slightly-less-slow escalation, never correctness.
            kwargs: dict = {"temperature": 0, "timeout": 4}
            if self.provider == "openai" and s.openai_api_key:
                kwargs["api_key"] = s.openai_api_key
            elif self.provider == "anthropic" and s.anthropic_api_key:
                kwargs["api_key"] = s.anthropic_api_key
            elif self.provider == "groq" and s.groq_api_key:
                kwargs["api_key"] = s.groq_api_key
            elif self.provider == "google-genai" and s.google_api_key:
                kwargs["api_key"] = s.google_api_key
            elif self.provider == "ollama":
                kwargs["base_url"] = s.ollama_base_url
            self._model = init_chat_model(
                self.model_name, model_provider=self.provider, **kwargs
            )
        return self._model

    async def suggest_mapping(
        self,
        source_column: str,
        sample_values: list[str],
        candidate_fields: list[str],
    ) -> MappingSuggestion | None:
        if not candidate_fields:
            return None
        prompt = _PROMPT.format(
            source_column=source_column,
            samples=sample_values[:5],
            candidates=candidate_fields,
        )
        try:
            resp = await self._get_model().ainvoke(prompt)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                return None
            data = json.loads(m.group(0))
            target = data.get("target_field")
            if target is not None and target not in candidate_fields:
                return None
            return MappingSuggestion(
                target_field=target,
                confidence=max(0.0, min(1.0, float(data.get("confidence", 0)))),
                rationale=str(data.get("rationale", ""))[:300],
            )
        except Exception:
            # LLM failure must never break the pipeline — caller escalates.
            return None
