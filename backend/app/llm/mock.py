from rapidfuzz import fuzz, process

from .base import LLMClient, MappingSuggestion


class MockLLMClient(LLMClient):
    """Deterministic stand-in used when no LLM provider is configured.

    Keeps the whole pipeline runnable with zero API keys — mapping still
    works via the closest fuzzy candidate (Epic 0.6 / 13.5 graceful
    degradation).
    """

    async def suggest_mapping(
        self,
        source_column: str,
        sample_values: list[str],
        candidate_fields: list[str],
    ) -> MappingSuggestion | None:
        if not candidate_fields:
            return None
        match = process.extractOne(
            source_column, candidate_fields, scorer=fuzz.token_sort_ratio
        )
        if not match:
            return None
        field, score, _ = match
        return MappingSuggestion(
            target_field=field,
            confidence=round(score / 100, 3),
            rationale="mock heuristic: closest fuzzy candidate",
        )
