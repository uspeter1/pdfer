import re
from pathlib import Path
from urllib.parse import urlparse


def run(input_files: list, params: dict, work_dir: Path) -> list:
    """Render a URL to PDF using a headless Chromium browser."""
    url = str(params.get('url', '') or '').strip()

    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(
            f'Invalid URL {url!r}. Must start with http:// or https://'
        )

    wait_until  = str(params.get('wait_until', 'networkidle'))
    page_format = str(params.get('page_format', 'A4'))

    if wait_until not in ('load', 'domcontentloaded', 'networkidle', 'commit'):
        wait_until = 'networkidle'
    if page_format not in ('A4', 'Letter'):
        page_format = 'A4'

    from playwright.sync_api import sync_playwright

    stem = re.sub(r'[^a-zA-Z0-9_-]', '_', parsed.netloc + parsed.path).strip('_')[:60] or 'webpage'
    out  = work_dir / f'{stem}.pdf'

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page    = browser.new_page()
        page.goto(url, wait_until=wait_until, timeout=30_000)
        page.pdf(path=str(out), format=page_format, print_background=True)
        browser.close()

    return list(input_files) + [out]
