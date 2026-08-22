"""Validation (Epic 5): enforce the target schema per record.

Checks required presence, email/date/enum/number validity. One auto-fix pass
runs first; anything still failing after that is a hard failure the pipeline
escalates as validation_failure (never silently dropped).
"""

import re
from dataclasses import dataclass
from datetime import datetime

from .schema_loader import TargetSchema

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class FieldError:
    field: str
    error: str
    value: str | None


def _is_iso_date(v: str) -> bool:
    try:
        datetime.strptime(v.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_record(
    merged: dict[str, str | None], schema: TargetSchema
) -> list[FieldError]:
    errors: list[FieldError] = []
    for fname, spec in schema.fields.items():
        val = merged.get(fname)
        present = val is not None and str(val).strip() != ""

        if spec.required and not present:
            errors.append(FieldError(fname, "required field missing", val))
            continue
        if not present:
            continue

        v = str(val).strip()
        if spec.type == "email" and not EMAIL_RE.match(v):
            errors.append(FieldError(fname, "invalid email", v))
        elif spec.type == "date" and not _is_iso_date(v):
            errors.append(FieldError(fname, "invalid date (expected YYYY-MM-DD)", v))
        elif spec.type == "enum" and spec.allowed and v not in spec.allowed:
            errors.append(
                FieldError(fname, f"not an allowed value {spec.allowed}", v)
            )
        elif spec.type == "number":
            try:
                float(v.replace(",", ""))
            except ValueError:
                errors.append(FieldError(fname, "invalid number", v))
    return errors


_FIXABLE_DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"]


def auto_fix(
    merged: dict[str, str | None], schema: TargetSchema
) -> tuple[dict[str, str | None], list[dict]]:
    """One deterministic fix-up pass before declaring hard failures."""
    out = dict(merged)
    fixes: list[dict] = []
    for fname, spec in schema.fields.items():
        val = out.get(fname)
        if not val:
            continue
        v = str(val).strip()

        if spec.type == "email" and not EMAIL_RE.match(v):
            fixed = v.lower().replace(" ", "")
            if EMAIL_RE.match(fixed):
                out[fname] = fixed
                fixes.append({"field": fname, "before": val, "after": fixed,
                              "reason": "auto-fixed email casing/spacing"})
        # NOTE: dates are deliberately NOT auto-fixed here — the clean stage
        # owns date parsing, and ambiguity must escalate, never be guessed.
        elif spec.type == "number":
            try:
                float(v.replace(",", ""))
                if v != v.replace(",", ""):
                    out[fname] = v.replace(",", "")
                    fixes.append({"field": fname, "before": val,
                                  "after": out[fname], "reason": "stripped thousands separators"})
            except ValueError:
                pass
    return out, fixes
