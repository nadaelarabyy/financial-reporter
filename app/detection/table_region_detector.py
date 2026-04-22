import re
from typing import List

from app.schemas import DIExtractionBundle, TableRegion
from app.utils.bbox_utils import polygon_to_bbox, merge_bboxes


NUMERIC_RE = re.compile(r"[\d,().%-]")


def _is_numericish(text: str) -> bool:
    return bool(NUMERIC_RE.search(text))


def detect_table_regions(bundle: DIExtractionBundle) -> List[TableRegion]:
    regions: List[TableRegion] = []

    # 1) Prefer native DI tables if available
    if getattr(bundle.raw_result, "tables", None):
        for table in bundle.raw_result.tables:
            if not table.bounding_regions:
                continue

            # Use first bounding region page number if available
            page_number = table.bounding_regions[0].page_number

            all_boxes = []
            for br in table.bounding_regions:
                if br.polygon:
                    all_boxes.append(polygon_to_bbox(list(br.polygon)))

            if all_boxes:
                bbox = merge_bboxes(all_boxes)
                regions.append(
                    TableRegion(
                        page_number=page_number,
                        bbox=bbox,
                        source="di_table",
                        confidence=0.9
                    )
                )

    # 2) Heuristic fallback if DI found nothing
    if regions:
        return regions

    for page in bundle.pages:
        lines = page.lines
        if len(lines) < 4:
            continue

        # sliding windows of lines to find dense numeric regions
        window_size = 8
        for i in range(0, max(1, len(lines) - window_size + 1)):
            window = lines[i:i + window_size]
            if len(window) < 4:
                continue

            numeric_count = sum(1 for l in window if _is_numericish(l.text))
            if numeric_count / len(window) >= 0.5:
                bboxes = [l.bbox for l in window]
                bbox = merge_bboxes(bboxes)

                regions.append(
                    TableRegion(
                        page_number=page.page_number,
                        bbox=bbox,
                        source="heuristic",
                        confidence=0.55
                    )
                )

    return _dedupe_regions(regions)


def _dedupe_regions(regions: List[TableRegion]) -> List[TableRegion]:
    # very simple dedupe for Phase 1
    deduped = []
    seen = set()

    for r in regions:
        key = (
            r.page_number,
            round(r.bbox[0], 2),
            round(r.bbox[1], 2),
            round(r.bbox[2], 2),
            round(r.bbox[3], 2),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped