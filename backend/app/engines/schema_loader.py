"""Load and parse target schemas — from file or user-uploaded content.

The schema drives everything downstream: alias/fuzzy mapping, enum
normalization, and Pydantic validation. It is the canonical spec the agent
maps every source file into (PRD §15, Epic 1.4).

Schemas can come from:
  1. The static default file (data/target_schema.yaml)
  2. A user-uploaded YAML/JSON per migration run
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel

from ..config import get_settings

if TYPE_CHECKING:
    from ..models import MigrationRun


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


# ---- Type inference for lenient parsing ------------------------------------

_EMAIL_HINTS = {"email", "e-mail", "mail"}
_DATE_HINTS = {"date", "dob", "doj", "birth", "joining", "created", "updated"}
_NUMBER_HINTS = {"salary", "ctc", "compensation", "amount", "price", "cost", "age"}
_ENUM_HINTS = {"status", "state", "type", "category", "level", "grade"}


def _infer_type(field_name: str) -> str:
    """Best-effort type inference from a field name when no type is given."""
    lower = field_name.lower().replace("_", " ").replace("-", " ")
    tokens = set(lower.split())
    if tokens & _EMAIL_HINTS:
        return "email"
    if tokens & _DATE_HINTS:
        return "date"
    if tokens & _NUMBER_HINTS:
        return "number"
    if tokens & _ENUM_HINTS:
        return "enum"
    return "string"


# ---- Lenient schema parsing ------------------------------------------------

def parse_target_schema(raw: dict[str, Any]) -> TargetSchema:
    """Parse a raw dict into a TargetSchema, auto-filling missing top-level
    keys so users can upload minimal schemas (even just a list of field names).

    Accepts many shapes:
      - Full spec with entity/primary_key/match_keys/fields
      - Just {"fields": {"name": {"type": "string"}, ...}}
      - Just {"fields": {"name": "string", ...}}   (shorthand)
      - Just {"fields": ["name", "email", ...]}     (list of names)
      - Just ["name", "email", ...]                  (bare list)
    """
    # Bare list at root → treat as field names
    if isinstance(raw, list):
        raw = {"fields": raw}

    raw_fields = raw.get("fields", {})
    fields: dict[str, FieldSpec] = {}

    if isinstance(raw_fields, list):
        # List of field names or dicts
        for item in raw_fields:
            if isinstance(item, str):
                fields[item] = FieldSpec(name=item, type=_infer_type(item))
            elif isinstance(item, dict):
                name = item.get("name", item.get("field", ""))
                if name:
                    fields[name] = _parse_field(name, item)
    elif isinstance(raw_fields, dict):
        for name, spec in raw_fields.items():
            if spec is None:
                fields[name] = FieldSpec(name=name, type=_infer_type(name))
            elif isinstance(spec, str):
                # shorthand: field_name: "type"
                fields[name] = FieldSpec(name=name, type=spec or _infer_type(name))
            elif isinstance(spec, dict):
                fields[name] = _parse_field(name, spec)
            else:
                fields[name] = FieldSpec(name=name, type=_infer_type(name))

    if not fields:
        raise ValueError(
            "Schema must contain at least one field. Provide a 'fields' key "
            "with field definitions, or a simple list of field names."
        )

    # Auto-fill top-level keys
    entity = raw.get("entity", "record")
    field_list = list(fields.keys())

    # primary_key: use explicit, else first field with 'id' in name, else first field
    primary_key = raw.get("primary_key", "")
    if not primary_key:
        id_fields = [f for f in field_list if "id" in f.lower()]
        primary_key = id_fields[0] if id_fields else field_list[0]

    # match_keys: use explicit, else email fields + primary_key
    match_keys = raw.get("match_keys", [])
    if not match_keys:
        email_fields = [f for f in field_list if fields[f].type == "email"]
        match_keys = email_fields + ([primary_key] if primary_key not in email_fields else [])
        if not match_keys:
            match_keys = [primary_key]

    return TargetSchema(
        entity=entity,
        primary_key=primary_key,
        match_keys=match_keys,
        fields=fields,
        enum_normalization=raw.get("enum_normalization", {}),
        unmapped_source_columns_policy=raw.get(
            "unmapped_source_columns_policy", "escalate"
        ),
    )


def _parse_field(name: str, spec: dict[str, Any]) -> FieldSpec:
    """Parse a single field spec dict leniently."""
    return FieldSpec(
        name=name,
        type=spec.get("type", _infer_type(name)),
        required=spec.get("required", False),
        aliases=spec.get("aliases", []),
        format=spec.get("format"),
        allowed=spec.get("allowed", []),
        notes=spec.get("notes", spec.get("description", "")),
    )


# ---- Content-based loading (for uploaded schemas) --------------------------

def load_schema_from_content(content: str, fmt: str = "yaml") -> TargetSchema:
    """Parse a user-uploaded schema string (YAML or JSON) into a TargetSchema.
    Raises ValueError on unparseable/empty content."""
    try:
        if fmt in ("json",):
            raw = json.loads(content)
        else:
            raw = yaml.safe_load(content)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Failed to parse {fmt.upper()} content: {exc}") from exc

    if raw is None:
        raise ValueError("Schema file is empty.")

    return parse_target_schema(raw)


def schema_to_dict(schema: TargetSchema) -> dict[str, Any]:
    """Serialize a TargetSchema to a JSON-safe dict for DB storage."""
    return schema.model_dump(mode="json")


# ---- Run-aware loading -----------------------------------------------------

def get_run_schema(run: "MigrationRun") -> TargetSchema:
    """Return the effective schema for a migration run: custom if uploaded,
    else the default from the static file."""
    if run.custom_schema_json:
        return parse_target_schema(run.custom_schema_json)
    return load_target_schema()


# ---- Default file loading --------------------------------------------------

@lru_cache
def load_target_schema() -> TargetSchema:
    path = Path(get_settings().target_schema_path)
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_target_schema(raw)
