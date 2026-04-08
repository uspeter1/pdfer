import re
import shutil
from datetime import datetime
from pathlib import Path

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Rename output PDFs using a template or explicit names.

    Template tokens (evaluated at run time):
        {original}   original filename stem
        {date}       YYYY-MM-DD
        {time}       HH-MM-SS
        {datetime}   YYYY-MM-DD_HH-MM-SS
        {index}      1-based counter across PDFs in this batch

    params:
        template  str   name template, e.g. "invoice_{date}"
        ask       bool  if True the backend pauses for user input before calling run()
        names     list  explicit names per PDF (supplied after user input in ask mode)
    """
    template = str(params.get('template', '{original}'))
    names    = params.get('names') or []   # one per PDF, provided in ask/resume mode

    pdf_idx = 0
    outputs = []

    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        if pdf_idx < len(names):
            raw = str(names[pdf_idx])
        else:
            raw = _eval_template(template, f, pdf_idx)

        safe = _sanitize(raw) or f.stem
        out  = work_dir / f"{safe}.pdf"

        # Avoid collisions
        stem, n = out.stem, 1
        while out.exists():
            out = work_dir / f"{stem}_{n}.pdf"
            n  += 1

        shutil.copy2(f, out)
        outputs.append(out)
        pdf_idx += 1

    return outputs


def eval_template_for_preview(template: str, stem: str, index: int) -> str:
    """Public helper used by the /api/run pause response to pre-fill UI inputs."""
    class _FakeFile:
        pass
    f = _FakeFile()
    f.stem = stem  # type: ignore[attr-defined]
    return _eval_template(template, f, index)  # type: ignore[arg-type]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _eval_template(template: str, f, index: int) -> str:
    now = datetime.now()
    t   = template
    t   = t.replace('{original}',  f.stem)
    t   = t.replace('{date}',      now.strftime('%Y-%m-%d'))
    t   = t.replace('{time}',      now.strftime('%H-%M-%S'))
    t   = t.replace('{datetime}',  now.strftime('%Y-%m-%d_%H-%M-%S'))
    t   = t.replace('{index}',     str(index + 1))
    return t


def _sanitize(name: str) -> str:
    name = _UNSAFE.sub('-', name)
    name = name.strip('. ')
    return name[:200]
