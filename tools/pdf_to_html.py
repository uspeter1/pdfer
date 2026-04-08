import base64
import html as html_mod
from pathlib import Path


_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #f5f4f0;
    font-family: Georgia, 'Times New Roman', serif;
    color: #1a1a1a;
    line-height: 1.75;
    padding: 40px 16px 80px;
  }
  .doc-wrap {
    max-width: 820px;
    margin: 0 auto;
    background: #fff;
    padding: 60px 72px;
    box-shadow: 0 4px 24px rgba(0,0,0,.10);
    border-radius: 3px;
  }
  h1.doc-title {
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -.02em;
    margin-bottom: 48px;
    padding-bottom: 16px;
    border-bottom: 2px solid #1a1a1a;
    color: #111;
  }
  .page-section { margin-bottom: 40px; }
  .page-image { display: block; max-width: 100%; margin: 20px 0; border-radius: 2px; }
  .page-text p { margin-bottom: 10px; }
  @media (max-width: 600px) { .doc-wrap { padding: 32px 20px; } }
  @media print { body { background: white; padding: 0; } .doc-wrap { box-shadow: none; } }
"""


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Convert each PDF to a self-contained single-page HTML file."""
    import fitz

    include_images = bool(params.get('include_images', True))
    image_dpi      = max(72, min(300, int(params.get('image_dpi', 120) or 120)))

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        out = work_dir / f'{f.stem}.html'

        sections = []
        with fitz.open(str(f)) as doc:
            title = (doc.metadata or {}).get('title', '') or f.stem

            for i, page in enumerate(doc):
                text_blocks = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']
                text_paras = []
                for block in text_blocks:
                    if block['type'] != 0:
                        continue
                    for line in block.get('lines', []):
                        t = ' '.join(s['text'] for s in line.get('spans', [])).strip()
                        if t:
                            text_paras.append(f'<p>{html_mod.escape(t)}</p>')

                text_html = '\n'.join(text_paras) if text_paras else ''

                img_html = ''
                if include_images:
                    mat = fitz.Matrix(image_dpi / 72, image_dpi / 72)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    b64 = base64.b64encode(pix.tobytes('png')).decode()
                    img_html = f'<img class="page-image" src="data:image/png;base64,{b64}" alt="Page {i+1}">'

                sections.append(f"""
    <div class="page-section">
      {img_html}
      <div class="page-text">{text_html}</div>
    </div>""")

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html_mod.escape(title)}</title>
  <style>{_CSS}</style>
</head>
<body>
  <div class="doc-wrap">
    <h1 class="doc-title">{html_mod.escape(title)}</h1>
{''.join(sections)}
  </div>
</body>
</html>"""

        out.write_text(html_content, encoding='utf-8')
        outputs.append(out)

    return outputs
