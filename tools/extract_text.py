from pathlib import Path

import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Extract all text from each PDF and save as a .txt file."""
    include_page_numbers = bool(params.get('include_page_numbers', True))

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        out = work_dir / f'{f.stem}.txt'
        with fitz.open(str(f)) as doc:
            lines = []
            for i, page in enumerate(doc):
                if include_page_numbers:
                    lines.append(f'--- Page {i + 1} ---')
                text = page.get_text('text').strip()
                if text:
                    lines.append(text)
                elif include_page_numbers:
                    lines.append('[No text on this page]')
                lines.append('')
            out.write_text('\n'.join(lines), encoding='utf-8')

        outputs.append(out)

    return outputs
