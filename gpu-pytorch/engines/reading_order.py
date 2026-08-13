"""Reading order sorting for detected layout regions."""

from __future__ import annotations

from typing import TypedDict

Region = TypedDict(
    "Region",
    {"class": str, "bbox": list[float], "confidence": float},
)


def _center(bbox: list[float]) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def sort_regions(regions: list[Region]) -> list[Region]:
    """Sort regions top-to-bottom, left-to-right within a line."""
    if not regions:
        return []
    for region in regions:
        bbox = region.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return list(regions)
        if not all(isinstance(value, (int, float)) for value in bbox):
            return list(regions)

    centers = [_center(region["bbox"]) for region in regions]
    heights = [
        max(region["bbox"][3] - region["bbox"][1], 0.0)
        for region in regions
    ]
    tolerance = max(8.0, max(heights) * 0.35)
    ordered = sorted(range(len(regions)), key=lambda index: centers[index][1])

    lines: list[list[int]] = []
    for index in ordered:
        if not lines:
            lines.append([index])
            continue
        last_index = lines[-1][0]
        if abs(centers[index][1] - centers[last_index][1]) <= tolerance:
            lines[-1].append(index)
        else:
            lines.append([index])

    result: list[Region] = []
    for line in sorted(
        lines, key=lambda line: min(centers[index][1] for index in line)
    ):
        for index in sorted(line, key=lambda index: centers[index][0]):
            result.append(regions[index])
    return result
