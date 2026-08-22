"""Mapping engine (Epic 2): source column -> target field with confidence.

Deterministic-first, LLM-last:
  1. exact alias match (confidence 1.0)
  2. RapidFuzz token_sort_ratio against field names + aliases
  3. decision fn applies the PRD §8 thresholds:
       score >= auto_apply and single clear winner  -> auto_apply
       top-2 within ambiguous_delta                  -> ambiguous_mapping
       min <= score < auto_apply, single winner      -> auto_apply (low-conf note)
       score < min                                   -> LLM adjudicates, else unmapped_column
"""

from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from ..config import get_settings
from .schema_loader import TargetSchema


@dataclass
class MappingDecision:
    source_column: str
    decision: str  # auto_apply | ambiguous_mapping | unmapped_column
    target_field: str | None = None
    method: str = "fuzzy"  # alias | fuzzy | llm | manual
    confidence: float = 0.0
    rationale: str = ""
    candidates: list[dict] = field(default_factory=list)
    low_confidence_note: bool = False


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def score_candidates(source_column: str, schema: TargetSchema) -> list[dict]:
    """Top fuzzy candidates across all matchable surface forms, folded back
    to canonical field names (best score per field wins)."""
    terms = schema.fuzzy_terms()
    raw = process.extract(
        source_column,
        list(terms.keys()),
        scorer=fuzz.token_sort_ratio,
        limit=8,
    )
    best: dict[str, float] = {}
    for surface, score, _ in raw:
        canon = terms[surface]
        best[canon] = max(best.get(canon, 0.0), score)
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    return [
        {"field": f, "score": round(s / 100, 3)} for f, s in ranked[:4]
    ]


def decide_mapping(source_column: str, schema: TargetSchema) -> MappingDecision:
    s = get_settings()

    # 1. exact alias
    alias_hit = schema.alias_index().get(_norm(source_column))
    if alias_hit:
        return MappingDecision(
            source_column=source_column,
            decision="auto_apply",
            target_field=alias_hit,
            method="alias",
            confidence=1.0,
            rationale=f"exact alias match for '{source_column}'",
        )

    # 2. fuzzy
    candidates = score_candidates(source_column, schema)
    if not candidates:
        return MappingDecision(
            source_column=source_column,
            decision="unmapped_column",
            rationale="no fuzzy candidates",
        )

    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None

    # 3a. ambiguous: top-2 within delta
    if second and (top["score"] - second["score"]) <= s.ambiguous_delta:
        return MappingDecision(
            source_column=source_column,
            decision="ambiguous_mapping",
            confidence=top["score"],
            rationale=(
                f"top candidates within {s.ambiguous_delta} delta: "
                f"{top['field']} ({top['score']}) vs "
                f"{second['field']} ({second['score']})"
            ),
            candidates=candidates,
        )

    # 3b. clear winner
    if top["score"] >= s.auto_apply_threshold:
        return MappingDecision(
            source_column=source_column,
            decision="auto_apply",
            target_field=top["field"],
            method="fuzzy",
            confidence=top["score"],
            rationale=f"fuzzy match {top['score']} (>= {s.auto_apply_threshold})",
            candidates=candidates,
        )
    if top["score"] >= s.min_map_threshold:
        return MappingDecision(
            source_column=source_column,
            decision="auto_apply",
            target_field=top["field"],
            method="fuzzy",
            confidence=top["score"],
            rationale=(
                f"fuzzy match {top['score']} "
                f"(below {s.auto_apply_threshold} — low-confidence, audited)"
            ),
            candidates=candidates,
            low_confidence_note=True,
        )

    # 3c. below min -> LLM adjudication happens in the orchestrator (async);
    # here we mark it for that path.
    return MappingDecision(
        source_column=source_column,
        decision="unmapped_column",
        confidence=top["score"],
        rationale=f"best fuzzy score {top['score']} below {s.min_map_threshold}",
        candidates=candidates,
    )
