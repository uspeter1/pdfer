from pathlib import Path


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Encrypt PDFs with user and/or owner passwords."""
    try:
        import pikepdf
    except ImportError:
        raise RuntimeError('pikepdf is not installed. Run: pip install pikepdf')

    user_pw  = str(params.get('user_password',  '') or '')
    owner_pw = str(params.get('owner_password', '') or '')
    allow_print  = bool(params.get('allow_print',  True))
    allow_copy   = bool(params.get('allow_copy',   True))
    allow_modify = bool(params.get('allow_modify', False))

    if not user_pw and not owner_pw:
        raise ValueError('At least one password (user or owner) must be set.')

    # pikepdf requires an owner password; default to user password if omitted
    if not owner_pw:
        owner_pw = user_pw

    permissions = pikepdf.Permissions(
        print_lowres=allow_print,
        print_highres=allow_print,
        extract=allow_copy,
        modify_annotation=allow_modify,
        modify_assembly=allow_modify,
        modify_form=allow_modify,
        modify_other=allow_modify,
        accessibility=True,
    )

    enc = pikepdf.Encryption(
        user=user_pw,
        owner=owner_pw,
        allow=permissions,
    )

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue
        out = work_dir / f'{f.stem}_protected.pdf'
        with pikepdf.open(str(f)) as pdf:
            pdf.save(str(out), encryption=enc)
        outputs.append(out)

    return outputs
