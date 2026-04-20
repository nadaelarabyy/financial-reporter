import re
from typing import Optional
import pdfplumber
from .utils import normalize_spaces


STATEMENT_PATTERNS = {
    "balance_sheet": [
        r"statement of financial position",
        r"balance sheet",
        r"financial position",
    ],
    "income_statement": [
        r"income statement",
        r"statement of income",
        r"statement of profit or loss",
        r"profit or loss",
        r"statement of operations",
    ],
    "cash_flow": [
        r"cash flow",
        r"statement of cash flows",
    ],
    "equity_changes": [
        r"statement of changes in equity",
        r"changes in equity",
    ],
}


def page_text(page) -> str:
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def detect_statement_type(text: str) -> Optional[str]:
    t = normalize_spaces(text).lower()
    for stype, patterns in STATEMENT_PATTERNS.items():
        for p in patterns:
            if re.search(p, t):
                return stype
    return None


def extract_page_title(pdf_path: str, page_number: int) -> str:
    """
    page_number is 1-based.
    Uses top portion of page text heuristically.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number - 1]
        text = page_text(page)
        lines = [normalize_spaces(l) for l in text.splitlines() if normalize_spaces(l)]

        # take first 3-5 lines, join until likely title length
        title_lines = []
        for line in lines[:6]:
            if len(line) < 3:
                continue
            title_lines.append(line)
            joined = " ".join(title_lines)
            if len(joined) >= 40:
                break

        return normalize_spaces(" ".join(title_lines))


def detect_statement_type_for_page(pdf_path: str, page_number: int) -> Optional[str]:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number - 1]
        text = page_text(page)
        return detect_statement_type(text)