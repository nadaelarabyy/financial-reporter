from typing import List, Dict, Any
import pdfplumber
import pandas as pd

try:
    import camelot
    HAS_CAMELOT = True
except Exception:
    HAS_CAMELOT = False

from .utils import normalize_spaces


def df_to_rows(df: pd.DataFrame) -> List[List[str]]:
    rows = []
    for _, r in df.iterrows():
        row = [normalize_spaces(v) for v in r.tolist()]
        if any(row):
            rows.append(row)
    return rows


def extract_tables_camelot(pdf_path: str, page_number: int) -> List[Dict[str, Any]]:
    if not HAS_CAMELOT:
        return []

    tables = []
    try:
        # Try lattice first
        tb = camelot.read_pdf(pdf_path, pages=str(page_number), flavor="lattice")
        for i, t in enumerate(tb):
            rows = df_to_rows(t.df)
            if rows:
                tables.append({
                    "source": "camelot_lattice",
                    "pdf_page": page_number,
                    "rows": rows
                })

        # If nothing good, try stream
        if not tables:
            tb = camelot.read_pdf(pdf_path, pages=str(page_number), flavor="stream")
            for i, t in enumerate(tb):
                rows = df_to_rows(t.df)
                if rows:
                    tables.append({
                        "source": "camelot_stream",
                        "pdf_page": page_number,
                        "rows": rows
                    })

    except Exception:
        pass

    return tables


def extract_tables_pdfplumber(pdf_path: str, page_number: int) -> List[Dict[str, Any]]:
    tables = []

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number - 1]

        # Try explicit table extraction
        try:
            extracted = page.extract_tables()
            for i, t in enumerate(extracted):
                rows = []
                for row in t:
                    cleaned = [normalize_spaces(c) for c in row]
                    if any(cleaned):
                        rows.append(cleaned)
                if rows:
                    tables.append({
                        "source": "pdfplumber",
                        "pdf_page": page_number,
                        "rows": rows
                    })
        except Exception:
            pass

    return tables


def extract_tables_hybrid(pdf_path: str, page_number: int) -> List[Dict[str, Any]]:
    camelot_tables = extract_tables_camelot(pdf_path, page_number)
    pdfplumber_tables = extract_tables_pdfplumber(pdf_path, page_number)
    return camelot_tables + pdfplumber_tables