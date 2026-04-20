import re
import os
import statistics
from typing import List, Tuple, Optional
import numpy as np
import pandas as pd
import pdfplumber

# ─────────────────────────────────────────────
# REGEX PATTERNS
# ─────────────────────────────────────────────
DIGIT_RE = re.compile(r'\d')
DASH_RE  = re.compile(r'^[-–—]$')


# ─────────────────────────────────────────────
# STEP 1 — EXTRACT WORDS WITH BOUNDING BOXES
# ─────────────────────────────────────────────
def extract_words(page) -> List[dict]:
    """
    Extract all words from a pdfplumber page with their bounding boxes.
    Each word dict has: text, x0, x1, top, bottom
    """
    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=1,
        keep_blank_chars=False
    ) or []

    # Attach computed centers
    for w in words:
        w["_yc"] = (w["top"]  + w["bottom"]) / 2.0
        w["_xc"] = (w["x0"]   + w["x1"])     / 2.0

    return words


# ─────────────────────────────────────────────
# STEP 2 — GROUP WORDS INTO LINES BY Y POSITION
# ─────────────────────────────────────────────
def words_to_lines(words: List[dict], y_tol: Optional[float] = None) -> List[List[dict]]:
    """
    Group words into lines based on vertical (Y) proximity.
    Words on the same line share roughly the same Y center.
    """
    if not words:
        return []

    # Auto-estimate Y tolerance from median word height
    heights = [(w["bottom"] - w["top"]) for w in words]
    med_h   = statistics.median(heights) if heights else 5
    y_tol   = y_tol or max(2, med_h * 0.6)

    words_sorted = sorted(words, key=lambda w: (w["_yc"], w["x0"]))

    lines   = []
    current = [words_sorted[0]]

    for w in words_sorted[1:]:
        if abs(w["_yc"] - current[-1]["_yc"]) <= y_tol:
            current.append(w)
        else:
            lines.append(sorted(current, key=lambda ww: ww["x0"]))
            current = [w]

    if current:
        lines.append(sorted(current, key=lambda ww: ww["x0"]))

    return lines


# ─────────────────────────────────────────────
# STEP 3 — DETECT THE LINE ITEM BLOCK
# ─────────────────────────────────────────────
def is_item_like(line: List[dict]) -> bool:
    """
    Heuristic: a line looks like a table row if it has several
    "numeric" tokens (any token containing a digit, or a standalone
    dash used as a zero placeholder, or a stray parenthesis from a
    negative number like "(5,366,429)").
    """
    tokens = [w["text"] for w in line]
    if len(tokens) < 2:
        return False
    numeric_like = sum(
        1 for t in tokens
        if DIGIT_RE.search(t) or DASH_RE.match(t.strip()) or t.strip() in ("(", ")")
    )
    return numeric_like >= 3


# ─────────────────────────────────────────────
# STEP 4 — DISCOVER COLUMNS FROM THE FULLEST ROW
# ─────────────────────────────────────────────
def columns_from_fullest_row(
    lines_block: List[List[dict]],
    merge_gap: float = 20.0,
) -> Tuple[float, List[float]]:
    """
    Detect column layout from the row with the most tokens.

    Many PDFs (esp. financial statements) split numbers like "30,195,010"
    into two tokens ("3" + "0,195,010"). We sort the fullest row's tokens
    by X-center and group adjacent ones whose centers are within
    `merge_gap` pixels — each group becomes one column.

    The first group is treated as the label column; the rest are numeric.

    Returns:
        label_boundary:   x-position below which any token is a label
        numeric_centers:  list of X centers, one per numeric column
    """
    if not lines_block:
        return 0.0, []

    fullest = max(lines_block, key=len)
    if not fullest:
        return 0.0, []

    sorted_toks = sorted(fullest, key=lambda w: w["_xc"])
    groups: List[List[dict]] = [[sorted_toks[0]]]
    for w in sorted_toks[1:]:
        if w["_xc"] - groups[-1][-1]["_xc"] < merge_gap:
            groups[-1].append(w)
        else:
            groups.append([w])

    if len(groups) < 2:
        # No numeric columns detected
        return 0.0, []

    numeric_groups = groups[1:]
    numeric_centers = [
        (min(w["_xc"] for w in g) + max(w["_xc"] for w in g)) / 2.0
        for g in numeric_groups
    ]

    # Label boundary = just before the leftmost edge of the first numeric column
    first_num_left = min(w["x0"] for w in numeric_groups[0])
    label_boundary = first_num_left - 1.0

    return label_boundary, numeric_centers


# ─────────────────────────────────────────────
# STEP 5 — ASSIGN WORDS TO COLUMN BUCKETS
# ─────────────────────────────────────────────
def assign_to_layout(
    line: List[dict],
    label_boundary: float,
    numeric_centers: List[float],
) -> List[str]:
    """
    Assign each word in a line to its column.

    - Tokens whose x0 < `label_boundary` belong to the label column (col 0).
    - All other tokens are assigned to the nearest numeric column center.

    Returns a list of cell strings: [label, num_col_1, num_col_2, ...]
    """
    buckets: List[List[dict]] = [[] for _ in range(1 + len(numeric_centers))]

    for w in line:
        if w["x0"] < label_boundary:
            buckets[0].append(w)
        else:
            dists = [abs(w["_xc"] - c) for c in numeric_centers]
            idx = int(np.argmin(dists))
            buckets[1 + idx].append(w)

    # Preserve left-to-right order within each bucket
    return [
        " ".join(w["text"] for w in sorted(b, key=lambda w: w["x0"]))
        for b in buckets
    ]


# ─────────────────────────────────────────────
# STEP 6 — EXTRACT COLUMN HEADERS
# ─────────────────────────────────────────────
def extract_column_headers(
    words: List[dict],
    lines: List[List[dict]],
    first_item_idx: int,
    label_boundary: float,
    numeric_centers: List[float],
) -> List[str]:
    """
    Recover column header text from the words lying between the page
    title and the first data row.

    For each header word we look at its X-center and drop it into the
    column bucket whose detected center is nearest. Within each bucket
    we sort by (top, x0) — so words from different visual header rows
    stitch back together in natural reading order.
    """
    if first_item_idx <= 0 or not numeric_centers:
        return []

    # Header region = strictly above the first data row.
    first_item_top = min(w["top"] for w in lines[first_item_idx])

    # Skip a text-only title line (e.g. "Condensed Consolidated ...")
    # by pushing the header top below its last character.
    title_bottom = 0.0
    if lines and not any(DIGIT_RE.search(w["text"]) for w in lines[0]):
        title_bottom = max(w["bottom"] for w in lines[0])

    header_words = [
        w for w in words
        if title_bottom <= w["top"] and w["bottom"] <= first_item_top
    ]

    n = len(numeric_centers)
    # Boundaries between adjacent numeric columns (midpoints).
    inner_bounds = [
        (numeric_centers[i] + numeric_centers[i + 1]) / 2.0
        for i in range(n - 1)
    ]

    buckets: List[List[dict]] = [[] for _ in range(n + 1)]
    for w in header_words:
        xc = w["_xc"]
        if xc < label_boundary:
            buckets[0].append(w)
            continue
        placed = False
        for i, b in enumerate(inner_bounds):
            if xc < b:
                buckets[1 + i].append(w)
                placed = True
                break
        if not placed:
            buckets[n].append(w)  # rightmost column

    def _finalize(bucket: List[dict]) -> str:
        # Round `top` so words from the same visual row sort together
        # even if their baselines differ by a fraction of a pixel.
        bucket.sort(key=lambda w: (round(w["top"]), w["x0"]))
        text = " ".join(w["text"] for w in bucket)
        return re.sub(r"\s+", " ", text).strip()

    return [_finalize(b) for b in buckets]


# ─────────────────────────────────────────────
# MAIN EXTRACTION — PER PAGE
# ─────────────────────────────────────────────
def extract_line_items_from_page(
    page,
    y_tol: Optional[float] = None,
    merge_gap: float = 20.0,
) -> pd.DataFrame:
    """
    Extract a data table from one PDF page using positional layout.

    Pipeline:
      1. Extract words with bounding boxes.
      2. Group words into lines by Y.
      3. Gather item-like lines (anything with numbers).
      4. Detect the column layout from the fullest item-like row
         (label + N numeric columns).
      5. Walk every line between first and last item-like line and:
           - assign item-like lines to columns,
           - merge "label-only" continuation lines into the previous row,
           - skip everything else (headers, blank lines).
      6. Strip internal spaces from numeric cells to rejoin split numbers
         (e.g. "3" + "0,195,010" → "30,195,010").
      7. Return a DataFrame with generic column names:
           description, col_1, col_2, ...
    """
    # 1 & 2
    words = extract_words(page)
    lines = words_to_lines(words, y_tol=y_tol)
    if not lines:
        return pd.DataFrame()

    # 3 — item-like lines anchor the table block
    item_flags = [is_item_like(ln) for ln in lines]
    if not any(item_flags):
        return pd.DataFrame()

    first_item = item_flags.index(True)
    last_item  = len(item_flags) - 1 - item_flags[::-1].index(True)
    item_lines = [ln for ln, flag in zip(lines, item_flags) if flag]

    # 4 — derive column layout from the fullest data row
    label_boundary, numeric_centers = columns_from_fullest_row(
        item_lines, merge_gap=merge_gap
    )
    if not numeric_centers:
        return pd.DataFrame()

    n_cols = 1 + len(numeric_centers)

    # 5 — walk the block and emit rows
    rows: List[List[str]] = []
    for i in range(first_item, last_item + 1):
        ln = lines[i]
        cells = assign_to_layout(ln, label_boundary, numeric_centers)

        if item_flags[i]:
            rows.append(cells)
            continue

        # Not item-like: is it a wrapped label continuation? (only col 0 has text)
        non_empty = [c for c in cells if c.strip()]
        if rows and len(non_empty) == 1 and cells[0].strip():
            rows[-1][0] = (rows[-1][0] + " " + cells[0]).strip()
        # else: skip (section header, blank, etc.)

    if not rows:
        return pd.DataFrame()

    # 7 — recover column headers from the page layout; fall back to generic
    headers = extract_column_headers(
        words, lines, first_item, label_boundary, numeric_centers
    )
    if len(headers) != n_cols or not any(h for h in headers):
        headers = ["description"] + [f"col_{i}" for i in range(1, n_cols)]
    else:
        # Ensure uniqueness + fill empties
        seen: dict = {}
        for i, h in enumerate(headers):
            h = h or (f"col_{i}" if i else "description")
            if h in seen:
                seen[h] += 1
                headers[i] = f"{h}_{seen[h]}"
            else:
                seen[h] = 1
                headers[i] = h

    df = pd.DataFrame(rows, columns=headers)

    # 6 — rejoin split numbers in numeric columns
    for c in df.columns[1:]:
        df[c] = df[c].str.replace(r"\s+", "", regex=True)

    # Normalize: blank cells → NaN, drop fully empty rows
    df = (
        df.replace(r"^\s*$", np.nan, regex=True)
          .dropna(how="all", axis=0)
          .reset_index(drop=True)
    )

    return df


# ─────────────────────────────────────────────
# MULTI-PAGE EXTRACTION
# ─────────────────────────────────────────────
def extract_pdf_items(
    pdf_path: str,
    page_num: int,
    y_tol: Optional[float] = None,
    merge_gap: float = 20.0,
) -> pd.DataFrame:
    """
    Run the extraction pipeline on a single page of a PDF (1-indexed).

    Args:
        pdf_path:   Path to the PDF file
        page_num:   1-indexed page number to extract
        y_tol:      Y tolerance for line grouping (None = auto)
        merge_gap:  Max x-center distance (in pixels) between tokens that
                    belong to the same column — e.g. "3" and "0,195,010"
                    being two halves of "30,195,010". Raise if columns bleed
                    together; lower if adjacent columns get merged.
    """
    # Helpful existence check: if the given path doesn't exist, try
    # looking for the same basename inside the `input/` directory before
    # failing — this covers the common case of running the script from
    # the project root while using a bare filename.
    if not os.path.exists(pdf_path):
        alt = os.path.join("input", os.path.basename(pdf_path))
        if os.path.exists(alt):
            print(f"Note: '{pdf_path}' not found — using '{alt}' instead.")
            pdf_path = alt
        else:
            searched = [pdf_path, alt]
            raise FileNotFoundError(
                f"No such file or directory: {pdf_path!r}.\nSearched: {', '.join(repr(s) for s in searched)}\n"
                "Tip: place the PDF in the 'input/' folder or provide an absolute path."
            )

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        if page_num < 1 or page_num > total:
            raise ValueError(f"page_num {page_num} out of range (PDF has {total} pages)")

        print(f"Processing page {page_num}/{total}...", end=" ")
        df = extract_line_items_from_page(
            pdf.pages[page_num - 1],
            y_tol=y_tol,
            merge_gap=merge_gap,
        )

    if df.empty:
        print("(no table found)")
        print("Tips:")
        print("  - If scanned: run  ocrmypdf --deskew input.pdf ocr.pdf  first")
        print("  - Try adjusting merge_gap (default 20)")
        return df

    print(f"({len(df)} rows, {len(df.columns)} cols)")
    df.insert(0, "page", page_num)
    return df


# ─────────────────────────────────────────────
# STEP 8 — EXPORT TO CSV
# ─────────────────────────────────────────────
def save_results(
    df: pd.DataFrame,
    base_name: str = "line_items",
    out_dir: str = "out"
) -> None:
    """
    Save the extracted DataFrame to a CSV file (out/{base_name}.csv).
    """
    os.makedirs(out_dir, exist_ok=True)

    csv_path = os.path.join(out_dir, f"{base_name}.csv")
    df.to_csv(csv_path, index=False)
    print(f"\n✅ CSV saved → {csv_path}")

    # Preview
    print(f"\n📋 Preview ({min(5, len(df))} of {len(df)} rows):")
    print(df.head(5).to_string(index=False))


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":

    # ── Configuration ──────────────────────────
    PDF_PATH    = "cib.pdf"            # ← change this
    PAGE_NUM    = 8                    # ← 1-indexed page to extract
    Y_TOLERANCE = None                 # ← set to e.g. 3.0 to tune line grouping
    MERGE_GAP   = 20.0                 # ← column-grouping gap (see docstring)
    OUTPUT_NAME = "cib_page8"          # ← output file base name
    OUTPUT_DIR  = "out"                # ← output folder
    # ───────────────────────────────────────────

    df = extract_pdf_items(
        pdf_path  = PDF_PATH,
        page_num  = PAGE_NUM,
        y_tol     = Y_TOLERANCE,
        merge_gap = MERGE_GAP,
    )

    if not df.empty:
        save_results(df, base_name=OUTPUT_NAME, out_dir=OUTPUT_DIR)