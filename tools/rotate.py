from pathlib import Path
import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Rotate PDF pages by a specified angle."""
    angle     = int(params.get('angle', 90))
    pages_str = str(params.get('pages', 'all')).strip()

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)  # pass non-PDFs through to the next step
            continue
        out = work_dir / f"{f.stem}_rotated.pdf"
        with fitz.open(str(f)) as doc:
            indices = _parse_pages(pages_str, len(doc))
            for i in indices:
                page = doc[i]
                page.set_rotation((page.rotation + angle) % 360)
            doc.save(str(out))
        outputs.append(out)
    return outputs


def _parse_pages(s: str, total: int) -> list:
    if s.lower() == 'all':
        return list(range(total))
    indices = set()
    for part in s.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            indices.update(range(int(a) - 1, int(b)))
        elif part.isdigit():
            indices.add(int(part) - 1)
    return sorted(i for i in indices if 0 <= i < total)
