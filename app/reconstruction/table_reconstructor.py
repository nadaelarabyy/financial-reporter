from typing import List

from app.config import Y_CLUSTER_TOLERANCE, X_CLUSTER_TOLERANCE
from app.schemas import TableRegion, ReconstructedTable, RawCell
from app.extraction.geometry_indexer import GeometryIndexer
from app.reconstruction.row_clusterer import cluster_rows
from app.reconstruction.column_clusterer import infer_columns, assign_row_to_columns
from app.reconstruction.cell_merger import merge_wrapped_first_column_rows
from app.reconstruction.multiline_header_merger import build_headers_and_body


def reconstruct_table(region: TableRegion, geometry: GeometryIndexer) -> ReconstructedTable:
    lines = geometry.get_lines_in_bbox(region.page_number, region.bbox)

    rows = cluster_rows(lines, tolerance=Y_CLUSTER_TOLERANCE)
    column_centers = infer_columns(rows, tolerance=X_CLUSTER_TOLERANCE)

    raw_matrix: List[List[str]] = []
    raw_cells: List[RawCell] = []

    for row_idx, row in enumerate(rows):
        assigned = assign_row_to_columns(row, column_centers)
        raw_matrix.append(assigned)

        for line in row:
            if column_centers:
                x_center = (line.bbox[0] + line.bbox[2]) / 2.0
                col_idx = min(
                    range(len(column_centers)),
                    key=lambda i: abs(column_centers[i] - x_center)
                )
            else:
                col_idx = 0

            raw_cells.append(
                RawCell(
                    text=line.text,
                    row_index=row_idx,
                    col_index=col_idx,
                    bbox=line.bbox
                )
            )

    # Phase 2 improvements
    merged_matrix = merge_wrapped_first_column_rows(raw_matrix)
    headers, body_rows, header_row_count = build_headers_and_body(merged_matrix)

    # Keep matrix = headers row + body rows for compatibility/debug
    final_matrix = [headers] + body_rows if headers else merged_matrix

    notes = []
    if header_row_count > 1:
        notes.append(f"Merged {header_row_count} header rows")

    if len(merged_matrix) != len(raw_matrix):
        notes.append("Merged wrapped first-column rows")

    return ReconstructedTable(
        page_number=region.page_number,
        region_bbox=region.bbox,
        source=region.source,
        matrix=final_matrix,
        headers=headers if headers else (merged_matrix[0] if merged_matrix else []),
        raw_cells=raw_cells,
        header_row_count=header_row_count,
        notes=notes
    )