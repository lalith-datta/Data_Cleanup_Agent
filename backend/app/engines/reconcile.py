"""Reconciliation & merge (Epic 3): one record per person across files.

- IDs are normalized (`E1001` <-> `1001`) but the match keys from the target
  schema rule: email primary, employee_id fallback.
- Fields merge into one target-shaped record; provenance kept per field.
- Two files giving different non-null values for the same field raises a
  value_conflict escalation — never silent last-write-wins (PRD §3 #2).
- A field only one file has enriches the merged record silently (audited).
"""

import re
from dataclasses import dataclass, field

from .schema_loader import TargetSchema


@dataclass
class SourceRow:
    file: str
    row_index: int
    values: dict[str, str]  # canonical target field -> raw value


@dataclass
class MergeResult:
    natural_key: str
    merged: dict[str, str | None]
    provenance: dict[str, dict]  # field -> {"file": ..., "raw": ...}
    conflicts: list[dict] = field(default_factory=list)
    # each: {"field": ..., "values": [{"file":..., "value":...}, ...]}


def normalize_id(raw: str) -> str:
    """Digit-only, so `E1001` and `1001` normalize to the same key. A prefix
    letter is a formatting convention, not part of the identity."""
    return re.sub(r"\D", "", raw or "")


def natural_key_for(values: dict[str, str | None], schema: TargetSchema) -> str:
    """Match keys from schema: email primary, then employee_id."""
    for key in schema.match_keys:
        v = values.get(key)
        if v and str(v).strip():
            if key == schema.primary_key:
                return f"id:{normalize_id(str(v))}"
            return f"{key}:{str(v).strip().lower()}"
    return ""


def _equivalent(
    field: str,
    a: str,
    b: str,
    schema: TargetSchema,
    forced_formats: dict[str, str] | None = None,
) -> bool:
    """True when two raw values are the SAME fact in different surface forms
    (e.g. `15-03-2021` vs `2021-03-15`). Those are format differences for the
    cleaning stage, not human-worthy conflicts. Genuinely different values
    (work vs personal email) still conflict.

    By the time this runs, `apply_inferred_formats` has already rewritten
    whatever each file's own column evidence could resolve to ISO — so most
    date pairs are already identical strings and never reach the branch
    below. It exists as a fallback for whatever inference couldn't resolve,
    and for a human's explicit forced-format choice on rebuild."""
    na = " ".join(str(a).strip().split())
    nb = " ".join(str(b).strip().split())
    if na.lower() == nb.lower():
        return True
    spec = schema.fields.get(field)
    if spec and spec.type == "date":
        forced = (forced_formats or {}).get(field)
        if forced:
            ra = _parse_with_label(forced, na)
            rb = _parse_with_label(forced, nb)
            return bool(ra and rb and ra == rb)
        pa = set(_date_candidates(na).values())
        pb = set(_date_candidates(nb).values())
        if pa and pb:
            # Equivalent only when one side is unambiguous (a single
            # possible reading) and that reading is among the other side's
            # possibilities — the unambiguous side settles it. Two sides
            # that are BOTH ambiguous (even with full overlap, like
            # `03-04-2023` vs `04/03/2023` read either way) are a genuine
            # open question, not a coincidence to paper over.
            if len(pa) == 1 and next(iter(pa)) in pb:
                return True
            if len(pb) == 1 and next(iter(pb)) in pa:
                return True
        return False
    if spec and spec.type == "enum":
        # Two spellings of the same canonical value ("Pro" and "Premium"
        # both meaning premium) are the same fact, not a conflict —
        # enum_normalization already knows this mapping; conflict
        # detection has to use it too, or it fires before the cleaning
        # stage ever gets a chance to reconcile them.
        canon_a = _canonical_enum_value(field, na, schema)
        canon_b = _canonical_enum_value(field, nb, schema)
        if canon_a and canon_b and canon_a == canon_b:
            return True
    if spec and field == schema.primary_key:
        # E1001 vs 1001 — same employee id, different prefix formats
        da, db = re.sub(r"\D", "", na), re.sub(r"\D", "", nb)
        if da and da == db:
            return True
    if spec and spec.type == "email":
        # one side conforms to the field type, the other doesn't (e.g.
        # manager_email = "anil.kumar@acme.com" vs "Anil Kumar") — the
        # type-conformant value wins automatically; audited, not escalated
        a_ok, b_ok = "@" in na, "@" in nb
        if a_ok != b_ok:
            return True
    return False


def _canonical_enum_value(
    field: str, value: str, schema: TargetSchema
) -> str | None:
    """The canonical enum key `value` normalizes to, per the schema's own
    enum_normalization map — or None if it doesn't match any variant."""
    norm_map = schema.enum_normalization.get(field, {})
    lv = value.strip().lower()
    for canon, variants in norm_map.items():
        if lv == canon.lower() or lv in (v.lower() for v in variants):
            return canon
    return None


def _try_parse(fmt: str, value: str) -> str | None:
    from datetime import datetime

    try:
        return datetime.strptime(value.strip(), fmt).date().isoformat()
    except ValueError:
        return None


_DATE_FORMATS = [
    ("%Y-%m-%d", "iso"),
    ("%Y/%m/%d", "iso"),
    ("%d-%m-%Y", "dd/mm"),
    ("%d/%m/%Y", "dd/mm"),
    ("%m-%d-%Y", "mm/dd"),
    ("%m/%d/%Y", "mm/dd"),
    # Spelled-out months are never day/month-order ambiguous — their own
    # label, always a single candidate when they match at all.
    ("%d-%b-%Y", "text-month"),
    ("%d %b %Y", "text-month"),
    ("%d-%B-%Y", "text-month"),
    ("%d %B %Y", "text-month"),
]
# Order-only labels (dash vs slash is just a separator choice) so a human's
# "read this column dd/mm" resolution applies regardless of which
# punctuation a given file happens to use.
_LABEL_FORMATS: dict[str, list[str]] = {
    "dd/mm": ["%d-%m-%Y", "%d/%m/%Y"],
    "mm/dd": ["%m-%d-%Y", "%m/%d/%Y"],
    "text-month": ["%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y"],
}


def _date_candidates(value: str) -> dict[str, str]:
    """label -> parsed ISO date, for every format that accepts `value`."""
    out: dict[str, str] = {}
    for fmt, label in _DATE_FORMATS:
        parsed = _try_parse(fmt, value)
        if parsed:
            out[label] = parsed
    return out


def _parse_with_label(label: str, value: str) -> str | None:
    for fmt in _LABEL_FORMATS.get(label, []):
        parsed = _try_parse(fmt, value)
        if parsed:
            return parsed
    # ISO (either separator) is always acceptable regardless of the forced
    # day/month order
    return _try_parse("%Y-%m-%d", value) or _try_parse("%Y/%m/%d", value)


def infer_source_date_formats(
    rows: list["SourceRow"], schema: TargetSchema
) -> dict[tuple[str, str], str]:
    """For each (source file, target date field), infer the day/month order
    from that file's OWN column evidence only — never pooled across files,
    since different files legitimately use different conventions (PRD §7.4).
    A row anchors the order when only one reading is possible for it (day or
    month > 12); if every anchor row in that file's column agrees, adopt it
    for the whole column. Ambiguous rows are counted only as evidence they
    can neither confirm nor deny."""
    raws_by_key: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        for fname, raw in row.values.items():
            spec = schema.fields.get(fname)
            if not spec or spec.type != "date" or not raw or not str(raw).strip():
                continue
            raws_by_key.setdefault((row.file, fname), []).append(str(raw))

    inferred: dict[tuple[str, str], str] = {}
    for key, raws in raws_by_key.items():
        anchors = {
            next(iter(labels))
            for raw in raws
            if len(labels := set(_date_candidates(raw).keys())) == 1
        }
        if len(anchors) == 1:
            inferred[key] = next(iter(anchors))
    return inferred


def apply_inferred_formats(
    rows: list["SourceRow"], inferred: dict[tuple[str, str], str]
) -> list["SourceRow"]:
    """Rewrite each row's date values to ISO using its own file's inferred
    format, where one was found — later stages then see one settled fact
    instead of re-deriving (or mis-guessing) it per record."""
    out: list[SourceRow] = []
    for row in rows:
        values = dict(row.values)
        for fname, raw in row.values.items():
            label = inferred.get((row.file, fname))
            if not label or not raw:
                continue
            parsed = _parse_with_label(label, str(raw))
            if parsed:
                values[fname] = parsed
        out.append(SourceRow(file=row.file, row_index=row.row_index, values=values))
    return out


def merge_rows(
    rows: list[SourceRow],
    schema: TargetSchema,
    forced_formats: dict[str, str] | None = None,
) -> MergeResult:
    """Merge rows that share a natural key into one target-shaped record."""
    merged: dict[str, str | None] = {f: None for f in schema.field_names()}
    provenance: dict[str, dict] = {}
    conflicts: list[dict] = []

    for row in rows:
        for fname, raw in row.values.items():
            if fname not in merged:
                continue  # unmapped/dropped column — handled by escalations
            val = raw if raw is None else str(raw)
            if val is None or not str(val).strip():
                continue
            current = merged[fname]
            if current is None:
                merged[fname] = val
                provenance[fname] = {"file": row.file, "raw": raw}
            elif _equivalent(fname, str(current), str(val), schema, forced_formats):
                # equivalent values — prefer the type-conformant one
                spec = schema.fields.get(fname)
                if spec and spec.type == "email" and "@" not in str(current) and "@" in str(val):
                    merged[fname] = val
                    provenance[fname] = {"file": row.file, "raw": raw}
            else:
                conflict: dict = {
                    "field": fname,
                    "values": [
                        {"file": provenance[fname]["file"], "value": current},
                        {"file": row.file, "value": val},
                    ],
                }
                spec = schema.fields.get(fname)
                if spec and spec.type == "date":
                    # A remaining date disagreement is a format question, not
                    # a value dispute — route it like ambiguous_date (pick a
                    # reading, apply column-wide) rather than a raw
                    # pick-a-file value_conflict.
                    combined = {
                        **_date_candidates(str(current)),
                        **_date_candidates(str(val)),
                    }
                    if combined:
                        conflict["date_format_question"] = True
                        conflict["date_options"] = [
                            {"format": label, "parsed": parsed}
                            for label, parsed in combined.items()
                        ]
                conflicts.append(conflict)
                # keep first value pending human resolution (no silent guess)

    key = natural_key_for(merged, schema)
    return MergeResult(
        natural_key=key, merged=merged, provenance=provenance, conflicts=conflicts
    )


def group_rows(
    rows: list[SourceRow], schema: TargetSchema
) -> dict[str, list[SourceRow]]:
    """Group source rows into one group per person (union-find over ALL
    match keys). A row joins an existing group when it shares ANY match key
    with it — so `E1001`+work-email (HR) and `E1001`+gmail (payroll) still
    land together, and the email difference surfaces as a value_conflict
    instead of a duplicate person.
    """
    key_to_group: dict[str, str] = {}
    groups: dict[str, list[SourceRow]] = {}

    def keys_of(values: dict[str, str | None]) -> list[str]:
        keys: list[str] = []
        for key in schema.match_keys:
            v = values.get(key)
            if v and str(v).strip():
                if key == schema.primary_key:
                    keys.append(f"id:{normalize_id(str(v))}")
                else:
                    keys.append(f"{key}:{str(v).strip().lower()}")
        return keys

    for row in rows:
        keys = keys_of(row.values)
        gid = next((key_to_group[k] for k in keys if k in key_to_group), None)
        if gid is None:
            gid = keys[0] if keys else f"unmatched:{row.file}:{row.row_index}"
            groups[gid] = []
        groups[gid].append(row)
        for k in keys:
            key_to_group[k] = gid
    return groups


def reconcile(
    rows: list[SourceRow],
    schema: TargetSchema,
    forced_formats: dict[str, str] | None = None,
) -> list[MergeResult]:
    return [
        merge_rows(group, schema, forced_formats)
        for group in group_rows(rows, schema).values()
    ]
