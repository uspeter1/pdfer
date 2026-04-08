from pathlib import Path

import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Set PDF metadata fields (title, author, subject, keywords, creator)."""
    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        out = work_dir / f'{f.stem}_meta.pdf'
        with fitz.open(str(f)) as doc:
            existing = doc.metadata or {}
            new_meta = {
                'title':    str(params.get('title',    existing.get('title',    '')) or ''),
                'author':   str(params.get('author',   existing.get('author',   '')) or ''),
                'subject':  str(params.get('subject',  existing.get('subject',  '')) or ''),
                'keywords': str(params.get('keywords', existing.get('keywords', '')) or ''),
                'creator':  str(params.get('creator',  existing.get('creator',  '')) or ''),
            }
            doc.set_metadata(new_meta)
            doc.save(str(out), deflate=True)

        outputs.append(out)

    return outputs


def read_metadata(path: Path) -> dict:
    """Return current metadata dict for a single PDF file."""
    try:
        with fitz.open(str(path)) as doc:
            m = doc.metadata or {}
            return {
                'title':    m.get('title',    ''),
                'author':   m.get('author',   ''),
                'subject':  m.get('subject',  ''),
                'keywords': m.get('keywords', ''),
                'creator':  m.get('creator',  ''),
            }
    except Exception:
        return {}
