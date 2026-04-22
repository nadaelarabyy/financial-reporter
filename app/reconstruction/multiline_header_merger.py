import re
from typing import List, Tuple

from app.reconstruction.cell_merger import merge_adjacent_header_rows


NUMERIC_RE = re.compile(r"[\d,().%-]")


def _is_numericish(text: str) -> bool:
    return bool(NUMERIC_RE.search(text))


def detect_header_row_count(matrix: List[List[str]], max_header_rows: int = 3) -> int:
    """
    Heuristic:
    - first rows with low numeric density are likely headers
    - stop when row looks data-like
    """
    if not matrix:
        return 0

    header_count = 0

    for row in matrix[:max_header_rows]:
        filled = [c for c in row if c.strip()]
        if not filled:
            continue

        numericish = sum(1 for c in filled if _is_numericish(c))
        ratio = numericish / len(filled)

        # if mostly non-numeric => likely header
        if ratio <= 0.35:
            header_count += 1
        else:
            break

    return max(1, header_count) if matrix else 0


def build_headers_and_body(matrix: List[List[str]]) -> Tuple[List[str], List[List[str]], int]:
    if not matrix:
        return [], [], 0

    header_row_count = detect_header_row_count(matrix)

    header_rows = matrix[:header_row_count]
    body_rows = matrix[header_row_count:]

    headers = merge_adjacent_header_rows(header_rows)

    return headers, body_rows, header_row_count