"""Compatibility entry point. V0.5.1 replaces the old layout-only test."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name('browser_ai_v051.py')),run_name='__main__')
