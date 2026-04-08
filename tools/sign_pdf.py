import base64
import datetime
from pathlib import Path

import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Stamp one or more signatures on PDF pages.

    params.signatures: list of {
        page   int     0-based page index
        fx,fy  float   top-left corner as fraction of page width/height
        fw,fh  float   width/height as fraction
        type   str     'drawn' | 'text'
        data   str     base64 PNG data URL (drawn) or signature string (text)
        color  str     hex color e.g. '#1a1a2e'
    }
    """
    signatures = params.get('signatures') or []

    # Legacy single-placement fallback
    if not signatures:
        sig_text  = str(params.get('signature_text', '') or '').strip()
        placement = params.get('placement') or {}
        if sig_text:
            signatures = [{
                'page': int(placement.get('page', 0)),
                'fx':   float(placement.get('fx', 0.55)),
                'fy':   float(placement.get('fy', 0.85)),
                'fw':   float(placement.get('fw', 0.35)),
                'fh':   float(placement.get('fh', 0.07)),
                'type': 'text',
                'data': sig_text,
                'color': str(params.get('color', '#1a1a2e')),
            }]

    if not signatures:
        raise ValueError('No signatures provided.')

    today = datetime.date.today().strftime('%Y-%m-%d')

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        out = work_dir / f'{f.stem}_signed.pdf'
        with fitz.open(str(f)) as doc:
            for sig in signatures:
                page_idx = min(int(sig.get('page', 0)), len(doc) - 1)
                page     = doc[page_idx]
                pw, ph   = page.rect.width, page.rect.height

                fx = float(sig.get('fx', 0.55))
                fy = float(sig.get('fy', 0.82))
                fw = float(sig.get('fw', 0.28))
                fh = float(sig.get('fh', 0.08))

                x0 = pw * fx
                y0 = ph * fy
                x1 = pw * (fx + fw)
                y1 = ph * (fy + fh)
                rect = fitz.Rect(x0, y0, x1, y1)

                color_hex = str(sig.get('color', '#1a1a2e') or '#1a1a2e').lstrip('#')
                try:
                    r = int(color_hex[0:2], 16) / 255
                    g = int(color_hex[2:4], 16) / 255
                    b = int(color_hex[4:6], 16) / 255
                except Exception:
                    r, g, b = 0.1, 0.1, 0.18

                sig_type = str(sig.get('type', 'text'))

                if sig_type == 'drawn':
                    raw = str(sig.get('data', ''))
                    if ',' in raw:
                        raw = raw.split(',', 1)[1]
                    img_bytes = base64.b64decode(raw)
                    page.insert_image(rect, stream=img_bytes, keep_proportion=True)
                    # Date below the image
                    date_size = max(6, ph * fh * 0.28)
                    page.insert_text(
                        (x0, y1 + date_size + 2), today,
                        fontsize=date_size, color=(r, g, b),
                    )

                else:  # text
                    sig_text = str(sig.get('data', '') or '').strip()
                    display  = f'{sig_text}  ·  {today}'
                    font_size = max(6, min(ph * fh * 0.60, 48))
                    tw    = fitz.get_text_length(display, fontsize=font_size)
                    bw    = pw * fw
                    # center text horizontally, sit on baseline at 72% of box height
                    tx = x0 + max(0, (bw - tw) / 2)
                    ty = y0 + ph * fh * 0.72
                    page.draw_line((x0, y1), (x1, y1), color=(r, g, b), width=0.8)
                    page.insert_text((tx, ty), display, fontsize=font_size, color=(r, g, b))

            doc.save(str(out), deflate=True)

        outputs.append(out)

    return outputs
