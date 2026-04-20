from typing import List, Dict, Any
from .utils import normalize_spaces


def headers_similar(h1: List[str], h2: List[str], threshold: float = 0.6) -> bool:
    if not h1 or not h2:
        return False

    # compare common length
    n = min(len(h1), len(h2))
    if n == 0:
        return False

    matches = 0
    for i in range(n):
        if normalize_spaces(h1[i]).lower() == normalize_spaces(h2[i]).lower():
            matches += 1

    return (matches / n) >= threshold


def first_row_equals_header(table: Dict[str, Any]) -> bool:
    rows = table.get("rows", [])
    headers = table.get("headers", [])
    if not rows:
        return False

    first = rows[0]
    n = min(len(first), len(headers))
    if n == 0:
        return False

    matches = 0
    for i in range(n):
        if normalize_spaces(first[i]).lower() == normalize_spaces(headers[i]).lower():
            matches += 1

    return (matches / n) >= 0.7


def remove_duplicate_header_row(table: Dict[str, Any]) -> Dict[str, Any]:
    if first_row_equals_header(table):
        table["rows"] = table["rows"][1:]
    return table


def can_merge(prev_table: Dict[str, Any], curr_table: Dict[str, Any]) -> bool:
    prev_pages = prev_table.get("source_pages", [prev_table.get("pdf_page")])
    curr_pages = curr_table.get("source_pages", [curr_table.get("pdf_page")])

    prev_last_page = prev_pages[-1]
    curr_first_page = curr_pages[0]

    if curr_first_page != prev_last_page + 1:
        return False

    if prev_table.get("statement_type") != curr_table.get("statement_type"):
        return False

    if not headers_similar(prev_table.get("headers", []), curr_table.get("headers", [])):
        return False

    return True


def merge_continued_tables(tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not tables:
        return []

    tables = [remove_duplicate_header_row(t) for t in tables]
    tables.sort(key=lambda x: x.get("pdf_page", 9999))

    merged = [tables[0]]

    for curr in tables[1:]:
        prev = merged[-1]

        if can_merge(prev, curr):
            prev["rows"].extend(curr["rows"])
            prev["source_pages"] = sorted(set(prev.get("source_pages", [prev["pdf_page"]]) + curr.get("source_pages", [curr["pdf_page"]])))
        else:
            merged.append(curr)

    return merged