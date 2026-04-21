import os
import json
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient


# =========================================================
# CONFIG
# =========================================================

load_dotenv()

AZURE_ENDPOINT = os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT")
AZURE_KEY = os.getenv("AZURE_DOC_INTELLIGENCE_KEY")

if not AZURE_ENDPOINT or not AZURE_KEY:
    raise ValueError(
        "Missing AZURE_DOC_INTELLIGENCE_ENDPOINT or AZURE_DOC_INTELLIGENCE_KEY in .env"
    )

MODEL_ID = "prebuilt-layout"

client = DocumentIntelligenceClient(
    endpoint=AZURE_ENDPOINT,
    credential=AzureKeyCredential(AZURE_KEY)
)

RAW_OUTPUT_FILE = "doc_intelligence_raw_output.json"
TABLES_OUTPUT_FILE = "doc_intelligence_tables_only.json"


# =========================================================
# HELPERS
# =========================================================

def polygon_to_list(polygon) -> Optional[List[Dict[str, float]]]:
    """
    Azure returns polygon as a flat list of points.
    Convert to readable [{x, y}, ...]
    """
    if not polygon:
        return None

    out = []
    for p in polygon:
        out.append({"x": round(p.x, 2), "y": round(p.y, 2)})
    return out


def bounding_regions_to_json(obj) -> List[Dict[str, Any]]:
    """
    Works for tables / cells / paragraphs etc.
    """
    regions = []
    if not getattr(obj, "bounding_regions", None):
        return regions

    for br in obj.bounding_regions:
        regions.append({
            "page_number": br.page_number,
            "polygon": polygon_to_list(br.polygon)
        })
    return regions


def spans_to_json(obj) -> List[Dict[str, Any]]:
    spans = []
    if not getattr(obj, "spans", None):
        return spans

    for s in obj.spans:
        spans.append({
            "offset": s.offset,
            "length": s.length
        })
    return spans


def safe_enum_to_str(value):
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


# =========================================================
# TABLE PROCESSING
# =========================================================

def build_empty_grid(rows: int, cols: int) -> List[List[Optional[str]]]:
    return [[None for _ in range(cols)] for _ in range(rows)]


def fill_grid_from_cells(row_count: int, col_count: int, cells) -> List[List[Optional[str]]]:
    """
    Simple preview grid:
    - places cell content in top-left of each cell
    - does not fully expand merged spans (for simplicity)
    """
    grid = build_empty_grid(row_count, col_count)

    for cell in cells:
        r = cell.row_index
        c = cell.column_index
        if 0 <= r < row_count and 0 <= c < col_count:
            grid[r][c] = cell.content.strip() if cell.content else ""

    return grid


def table_to_json(table, table_index: int) -> Dict[str, Any]:
    row_count = table.row_count
    col_count = table.column_count

    grid = fill_grid_from_cells(row_count, col_count, table.cells)

    cells_json = []
    for cell in table.cells:
        cell_json = {
            "row_index": cell.row_index,
            "column_index": cell.column_index,
            "row_span": getattr(cell, "row_span", 1) or 1,
            "column_span": getattr(cell, "column_span", 1) or 1,
            "content": cell.content.strip() if cell.content else "",
            "kind": safe_enum_to_str(getattr(cell, "kind", None)),
            "bounding_regions": bounding_regions_to_json(cell),
            "spans": spans_to_json(cell)
        }
        cells_json.append(cell_json)

    # infer primary page from first bounding region
    page_number = None
    if getattr(table, "bounding_regions", None):
        if len(table.bounding_regions) > 0:
            page_number = table.bounding_regions[0].page_number

    return {
        "table_index": table_index,
        "page_number": page_number,
        "row_count": row_count,
        "column_count": col_count,
        "bounding_regions": bounding_regions_to_json(table),
        "cells": cells_json,
        "grid_preview": grid
    }


def grid_to_dataframe(grid: List[List[Optional[str]]]) -> pd.DataFrame:
    if not grid:
        return pd.DataFrame()

    # Heuristic: first row as header if it has at least one non-empty cell
    first_row = grid[0]
    has_header = any(v is not None and str(v).strip() != "" for v in first_row)

    if has_header and len(grid) > 1:
        headers = []
        for i, v in enumerate(first_row):
            header = str(v).strip() if v is not None and str(v).strip() else f"col_{i+1}"
            headers.append(header)
        data_rows = grid[1:]
        return pd.DataFrame(data_rows, columns=headers)

    return pd.DataFrame(grid)


# =========================================================
# RAW RESULT SERIALIZATION
# =========================================================

def pages_to_json(result) -> List[Dict[str, Any]]:
    pages_json = []

    if not result.pages:
        return pages_json

    for page in result.pages:
        page_json = {
            "page_number": page.page_number,
            "width": round(page.width, 2) if page.width else None,
            "height": round(page.height, 2) if page.height else None,
            "unit": safe_enum_to_str(getattr(page, "unit", None)),
            "lines": [],
            "words": []
        }

        # lines
        if getattr(page, "lines", None):
            for line in page.lines:
                page_json["lines"].append({
                    "content": line.content,
                    "polygon": polygon_to_list(line.polygon),
                    "spans": spans_to_json(line)
                })

        # words
        if getattr(page, "words", None):
            for word in page.words:
                page_json["words"].append({
                    "content": word.content,
                    "confidence": word.confidence,
                    "polygon": polygon_to_list(word.polygon),
                    "span": {
                        "offset": word.span.offset,
                        "length": word.span.length
                    } if getattr(word, "span", None) else None
                })

        pages_json.append(page_json)

    return pages_json


def paragraphs_to_json(result) -> List[Dict[str, Any]]:
    paragraphs_json = []

    if not getattr(result, "paragraphs", None):
        return paragraphs_json

    for p in result.paragraphs:
        paragraphs_json.append({
            "content": p.content,
            "role": safe_enum_to_str(getattr(p, "role", None)),
            "bounding_regions": bounding_regions_to_json(p),
            "spans": spans_to_json(p)
        })

    return paragraphs_json


# =========================================================
# MAIN ANALYSIS
# =========================================================

def analyze_pdf_with_layout(pdf_path: str, pages: Optional[str] = None) -> Dict[str, Any]:
    """
    pages examples:
      None      -> all pages
      "1-10"    -> first 10 pages
      "3,4,6,8" -> selected pages
    """

    print(f"Analyzing PDF with Azure Document Intelligence ({MODEL_ID})...")
    print(f"PDF: {pdf_path}")
    print(f"Pages filter: {pages or 'ALL'}")

    with open(pdf_path, "rb") as f:
        poller = client.begin_analyze_document(
            model_id=MODEL_ID,
            body=f,
            pages=pages
        )
        result = poller.result()

    output = {
        "pdf_path": pdf_path,
        "model_id": MODEL_ID,
        "pages_requested": pages,
        "page_count": len(result.pages) if result.pages else 0,
        "paragraph_count": len(result.paragraphs) if getattr(result, "paragraphs", None) else 0,
        "table_count": len(result.tables) if getattr(result, "tables", None) else 0,
        "pages": pages_to_json(result),
        "paragraphs": paragraphs_to_json(result),
        "tables": []
    }

    if not result.tables:
        print("\nNo tables detected.")
        return output

    print(f"\nDetected {len(result.tables)} tables total\n")

    for idx, table in enumerate(result.tables, start=1):
        table_json = table_to_json(table, idx)
        output["tables"].append(table_json)

        page_no = table_json["page_number"]
        row_count = table_json["row_count"]
        col_count = table_json["column_count"]

        print("=" * 80)
        print(f"TABLE {idx} | PAGE {page_no} | ROWS={row_count} | COLS={col_count}")
        print("=" * 80)

        # DataFrame preview
        df = grid_to_dataframe(table_json["grid_preview"])

        if not df.empty:
            preview_rows = min(len(df), 12)
            print(f"\nGrid Preview (first {preview_rows} rows):")
            try:
                print(df.head(preview_rows).to_string(index=False))
            except Exception:
                print(df.head(preview_rows))
        else:
            print("\nGrid Preview: (empty)")

        # Print first few cells
        print("\nFirst 10 cells:")
        for cell in table_json["cells"][:10]:
            print(
                f"  r={cell['row_index']}, c={cell['column_index']}, "
                f"content={repr(cell['content'])}, "
                f"row_span={cell['row_span']}, col_span={cell['column_span']}, "
                f"kind={cell['kind']}"
            )

        print()

    return output


# =========================================================
# SAVE
# =========================================================

def save_json(data: Dict[str, Any], output_path: str):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON -> {output_path}")


def save_tables_only(data: Dict[str, Any], output_path: str):
    tables_only = {
        "pdf_path": data.get("pdf_path"),
        "model_id": data.get("model_id"),
        "table_count": data.get("table_count"),
        "tables": data.get("tables", [])
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tables_only, f, indent=2, ensure_ascii=False)
    print(f"Saved tables-only JSON -> {output_path}")


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    # Replace with your local file path if needed
    pdf_path = "cib.pdf"

    # IMPORTANT:
    # For your POC, test selected pages first (better than whole 150 pages)
    # Good examples:
    #   "3,4,6,8,10"
    #   "3-10"
    pages = "3,4,6,8,10"

    result = analyze_pdf_with_layout(pdf_path=pdf_path, pages=pages)

    print("\nSUMMARY")
    print("-" * 80)
    print(f"Pages analyzed : {result['page_count']}")
    print(f"Paragraphs     : {result['paragraph_count']}")
    print(f"Tables         : {result['table_count']}")

    save_json(result, RAW_OUTPUT_FILE)
    save_tables_only(result, TABLES_OUTPUT_FILE)