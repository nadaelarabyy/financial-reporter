from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any


BBox = Tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max)


@dataclass
class LineItem:
    text: str
    page_number: int
    bbox: BBox
    polygon: Optional[List[float]] = None


@dataclass
class PageLines:
    page_number: int
    width: float
    height: float
    lines: List[LineItem] = field(default_factory=list)


@dataclass
class DIExtractionBundle:
    raw_result: Any
    content: str
    pages: List[PageLines]


@dataclass
class TableRegion:
    page_number: int
    bbox: BBox
    source: str  # "di_table" | "heuristic"
    confidence: float


@dataclass
class RawCell:
    text: str
    row_index: int
    col_index: int
    bbox: BBox


@dataclass
class ReconstructedTable:
    page_number: int
    region_bbox: BBox
    source: str
    matrix: List[List[str]]
    headers: List[str]
    raw_cells: List[RawCell] = field(default_factory=list)
    header_row_count: int = 1
    notes: List[str] = field(default_factory=list)


@dataclass
class TableQualityScore:
    row_count: int
    col_count: int
    row_length_variance: float
    empty_cell_ratio: float
    numeric_row_ratio: float
    overall_confidence: float
    warnings: List[str] = field(default_factory=list)


@dataclass
class RoutingDecision:
    route: str  # "DETERMINISTIC_ONLY" | "DETERMINISTIC_PLUS_AI_NORMALIZATION" | "AI_FALLBACK"
    reason: str