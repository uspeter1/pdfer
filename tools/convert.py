import shutil
import subprocess
from pathlib import Path

from PIL import Image

IMAGE_EXTS  = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp'}
OFFICE_EXTS = {'.pptx', '.ppt', '.docx', '.doc', '.xlsx', '.xls', '.odp', '.odt', '.ods'}


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Convert images and Office documents to PDF."""
    outputs = []
    for f in input_files:
        ext = f.suffix.lower()
        out = work_dir / f"{f.stem}.pdf"
        if ext == '.pdf':
            shutil.copy(f, out)
        elif ext in IMAGE_EXTS:
            _image_to_pdf(f, out)
        elif ext in OFFICE_EXTS:
            _office_to_pdf(f, out, work_dir)
        else:
            raise ValueError(f"Unsupported format for conversion: {ext}")
        outputs.append(out)
    return outputs


def _image_to_pdf(src: Path, dst: Path):
    img = Image.open(str(src))
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    img.save(str(dst), 'PDF', resolution=150.0)


def _office_to_pdf(src: Path, dst: Path, work_dir: Path):
    lo = shutil.which('libreoffice') or shutil.which('soffice')
    if not lo:
        raise RuntimeError(
            "LibreOffice is required to convert Office files. "
            "Install it with: sudo apt install libreoffice"
        )
    result = subprocess.run(
        [lo, '--headless', '--convert-to', 'pdf', '--outdir', str(work_dir), str(src)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice failed:\n{result.stderr}")
    expected = work_dir / f"{src.stem}.pdf"
    if not expected.exists():
        raise RuntimeError(f"Converted file not found: {expected}")
    if expected != dst:
        expected.rename(dst)
