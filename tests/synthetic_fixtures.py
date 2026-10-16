from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter

_TEMP = tempfile.TemporaryDirectory(prefix="homework-grading-collab-tests-")
SYNTHETIC_IMAGE_PATH = Path(_TEMP.name) / "synthetic-homework-page.png"


def _create_synthetic_image() -> None:
    image = Image.new("RGB", (1800, 1050), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((80, 24), "SYNTHETIC TEST PAGE - NOT STUDENT DATA", fill="black", font=font)
    draw.text((100, 100), "Question 1: 3 + 5 = ?", fill="black", font=font)
    draw.text((100, 483), "Question 2: 12 - 7 = ?", fill="black", font=font)
    draw.text((100, 850), "Question 3: 4 x 6 = ?", fill="black", font=font)
    image.save(SYNTHETIC_IMAGE_PATH, format="PNG")


def synthetic_reference_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


_create_synthetic_image()
