import datetime
from pathlib import Path

import fitz


def _resolve(template: str, page_num: int, total: int) -> str:
    today = datetime.date.today()
    return (template
            .replace('{page}',  str(page_num))
            .replace('{total}', str(total))
            .replace('{date}',  today.strftime('%Y-%m-%d'))
            .replace('{datetime}', datetime.datetime.now().strftime('%Y-%m-%d %H:%M')))


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Stamp header and/or footer text on every page."""
    header_tpl  = str(params.get('header_text', '') or '').strip()
    footer_tpl  = str(params.get('footer_text', '{page} / {total}') or '').strip()
    font_size   = max(6, min(72, float(params.get('font_size', 10) or 10)))
    margin      = max(4, float(params.get('margin', 20) or 20))

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        out = work_dir / f'{f.stem}_headerfooter.pdf'
        with fitz.open(str(f)) as doc:
            total = len(doc)
            for i, page in enumerate(doc):
                w = page.rect.width

                if header_tpl:
                    text = _resolve(header_tpl, i + 1, total)
                    tw   = fitz.get_text_length(text, fontsize=font_size)
                    x    = (w - tw) / 2
                    y    = margin
                    page.insert_text((x, y), text, fontsize=font_size, color=(0, 0, 0))

                if footer_tpl:
                    text = _resolve(footer_tpl, i + 1, total)
                    tw   = fitz.get_text_length(text, fontsize=font_size)
                    x    = (w - tw) / 2
                    y    = page.rect.height - margin
                    page.insert_text((x, y), text, fontsize=font_size, color=(0, 0, 0))

            doc.save(str(out), deflate=True)

        outputs.append(out)

    return outputs
