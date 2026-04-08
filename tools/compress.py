import shutil
import subprocess
import tempfile
from pathlib import Path


# Ghostscript PDFSETTINGS presets, ordered from gentlest to most aggressive
_GS_PRESETS = {
    'light':      ['/printer', '/ebook', '/screen'],
    'medium':     ['/ebook', '/screen'],
    'aggressive': ['/screen'],
}


def _gs_compress(src: Path, dst: Path, level: str) -> bool:
    """Try Ghostscript compression with fallback presets. Returns True on success."""
    gs = shutil.which('gs') or shutil.which('gswin64c') or shutil.which('gswin32c')
    if not gs:
        return False

    presets = _GS_PRESETS.get(level, ['/ebook', '/screen'])
    src_size = src.stat().st_size
    best_size = src_size
    best_dst = None

    with tempfile.TemporaryDirectory() as td:
        for preset in presets:
            candidate = Path(td) / f'{preset.lstrip("/")}.pdf'
            try:
                result = subprocess.run(
                    [
                        gs, '-q', '-dNOPAUSE', '-dBATCH', '-dSAFER',
                        '-sDEVICE=pdfwrite',
                        f'-dPDFSETTINGS={preset}',
                        '-dCompatibilityLevel=1.4',
                        f'-sOutputFile={candidate}',
                        str(src),
                    ],
                    capture_output=True, timeout=120,
                )
            except Exception:
                continue

            if result.returncode == 0 and candidate.exists():
                sz = candidate.stat().st_size
                if sz > 0 and sz < best_size:
                    best_size = sz
                    best_dst = candidate

        if best_dst is not None:
            shutil.copy2(str(best_dst), str(dst))
            return True

    return False


def _pikepdf_compress(src: Path, dst: Path, level: str) -> bool:
    """Re-encode images with pikepdf + Pillow. Returns True on success."""
    try:
        import pikepdf
        from PIL import Image
        import io

        quality = {'light': 85, 'medium': 72, 'aggressive': 55}.get(level, 72)

        with pikepdf.open(str(src)) as pdf:
            for page in pdf.pages:
                if '/Resources' not in page:
                    continue
                resources = page['/Resources']
                if '/XObject' not in resources:
                    continue
                for key, obj in resources['/XObject'].items():
                    try:
                        xobj = obj.get_object()
                        if xobj.get('/Subtype') != '/Image':
                            continue
                        # Only re-encode if not already highly compressed JPEG
                        if xobj.get('/Filter') == '/DCTDecode':
                            continue
                        w = int(xobj['/Width'])
                        h = int(xobj['/Height'])
                        cs = xobj.get('/ColorSpace', '/DeviceRGB')
                        raw = bytes(xobj.read_raw_bytes())
                        # Determine PIL mode
                        mode = 'RGB' if cs == '/DeviceRGB' else 'L'
                        img = Image.frombytes(mode, (w, h), raw)
                        buf = io.BytesIO()
                        img.save(buf, format='JPEG', quality=quality, optimize=True)
                        buf.seek(0)
                        xobj.write(buf.read(), filter=pikepdf.Name('/DCTDecode'))
                    except Exception:
                        continue

            pdf.save(str(dst), compress_streams=True)

        if dst.exists() and dst.stat().st_size > 0:
            if dst.stat().st_size < src.stat().st_size:
                return True
            dst.unlink(missing_ok=True)
    except Exception:
        pass
    return False


def _fitz_compress(src: Path, dst: Path) -> None:
    """Fallback: fitz garbage collection + deflate."""
    import fitz
    with fitz.open(str(src)) as doc:
        doc.save(
            str(dst),
            garbage=4,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            clean=True,
        )


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Compress PDFs using Ghostscript (primary) with fallbacks."""
    level = str(params.get('level', 'medium')).lower()
    if level not in _GS_PRESETS:
        level = 'medium'

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        out = work_dir / f'{f.stem}_compressed.pdf'

        # 1. Try Ghostscript
        if _gs_compress(f, out, level):
            outputs.append(out)
            continue

        # 2. Try pikepdf image re-encoding
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False, dir=work_dir) as tmp:
            tmp_path = Path(tmp.name)

        if _pikepdf_compress(f, tmp_path, level):
            tmp_path.rename(out)
            outputs.append(out)
            continue
        else:
            tmp_path.unlink(missing_ok=True)

        # 3. Fitz fallback
        _fitz_compress(f, out)
        outputs.append(out)

    return outputs
