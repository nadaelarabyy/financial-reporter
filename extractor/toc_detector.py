import re
from typing import List, Dict, Any, Tuple
import pdfplumber
from .utils import normalize_spaces


TOC_TITLE_PATTERNS = [
    r"table of contents",
    r"contents",
    r"index",
]

TOC_LINE_RE = re.compile(
    r"""
    ^
    (?P<title>.+?)
    \s*(?:\.{2,}|\s{2,})
    (?P<page>\d{1,4})
    $
    """,
    re.VERBOSE
)


def page_text(page) -> str:
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def detect_toc(pdf_path: str, max_scan_pages: int = 8) -> List[Dict[str, Any]]:
    toc_entries = []

    with pdfplumber.open(pdf_path) as pdf:
        for idx in range(min(max_scan_pages, len(pdf.pages))):
            page = pdf.pages[idx]
            text = page_text(page)
            text_norm = text.lower()

            if any(re.search(p, text_norm) for p in TOC_TITLE_PATTERNS):
                lines = [normalize_spaces(l) for l in text.splitlines() if normalize_spaces(l)]

                for line in lines:
                    m = TOC_LINE_RE.match(line)
                    if m:
                        title = normalize_spaces(m.group("title"))
                        page_num = int(m.group("page"))
                        toc_entries.append({
                            "title": title,
                            "page": page_num
                        })

                # if TOC found, don't keep scanning more TOC pages in POC
                if toc_entries:
                    break

    # sort by page
    toc_entries.sort(key=lambda x: x["page"])
    return toc_entries


def build_toc_ranges(toc_entries: List[Dict[str, Any]], total_pages: int) -> List[Tuple[int, int, str]]:
    """
    Returns list of (start_page, end_page, title) in 1-based PDF page numbers.
    """
    if not toc_entries:
        return []

    ranges = []
    for i, entry in enumerate(toc_entries):
        start_page = entry["page"]
        end_page = total_pages
        if i + 1 < len(toc_entries):
            end_page = toc_entries[i + 1]["page"] - 1
        ranges.append((start_page, end_page, entry["title"]))
    return ranges