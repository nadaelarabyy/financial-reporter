import re
from typing import List, Dict, Any, Tuple
from .utils import normalize_spaces, looks_numeric, has_date_or_period_signal, is_mostly_text


COMMON_SECTION_WORDS = {
    "assets", "liabilities", "equity", "income", "expenses"
}


def fill_spanning_cells(row: List[str]) -> List[str]:
    filled = []
    last = ""
    for c in row:
        c = normalize_spaces(c)
        if c:
            last = c
            filled.append(c)
        else:
            filled.append(last)
    return filled


def detect_header_rows(rows: List[List[str]], max_check: int = 4) -> Tuple[List[List[str]], List[List[str]]]:
    """
    Detect top header rows.
    Heuristic:
    - first 1-4 rows
    - mostly text
    - stop at first strongly numeric row
    """
    header_rows = []
    data_rows = []

    for idx, row in enumerate(rows[:max_check]):
        if is_mostly_text(row):
            header_rows.append(row)
        else:
            data_rows = rows[idx:]
            break

    if not data_rows:
        data_rows = rows[len(header_rows):]

    # ensure at least 1 header row
    if not header_rows and rows:
        header_rows = [rows[0]]
        data_rows = rows[1:]

    return header_rows, data_rows


def merge_header_rows(header_rows: List[List[str]]) -> List[str]:
    if not header_rows:
        return []

    normalized = [fill_spanning_cells(r) for r in header_rows]
    max_cols = max(len(r) for r in normalized)

    merged = []
    for col in range(max_cols):
        parts = []
        for row in normalized:
            if col < len(row):
                cell = normalize_spaces(row[col])
                if cell:
                    parts.append(cell)

        # dedupe while preserving order
        seen = set()
        deduped = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                deduped.append(p)

        merged.append(normalize_spaces(" ".join(deduped)))

    return merged


def clean_header_text(text: str) -> str:
    t = normalize_spaces(text)

    if re.search(r"\bnotes?\b", t, flags=re.IGNORECASE):
        return "Notes"

    # if it looks like a period/date column, strip obvious section words accidentally merged in
    if has_date_or_period_signal(t):
        tokens = t.split()
        cleaned_tokens = []
        for tok in tokens:
            if tok.lower() in COMMON_SECTION_WORDS:
                continue
            cleaned_tokens.append(tok)
        t = normalize_spaces(" ".join(cleaned_tokens))

    return t


def normalize_headers(headers: List[str]) -> List[str]:
    cleaned = [clean_header_text(h) for h in headers]

    if cleaned:
        cleaned[0] = "Line Item"

    seen = {}
    final = []
    for h in cleaned:
        h = h or "Column"
        if h not in seen:
            seen[h] = 1
            final.append(h)
        else:
            seen[h] += 1
            final.append(f"{h}_{seen[h]}")
    return final


def process_headers(rows: List[List[str]]) -> Dict[str, Any]:
    header_rows, data_rows = detect_header_rows(rows)
    merged_headers = merge_header_rows(header_rows)
    headers = normalize_headers(merged_headers)

    # pad data rows to header width
    width = len(headers)
    padded_data_rows = []
    for r in data_rows:
        rr = list(r)
        if len(rr) < width:
            rr += [""] * (width - len(rr))
        elif len(rr) > width:
            # allow extra fragmented columns (keep as-is for curator to fix)
            pass
        padded_data_rows.append(rr)

    return {
        "header_rows": header_rows,
        "headers": headers,
        "rows": padded_data_rows
    }