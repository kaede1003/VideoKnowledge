"""Portable browser lookup and ignored test output, not a product dependency."""
from __future__ import annotations
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def browser_executable() -> str | None:
    override = os.getenv('VKN_CHROMIUM', '').strip()
    if override:
        if override.lower() == 'playwright':
            return None
        target = Path(override)
        if not target.is_file():
            raise FileNotFoundError('VKN_CHROMIUM does not point to a browser executable')
        return str(target)
    # Use a local Chromium on the current machine, or Playwright's installed binary.
    return shutil.which('chromium') or shutil.which('chromium-browser')

def screenshot_path(filename: str) -> Path:
    if Path(filename).name != filename:
        raise ValueError('Expected screenshot basename')
    out = ROOT / 'artifacts' / 'browser'
    out.mkdir(parents=True, exist_ok=True)
    return out / filename
