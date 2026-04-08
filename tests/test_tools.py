"""
Comprehensive unit tests for pdfer tool functions.

Each tool exposes:
    run(input_files: list[Path], params: dict, work_dir: Path) -> list[Path]

Tests call run() directly -- no HTTP layer involved.
"""
from pathlib import Path

import fitz
import pytest

# Project root is already on sys.path via conftest.py
from tools import compress, convert, merge, page_numbers, rotate, split, watermark


# ===========================================================================
# Helpers
# ===========================================================================

def _page_count(pdf_path: Path) -> int:
    with fitz.open(str(pdf_path)) as doc:
        return len(doc)


def _page_text(pdf_path: Path, page_index: int = 0) -> str:
    with fitz.open(str(pdf_path)) as doc:
        return doc[page_index].get_text()


def _page_rotation(pdf_path: Path, page_index: int) -> int:
    with fitz.open(str(pdf_path)) as doc:
        return doc[page_index].rotation


# ===========================================================================
# MERGE
# ===========================================================================

class TestMerge:

    def test_merge_two_pdfs(self, sample_pdf, sample_pdf_2page, work_dir):
        """Merging a 4-page and a 2-page PDF should produce a 6-page PDF."""
        outputs = merge.run([sample_pdf, sample_pdf_2page], {}, work_dir)
        assert len(outputs) == 1
        assert outputs[0].suffix.lower() == ".pdf"
        assert _page_count(outputs[0]) == 6

    def test_merge_single_pdf(self, sample_pdf, work_dir):
        """Merging a single PDF should pass it through unchanged (same page count)."""
        outputs = merge.run([sample_pdf], {}, work_dir)
        assert len(outputs) == 1
        assert _page_count(outputs[0]) == _page_count(sample_pdf)

    def test_merge_ignores_non_pdf(self, sample_pdf, sample_png, work_dir):
        """Non-PDF files in the input list are silently skipped; only PDFs are merged."""
        outputs = merge.run([sample_pdf, sample_png], {}, work_dir)
        assert len(outputs) == 1
        assert _page_count(outputs[0]) == _page_count(sample_pdf)

    def test_merge_raises_with_no_pdfs(self, sample_png, work_dir):
        """Merge should raise ValueError when no PDF files are provided."""
        with pytest.raises(ValueError):
            merge.run([sample_png], {}, work_dir)


# ===========================================================================
# SPLIT
# ===========================================================================

class TestSplit:

    def test_split_produces_one_file_per_page(self, sample_pdf, work_dir):
        """Splitting a 4-page PDF should produce exactly 4 output files."""
        outputs = split.run([sample_pdf], {}, work_dir)
        assert len(outputs) == 4

    def test_split_page_count(self, sample_pdf, work_dir):
        """Every file produced by split should contain exactly 1 page."""
        outputs = split.run([sample_pdf], {}, work_dir)
        for out in outputs:
            assert _page_count(out) == 1, f"{out.name} has more than 1 page"

    def test_split_passes_through_non_pdf(self, sample_pdf, sample_png, work_dir):
        """Non-PDF files should be returned as-is (no conversion)."""
        outputs = split.run([sample_pdf, sample_png], {}, work_dir)
        pdf_outputs = [o for o in outputs if o.suffix.lower() == ".pdf"]
        non_pdf_outputs = [o for o in outputs if o.suffix.lower() != ".pdf"]
        assert len(pdf_outputs) == 4
        assert len(non_pdf_outputs) == 1
        assert non_pdf_outputs[0] == sample_png


# ===========================================================================
# COMPRESS
# ===========================================================================

class TestCompress:

    def test_compress_produces_valid_pdf(self, sample_pdf, work_dir):
        """Compress should return a valid, openable PDF."""
        outputs = compress.run([sample_pdf], {}, work_dir)
        assert len(outputs) == 1
        with fitz.open(str(outputs[0])) as doc:
            assert doc.page_count > 0

    def test_compress_page_count_preserved(self, sample_pdf, work_dir):
        """Compressing should not change the number of pages."""
        outputs = compress.run([sample_pdf], {}, work_dir)
        assert _page_count(outputs[0]) == _page_count(sample_pdf)

    def test_compress_passes_through_non_pdf(self, sample_png, work_dir):
        """Non-PDF files should be returned unchanged (same path object)."""
        outputs = compress.run([sample_png], {}, work_dir)
        assert len(outputs) == 1
        assert outputs[0] == sample_png


# ===========================================================================
# PAGE NUMBERS
# ===========================================================================

class TestPageNumbers:

    def test_page_numbers_bottom_center(self, sample_pdf, work_dir):
        """Default params should produce a valid PDF with the same page count."""
        outputs = page_numbers.run(
            [sample_pdf],
            {"position": "bottom-center", "start": 1, "prefix": "", "font_size": 11},
            work_dir,
        )
        assert len(outputs) == 1
        assert outputs[0].suffix.lower() == ".pdf"
        assert _page_count(outputs[0]) == _page_count(sample_pdf)

    def test_page_numbers_custom_start(self, tmp_path, work_dir):
        """With start=5, the first page should contain the number '5'."""
        # Use a fresh blank PDF so only the stamped number appears in get_text().
        src = tmp_path / "blank.pdf"
        doc = fitz.open()
        doc.new_page(width=595, height=842)
        doc.save(str(src))
        doc.close()

        outputs = page_numbers.run(
            [src],
            {"position": "bottom-center", "start": 5, "prefix": "", "font_size": 11},
            work_dir,
        )
        text = _page_text(outputs[0], page_index=0)
        assert "5" in text, f"Expected '5' in page text, got: {repr(text)}"

    def test_page_numbers_with_prefix(self, tmp_path, work_dir):
        """With prefix='Page ', the first page should contain 'Page 1'."""
        src = tmp_path / "blank.pdf"
        doc = fitz.open()
        doc.new_page(width=595, height=842)
        doc.save(str(src))
        doc.close()

        outputs = page_numbers.run(
            [src],
            {"position": "bottom-center", "start": 1, "prefix": "Page ", "font_size": 11},
            work_dir,
        )
        text = _page_text(outputs[0], page_index=0)
        assert "Page 1" in text, f"Expected 'Page 1' in page text, got: {repr(text)}"

    def test_page_numbers_passes_through_non_pdf(self, sample_png, work_dir):
        """Non-PDF files should be returned as-is."""
        outputs = page_numbers.run(
            [sample_png],
            {"position": "bottom-center", "start": 1, "prefix": "", "font_size": 11},
            work_dir,
        )
        assert len(outputs) == 1
        assert outputs[0] == sample_png


# ===========================================================================
# ROTATE
# ===========================================================================

class TestRotate:

    def test_rotate_90_degrees(self, sample_pdf, work_dir):
        """All pages should have rotation == 90 after rotating by 90."""
        outputs = rotate.run(
            [sample_pdf],
            {"angle": "90", "pages": "all"},
            work_dir,
        )
        assert len(outputs) == 1
        with fitz.open(str(outputs[0])) as doc:
            for page in doc:
                assert page.rotation == 90, f"Expected rotation 90, got {page.rotation}"

    def test_rotate_180_degrees(self, sample_pdf, work_dir):
        """All pages should have rotation == 180 after rotating by 180."""
        outputs = rotate.run(
            [sample_pdf],
            {"angle": "180", "pages": "all"},
            work_dir,
        )
        with fitz.open(str(outputs[0])) as doc:
            for page in doc:
                assert page.rotation == 180

    def test_rotate_specific_pages(self, sample_pdf, work_dir):
        """Only page 1 (index 0) should be rotated; page 2 (index 1) stays at 0."""
        outputs = rotate.run(
            [sample_pdf],
            {"angle": "90", "pages": "1"},
            work_dir,
        )
        with fitz.open(str(outputs[0])) as doc:
            assert doc[0].rotation == 90, "Page 1 should be rotated 90 degrees"
            assert doc[1].rotation == 0, "Page 2 should be unchanged (0 degrees)"

    def test_rotate_passes_through_non_pdf(self, sample_png, work_dir):
        """Non-PDF files should be returned as-is."""
        outputs = rotate.run(
            [sample_png],
            {"angle": "90", "pages": "all"},
            work_dir,
        )
        assert len(outputs) == 1
        assert outputs[0] == sample_png


# ===========================================================================
# WATERMARK
# ===========================================================================

class TestWatermark:

    def test_watermark_produces_valid_pdf(self, sample_pdf, work_dir):
        """Watermark should return a valid, openable PDF."""
        outputs = watermark.run(
            [sample_pdf],
            {"text": "DRAFT", "font_size": 52, "color": "#aaaaaa"},
            work_dir,
        )
        assert len(outputs) == 1
        with fitz.open(str(outputs[0])) as doc:
            assert doc.page_count > 0

    def test_watermark_text_present(self, sample_pdf, work_dir):
        """The watermark text should be retrievable via page.get_text()."""
        wm_text = "TESTMARK"
        outputs = watermark.run(
            [sample_pdf],
            {"text": wm_text, "font_size": 52, "color": "#ff0000"},
            work_dir,
        )
        text = _page_text(outputs[0], page_index=0)
        assert wm_text in text, (
            f"Expected watermark text '{wm_text}' in page text, got: {repr(text)}"
        )

    def test_watermark_passes_through_non_pdf(self, sample_png, work_dir):
        """Non-PDF files should be returned as-is."""
        outputs = watermark.run(
            [sample_png],
            {"text": "CONFIDENTIAL", "font_size": 52, "color": "#aaaaaa"},
            work_dir,
        )
        assert len(outputs) == 1
        assert outputs[0] == sample_png


# ===========================================================================
# CONVERT
# ===========================================================================

class TestConvert:

    def test_convert_png_to_pdf(self, sample_png, work_dir):
        """A PNG file should be converted to a valid single-page PDF."""
        outputs = convert.run([sample_png], {}, work_dir)
        assert len(outputs) == 1
        assert outputs[0].suffix.lower() == ".pdf"
        assert _page_count(outputs[0]) == 1

    def test_convert_jpg_to_pdf(self, sample_jpg, work_dir):
        """A JPEG file should be converted to a valid single-page PDF."""
        outputs = convert.run([sample_jpg], {}, work_dir)
        assert len(outputs) == 1
        assert outputs[0].suffix.lower() == ".pdf"
        assert _page_count(outputs[0]) == 1

    def test_convert_pdf_passthrough(self, sample_pdf, work_dir):
        """A PDF input should be copied to work_dir and returned as a PDF."""
        outputs = convert.run([sample_pdf], {}, work_dir)
        assert len(outputs) == 1
        assert outputs[0].suffix.lower() == ".pdf"
        assert _page_count(outputs[0]) == _page_count(sample_pdf)
        assert outputs[0].parent == work_dir
