from pathlib import Path

import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Flatten PDF by rendering each page to an image, removing annotations/forms."""
    dpi = max(72, min(600, int(params.get('dpi', 150) or 150)))

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        out     = work_dir / f'{f.stem}_flat.pdf'
        out_doc = fitz.open()

        with fitz.open(str(f)) as doc:
            for page in doc:
                pix      = page.get_pixmap(dpi=dpi, alpha=False)
                new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
                new_page.insert_image(new_page.rect, pixmap=pix)

        out_doc.save(str(out), deflate=True)
        out_doc.close()
        outputs.append(out)

    return outputs
