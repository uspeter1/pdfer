import zipfile
from pathlib import Path

import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Extract all embedded images from each PDF and bundle into a ZIP."""
    outputs = []

    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        zip_path = work_dir / f'{f.stem}_images.zip'
        count = 0

        with fitz.open(str(f)) as doc:
            seen_xrefs: set = set()
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for page_num, page in enumerate(doc):
                    for img_info in page.get_images(full=True):
                        xref = img_info[0]
                        if xref in seen_xrefs:
                            continue
                        seen_xrefs.add(xref)

                        try:
                            base_img = doc.extract_image(xref)
                        except Exception:
                            continue

                        ext       = base_img.get('ext', 'png')
                        img_bytes = base_img.get('image', b'')
                        if not img_bytes:
                            continue

                        count += 1
                        name = f'p{page_num+1:03d}_img{count:03d}.{ext}'
                        zf.writestr(name, img_bytes)

        if count == 0:
            zip_path.unlink(missing_ok=True)
            raise ValueError(f'No embedded images found in "{f.name}".')

        outputs.append(zip_path)

    return outputs
