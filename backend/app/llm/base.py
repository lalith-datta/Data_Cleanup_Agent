from abc import ABC, abstractmethod

from pydantic import BaseModel


class MappingSuggestion(BaseModel):
    target_field: str | None  # None = model thinks no candidate fits
    confidence: float  # 0.0 - 1.0
    rationale: str


class LLMClient(ABC):
    """Provider-agnostic LLM interface. The LLM adjudicates ONLY genuinely
    ambiguous mapping decisions — the deterministic engines never call it
    for the safe majority (deterministic-first, LLM-last)."""

    @abstractmethod
    async def suggest_mapping(
        self,
        source_column: str,
        sample_values: list[str],
        candidate_fields: list[str],
    ) -> MappingSuggestion | None:
        """Return a mapping suggestion, or None when no confident suggestion
        exists (caller escalates to a human in that case)."""
