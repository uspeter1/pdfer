import zipfile
from pathlib import Path

import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Render each PDF page to PNG or JPEG and bundle into a ZIP."""
    fmt     = str(params.get('format', 'PNG')).upper()
    dpi     = max(72, min(600, int(params.get('dpi', 150) or 150)))
    quality = max(1,  min(100, int(params.get('quality', 85) or 85)))
    ext     = 'jpg' if fmt == 'JPEG' else 'png'

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        with fitz.open(str(f)) as doc:
            total = len(doc)
            pad   = len(str(total))

            zip_path = work_dir / f'{f.stem}_images.zip'
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, page in enumerate(doc):
                    pix  = page.get_pixmap(dpi=dpi, alpha=False)
                    name = f'{f.stem}_p{str(i+1).zfill(pad)}.{ext}'
                    if fmt == 'JPEG':
                        img_bytes = pix.tobytes('jpeg', jpg_quality=quality)
                    else:
                        img_bytes = pix.tobytes('png')
                    zf.writestr(name, img_bytes)

            outputs.append(zip_path)

    return outputs
