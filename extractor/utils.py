import re
from typing import Any, Optional


NUMERIC_RE = re.compile(
    r"""
    ^\(?-?
    (?:
        \d{1,3}(?:[,\s]\d{3})+   # 1,234,567 or 1 234 567
        |
        \d+(?:\.\d+)?            # 123 or 123.45
    )
    \)?$
    """,
    re.VERBOSE
)

NOTE_RE = re.compile(r"^\d+(?:\.\d+)?$")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
MONTH_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\b",
    re.IGNORECASE
)


def normalize_spaces(text: Any) -> str:
    if text is None:
        return ""
    text = str(text).replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def looks_numeric(text: str) -> bool:
    t = normalize_spaces(text)
    if t in {"", "-", "—", "–"}:
        return False
    return bool(NUMERIC_RE.match(t))


def looks_note_ref(text: str) -> bool:
    return bool(NOTE_RE.match(normalize_spaces(text)))


def parse_numeric(text: str) -> Optional[float]:
    t = normalize_spaces(text)
    if not t or t in {"-", "—", "–"}:
        return None

    negative = t.startswith("(") and t.endswith(")")
    t = t.replace("(", "").replace(")", "")
    t = t.replace(",", "").replace(" ", "")

    try:
        val = float(t)
        return -val if negative else val
    except Exception:
        return None


def has_date_or_period_signal(text: str) -> bool:
    t = normalize_spaces(text)
    return bool(YEAR_RE.search(t) or MONTH_RE.search(t))


def is_mostly_text(row):
    non_empty = [normalize_spaces(c) for c in row if normalize_spaces(c)]
    if not non_empty:
        return False
    numeric = sum(1 for c in non_empty if looks_numeric(c))
    return numeric <= max(1, len(non_empty) * 0.3)