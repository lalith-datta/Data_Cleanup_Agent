"""Ingestion & column profiling (Epic 1).

Parses CSV/Excel into pandas DataFrames (encoding-safe, empty rows dropped)
and profiles each column: dominant type + sample values. Profiling feeds the
mapping engine's confidence decisions in Epic 2.
"""

from pathlib import Path
from typing import Any

import pandas as pd

EMAIL_HINT = "@"


def parse_file(path: str) -> pd.DataFrame:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(p, encoding=enc, dtype=str)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError(f"Could not decode {p.name}")
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(p, dtype=str)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    df = df.dropna(how="all").reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _classify_column(values: list[str]) -> str:
    """Dominant value type for a column's non-empty samples."""
    vals = [v for v in values if v and v.strip()]
    if not vals:
        return "empty"

    def frac(pred) -> float:
        return sum(1 for v in vals if pred(v)) / len(vals)

    if frac(lambda v: EMAIL_HINT in v) >= 0.6:
        return "email"
    if frac(_looks_like_date) >= 0.6:
        return "date"
    if frac(_looks_like_number) >= 0.8:
        return "number"
    return "string"


def _looks_like_date(v: str) -> bool:
    v = v.strip()
    if len(v) < 6 or len(v) > 12:
        return False
    digits = sum(c.isdigit() for c in v)
    seps = sum(c in "/-." for c in v)
    return seps >= 2 and digits >= 4


def _looks_like_number(v: str) -> bool:
    try:
        float(v.replace(",", "").strip())
        return True
    except ValueError:
        return False


def profile_columns(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    profile: dict[str, dict[str, Any]] = {}
    for col in df.columns:
        samples = [str(v) for v in df[col].dropna().head(5).tolist()]
        profile[col] = {
            "inferred_type": _classify_column(samples),
            "samples": samples,
            "non_empty": int(df[col].notna().sum()),
        }
    return profile
