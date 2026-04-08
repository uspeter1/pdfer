from pathlib import Path
import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Re-order (and optionally filter) pages across one or more PDFs.

    params['order'] is a list of zero-based *global* page indices that
    define the desired output sequence.  The global index space is built
    by flattening every PDF input in order:

        [pdf1-p0, pdf1-p1, …, pdf2-p0, pdf2-p1, …]

    Non-PDF files are passed through unchanged (they appear at the end
    of the output list, after the reorganised PDF).
    """
    order      = params.get('order', None)
    passthrough = [f for f in input_files if f.suffix.lower() != '.pdf']
    pdf_files   = [f for f in input_files if f.suffix.lower() == '.pdf']

    if not pdf_files:
        return list(input_files)

    # Build flat page list: list of (doc, page_index)
    open_docs: list = []
    flat_pages: list = []

    for f in pdf_files:
        doc = fitz.open(str(f))
        open_docs.append(doc)
        for i in range(len(doc)):
            flat_pages.append((doc, i))

    total = len(flat_pages)

    # Default: preserve original order
    if order is None or len(order) == 0:
        order = list(range(total))

    # Clamp / filter bad indices
    order = [int(i) for i in order if isinstance(i, (int, float)) and 0 <= int(i) < total]
    if not order:
        order = list(range(total))

    out     = work_dir / 'organized.pdf'
    out_doc = fitz.open()

    for idx in order:
        src_doc, page_idx = flat_pages[idx]
        out_doc.insert_pdf(src_doc, from_page=page_idx, to_page=page_idx)

    out_doc.save(str(out), deflate=True, garbage=3)
    out_doc.close()

    for doc in open_docs:
        doc.close()

    return [out] + passthrough
