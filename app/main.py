import json
import os

from app.config import OUTPUT_DIR
from app.extraction.di_extractor import run_layout_analysis
from app.extraction.geometry_indexer import GeometryIndexer
from app.detection.header_footer_detector import detect_repeated_noise
from app.detection.table_region_detector import detect_table_regions
from app.reconstruction.table_reconstructor import reconstruct_table
from app.detection.table_quality_scorer import score_table_quality
from app.routing.confidence_router import route_table
from app.export.dataframe_builder import export_table_csv


def process_pdf(pdf_path: str):
    print(f"[INFO] Processing PDF: {pdf_path}")

    # 1) Extract with Azure DI
    bundle = run_layout_analysis(pdf_path)
    print(f"[INFO] Pages extracted: {len(bundle.pages)}")

    # 2) Detect repeated headers/footers
    noise_by_page = detect_repeated_noise(bundle)
    print("[INFO] Repeated page noise detected")

    # 3) Build geometry index with noise filtering
    geometry = GeometryIndexer(bundle, noise_by_page=noise_by_page)

    # 4) Detect table regions
    regions = detect_table_regions(bundle)
    print(f"[INFO] Table regions found: {len(regions)}")

    # 5) Reconstruct + score + route
    results = []
    exported_files = []

    for idx, region in enumerate(regions, start=1):
        print(f"[INFO] Reconstructing table {idx} on page {region.page_number} (source={region.source})")

        table = reconstruct_table(region, geometry)
        score = score_table_quality(table)
        routing = route_table(score)

        csv_path = export_table_csv(table, idx)
        exported_files.append(csv_path)

        results.append({
            "table_index": idx,
            "page_number": table.page_number,
            "source": table.source,
            "region_bbox": table.region_bbox,
            "header_row_count": table.header_row_count,
            "headers": table.headers,
            "reconstruction_notes": table.notes,
            "matrix_preview": table.matrix[:10],
            "quality": {
                "row_count": score.row_count,
                "col_count": score.col_count,
                "row_length_variance": score.row_length_variance,
                "empty_cell_ratio": score.empty_cell_ratio,
                "numeric_row_ratio": score.numeric_row_ratio,
                "overall_confidence": score.overall_confidence,
                "warnings": score.warnings,
            },
            "routing": {
                "route": routing.route,
                "reason": routing.reason,
            },
            "csv_path": csv_path
        })

    # 6) Save debug JSON
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_json = os.path.join(OUTPUT_DIR, "phase2_output.json")

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({
            "pdf_path": pdf_path,
            "table_count": len(results),
            "tables": results,
            "exports": exported_files
        }, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Done. Output JSON: {output_json}")
    for f in exported_files:
        print(f"[INFO] Exported CSV: {f}")


if __name__ == "__main__":
    PDF_PATH = "sample_financial_report.pdf"
    process_pdf(PDF_PATH)