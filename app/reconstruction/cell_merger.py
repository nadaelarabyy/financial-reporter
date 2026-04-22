from typing import List


def merge_wrapped_first_column_rows(matrix: List[List[str]]) -> List[List[str]]:
    """
    Heuristic:
    If a row has only first column filled and next row has numeric/data columns,
    merge the first-column label into the next row.

    Example:
      ["Trade receivables", "", "", ""]
      ["", "100", "90", "80"]
    =>
      ["Trade receivables", "100", "90", "80"]
    """
    if not matrix:
        return matrix

    merged = []
    i = 0

    while i < len(matrix):
        current = matrix[i]

        if i < len(matrix) - 1:
            nxt = matrix[i + 1]

            current_non_empty = [idx for idx, c in enumerate(current) if c.strip()]
            next_non_empty = [idx for idx, c in enumerate(nxt) if c.strip()]

            # wrapped label row: only col 0 filled
            if current_non_empty == [0]:
                # next row has data beyond first col
                if any(idx > 0 for idx in next_non_empty):
                    merged_row = list(nxt)
                    if merged_row[0].strip():
                        merged_row[0] = current[0].strip() + " " + merged_row[0].strip()
                    else:
                        merged_row[0] = current[0].strip()

                    merged.append(merged_row)
                    i += 2
                    continue

        merged.append(current)
        i += 1

    return merged


def merge_adjacent_header_rows(header_rows: List[List[str]]) -> List[str]:
    """
    Merge multiple header rows column-wise.
    """
    if not header_rows:
        return []

    max_cols = max(len(r) for r in header_rows)
    normalized = []

    for row in header_rows:
        row = list(row)
        if len(row) < max_cols:
            row += [""] * (max_cols - len(row))
        normalized.append(row)

    merged_headers = []
    for col_idx in range(max_cols):
        parts = [r[col_idx].strip() for r in normalized if r[col_idx].strip()]
        merged_headers.append(" | ".join(parts) if parts else f"col_{col_idx}")

    return merged_headers