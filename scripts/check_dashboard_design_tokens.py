#!/usr/bin/env python3
"""Reject dashboard styling that bypasses the Builder design-system tokens."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (REPO_ROOT / "frontend" / "src",)
PACKAGE_FILES = (
    REPO_ROOT / "frontend" / "package.json",
    REPO_ROOT / "frontend" / "package-lock.json",
)
TEXT_EXTENSIONS = {".css", ".js", ".jsx", ".json", ".ts", ".tsx"}

FORBIDDEN_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "raw_hex_color",
        "use CSS variables or semantic Tailwind tokens instead of raw hex colors",
        re.compile(r"(?<![\w-])#[0-9a-fA-F]{3,8}\b"),
    ),
    (
        "rgba_color",
        "use CSS variables or shared shadow tokens instead of rgba() literals",
        re.compile(r"rgba\s*\("),
    ),
    (
        "legacy_tailwind_palette",
        "use Builder semantic tokens instead of one-off Tailwind palette colors",
        re.compile(r"\b(?:amber|rose|sky|slate)-\d{2,3}\b"),
    ),
    (
        "shadcn_css_import",
        "remove shadcn CSS imports; Builder tokens own dashboard styling",
        re.compile(r"shadcn/tailwind\.css"),
    ),
    (
        "radix_luma",
        "remove Luma theme config; Builder tokens own dashboard styling",
        re.compile(r"radix-luma"),
    ),
)


# Brand/icon SVG markup legitimately carries fixed hex in fill/stroke attributes
# (e.g. a provider logo). Those are assets, not themeable UI styling, so the
# raw_hex_color rule is exempted INSIDE <svg>...</svg> spans only. Body styling
# hex (CSS, style props, className) stays flagged everywhere else.
_SVG_BLOCK = re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE)
_HEX_EXEMPT_INSIDE_SVG = frozenset({"raw_hex_color"})


def _svg_spans(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in _SVG_BLOCK.finditer(text)]


def _within_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def iter_text_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix in TEXT_EXTENSIONS)


def issue(path: Path, code: str, message: str, line: int | None = None, text: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": code,
        "path": str(path.relative_to(REPO_ROOT)),
        "message": message,
    }
    if line is not None:
        payload["line"] = line
    if text is not None:
        payload["text"] = text.strip()
    return payload


def scan_text(text: str) -> list[tuple[str, int, str]]:
    """Pure scan: return (code, line_number, line_text) per violation.

    ``raw_hex_color`` matches inside ``<svg>...</svg>`` spans are exempt (brand /
    icon assets); every other rule and location is flagged as before. At most one
    finding per (line, code), preserving the original behavior.
    """
    svg_spans = _svg_spans(text)
    results: list[tuple[str, int, str]] = []
    offset = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        for code, _message, pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(line):
                if code in _HEX_EXEMPT_INSIDE_SVG and _within_spans(offset + match.start(), svg_spans):
                    continue
                results.append((code, line_number, line.rstrip("\n")))
                break
        offset += len(line)
    return results


def scan_file(path: Path) -> list[dict[str, object]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    message_by_code = {code: message for code, message, _ in FORBIDDEN_PATTERNS}
    return [
        issue(path, code, message_by_code[code], line_number, line_text)
        for code, line_number, line_text in scan_text(text)
    ]


def collect_findings() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for root in SCAN_ROOTS:
        for path in iter_text_files(root):
            findings.extend(scan_file(path))

    for package_file in PACKAGE_FILES:
        if package_file.exists():
            findings.extend(scan_file(package_file))

    components_config = REPO_ROOT / "frontend" / "components.json"
    if components_config.exists():
        findings.append(
            issue(
                components_config,
                "shadcn_components_config",
                "remove frontend/components.json; Builder dashboard styling must not reintroduce shadcn/Luma config",
            )
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    args = parser.parse_args()

    findings = collect_findings()
    payload = {
        "ok": not findings,
        "status": "passed" if not findings else "failed",
        "checked_roots": [str(path.relative_to(REPO_ROOT)) for path in SCAN_ROOTS],
        "findings": findings,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    elif findings:
        for finding in findings:
            line = f":{finding['line']}" if "line" in finding else ""
            print(f"{finding['path']}{line}: {finding['code']}: {finding['message']}")
    else:
        print("dashboard design token check passed")

    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
