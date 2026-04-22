from collections import defaultdict
from typing import Dict, List, Set

from app.config import TOP_PAGE_BAND_RATIO, BOTTOM_PAGE_BAND_RATIO, REPEATED_TEXT_MIN_PAGES
from app.schemas import DIExtractionBundle, LineItem


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def detect_repeated_noise(bundle: DIExtractionBundle) -> Dict[int, Set[str]]:
    """
    Returns a mapping:
      page_number -> set(normalized_texts_to_remove)
    Only detects repeated top/bottom band text across pages.
    """
    top_candidates = defaultdict(set)     # normalized_text -> set(page_numbers)
    bottom_candidates = defaultdict(set)  # normalized_text -> set(page_numbers)

    page_heights = {p.page_number: p.height for p in bundle.pages}

    for page in bundle.pages:
        page_height = page.height
        top_limit = page_height * TOP_PAGE_BAND_RATIO
        bottom_limit = page_height * (1 - BOTTOM_PAGE_BAND_RATIO)

        for line in page.lines:
            norm = _normalize_text(line.text)
            if not norm:
                continue

            y_min = line.bbox[1]
            y_max = line.bbox[3]

            if y_max <= top_limit:
                top_candidates[norm].add(page.page_number)

            if y_min >= bottom_limit:
                bottom_candidates[norm].add(page.page_number)

    repeated_texts = set()

    for text, pages in top_candidates.items():
        if len(pages) >= REPEATED_TEXT_MIN_PAGES:
            repeated_texts.add(text)

    for text, pages in bottom_candidates.items():
        if len(pages) >= REPEATED_TEXT_MIN_PAGES:
            repeated_texts.add(text)

    noise_by_page: Dict[int, Set[str]] = {p.page_number: set() for p in bundle.pages}

    for page in bundle.pages:
        for line in page.lines:
            norm = _normalize_text(line.text)
            if norm in repeated_texts:
                noise_by_page[page.page_number].add(norm)

    return noise_by_page


def filter_page_lines(lines: List[LineItem], noise_texts: Set[str]) -> List[LineItem]:
    if not noise_texts:
        return lines

    filtered = []
    for line in lines:
        norm = _normalize_text(line.text)
        if norm not in noise_texts:
            filtered.append(line)
    return filtered