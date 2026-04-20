import os
import json
import pdfplumber

from extractor.toc_detector import detect_toc
from extractor.section_detector import extract_page_title, detect_statement_type_for_page
from extractor.table_extractor import extract_tables_hybrid
from extractor.header_processor import process_headers
from extractor.table_merger import merge_continued_tables
from extractor.final_curator import curate_output
from extractor.excel_exporter import export_clean_tables_to_excel


# =========================
# CONFIG
# =========================
PDF_PATH = "input/cib.pdf"   # <-- change this
OUTPUT_DIR = "output"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_total_pages(pdf_path: str) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def page_has_table_signal(processed_rows):
    """
    Generic signal to discard text-only pages:
    - at least 2 rows
    - at least 1 row has numeric cells
    """
    if not processed_rows or len(processed_rows) < 2:
        return False

    numeric_rows = 0
    for row in processed_rows:
        numeric_count = sum(
            1 for c in row
            if c and any(ch.isdigit() for ch in str(c))
        )
        if numeric_count >= 1:
            numeric_rows += 1

    return numeric_rows >= 1


def main():
    total_pages = get_total_pages(PDF_PATH)

    # 1) TOC (optional)
    toc_entries = detect_toc(PDF_PATH)

    # 2) Extract raw candidate tables
    raw_tables = []

    for page_num in range(1, total_pages + 1):
        page_title = extract_page_title(PDF_PATH, page_num)
        statement_type = detect_statement_type_for_page(PDF_PATH, page_num)

        candidates = extract_tables_hybrid(PDF_PATH, page_num)

        for idx, cand in enumerate(candidates, start=1):
            processed = process_headers(cand["rows"])

            # discard text-only / bad candidates
            if not page_has_table_signal(processed["rows"]):
                continue

            raw_tables.append({
                "table_id": f"p{page_num}_t{idx}_{cand['source']}",
                "source": cand["source"],
                "pdf_page": page_num,
                "source_pages": [page_num],
                "page_title": page_title,
                "statement_type": statement_type,
                "header_rows_raw": processed["header_rows"],
                "headers": processed["headers"],
                "rows": processed["rows"]
            })

    # 3) Merge continued tables across pages
    # group by statement type to improve merge behavior
    grouped = {}
    for t in raw_tables:
        key = t.get("statement_type") or "unknown"
        grouped.setdefault(key, []).append(t)

    merged_tables = []
    for _, group in grouped.items():
        merged_tables.extend(merge_continued_tables(group))

    # 4) Save raw output (debugging)
    raw_output = {
        "toc": toc_entries,
        "tables": merged_tables
    }

    raw_json_path = os.path.join(OUTPUT_DIR, "raw_extracted_tables.json")
    with open(raw_json_path, "w", encoding="utf-8") as f:
        json.dump(raw_output, f, indent=2, ensure_ascii=False)

    # 5) Final generic curation
    clean_output = curate_output(raw_output)

    clean_json_path = os.path.join(OUTPUT_DIR, "final_clean_tables.json")
    with open(clean_json_path, "w", encoding="utf-8") as f:
        json.dump(clean_output, f, indent=2, ensure_ascii=False)

    # 6) Excel export
    clean_excel_path = os.path.join(OUTPUT_DIR, "final_clean_tables.xlsx")
    export_clean_tables_to_excel(clean_output, clean_excel_path)

    print("Done.")
    print(f"Raw JSON   : {raw_json_path}")
    print(f"Clean JSON : {clean_json_path}")
    print(f"Excel      : {clean_excel_path}")


if __name__ == "__main__":
    main()