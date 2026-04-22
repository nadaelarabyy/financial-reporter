import re
from statistics import variance
from typing import List

from app.schemas import ReconstructedTable, TableQualityScore


NUMERIC_RE = re.compile(r"[\d,().%-]")


def _is_numericish(text: str) -> bool:
    return bool(NUMERIC_RE.search(text))


def score_table_quality(table: ReconstructedTable) -> TableQualityScore:
    matrix = table.matrix

    if not matrix:
        return TableQualityScore(
            row_count=0,
            col_count=0,
            row_length_variance=0.0,
            empty_cell_ratio=1.0,
            numeric_row_ratio=0.0,
            overall_confidence=0.0,
            warnings=["Empty table"]
        )

    row_lengths = [len(r) for r in matrix]
    row_count = len(matrix)
    col_count = max(row_lengths) if row_lengths else 0

    row_length_variance = variance(row_lengths) if len(row_lengths) > 1 else 0.0

    total_cells = sum(len(r) for r in matrix)
    empty_cells = sum(1 for r in matrix for c in r if not c.strip())
    empty_cell_ratio = empty_cells / total_cells if total_cells else 1.0

    # Skip header row when possible
    body_rows = matrix[1:] if len(matrix) > 1 else matrix

    numeric_rows = 0
    for row in body_rows:
        filled = [c for c in row if c.strip()]
        if filled:
            numericish = sum(1 for c in filled if _is_numericish(c))
            if numericish / len(filled) >= 0.4:
                numeric_rows += 1

    numeric_row_ratio = numeric_rows / len(body_rows) if body_rows else 0.0

    confidence = 0.0
    warnings: List[str] = []

    if row_count >= 4:
        confidence += 0.20
    else:
        warnings.append("Low row count")

    if col_count >= 2:
        confidence += 0.20
    else:
        warnings.append("Low column count")

    if row_length_variance <= 1.5:
        confidence += 0.20
    else:
        warnings.append("High row length variance")

    if empty_cell_ratio <= 0.45:
        confidence += 0.15
    else:
        warnings.append("High empty cell ratio")

    if numeric_row_ratio >= 0.4:
        confidence += 0.15
    else:
        warnings.append("Low numeric row ratio")

    # header quality bonus
    non_empty_headers = sum(1 for h in table.headers if h.strip())
    if table.headers and col_count > 0 and non_empty_headers / col_count >= 0.6:
        confidence += 0.10
    else:
        warnings.append("Weak header quality")

    return TableQualityScore(
        row_count=row_count,
        col_count=col_count,
        row_length_variance=row_length_variance,
        empty_cell_ratio=empty_cell_ratio,
        numeric_row_ratio=numeric_row_ratio,
        overall_confidence=round(min(confidence, 1.0), 3),
        warnings=warnings
    )