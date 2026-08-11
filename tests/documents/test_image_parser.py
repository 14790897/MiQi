"""Tests for image parsing (OCR) in document_parser (#659)."""

from __future__ import annotations

from pathlib import Path

import pytest

from miqi.documents.document_parser import (
    is_supported_document,
    parse_document,
)


@pytest.fixture
def png_image(tmp_path: Path) -> Path:
    """A small valid PNG (1x1 red pixel) — no tesseract needed for metadata."""
    from PIL import Image

    img = Image.new("RGB", (1, 1), (255, 0, 0))
    p = tmp_path / "pixel.png"
    img.save(p)
    return p


@pytest.fixture
def bmp_image(tmp_path: Path) -> Path:
    from PIL import Image

    img = Image.new("RGB", (2, 2), (0, 0, 255))
    p = tmp_path / "pixel.bmp"
    img.save(p)
    return p


@pytest.mark.parametrize(
    "suffix",
    [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif", ".ico"],
)
def test_image_suffixes_are_supported(tmp_path: Path, suffix: str) -> None:
    from PIL import Image

    img = Image.new("RGB", (4, 4), "white")
    p = tmp_path / f"img{suffix}"
    img.save(p, format="PNG" if suffix in (".png", ".ico") else None)
    assert is_supported_document(p)


def test_parse_image_returns_metadata_and_header(png_image: Path) -> None:
    result = parse_document(png_image, max_chars=500)
    assert result["page_count"] == 1
    assert result["size_bytes"] > 0
    assert "png" in result["mime_type"].lower()
    assert "[图片] pixel.png (1x1" in result["text"]
    # tesseract may or may not be installed; either way text is non-empty
    # (OCR text or the graceful-degradation note).
    assert result["text"].strip()


def test_parse_image_bmp(bmp_image: Path) -> None:
    result = parse_document(bmp_image, max_chars=500)
    assert "[图片] pixel.bmp (2x2" in result["text"]


def test_parse_image_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_document(tmp_path / "nope.png", max_chars=500)
