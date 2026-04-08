from pathlib import Path
import fitz


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Split each PDF into groups of pages.

    params:
        groups  list  Preferred — list of lists of 0-based global page indices
                      provided by the interactive UI.  Each inner list becomes
                      one output PDF.
        ranges  str   Fallback — comma-separated page ranges, e.g. "1-3, 4-6, 7-"
        every   int   Fallback — split every N pages
    """
    groups_param = params.get('groups')

    outputs = []
    for f in input_files:
        if f.suffix.lower() != '.pdf':
            outputs.append(f)
            continue

        with fitz.open(str(f)) as doc:
            total = len(doc)

            if groups_param:
                # ── Interactive mode: user-defined groups ──────────────────
                for g_idx, page_indices in enumerate(groups_param, 1):
                    valid = [int(p) for p in page_indices if 0 <= int(p) < total]
                    if not valid:
                        continue
                    out     = work_dir / f"{f.stem}_group{g_idx}.pdf"
                    out_doc = fitz.open()
                    for p in valid:
                        out_doc.insert_pdf(doc, from_page=p, to_page=p)
                    out_doc.save(str(out), deflate=True)
                    out_doc.close()
                    outputs.append(out)

            else:
                # ── Range / every-N fallback ───────────────────────────────
                ranges_str = str(params.get('ranges', '')).strip()
                every      = int(params.get('every') or 0)
                page_groups = _parse_groups(ranges_str, every, total)

                pad = len(str(len(page_groups)))
                for idx, (start, end) in enumerate(page_groups, 1):
                    label = f"p{str(start+1).zfill(len(str(total)))}"
                    if end > start:
                        label += f"-{str(end+1).zfill(len(str(total)))}"
                    out     = work_dir / f"{f.stem}_{str(idx).zfill(pad)}_{label}.pdf"
                    out_doc = fitz.open()
                    out_doc.insert_pdf(doc, from_page=start, to_page=end)
                    out_doc.save(str(out), deflate=True)
                    out_doc.close()
                    outputs.append(out)

    return outputs


def _parse_groups(ranges_str: str, every: int, total: int) -> list:
    """Return list of (start, end) 0-based inclusive page index tuples."""
    if ranges_str:
        groups = []
        for part in ranges_str.split(','):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                lo, _, hi = part.partition('-')
                lo = int(lo.strip()) - 1 if lo.strip() else 0
                hi = int(hi.strip()) - 1 if hi.strip() else total - 1
            else:
                lo = hi = int(part) - 1
            lo = max(0, min(lo, total - 1))
            hi = max(lo, min(hi, total - 1))
            groups.append((lo, hi))
        return groups or [(0, total - 1)]

    if every and every > 0:
        return [(s, min(s + every - 1, total - 1)) for s in range(0, total, every)]

    # Default: one page per file
    return [(i, i) for i in range(total)]
