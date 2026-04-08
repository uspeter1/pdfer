from pathlib import Path
import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Stamp a diagonal text watermark on every page.

    PyMuPDF's insert_text only accepts rotate in {0,90,180,270}.
    We use the `morph` parameter instead to get a true 45° diagonal.
    """
    text      = str(params.get('text', 'CONFIDENTIAL'))
    font_size = float(params.get('font_size', 52))
    hex_color = str(params.get('color', '#aaaaaa')).lstrip('#')
    try:
        color = tuple(int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        color = (0.67, 0.67, 0.67)

    # 45-degree rotation matrix
    rot45 = fitz.Matrix(45)

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue
        out = work_dir / f"{f.stem}_watermarked.pdf"
        with fitz.open(str(f)) as doc:
            for page in doc:
                r  = page.rect
                cx = r.width  / 2
                cy = r.height / 2

                # Estimate text half-width to pre-center before rotation
                half_w = font_size * 0.3 * len(text)
                x = cx - half_w
                y = cy + font_size * 0.35   # baseline sits a bit above center

                # morph rotates the rendered text 45° around the page center
                page.insert_text(
                    fitz.Point(x, y),
                    text,
                    fontsize=font_size,
                    fontname='helv',
                    color=color,
                    morph=(fitz.Point(cx, cy), rot45),
                )
            doc.save(str(out))
        outputs.append(out)
    return outputs
