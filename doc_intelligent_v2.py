import re
from collections import Counter
from typing import List, Dict, Any, Optional

import pdfplumber


# =========================================================
# Helpers
# =========================================================

def is_numeric_like(text: str) -> bool:
    if not text:
        return False
    text = text.strip().replace(",", "").replace("%", "").replace("(", "-").replace(")", "")
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", text))


def clean_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def row_numeric_ratio(row: List[str]) -> float:
    non_empty = [x for x in row if x.strip()]
    if not non_empty:
        return 0.0
    numeric_count = sum(1 for x in non_empty if is_numeric_like(x))
    return numeric_count / len(non_empty)


def table_score(table: Dict[str, Any]) -> float:
    """
    Very simple POC score:
    - reward non-empty rows
    - reward headers
    - reward mixed text+numeric pattern
    """
    headers = table.get("headers", [])
    rows = table.get("rows", [])

    if not rows:
        return 0.0

    score = 0.0

    # 1) rows count
    score += min(len(rows), 20) * 2

    # 2) header quality
    non_empty_headers = sum(1 for h in headers if h.strip())
    score += non_empty_headers * 3

    # 3) reward if first col is text-heavy and later cols numeric-heavy
    if rows and len(rows[0]) >= 2:
        first_col = [r[0] for r in rows if len(r) > 0]
        other_cols = []
        for r in rows:
            other_cols.extend(r[1:])

        first_col_text_ratio = 1 - (sum(1 for x in first_col if is_numeric_like(x)) / max(len(first_col), 1))
        other_cols_numeric_ratio = sum(1 for x in other_cols if is_numeric_like(x)) / max(len(other_cols), 1)

        score += first_col_text_ratio * 10
        score += other_cols_numeric_ratio * 10

    return round(score, 2)


# =========================================================
# 1) Strategy A: Use Azure DI detected table cells
# =========================================================

def extract_from_di_table(di_table) -> Dict[str, Any]:
    row_count = getattr(di_table, "row_count", 0) or 0
    col_count = getattr(di_table, "column_count", 0) or 0
    cells = getattr(di_table, "cells", []) or []

    matrix = [["" for _ in range(col_count)] for _ in range(row_count)]
    header_rows = set()

    for cell in cells:
        r = getattr(cell, "row_index", None)
        c = getattr(cell, "column_index", None)
        if r is None or c is None:
            continue

        content = clean_text(getattr(cell, "content", ""))
        kind = str(getattr(cell, "kind", "") or "").lower()
        row_span = getattr(cell, "row_span", 1) or 1
        col_span = getattr(cell, "column_span", 1) or 1

        if kind == "columnheader":
            header_rows.add(r)

        # top-left
        if 0 <= r < row_count and 0 <= c < col_count:
            matrix[r][c] = content

        # lightly fill spans
        for rr in range(r, min(r + row_span, row_count)):
            for cc in range(c, min(c + col_span, col_count)):
                if rr == r and cc == c:
                    continue
                if not matrix[rr][cc]:
                    matrix[rr][cc] = content

    # if no explicit header, assume first row
    if not header_rows and row_count > 0:
        header_rows = {0}

    header_rows = sorted(header_rows)

    # merge header rows column-wise
    headers = []
    for c in range(col_count):
        parts = []
        for hr in header_rows:
            val = clean_text(matrix[hr][c])
            if val and val not in parts:
                parts.append(val)
        headers.append(" | ".join(parts) if parts else f"col_{c}")

    # data rows
    rows = []
    for r in range(row_count):
        if r in header_rows:
            continue
        row = [clean_text(matrix[r][c]) for c in range(col_count)]
        if any(row):
            rows.append(row)

    return {"headers": headers, "rows": rows, "method": "azure_di"}


# =========================================================
# 2) Repair headers / spans (simple POC)
# =========================================================

def repair_table_simple(table: Dict[str, Any]) -> Dict[str, Any]:
    headers = table["headers"][:]
    rows = [r[:] for r in table["rows"]]

    # Fix empty headers
    for i, h in enumerate(headers):
        if not h.strip():
            headers[i] = f"col_{i}"

    # Merge wrapped label rows:
    # if row has only first column text and next row has numeric values
    repaired_rows = []
    i = 0
    while i < len(rows):
        current = rows[i]
        non_empty_count = sum(1 for x in current if x.strip())

        if (
            i + 1 < len(rows)
            and non_empty_count == 1
            and current[0].strip()
            and row_numeric_ratio(rows[i + 1]) > 0.4
        ):
            merged = rows[i + 1][:]
            merged[0] = clean_text(current[0] + " " + merged[0])
            repaired_rows.append(merged)
            i += 2
        else:
            repaired_rows.append(current)
            i += 1

    return {"headers": headers, "rows": repaired_rows, "method": table["method"] + "_repaired"}


# =========================================================
# 3) If poor quality: header-anchor reconstruction
#    Use Azure DI page words/lines with polygons if available
# =========================================================

def get_line_bbox(line) -> Optional[Dict[str, float]]:
    """
    Azure DI line.polygon usually contains 8 numbers [x1,y1,x2,y2,x3,y3,x4,y4]
    """
    poly = getattr(line, "polygon", None)
    if not poly or len(poly) < 8:
        return None

    xs = poly[0::2]
    ys = poly[1::2]

    return {
        "x1": min(xs),
        "y1": min(ys),
        "x2": max(xs),
        "y2": max(ys),
    }


def build_items_from_di_page(page) -> List[Dict[str, Any]]:
    items = []
    lines = getattr(page, "lines", []) or []
    for line in lines:
        bbox = get_line_bbox(line)
        if not bbox:
            continue
        items.append({
            "text": clean_text(getattr(line, "content", "")),
            "x1": bbox["x1"],
            "y1": bbox["y1"],
            "x2": bbox["x2"],
            "y2": bbox["y2"],
            "cx": (bbox["x1"] + bbox["x2"]) / 2,
            "cy": (bbox["y1"] + bbox["y2"]) / 2,
        })
    return items


def cluster_rows_by_y(items: List[Dict[str, Any]], tolerance: float = 0.015) -> List[List[Dict[str, Any]]]:
    """
    Simple Y grouping for DI normalized coords (0..1-ish depending on API output)
    """
    items = sorted(items, key=lambda x: x["cy"])
    rows = []

    for item in items:
        placed = False
        for row in rows:
            avg_y = sum(x["cy"] for x in row) / len(row)
            if abs(item["cy"] - avg_y) <= tolerance:
                row.append(item)
                placed = True
                break
        if not placed:
            rows.append([item])

    # sort each row by x
    for row in rows:
        row.sort(key=lambda x: x["x1"])

    return rows


def detect_header_row(rows: List[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """
    Pick first row that is mostly text and has 2+ items
    """
    for row in rows[:3]:
        texts = [x["text"] for x in row if x["text"]]
        if len(texts) < 2:
            continue
        numeric_ratio = sum(1 for t in texts if is_numeric_like(t)) / len(texts)
        if numeric_ratio < 0.4:
            return row
    return None


def reconstruct_using_header_anchors(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rows = cluster_rows_by_y(items)
    header_row = detect_header_row(rows)
    if not header_row:
        return None

    # use header item centers as anchors
    anchors = [x["cx"] for x in header_row]
    headers = [x["text"] for x in header_row]

    data_rows = []
    header_used = False

    for row in rows:
        # skip first matched header row only
        if not header_used and row == header_row:
            header_used = True
            continue

        output_row = [""] * len(anchors)

        for item in row:
            # assign item to nearest anchor
            nearest_idx = min(range(len(anchors)), key=lambda i: abs(item["cx"] - anchors[i]))
            if output_row[nearest_idx]:
                output_row[nearest_idx] += " " + item["text"]
            else:
                output_row[nearest_idx] = item["text"]

        if any(output_row):
            data_rows.append([clean_text(x) for x in output_row])

    return {"headers": headers, "rows": data_rows, "method": "header_anchor"}


# =========================================================
# 4) If header weak: x-axis projection / whitespace valleys
# =========================================================

def infer_columns_by_x_projection(items: List[Dict[str, Any]], bins: int = 40) -> List[float]:
    """
    Very simple POC:
    - build occupancy across x-axis
    - find bins with activity
    - group contiguous active bins into column bands
    - return center x for each band
    """
    if not items:
        return []

    min_x = min(i["x1"] for i in items)
    max_x = max(i["x2"] for i in items)
    if max_x <= min_x:
        return []

    bin_width = (max_x - min_x) / bins
    hist = [0] * bins

    for item in items:
        start_bin = max(0, min(bins - 1, int((item["x1"] - min_x) / bin_width)))
        end_bin = max(0, min(bins - 1, int((item["x2"] - min_x) / bin_width)))
        for b in range(start_bin, end_bin + 1):
            hist[b] += 1

    # active bins
    active_groups = []
    current = []
    for idx, val in enumerate(hist):
        if val > 0:
            current.append(idx)
        else:
            if current:
                active_groups.append(current)
                current = []
    if current:
        active_groups.append(current)

    anchors = []
    for group in active_groups:
        start = min(group)
        end = max(group)
        center_bin = (start + end) / 2
        center_x = min_x + (center_bin + 0.5) * bin_width
        anchors.append(center_x)

    return anchors


def reconstruct_using_projection(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rows = cluster_rows_by_y(items)
    anchors = infer_columns_by_x_projection(items)

    if len(anchors) < 2:
        return None

    matrix = []
    for row in rows:
        output_row = [""] * len(anchors)
        for item in row:
            nearest_idx = min(range(len(anchors)), key=lambda i: abs(item["cx"] - anchors[i]))
            if output_row[nearest_idx]:
                output_row[nearest_idx] += " " + item["text"]
            else:
                output_row[nearest_idx] = item["text"]
        if any(output_row):
            matrix.append([clean_text(x) for x in output_row])

    if not matrix:
        return None

    # assume first row is header if mostly text
    first_row = matrix[0]
    numeric_ratio = row_numeric_ratio(first_row)
    if numeric_ratio < 0.4:
        headers = [x if x else f"col_{i}" for i, x in enumerate(first_row)]
        rows_out = matrix[1:]
    else:
        headers = [f"col_{i}" for i in range(len(anchors))]
        rows_out = matrix

    return {"headers": headers, "rows": rows_out, "method": "x_projection"}


# =========================================================
# 5) If native PDF: pdfplumber fallback
# =========================================================

def extract_with_pdfplumber(pdf_path: str, page_number: int = 0) -> Optional[Dict[str, Any]]:
    """
    page_number is 0-based here
    """
    with pdfplumber.open(pdf_path) as pdf:
        if page_number >= len(pdf.pages):
            return None

        page = pdf.pages[page_number]
        table = page.extract_table()

        if not table or len(table) < 2:
            return None

        headers = [clean_text(x or "") for x in table[0]]
        rows = [[clean_text(x or "") for x in row] for row in table[1:]]

        rows = [r for r in rows if any(r)]
        headers = [h if h else f"col_{i}" for i, h in enumerate(headers)]

        return {"headers": headers, "rows": rows, "method": "pdfplumber"}


# =========================================================
# 6) Compare candidates with confidence scoring
# =========================================================

def choose_best_table(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None

    scored = []
    for c in candidates:
        score = table_score(c)
        c["score"] = score
        scored.append(c)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[0]


# =========================================================
# 7) Main POC pipeline
# =========================================================

def extract_best_table_from_page(di_result, page_index: int = 0, pdf_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    candidates = []

    # Strategy 1: Azure DI tables on this page
    di_tables = getattr(di_result, "tables", []) or []
    for t in di_tables:
        # If table has bounding_regions, filter by page
        table_pages = []
        for br in getattr(t, "bounding_regions", []) or []:
            pnum = getattr(br, "page_number", None)
            if pnum is not None:
                table_pages.append(pnum - 1)  # Azure page_number is 1-based

        if table_pages and page_index not in table_pages:
            continue

        di_table = extract_from_di_table(t)
        di_table = repair_table_simple(di_table)
        candidates.append(di_table)

    # Build page items from Azure DI lines
    pages = getattr(di_result, "pages", []) or []
    if page_index < len(pages):
        items = build_items_from_di_page(pages[page_index])

        # Strategy 2: header anchors
        header_anchor_candidate = reconstruct_using_header_anchors(items)
        if header_anchor_candidate:
            candidates.append(header_anchor_candidate)

        # Strategy 3: x projection
        projection_candidate = reconstruct_using_projection(items)
        if projection_candidate:
            candidates.append(projection_candidate)

    # Strategy 4: pdfplumber if native PDF path provided
    if pdf_path:
        plumber_candidate = extract_with_pdfplumber(pdf_path, page_number=page_index)
        if plumber_candidate:
            candidates.append(plumber_candidate)

    best = choose_best_table(candidates)
    return best


# =========================================================
# 8) Example usage
# =========================================================

if __name__ == "__main__":
    # Example:
    # You already have:
    # result = poller.result()
    #
    # Then:
    #
    # best_table = extract_best_table_from_page(result, page_index=0, pdf_path="sample.pdf")
    # print(best_table)
    #
    # This file intentionally doesn't run standalone because it expects an Azure DI result object.
    pass