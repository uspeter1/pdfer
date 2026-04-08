from pathlib import Path
import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Merge multiple PDFs into one document."""
    pdf_files = [f for f in input_files if f.suffix.lower() == '.pdf']
    if not pdf_files:
        raise ValueError("Merge requires at least one PDF file.")

    output_path = work_dir / "merged.pdf"
    doc = fitz.open()
    for f in pdf_files:
        with fitz.open(str(f)) as src:
            doc.insert_pdf(src)
    doc.save(str(output_path), deflate=True, garbage=3)
    doc.close()
    return [output_path]
