import re
from typing import List, Dict, Any, Optional
from .utils import normalize_spaces, looks_numeric, looks_note_ref, parse_numeric


ROLE_KEYWORDS = {
    "chairman", "director", "ceo", "cfo", "board", "officer",
    "auditor", "partner", "member", "manager", "president",
    "secretary", "treasurer"
}

COMMON_SECTION_LABELS = {
    "assets", "liabilities", "equity", "financial investments",
    "earnings per share", "operating activities", "investing activities",
    "financing activities", "cash flows from operating activities",
    "cash flows from investing activities", "cash flows from financing activities"
}


def detect_note_col_idx(headers: List[str]) -> Optional[int]:
    for i, h in enumerate(headers):
        h_norm = normalize_spaces(h).lower()
        if h_norm in {"notes", "note"}:
            return i
    return None


def detect_first_numeric_col(row: List[str]) -> int:
    for i, cell in enumerate(row):
        if looks_numeric(normalize_spaces(cell)):
            return i
    return len(row)


def score_table_candidate(table: Dict[str, Any]) -> float:
    rows = table.get("rows", [])
    headers = table.get("headers", [])
    source = (table.get("source") or "").lower()

    score = 0.0
    numeric_rows = 0
    fragmented_rows = 0

    for row in rows:
        numeric_count = sum(1 for c in row if looks_numeric(normalize_spaces(c)))
        if numeric_count > 0:
            numeric_rows += 1

        tiny_text = sum(
            1 for c in row
            if 0 < len(normalize_spaces(c)) <= 3 and not looks_numeric(normalize_spaces(c))
        )
        if tiny_text >= 3:
            fragmented_rows += 1

    score += min(len(rows), 200) * 0.25
    score += numeric_rows * 1.0

    col_count = len(headers)
    if 3 <= col_count <= 8:
        score += 8
    elif 9 <= col_count <= 14:
        score += 3
    elif col_count > 14:
        score -= (col_count - 14) * 1.2

    if "camelot" in source:
        score += 4
    elif "pdfplumber" in source:
        score += 1

    score -= fragmented_rows * 0.5

    return score


def dedupe_best_tables(raw_tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups = {}

    for t in raw_tables:
        key = (
            t.get("pdf_page"),
            normalize_spaces(t.get("page_title", "")),
            t.get("statement_type", "")
        )
        groups.setdefault(key, []).append(t)

    chosen = []
    for _, candidates in groups.items():
        chosen.append(max(candidates, key=score_table_candidate))

    chosen.sort(key=lambda x: (x.get("source_pages", [x.get("pdf_page", 9999)])[0], x.get("pdf_page", 9999)))
    return chosen


def fix_broken_words(text: str) -> str:
    t = normalize_spaces(text)

    # conservative merge of common suffix fragments
    t = re.sub(
        r"\b([A-Za-z]{3,})\s+(s|es|ed|al|er|et|nt|nts|ly|ies)\b",
        lambda m: m.group(1) + m.group(2),
        t
    )

    # merge isolated single-char + word (e.g. "n et" -> "net")
    t = re.sub(r"\b([A-Za-z])\s+([A-Za-z]{2,})\b", lambda m: m.group(1) + m.group(2), t)

    return normalize_spaces(t)


def rebuild_label(row: List[str], headers: List[str]) -> str:
    """
    Generic label reconstruction:
    - combine all text cells before earliest of [note col, first numeric col]
    """
    note_idx = detect_note_col_idx(headers)
    first_num_idx = detect_first_numeric_col(row)

    stop_idx = first_num_idx
    if note_idx is not None and note_idx < stop_idx:
        stop_idx = note_idx

    parts = []
    for i in range(stop_idx):
        cell = normalize_spaces(row[i])
        if not cell:
            continue
        if looks_numeric(cell):
            continue
        parts.append(cell)

    # fallback
    if not parts:
        for i in range(first_num_idx):
            cell = normalize_spaces(row[i])
            if cell and not looks_numeric(cell):
                parts.append(cell)

    label = normalize_spaces(" ".join(parts))
    return fix_broken_words(label)


def classify_row(row: List[str], headers: List[str], label: str) -> str:
    non_empty = [normalize_spaces(c) for c in row if normalize_spaces(c)]
    numeric_cells = [c for c in non_empty if looks_numeric(c)]
    text_cells = [c for c in non_empty if not looks_numeric(c)]
    label_norm = label.lower().strip()

    if not non_empty:
        return "noise_row"

    # all zeros / placeholders
    if re.fullmatch(r"(0\s*){1,10}", " ".join(non_empty)):
        return "noise_row"

    # long prose note/footer
    if len(numeric_cells) == 0 and len(label) > 45 and (label.endswith(".") or len(text_cells) >= 2):
        return "note_row"

    # signature-like
    if len(numeric_cells) == 0:
        role_hits = sum(1 for w in ROLE_KEYWORDS if w in label_norm)
        if role_hits > 0:
            return "signature_row"

    # section row
    if len(numeric_cells) == 0 and 1 <= len(label.split()) <= 8:
        if label_norm in COMMON_SECTION_LABELS:
            return "section_row"

    # total row
    if label_norm.startswith("total ") or label_norm == "total":
        return "total_row"

    # subtotal / metrics
    subtotal_prefixes = ["net ", "profit ", "profit before", "earnings per share", "basic", "diluted"]
    if any(label_norm.startswith(p) for p in subtotal_prefixes) and len(numeric_cells) > 0:
        return "subtotal_row"

    if len(numeric_cells) > 0:
        return "data_row"

    return "noise_row"


def should_keep_row(row_type: str) -> bool:
    return row_type in {"data_row", "section_row", "subtotal_row", "total_row"}


def extract_note_and_values(row: List[str], headers: List[str], label: str) -> Dict[str, Any]:
    note_idx = detect_note_col_idx(headers)

    note = None
    if note_idx is not None and note_idx < len(row):
        note_candidate = normalize_spaces(row[note_idx])
        if looks_note_ref(note_candidate):
            note = note_candidate

    values = {}
    numeric_values = {}

    for i, cell in enumerate(row):
        if i == 0:
            continue
        if note_idx is not None and i == note_idx:
            continue

        col = headers[i] if i < len(headers) else f"Column_{i+1}"
        val = normalize_spaces(cell)

        if not val:
            continue

        # skip label duplication
        if val == label:
            continue

        values[col] = val
        numeric_values[col] = parse_numeric(val)

    return {
        "label": label,
        "note": note,
        "values": values,
        "numeric_values": numeric_values
    }


def build_final_columns(headers: List[str], rows: List[Dict[str, Any]]) -> List[str]:
    used = set()
    has_note = any(r.get("note") for r in rows)

    for r in rows:
        for k in r.get("values", {}).keys():
            used.add(k)

    final = ["Line Item"]
    if has_note and "Notes" in headers:
        final.append("Notes")

    for h in headers[1:]:
        if h in {"Line Item", "Notes"}:
            continue
        if h in used:
            final.append(h)

    return final


def curate_table(table: Dict[str, Any]) -> Dict[str, Any]:
    headers = table.get("headers", [])
    raw_rows = table.get("rows", [])

    curated_rows = []

    for row in raw_rows:
        if not isinstance(row, list):
            continue

        row = [normalize_spaces(c) for c in row]
        if not any(row):
            continue

        label = rebuild_label(row, headers)
        row_type = classify_row(row, headers, label)

        if not should_keep_row(row_type):
            continue

        row_obj = extract_note_and_values(row, headers, label)
        row_obj["row_type"] = row_type

        # ensure data/total/subtotal rows have numeric values
        if row_type in {"data_row", "subtotal_row", "total_row"}:
            has_numeric = any(v is not None for v in row_obj["numeric_values"].values())
            if not has_numeric:
                continue

        curated_rows.append(row_obj)

    final_columns = build_final_columns(headers, curated_rows)

    # trim to final columns only
    for r in curated_rows:
        r["values"] = {k: v for k, v in r["values"].items() if k in final_columns and k != "Line Item"}
        r["numeric_values"] = {k: v for k, v in r["numeric_values"].items() if k in final_columns and k != "Line Item"}

    return {
        "section_title": normalize_spaces(table.get("page_title", "")),
        "statement_type": table.get("statement_type"),
        "source_pages": table.get("source_pages", [table.get("pdf_page")]),
        "columns": final_columns,
        "rows": curated_rows
    }


def curate_output(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_tables = raw_payload.get("tables", [])
    toc = raw_payload.get("toc", [])

    best_tables = dedupe_best_tables(raw_tables)
    curated_tables = [curate_table(t) for t in best_tables]
    curated_tables = [t for t in curated_tables if t["rows"]]

    return {
        "toc": toc or [],
        "tables": curated_tables
    }