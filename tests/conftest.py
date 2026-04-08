"""Shared fixtures for pdfer tool tests."""
import sys
from pathlib import Path

# Ensure the project root is on sys.path so "tools" can be imported directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import fitz
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(path: Path, num_pages: int = 4) -> Path:
    """Create a simple PDF with *num_pages* pages, each containing visible text."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)  # A4 points
        page.insert_text(
            fitz.Point(72, 100 + i * 20),
            f"Page {i + 1} of {num_pages}",
            fontsize=14,
            fontname="helv",
        )
    doc.save(str(path))
    doc.close()
    return path


def _make_png(path: Path, width: int = 200, height: int = 100) -> Path:
    """Create a simple solid-colour PNG."""
    img = Image.new("RGB", (width, height), color=(100, 149, 237))  # cornflower blue
    img.save(str(path), "PNG")
    return path


def _make_jpg(path: Path, width: int = 200, height: int = 100) -> Path:
    """Create a simple solid-colour JPEG."""
    img = Image.new("RGB", (width, height), color=(255, 165, 0))  # orange
    img.save(str(path), "JPEG")
    return path


# ---------------------------------------------------------------------------
# Session-scoped source assets (created once, never mutated by tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory) -> Path:
    """A 4-page PDF with text on each page."""
    p = tmp_path_factory.mktemp("assets") / "sample.pdf"
    return _make_pdf(p, num_pages=4)


@pytest.fixture(scope="session")
def sample_pdf_2page(tmp_path_factory) -> Path:
    """A 2-page PDF used as a second input for merge tests."""
    p = tmp_path_factory.mktemp("assets2") / "sample2.pdf"
    return _make_pdf(p, num_pages=2)


@pytest.fixture(scope="session")
def sample_png(tmp_path_factory) -> Path:
    """A simple PNG image."""
    p = tmp_path_factory.mktemp("assets3") / "image.png"
    return _make_png(p)


@pytest.fixture(scope="session")
def sample_jpg(tmp_path_factory) -> Path:
    """A simple JPEG image."""
    p = tmp_path_factory.mktemp("assets4") / "photo.jpg"
    return _make_jpg(p)


# ---------------------------------------------------------------------------
# Function-scoped work dir (fresh per test)
# ---------------------------------------------------------------------------

@pytest.fixture
def work_dir(tmp_path) -> Path:
    """A clean temporary output directory for each test."""
    d = tmp_path / "work"
    d.mkdir()
    return d
