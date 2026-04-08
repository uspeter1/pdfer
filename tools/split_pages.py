from pathlib import Path
import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Explode each PDF into one file per page."""
    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue
        stem = f.stem
        with fitz.open(str(f)) as doc:
            total = len(doc)
            pad = len(str(total))
            for i in range(total):
                out = work_dir / f"{stem}_p{str(i + 1).zfill(pad)}.pdf"
                page_doc = fitz.open()
                page_doc.insert_pdf(doc, from_page=i, to_page=i)
                page_doc.save(str(out))
                page_doc.close()
                outputs.append(out)
    return outputs
