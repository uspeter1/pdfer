from pathlib import Path
import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Add page numbers to each page of a PDF."""
    position  = str(params.get('position', 'bottom-center'))
    start_num = int(params.get('start', 1))
    font_size = float(params.get('font_size', 11))
    prefix    = str(params.get('prefix', ''))

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue
        out = work_dir / f"{f.stem}_numbered.pdf"
        with fitz.open(str(f)) as doc:
            for i, page in enumerate(doc):
                text = f"{prefix}{i + start_num}"
                r    = page.rect
                mg   = 24

                if 'bottom' in position:
                    y0, y1 = r.height - mg - font_size * 2.2, r.height - mg
                else:
                    y0, y1 = mg, mg + font_size * 2.2

                if 'left' in position:
                    x0, x1, align = mg, r.width * 0.4, 0
                elif 'right' in position:
                    x0, x1, align = r.width * 0.6, r.width - mg, 2
                else:
                    x0, x1, align = 0, r.width, 1

                page.insert_textbox(
                    fitz.Rect(x0, y0, x1, y1),
                    text,
                    fontsize=font_size,
                    fontname='helv',
                    color=(0, 0, 0),
                    align=align,
                )
            doc.save(str(out))
        outputs.append(out)
    return outputs
