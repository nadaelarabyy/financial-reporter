from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class PageMeta:
    pdf_page: int
    printed_page: Optional[int]
    header_text: str
    body_text: str
    footer_text: str
    page_title: str
    page_type: str  # text_only / mixed / table_heavy
    toc_title: Optional[str] = None
    is_toc_page: bool = False


@dataclass
class ExtractedTable:
    table_id: str
    pdf_page: int
    source_pages: List[int]
    page_title: str
    statement_type: str
    headers: List[str]
    rows: List[List[str]]
    header_rows_raw: List[List[str]] = field(default_factory=list)
    is_continued: bool = False
    confidence: float = 0.0
    source: str = "unknown"
    currency: Optional[str] = None
    unit: Optional[str] = None
    periods: List[str] = field(default_factory=list)


@dataclass
class NormalizedRow:
    label: str
    note: Optional[str]
    values: Dict[str, str]
    numeric_values: Dict[str, Optional[float]]
    raw_row: List[str]


@dataclass
class NormalizedTable:
    table_id: str
    pdf_page: int
    source_pages: List[int]
    page_title: str
    statement_type: str
    headers: List[str]
    periods: List[str]
    currency: Optional[str]
    unit: Optional[str]
    rows: List[NormalizedRow]


@dataclass
class TocEntry:
    title: str
    printed_page: int
    toc_pdf_page: int
    resolved_pdf_page: Optional[int] = None
    resolved: bool = False