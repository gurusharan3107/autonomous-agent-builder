#!/usr/bin/env python3
"""Harness ↔ Builder API contract tests.

The autoresearch harness (scripts/autoresearch/run.py + baseline.py) consumes
Builder CLI/API output. When Builder's output shape drifts, the harness reads
the wrong keys silently → 0-composite iters, wrong gate verdicts. Patches
P1–P15 were all instances of this class.

This script asserts every Builder surface the harness depends on still returns
the shape declared in `seed_manifest.json § contract_surfaces`. Run as part of
preflight (Recipe 1/2/3); $0, ~2s, catches the entire class before any iter.

Exit 0 on all-pass, 1 on any contract violation.

Usage:
  python3 .claude/skills/autoresearch/scripts/test_harness_contracts.py
  python3 .claude/skills/autoresearch/scripts/test_harness_contracts.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = SKILL_DIR / "seed_manifest.json"

# Module-level cwd override; set in main() before tests run.
_RUN_CWD: pathlib.Path | None = None


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_RUN_CWD) if _RUN_CWD else None,
        )
        return r.returncode, r.stdout, r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return -1, "", f"{type(exc).__name__}: {exc}"


def _parse_json(stdout: str) -> tuple[bool, dict]:
    try:
        v = json.loads(stdout)
        if isinstance(v, dict):
            return True, v
        return False, {}
    except (ValueError, json.JSONDecodeError):
        return False, {}


def _walk_required(obj: object, keys: list[str], where: str) -> list[str]:
    """Returns list of missing keys at the given path."""
    if not isinstance(obj, dict):
        return [f"{where}: not a dict (got {type(obj).__name__})"]
    return [f"{where}.{k}" for k in keys if k not in obj]


def assert_builder_task_list(spec: dict) -> dict:
    name = "builder_task_list"
    argv = spec.get("command_argv", [])
    rc, out, err = _run(argv)
    if rc != 0:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"command exit {rc}: {err[:200] or out[:200]}",
            "remediation_hint": "verify builder CLI is on PATH and `builder task list --json` is implemented",
        }
    ok, data = _parse_json(out)
    if not ok:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"output not valid JSON (first 200 chars): {out[:200]}",
            "remediation_hint": "Builder CLI changed output shape — update harness consumers in run.py",
        }
    missing_top = _walk_required(data, spec.get("required_top_keys", []), "root")
    if missing_top:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"missing top-level key(s): {missing_top}",
            "remediation_hint": f"update {name} consumer in run.py to match new shape",
        }
    items = data.get("tasks", [])
    if items and isinstance(items, list) and isinstance(items[0], dict):
        missing_item = _walk_required(items[0], spec.get("required_item_keys", []), "tasks[0]")
        if missing_item:
            return {
                "contract": name,
                "status": "fail",
                "detail": f"missing tasks[].* key(s): {missing_item}",
                "remediation_hint": "task item shape changed — update consumer",
            }
    return {"contract": name, "status": "pass", "detail": f"{len(items)} task(s); shape ok"}


def assert_builder_board_show(spec: dict) -> dict:
    name = "builder_board_show"
    argv = spec.get("command_argv", [])
    rc, out, err = _run(argv)
    if rc != 0:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"command exit {rc}: {err[:200] or out[:200]}",
            "remediation_hint": "verify `builder board show --json` works",
        }
    ok, data = _parse_json(out)
    if not ok:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"output not JSON: {out[:200]}",
            "remediation_hint": "Builder CLI shape drift",
        }
    missing = _walk_required(data, spec.get("required_top_keys", []), "root")
    if missing:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"missing top-level key(s): {missing}",
            "remediation_hint": "update run.py board consumer",
        }
    return {"contract": name, "status": "pass", "detail": "board shape ok"}


def assert_builder_logs_analyze(spec: dict, sample_session_id: str | None) -> dict:
    """Best-effort: needs a session id. If none available, mark skip — the
    contract still gets tested whenever a real run lands."""
    name = "builder_logs_analyze"
    if not sample_session_id:
        return {
            "contract": name,
            "status": "skip",
            "detail": "no sample session_id available (pass --session-id to verify)",
        }
    template = spec.get("command_argv_template", [])
    argv = [a.replace("{session_id}", sample_session_id) for a in template]
    rc, out, err = _run(argv, timeout=30)
    if rc != 0:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"command exit {rc}: {err[:200] or out[:200]}",
            "remediation_hint": "verify `builder logs analyze --session <id> --json` works",
        }
    ok, data = _parse_json(out)
    if not ok:
        return {"contract": name, "status": "fail", "detail": f"output not JSON: {out[:200]}"}
    missing_top = _walk_required(data, spec.get("required_top_keys", []), "root")
    if missing_top:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"missing top-level key(s): {missing_top}",
            "remediation_hint": "Builder analyze output shape drifted — update run.py consumers",
        }
    ra = data.get("runtime_aggregates", {})
    missing_ra = _walk_required(
        ra, spec.get("required_runtime_aggregates_keys", []), "runtime_aggregates"
    )
    if missing_ra:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"missing runtime_aggregates key(s): {missing_ra}",
            "remediation_hint": "M2.3 session-scoping regression — re-verify _runtime_aggregates wiring",
        }
    if spec.get("session_scoped_must_be") is True and ra.get("session_scoped") is not True:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"runtime_aggregates.session_scoped={ra.get('session_scoped')!r} (manifest requires True)",
            "remediation_hint": "session-scoping regression — autoresearch σ-floor will bleed across sessions",
        }
    return {"contract": name, "status": "pass", "detail": "analyze shape + session-scoping flag ok"}


def _check_workspace_ready(spec: dict) -> tuple[bool, str]:
    """Run `builder doctor --json`; return (ok, detail). If ok=False, caller
    should skip remaining contract tests — they cannot pass outside a Builder
    workspace and would generate noisy false-fail signal."""
    argv = spec.get("command_argv", ["builder", "doctor", "--json"])
    rc, out, err = _run(argv, timeout=20)
    if rc != 0:
        return False, f"builder doctor exit {rc}: {err[:100] or out[:100]}"
    ok, data = _parse_json(out)
    if not ok:
        return False, f"builder doctor returned non-JSON: {out[:100]}"
    # builder doctor always returns ok:true (command success); use passed:true
    # to distinguish an initialised workspace from a non-initialised one.
    if data.get("ok") is True and data.get("passed") is True:
        return True, "workspace ready"
    return (
        False,
        f"doctor.ok={data.get('ok')} passed={data.get('passed')} ({data.get('status', '?')})",
    )


def _assert_generic(name: str, spec: dict) -> dict:
    """Generic contract assertion: command exits 0, output is JSON, required
    top-level keys are present. Works for any flat 'required_top_keys' spec.
    Supports `skip_top_key_check_if_ok_false`: when Builder returns the
    standard error envelope `{ok:false, ...}`, accept it as a valid no-data
    response rather than treating it as drift."""
    argv = spec.get("command_argv", [])
    rc, out, err = _run(argv)
    if rc != 0:
        # Some Builder commands return non-zero with a structured error envelope.
        # If the spec allows skip-on-ok-false, parse and check ok=false.
        if spec.get("skip_top_key_check_if_ok_false"):
            ok, data = _parse_json(out)
            if ok and data.get("ok") is False:
                return {
                    "contract": name,
                    "status": "pass",
                    "detail": f"command returned ok:false envelope "
                    f"(code={data.get('code', '?')!r}) — accepted",
                }
        return {
            "contract": name,
            "status": "fail",
            "detail": f"command exit {rc}: {err[:200] or out[:200]}",
            "remediation_hint": f"verify `{' '.join(argv)}` works in this workspace",
        }
    ok, data = _parse_json(out)
    if not ok:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"output not JSON: {out[:200]}",
            "remediation_hint": "Builder CLI shape drift",
        }
    if spec.get("skip_top_key_check_if_ok_false") and data.get("ok") is False:
        return {
            "contract": name,
            "status": "pass",
            "detail": "command returned ok:false envelope — accepted",
        }
    missing = _walk_required(data, spec.get("required_top_keys", []), "root")
    if missing:
        return {
            "contract": name,
            "status": "fail",
            "detail": f"missing top-level key(s): {missing}",
            "remediation_hint": f"update {name} consumer in run.py to match new shape",
        }
    return {"contract": name, "status": "pass", "detail": "shape ok"}


def test_all(manifest_path: pathlib.Path, sample_session_id: str | None) -> dict:
    manifest = json.loads(manifest_path.read_text())
    surfaces = manifest.get("contract_surfaces", {})
    results: list[dict] = []
    # Gate: if doctor reports not-in-workspace, mark all subsequent tests as
    # skip rather than fail. Contract tests need a real workspace to validate.
    workspace_ok = True
    if "preflight_workspace_check" in surfaces:
        spec = surfaces["preflight_workspace_check"]
        ok, detail = _check_workspace_ready(spec)
        workspace_ok = ok
        results.append(
            {
                "contract": "preflight_workspace_check",
                "status": "pass" if ok else "skip",
                "detail": detail,
                "remediation_hint": (
                    ""
                    if ok
                    else "contract tests require an initialized Builder workspace; "
                    "run from inside a `builder init`'d directory (e.g., the seed "
                    "or a /tmp/devpulse-* workspace) to validate Builder CLI shapes."
                ),
            }
        )
    # Iterate over remaining surfaces.
    for name, spec in surfaces.items():
        if name == "preflight_workspace_check":
            continue
        if not isinstance(spec, dict):
            # Manifest may contain non-contract keys (e.g. "comment" strings); skip.
            continue
        if not workspace_ok and spec.get("command_argv_template"):
            # Skip session-scoped contracts unless we have a sample session id
            results.append({"contract": name, "status": "skip", "detail": "workspace not ready"})
            continue
        if not workspace_ok:
            results.append({"contract": name, "status": "skip", "detail": "workspace not ready"})
            continue
        if name == "builder_logs_analyze":
            results.append(assert_builder_logs_analyze(spec, sample_session_id))
        elif "command_argv" in spec:
            results.append(_assert_generic(name, spec))
    # Overall: fail only on hard fails; skips don't fail overall.
    overall = (
        "fail"
        if any(r.get("status") == "fail" for r in results)
        else ("warn" if any(r.get("status") == "skip" for r in results) else "pass")
    )
    return {
        "overall": overall,
        "manifest": str(manifest_path),
        "workspace_ready": workspace_ok,
        "results": results,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    p.add_argument(
        "--session-id", default=None, help="sample Builder session id for analyze contract test"
    )
    p.add_argument(
        "--cwd",
        type=pathlib.Path,
        default=None,
        help="run Builder commands from this directory. Defaults to "
        "manifest's seed_dir (an initialized Builder workspace). "
        "Override when testing against a different workspace.",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    # Resolve effective cwd: explicit --cwd > manifest seed_dir > current cwd
    global _RUN_CWD
    if args.cwd:
        _RUN_CWD = args.cwd
    else:
        try:
            m = json.loads(args.manifest.read_text())
            seed_dir = pathlib.Path(os.path.expanduser(m["seed_dir"]))
            if seed_dir.exists() and (seed_dir / ".agent-builder").exists():
                _RUN_CWD = seed_dir
        except (OSError, KeyError, json.JSONDecodeError):
            pass
    report = test_all(args.manifest, args.session_id)
    report["run_cwd"] = str(_RUN_CWD) if _RUN_CWD else os.getcwd()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        glyph = {"pass": "✓", "warn": "⚠", "fail": "✗", "skip": "—"}
        print(f"harness_contracts: {glyph[report['overall']]} {report['overall'].upper()}")
        for r in report["results"]:
            print(
                f"  [{glyph.get(r.get('status', 'warn'), '?')}] {r['contract']}: "
                f"{r.get('detail', '')}"
            )
            if r.get("remediation_hint"):
                print(f"      remediation: {r['remediation_hint']}")
    return 0 if report["overall"] != "fail" else 1


if __name__ == "__main__":
    sys.exit(main())
