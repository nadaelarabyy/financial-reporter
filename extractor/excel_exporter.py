from typing import Dict, Any
import pandas as pd


def export_clean_tables_to_excel(clean_payload: Dict[str, Any], output_path: str):
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        toc = clean_payload.get("toc", [])
        if toc:
            toc_df = pd.DataFrame(toc)
            toc_df.to_excel(writer, sheet_name="TOC", index=False)

        tables = clean_payload.get("tables", [])

        for idx, table in enumerate(tables, start=1):
            rows = []
            columns = table.get("columns", [])
            has_note = "Notes" in columns

            for r in table.get("rows", []):
                record = {"Line Item": r["label"]}

                if has_note:
                    record["Notes"] = r.get("note")

                for k, v in r.get("values", {}).items():
                    record[k] = v

                record["_row_type"] = r.get("row_type")
                rows.append(record)

            df = pd.DataFrame(rows)

            sheet_name = f"T{idx}_{table.get('statement_type', 'table')}"
            sheet_name = sheet_name[:31]  # Excel limit
            df.to_excel(writer, sheet_name=sheet_name, index=False)