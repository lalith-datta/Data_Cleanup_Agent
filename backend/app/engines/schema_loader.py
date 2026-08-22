"""Load data/target_schema.yaml into a typed TargetSchema.

The schema drives everything downstream: alias/fuzzy mapping, enum
normalization, and Pydantic validation. It is the canonical spec the agent
maps every source file into (PRD §15, Epic 1.4).
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from ..config import get_settings


class FieldSpec(BaseModel):
    name: str
    type: str  # string | email | date | enum | number
    required: bool = False
    aliases: list[str] = []
    format: str | None = None
    allowed: list[str] = []  # enum values
    notes: str = ""


class TargetSchema(BaseModel):
    entity: str
    primary_key: str
    match_keys: list[str]
    fields: dict[str, FieldSpec]
    enum_normalization: dict[str, dict[str, list[str]]]
    unmapped_source_columns_policy: str = "escalate"

    def field_names(self) -> list[str]:
        return list(self.fields.keys())

    def alias_index(self) -> dict[str, str]:
        """normalized alias -> canonical field name (case/space-insensitive)."""
        idx: dict[str, str] = {}
        for fname, spec in self.fields.items():
            idx[_norm(fname)] = fname
            for a in spec.aliases:
                idx[_norm(a)] = fname
        return idx

    def fuzzy_terms(self) -> dict[str, str]:
        """every matchable surface form -> canonical field, for fuzzy scoring."""
        terms: dict[str, str] = {}
        for fname, spec in self.fields.items():
            terms[fname] = fname
            for a in spec.aliases:
                terms[a] = fname
        return terms


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


@lru_cache
def load_target_schema() -> TargetSchema:
    path = Path(get_settings().target_schema_path)
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    fields = {
        name: FieldSpec(name=name, **spec) for name, spec in raw["fields"].items()
    }
    return TargetSchema(
        entity=raw["entity"],
        primary_key=raw["primary_key"],
        match_keys=raw.get("match_keys", []),
        fields=fields,
        enum_normalization=raw.get("enum_normalization", {}),
        unmapped_source_columns_policy=raw.get(
            "unmapped_source_columns_policy", "escalate"
        ),
    )
