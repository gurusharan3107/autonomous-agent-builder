#!/usr/bin/env python3
"""Deterministic skill conformance checker.

Usage:
  python3 scripts/audit.py .claude/skills/<name>
  python3 scripts/audit.py --all
  python3 scripts/audit.py .claude/skills/<name> --json
  python3 scripts/audit.py .claude/skills/<name> --strict
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path


CHECKS = [
    ("A00", "skill is project-local (.claude/skills/)", "hard"),
    ("A01", "name frontmatter present",       "hard"),
    ("A02", "name equals directory name",      "hard"),
    ("A03", "name is kebab-case",              "hard"),
    ("A04", "description present",             "hard"),
    ("A05", "description ≤1024 chars",         "soft"),
    ("A06", "SKILL.md body ≤500 lines",        "soft"),
    ("A07", "Hard Rules section present",      "soft"),
    ("A08", "Workflow section present",        "soft"),
    ("A09", "CLOSEOUT step present",           "soft"),
    ("A10", "evals/evals.json present",        "soft"),
    ("A11", "description starts imperative",   "soft"),
    ("A12", "reference/ files have conditions","soft"),
]


def audit_skill(skill_path: Path, strict: bool = False) -> list[dict]:
    findings = []

    def finding(cid: str, label: str, severity: str, passed: bool, detail: str = ""):
        findings.append({"id": cid, "label": label, "severity": severity if not strict else "hard",
                         "passed": passed, "detail": detail})

    # A00 — project-local check (must live under .claude/skills/, not ~/.claude/skills/)
    resolved = skill_path.resolve()
    home_skills = Path.home() / ".claude" / "skills"
    is_global = str(resolved).startswith(str(home_skills.resolve()))
    finding("A00", "skill is project-local (.claude/skills/)", "hard", not is_global,
            "~/.claude/skills/ — move to .claude/skills/" if is_global else str(skill_path))

    if not skill_path.exists():
        findings.append({"id": "E00", "label": "path exists", "severity": "hard",
                         "passed": False, "detail": str(skill_path)})
        return findings

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        findings.append({"id": "E01", "label": "SKILL.md exists", "severity": "hard",
                         "passed": False, "detail": ""})
        return findings

    text = skill_md.read_text()
    lines = text.splitlines()

    # A01 — name present
    name_match = re.search(r'^name:\s*(.+)$', text, re.M)
    finding("A01", "name frontmatter present", "hard", bool(name_match),
            name_match.group(1).strip() if name_match else "missing")

    # A02 — name equals dir
    if name_match:
        fname = name_match.group(1).strip().strip('"\'')
        finding("A02", "name equals directory name", "hard",
                fname == skill_path.name, f"frontmatter={fname!r} dir={skill_path.name!r}")

    # A03 — kebab-case
    if name_match:
        fname = name_match.group(1).strip().strip('"\'')
        ok = bool(re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', fname))
        finding("A03", "name is kebab-case", "hard", ok, fname)

    # A04 — description present
    desc_match = re.search(r'^description:', text, re.M)
    finding("A04", "description present", "hard", bool(desc_match))

    # A05 — description ≤1024
    desc_text = ""
    if desc_match:
        block = re.search(r'^description:\s*[>|]?\s*\n((?:  .+\n)+)', text, re.M)
        if block:
            desc_text = block.group(1).replace("\n", " ").replace("  ", " ").strip()
        else:
            inline = re.search(r'^description:\s*"(.+?)"', text, re.M | re.DOTALL)
            if inline:
                desc_text = inline.group(1).strip()
    finding("A05", "description ≤1024 chars", "soft", len(desc_text) <= 1024,
            f"{len(desc_text)} chars")

    # A06 — body ≤500 lines
    finding("A06", "SKILL.md body ≤500 lines", "soft", len(lines) <= 500,
            f"{len(lines)} lines")

    # A07 — Hard Rules
    finding("A07", "Hard Rules section present", "soft",
            bool(re.search(r'## Hard [Rr]ules', text)))

    # A08 — Workflow
    finding("A08", "Workflow section present", "soft",
            bool(re.search(r'## Workflow', text)))

    # A09 — CLOSEOUT
    finding("A09", "CLOSEOUT step present", "soft", "CLOSEOUT" in text)

    # A10 — evals
    finding("A10", "evals/evals.json present", "soft",
            (skill_path / "evals" / "evals.json").exists())

    # A11 — description starts imperative
    first_word = desc_text.split()[0] if desc_text else ""
    imperative = first_word.rstrip(',').lower() in {
        "use", "analyze", "build", "create", "run", "generate", "produce",
        "scaffold", "automate", "extract", "search", "check", "verify",
    }
    finding("A11", "description starts imperative", "soft", imperative,
            f"starts with {first_word!r}")

    # A12 — reference files have load conditions
    ref_dir = skill_path / "reference"
    if ref_dir.exists():
        ref_files = list(ref_dir.glob("*.md"))
        if ref_files:
            conditions_ok = all(
                f"reference/{rf.name}" in text
                for rf in ref_files
            )
            finding("A12", "reference/ files have conditions in body", "soft",
                    conditions_ok,
                    f"{len(ref_files)} reference file(s)")

    return findings


def format_findings(skill_path: Path, findings: list[dict], as_json: bool) -> str:
    if as_json:
        hard = sum(1 for f in findings if not f["passed"] and f["severity"] == "hard")
        soft = sum(1 for f in findings if not f["passed"] and f["severity"] == "soft")
        return json.dumps({"skill": str(skill_path), "findings": findings,
                           "summary": {"hard": hard, "soft": soft}}, indent=2)

    lines = [f"SKILL: {skill_path}"]
    for f in findings:
        icon = "PASS" if f["passed"] else f.get("severity", "soft").upper()
        detail = f"  {f['detail']}" if f.get("detail") else ""
        lines.append(f"{f['id']} {icon:5s}  {f['label']}{detail}")

    hard = sum(1 for f in findings if not f["passed"] and f["severity"] == "hard")
    soft = sum(1 for f in findings if not f["passed"] and f["severity"] == "soft")
    verdict = "PASS" if hard == 0 and soft == 0 else ("FAIL" if hard > 0 else "WARN")
    lines.append(f"---\nHard: {hard}  Soft: {soft}  → {verdict}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Skill conformance checker")
    parser.add_argument("skill", nargs="?", help="Path to skill directory")
    parser.add_argument("--all", action="store_true", help="Audit all skills in .claude/skills/")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--strict", action="store_true", help="Promote soft → hard")
    args = parser.parse_args()

    if args.all:
        base = Path(".claude/skills")
        skills = [p for p in base.iterdir() if p.is_dir()] if base.exists() else []
    elif args.skill:
        skills = [Path(args.skill)]
    else:
        parser.print_help()
        sys.exit(1)

    exit_code = 0
    for skill_path in sorted(skills):
        findings = audit_skill(skill_path, strict=args.strict)
        print(format_findings(skill_path, findings, as_json=args.json))
        print()
        if any(not f["passed"] and f["severity"] == "hard" for f in findings):
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
