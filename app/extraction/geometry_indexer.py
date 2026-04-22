from typing import Dict, List, Optional, Set

from app.schemas import DIExtractionBundle, LineItem, BBox
from app.utils.bbox_utils import bbox_intersects
from app.detection.header_footer_detector import filter_page_lines


class GeometryIndexer:
    def __init__(self, bundle: DIExtractionBundle, noise_by_page: Optional[Dict[int, Set[str]]] = None):
        self.bundle = bundle
        self.noise_by_page = noise_by_page or {}

        self.lines_by_page: Dict[int, List[LineItem]] = {}
        for page in bundle.pages:
            raw_lines = page.lines
            noise = self.noise_by_page.get(page.page_number, set())
            self.lines_by_page[page.page_number] = filter_page_lines(raw_lines, noise)

    def get_page_lines(self, page_number: int) -> List[LineItem]:
        return self.lines_by_page.get(page_number, [])

    def get_lines_in_bbox(self, page_number: int, bbox: BBox) -> List[LineItem]:
        return [
            line for line in self.get_page_lines(page_number)
            if bbox_intersects(line.bbox, bbox)
        ]