from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "_check_dashboard_design_tokens",
        _REPO_ROOT / "scripts" / "check_dashboard_design_tokens.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dashboard_design_tokens_are_enforced() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_dashboard_design_tokens.py", "--json"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_raw_hex_inside_svg_is_exempt_but_body_hex_is_flagged() -> None:
    checker = _load_checker()
    # Brand/icon SVG hex is an asset, not themeable styling → exempt.
    svg_line = '<svg viewBox="0 0 1 1"><path fill="#D77655" d="M0 0z"/></svg>'
    # Body styling hex must still be flagged.
    body_line = "const accent = '#abcdef';"

    svg_codes = {code for code, _line, _text in checker.scan_text(svg_line)}
    body_codes = {code for code, _line, _text in checker.scan_text(body_line)}

    assert "raw_hex_color" not in svg_codes
    assert "raw_hex_color" in body_codes
    # A real-styling hex on the SAME line as an SVG block stays flagged (the
    # exemption is scoped to the <svg>...</svg> span, not the whole line).
    mixed = svg_line + " color:#123456;"
    assert "raw_hex_color" in {code for code, _l, _t in checker.scan_text(mixed)}
