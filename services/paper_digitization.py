"""Replaceable, fail-closed layout provider for paper homework pages.

This local provider finds ink bands only. It does not claim OCR, question-number
recognition, or handwriting removal; all returned crops remain pending teacher review.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True)
class PaperRegion:
    x1: int
    y1: int
    x2: int
    y2: int
    question_no: str | None = None
    confidence: float = 0.0

    def as_dict(self) -> dict:
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "question_no": self.question_no,
            "confidence": self.confidence,
        }


class PaperDigitizeProvider:
    name = "paper_digitize_provider"
    version = "interface-v1"

    def locate_regions(self, image_path: str | Path) -> list[PaperRegion]:
        raise NotImplementedError

    def crop_jpeg(self, image_path: str | Path, bbox: tuple[int, int, int, int]) -> bytes:
        raise NotImplementedError


class LocalWhitespacePaperDigitizeProvider(PaperDigitizeProvider):
    """Generate narrow, review-required text-band crops without inventing OCR."""

    name = "local_whitespace"
    version = "011-whitespace-v1"

    def locate_regions(self, image_path: str | Path) -> list[PaperRegion]:
        with Image.open(image_path) as opened:
            gray_image = ImageOps.exif_transpose(opened).convert("L")
            gray = np.asarray(gray_image)
        height, width = gray.shape
        if width < 16 or height < 16:
            return []

        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        _, ink = cv2.threshold(
            blurred, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
        )
        active_threshold = max(3, int(width * 0.001))
        active_rows = np.count_nonzero(ink, axis=1) >= active_threshold
        if float(active_rows.mean()) > 0.65:
            _, ink = cv2.threshold(blurred, 215, 255, cv2.THRESH_BINARY_INV)
            active_rows = np.count_nonzero(ink, axis=1) >= active_threshold

        bands: list[tuple[int, int]] = []
        start: int | None = None
        for y, active in enumerate(active_rows.tolist()):
            if active and start is None:
                start = y
            elif not active and start is not None:
                bands.append((start, y - 1))
                start = None
        if start is not None:
            bands.append((start, height - 1))

        # Merge wrapped lines and small within-question gaps. Larger blank gaps
        # remain separate review candidates; no candidate is auto-confirmed.
        merge_gap = max(8, int(height * 0.035))
        merged: list[tuple[int, int]] = []
        for top, bottom in bands:
            if merged and top - merged[-1][1] - 1 <= merge_gap:
                merged[-1] = (merged[-1][0], bottom)
            else:
                merged.append((top, bottom))

        margin_x = max(6, int(width * 0.012))
        margin_y = max(4, int(height * 0.008))
        min_band_height = max(7, int(height * 0.006))
        regions: list[PaperRegion] = []
        for top, bottom in merged:
            if bottom - top + 1 < min_band_height:
                continue
            content = ink[top : bottom + 1, :]
            columns = np.flatnonzero(np.count_nonzero(content, axis=0) > 0)
            if columns.size < max(6, int(width * 0.015)):
                continue
            x1 = max(0, int(columns[0]) - margin_x)
            x2 = min(width, int(columns[-1]) + margin_x + 1)
            y1 = max(0, top - margin_y)
            y2 = min(height, bottom + margin_y + 1)
            if x2 <= x1 or y2 <= y1:
                continue
            if (x1, y1, x2, y2) == (0, 0, width, height):
                continue
            if ((x2 - x1) * (y2 - y1)) / float(width * height) >= 0.95:
                continue
            regions.append(PaperRegion(x1=x1, y1=y1, x2=x2, y2=y2))
        return regions

    def crop_jpeg(self, image_path: str | Path, bbox: tuple[int, int, int, int]) -> bytes:
        with Image.open(image_path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = image.size
            x1, y1, x2, y2 = bbox
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError("question crop coordinates are outside the source image")
            if (x1, y1, x2, y2) == (0, 0, width, height):
                raise ValueError("a whole-page image cannot be stored as one question")
            if ((x2 - x1) * (y2 - y1)) / float(width * height) >= 0.95:
                raise ValueError("question crop is too close to a whole-page image")
            from io import BytesIO

            buffer = BytesIO()
            image.crop((x1, y1, x2, y2)).save(buffer, format="JPEG", quality=94)
            return buffer.getvalue()


paper_digitize_provider: PaperDigitizeProvider = LocalWhitespacePaperDigitizeProvider()
