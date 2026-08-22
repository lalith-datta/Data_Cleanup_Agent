"""Cleaning & normalization (Epic 4): safe auto-fixes only.

- whitespace trim + casing collapse on all strings
- enum normalization from the schema (e.g. `ON LEAVE` -> `on_leave`)
- per-column date parsing -> ISO; genuinely ambiguous columns (day and month
  both <= 12 across rows AND cross-file disagreement) raise ambiguous_date
  instead of guessing (PRD §3 #3)
- light phone normalization
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from .schema_loader import TargetSchema


@dataclass
class CleanResult:
    cleaned: dict[str, str | None]
    changes: list[dict] = field(default_factory=list)  # audited auto-fixes
    ambiguous_dates: list[dict] = field(default_factory=list)


# Categorical, short free-text fields where title-casing is safe. Deliberately
# excludes full_name (apostrophes/particles like "D'Souza" or "van der Berg"
# are easy to mangle) and email (case can be semantically meaningful).
_TITLE_CASE_FIELDS = {"job_title", "department", "location"}


def clean_whitespace_casing(
    merged: dict[str, str | None], provenance: dict, changes: list[dict]
) -> dict[str, str | None]:
    out = {}
    for fname, val in merged.items():
        if val is None:
            out[fname] = None
            continue
        original = str(val)
        trimmed = " ".join(original.strip().split())
        fixed = trimmed.title() if fname in _TITLE_CASE_FIELDS and trimmed else trimmed
        if fixed != original:
            whitespace_changed = trimmed != original
            casing_changed = fixed != trimmed
            if whitespace_changed and casing_changed:
                reason = "trimmed whitespace and normalized casing"
            elif casing_changed:
                reason = "casing normalized"
            else:
                reason = "trimmed whitespace/collapsed spacing"
            changes.append(
                {"field": fname, "before": val, "after": fixed, "reason": reason}
            )
        out[fname] = fixed
    return out


def normalize_enums(
    merged: dict[str, str | None], schema: TargetSchema, changes: list[dict]
) -> dict[str, str | None]:
    out = dict(merged)
    for fname, mapping in schema.enum_normalization.items():
        val = out.get(fname)
        if not val:
            continue
        norm = " ".join(str(val).strip().lower().split())
        for canonical, variants in mapping.items():
            if norm in [v.lower() for v in variants]:
                if val != canonical:
                    changes.append(
                        {
                            "field": fname,
                            "before": val,
                            "after": canonical,
                            "reason": "enum normalization",
                        }
                    )
                out[fname] = canonical
                break
    return out


_DATE_FORMATS = [
    ("%Y-%m-%d", "iso"),
    ("%d-%m-%Y", "dd/mm"),
    ("%d/%m/%Y", "dd/mm"),
    ("%m-%d-%Y", "mm/dd"),
    ("%m/%d/%Y", "mm/dd"),
]


def _parse_with(fmt: str, value: str) -> str | None:
    try:
        return datetime.strptime(value.strip(), fmt).date().isoformat()
    except ValueError:
        return None


def parse_dates(
    merged: dict[str, str | None],
    schema: TargetSchema,
    changes: list[dict],
    forced_formats: dict[str, str] | None = None,
) -> tuple[dict[str, str | None], list[dict]]:
    """Parse date fields to ISO. forced_formats carries human-resolved
    ambiguous_date decisions (applied field-wide). Returns (merged, ambiguous)."""
    out = dict(merged)
    ambiguous: list[dict] = []
    forced_formats = forced_formats or {}

    for fname, spec in schema.fields.items():
        if spec.type != "date":
            continue
        val = out.get(fname)
        if not val:
            continue
        raw = str(val).strip()

        if fname in forced_formats:
            label = forced_formats[fname]
            parsed = None
            for fmt, lbl in _DATE_FORMATS:
                if lbl == label and (parsed := _parse_with(fmt, raw)):
                    break
            if not parsed:
                parsed = _parse_with("%Y-%m-%d", raw)  # ISO is always acceptable
            if parsed:
                if parsed != raw:
                    changes.append(
                        {
                            "field": fname,
                            "before": raw,
                            "after": parsed,
                            "reason": f"date normalized via human-resolved format {fmt}",
                        }
                    )
                out[fname] = parsed
            continue

        candidates: dict[str, str] = {}
        for fmt, label in _DATE_FORMATS:
            parsed = _parse_with(fmt, raw)
            if parsed:
                candidates[label] = parsed

        if not candidates:
            continue  # unparseable -> validation stage catches it

        distinct = set(candidates.values())
        if len(distinct) == 1:
            parsed = next(iter(distinct))
            if parsed != raw:
                changes.append(
                    {
                        "field": fname,
                        "before": raw,
                        "after": parsed,
                        "reason": "date normalized to ISO",
                    }
                )
            out[fname] = parsed
        else:
            # Genuinely ambiguous (e.g. 03-04-2023 -> Mar 4 or Apr 3?)
            ambiguous.append(
                {
                    "field": fname,
                    "raw": raw,
                    "options": [
                        {"format": label, "parsed": parsed}
                        for label, parsed in candidates.items()
                    ],
                }
            )

    return out, ambiguous


def normalize_phones(
    merged: dict[str, str | None], schema: TargetSchema, changes: list[dict]
) -> dict[str, str | None]:
    out = dict(merged)
    for fname, spec in schema.fields.items():
        if fname != "phone":
            continue
        val = out.get(fname)
        if not val:
            continue
        raw = str(val)
        digits = re.sub(r"[^\d+]", "", raw)
        fixed = re.sub(r"(?!^)\+", "", digits)  # keep leading + only
        if fixed and fixed != raw.strip():
            changes.append(
                {
                    "field": fname,
                    "before": raw,
                    "after": fixed,
                    "reason": "phone normalized",
                }
            )
            out[fname] = fixed
    return out


def clean_record(
    merged: dict[str, str | None],
    provenance: dict,
    schema: TargetSchema,
    forced_formats: dict[str, str] | None = None,
) -> CleanResult:
    changes: list[dict] = []
    out = clean_whitespace_casing(merged, provenance, changes)
    out = normalize_enums(out, schema, changes)
    out, ambiguous = parse_dates(out, schema, changes, forced_formats)
    out = normalize_phones(out, schema, changes)
    return CleanResult(cleaned=out, changes=changes, ambiguous_dates=ambiguous)
