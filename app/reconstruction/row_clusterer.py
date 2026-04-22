from typing import List

from app.schemas import LineItem
from app.utils.bbox_utils import bbox_center_y


def cluster_rows(lines: List[LineItem], tolerance: float) -> List[List[LineItem]]:
    """
    Cluster lines into rows by Y-center proximity.
    """
    if not lines:
        return []

    sorted_lines = sorted(lines, key=lambda l: (bbox_center_y(l.bbox), l.bbox[0]))

    rows: List[List[LineItem]] = []
    current_row = [sorted_lines[0]]
    current_y = bbox_center_y(sorted_lines[0].bbox)

    for line in sorted_lines[1:]:
        y = bbox_center_y(line.bbox)

        if abs(y - current_y) <= tolerance:
            current_row.append(line)
            # running average
            current_y = sum(bbox_center_y(l.bbox) for l in current_row) / len(current_row)
        else:
            rows.append(sorted(current_row, key=lambda l: l.bbox[0]))
            current_row = [line]
            current_y = y

    if current_row:
        rows.append(sorted(current_row, key=lambda l: l.bbox[0]))

    return rows