from typing import List

from app.schemas import LineItem
from app.utils.bbox_utils import bbox_center_x


def infer_columns(rows: List[List[LineItem]], tolerance: float) -> List[float]:
    """
    Infer column centers from x-centers of all cells.
    Returns sorted list of column centers.
    """
    x_centers = []

    for row in rows:
        for line in row:
            x_centers.append(bbox_center_x(line.bbox))

    if not x_centers:
        return []

    x_centers.sort()

    clusters = [[x_centers[0]]]

    for x in x_centers[1:]:
        cluster_center = sum(clusters[-1]) / len(clusters[-1])
        if abs(x - cluster_center) <= tolerance:
            clusters[-1].append(x)
        else:
            clusters.append([x])

    return [sum(cluster) / len(cluster) for cluster in clusters]


def assign_row_to_columns(row: List[LineItem], column_centers: List[float]) -> List[str]:
    """
    Assign each line to nearest inferred column.
    """
    if not column_centers:
        return [line.text for line in row]

    cells = [""] * len(column_centers)

    for line in row:
        x = bbox_center_x(line.bbox)
        nearest_idx = min(
            range(len(column_centers)),
            key=lambda i: abs(column_centers[i] - x)
        )

        if cells[nearest_idx]:
            # if collision, append text (Phase 1 simple handling)
            cells[nearest_idx] += " " + line.text
        else:
            cells[nearest_idx] = line.text

    return cells