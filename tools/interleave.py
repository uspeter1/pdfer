from pathlib import Path

import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Interleave pages from exactly two PDFs (double-sided scan fix).

    Expects 2 PDF files:
      file A = odd pages  (1, 3, 5, …) in forward order
      file B = even pages (2, 4, 6, …) typically scanned bottom-to-top

    params:
      reverse_second  bool  Whether to reverse the order of file B (default True)
    """
    pdfs = [f for f in input_files if f.suffix.lower() == '.pdf']
    non_pdfs = [f for f in input_files if f.suffix.lower() != '.pdf']

    if len(pdfs) != 2:
        raise ValueError(
            f'Interleave requires exactly 2 PDF files, got {len(pdfs)}.'
        )

    reverse_second = bool(params.get('reverse_second', True))

    doc_a = fitz.open(str(pdfs[0]))
    doc_b = fitz.open(str(pdfs[1]))

    pages_a = list(range(len(doc_a)))
    pages_b = list(range(len(doc_b)))
    if reverse_second:
        pages_b = list(reversed(pages_b))

    out_doc = fitz.open()
    a_idx, b_idx = 0, 0
    while a_idx < len(pages_a) or b_idx < len(pages_b):
        if a_idx < len(pages_a):
            out_doc.insert_pdf(doc_a, from_page=pages_a[a_idx], to_page=pages_a[a_idx])
            a_idx += 1
        if b_idx < len(pages_b):
            out_doc.insert_pdf(doc_b, from_page=pages_b[b_idx], to_page=pages_b[b_idx])
            b_idx += 1

    out = work_dir / f'{pdfs[0].stem}_interleaved.pdf'
    out_doc.save(str(out), deflate=True)
    out_doc.close()
    doc_a.close()
    doc_b.close()

    return non_pdfs + [out]
