import base64
from pathlib import Path

import fitz


def _size_to_heading(size: float) -> int | None:
    """Return heading level (1-3) based on font size, or None for body text."""
    if size >= 20:
        return 1
    if size >= 15:
        return 2
    if size >= 13:
        return 3
    return None


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Convert each PDF to a Markdown (.md) file with embedded images."""
    outputs = []

    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        md_parts = []

        with fitz.open(str(f)) as doc:
            for page_num, page in enumerate(doc):
                # TEXT_PRESERVE_IMAGES includes inline raster images in the block dict
                flags  = fitz.TEXT_PRESERVE_IMAGES | fitz.TEXT_PRESERVE_WHITESPACE
                blocks = page.get_text('dict', flags=flags)['blocks']

                # Sort top-to-bottom, left-to-right (coarse row buckets)
                for block in sorted(blocks, key=lambda b: (round(b['bbox'][1] / 12), b['bbox'][0])):
                    btype = block['type']

                    if btype == 1:  # raster image block
                        img_bytes = block.get('image')
                        if img_bytes:
                            ext  = block.get('ext', 'png').lower()
                            mime = 'jpeg' if ext in ('jpg', 'jpeg') else ext
                            b64  = base64.b64encode(img_bytes).decode()
                            md_parts.append(f'\n![image](data:image/{mime};base64,{b64})\n')

                    elif btype == 0:  # text block
                        for line in block.get('lines', []):
                            spans = line.get('spans', [])
                            text  = ' '.join(s['text'] for s in spans).strip()
                            if not text:
                                continue
                            max_size = max((s['size'] for s in spans), default=11)
                            level = _size_to_heading(max_size)
                            if level:
                                md_parts.append(f'\n{"#" * level} {text}\n')
                            else:
                                md_parts.append(text)

                # Page separator (except after last page)
                if page_num < len(doc) - 1:
                    md_parts.append('\n\n---\n')

        out = work_dir / f'{f.stem}.md'
        out.write_text('\n'.join(md_parts), encoding='utf-8')
        outputs.append(out)

    return outputs
