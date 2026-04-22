import re
from typing import Optional


NOTE_REF_RE = re.compile(r"\(Note\s*\d+\)", re.IGNORECASE)
PARENS_NEG_RE = re.compile(r"^\(([\d,.\s]+)\)$")


def strip_note_references(text: str) -> str:
    return NOTE_REF_RE.sub("", text).strip()


def parse_numeric(text: str) -> Optional[float]:
    """
    Very basic numeric parser:
    - 1,234
    - (1,234)
    - 12.5
    - 5%
    """
    if not text:
        return None

    text = strip_note_references(text).strip()
    text = text.replace("%", "").replace(" ", "")

    m = PARENS_NEG_RE.match(text)
    if m:
        text = "-" + m.group(1)

    text = text.replace(",", "")

    try:
        return float(text)
    except ValueError:
        return None