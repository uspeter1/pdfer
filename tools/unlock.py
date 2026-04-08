from pathlib import Path


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Remove password protection from PDFs."""
    try:
        import pikepdf
    except ImportError:
        raise RuntimeError('pikepdf is not installed. Run: pip install pikepdf')

    password = str(params.get('password', '') or '')

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue
        out = work_dir / f'{f.stem}_unlocked.pdf'
        try:
            with pikepdf.open(str(f), password=password) as pdf:
                pdf.save(str(out))
        except pikepdf.PasswordError:
            raise ValueError(
                f'Incorrect password for "{f.name}". Please check and try again.'
            )
        outputs.append(out)

    return outputs
