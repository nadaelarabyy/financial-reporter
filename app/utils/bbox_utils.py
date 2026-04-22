from typing import List, Tuple

BBox = Tuple[float, float, float, float]


def polygon_to_bbox(polygon: List[float]) -> BBox:
    xs = polygon[0::2]
    ys = polygon[1::2]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_height(bbox: BBox) -> float:
    return bbox[3] - bbox[1]


def bbox_width(bbox: BBox) -> float:
    return bbox[2] - bbox[0]


def bbox_center_y(bbox: BBox) -> float:
    return (bbox[1] + bbox[3]) / 2.0


def bbox_center_x(bbox: BBox) -> float:
    return (bbox[0] + bbox[2]) / 2.0


def bbox_intersects(a: BBox, b: BBox) -> bool:
    return not (
        a[2] < b[0] or
        a[0] > b[2] or
        a[3] < b[1] or
        a[1] > b[3]
    )


def bbox_contains(outer: BBox, inner: BBox) -> bool:
    return (
        outer[0] <= inner[0] and
        outer[1] <= inner[1] and
        outer[2] >= inner[2] and
        outer[3] >= inner[3]
    )


def merge_bboxes(boxes: List[BBox]) -> BBox:
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[2] for b in boxes)
    y2 = max(b[3] for b in boxes)
    return (x1, y1, x2, y2)


def expand_bbox(bbox: BBox, x_pad: float = 0.0, y_pad: float = 0.0) -> BBox:
    return (
        max(0.0, bbox[0] - x_pad),
        max(0.0, bbox[1] - y_pad),
        bbox[2] + x_pad,
        bbox[3] + y_pad,
    )