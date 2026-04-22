import os
import pandas as pd

from app.config import OUTPUT_DIR
from app.schemas import ReconstructedTable


def table_to_dataframe(table: ReconstructedTable) -> pd.DataFrame:
    matrix = table.matrix
    if not matrix:
        return pd.DataFrame()

    headers = table.headers if table.headers else [f"col_{i}" for i in range(len(matrix[0]))]

    # Since Phase 2 stores matrix as [headers] + body_rows
    data_rows = matrix[1:] if len(matrix) > 1 else []

    normalized_rows = []
    for row in data_rows:
        row = list(row)
        if len(row) < len(headers):
            row += [""] * (len(headers) - len(row))
        elif len(row) > len(headers):
            row = row[:len(headers)]
        normalized_rows.append(row)

    return pd.DataFrame(normalized_rows, columns=headers)


def export_table_csv(table: ReconstructedTable, table_index: int) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = table_to_dataframe(table)

    path = os.path.join(OUTPUT_DIR, f"table_{table_index}_page_{table.page_number}.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path