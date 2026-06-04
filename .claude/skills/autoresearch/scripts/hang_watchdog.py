#!/usr/bin/env python3
"""Hang-watchdog for the autoresearch loop.

Why this exists
---------------
The autoresearch harness (`scripts/autoresearch/run.py`) has no aggregate
fixture-level timeout — only a per-question `wait_for_question_or_ship` loop
with a 25-minute default. If builder hangs *after* an `end_turn` response (no
new Anthropic API calls, no new DB writes, but CPU still active), run.py will
burn the full per-question budget before the operator notices, with zero
visibility into the root cause.

On 2026-05-23 a single fixture A iteration sat idle for 47 minutes in exactly
this state before being killed manually. This watchdog catches that pattern
within ~3 minutes and dumps full forensic data immediately.

How it works
------------
- Discovers active `builder start` processes by walking ``/proc/*/cmdline``.
- Restricts to autoresearch workspaces only (``/tmp/devpulse-<uuid>/``) so
  long-running dev/managed-app builder servers are not false-positives.
- For each tracked process, watches its workspace ``.agent-builder/agent_builder.db-wal``
  mtime as a liveness signal — every successful builder DB write touches it.
- When mtime has been stale longer than ``--idle-seconds`` (default 180s) and the
  process is past its ``--grace-seconds`` warm-up window, dumps:

    * ``STUCK_DETECTED.json`` with full metadata
    * ``builder logs --error --compact --json`` (workspace cwd)
    * ``builder agent sessions --limit 5 --full --json`` (workspace cwd)
    * ``/proc/<pid>/status`` + ``stack`` + ``wchan`` + per-thread wchan
    * Open FD snapshot (sockets/files)
    * ``py-spy dump --pid <pid>`` (if installed; ``pip install py-spy`` otherwise)
    * ``ss -tnp`` socket state
    * Copies of ``agent_builder.db`` + ``.db-wal`` + ``.db-shm``

Dumps land under ``--dump-root/<UTC-timestamp>-pid<PID>/`` so they survive the
harness's workspace teardown step.

Logs one stderr line per detection so an operator running ``tail -f`` of the
baseline output notices the hang the instant it's flagged.

Idempotent
----------
A workspace that has been dumped will not be re-dumped until its WAL mtime
advances past the value at the time of the dump — i.e., builder resumes
activity and then re-hangs at a later state.

Bounds + safety
---------------
- Read-only against builder processes (does **not** SIGTERM/SIGKILL).
- Filters to ``/tmp/devpulse-<uuid>`` workspaces; ignores live dev servers.
- Filters to processes owned by the running UID.
- Each shelled-out diagnostic command has a 15–25s timeout; the watchdog
  itself never blocks longer than ``--poll-seconds`` between scans.

Smoke test
----------
``python3 hang_watchdog.py --once --idle-seconds 180 --grace-seconds 0``
exits 0 after a single pass with no dumps if no autoresearch workspaces are
running.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

# -- Discovery -----------------------------------------------------------------


def _list_builder_pids() -> list[int]:
    """All live `builder start` python processes owned by this UID."""
    pids: list[int] = []
    uid = os.getuid()
    for proc in pathlib.Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            st = proc.stat()
            if st.st_uid != uid:
                continue
            cmdline = (proc / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if b"builder" not in cmdline or b"start" not in cmdline:
            continue
        args = cmdline.split(b"\x00")
        if not any(a.endswith(b"/builder") or a == b"builder" for a in args):
            continue
        if b"start" not in args:
            continue
        pids.append(int(proc.name))
    return pids


def _workspace_of(pid: int) -> pathlib.Path | None:
    try:
        return pathlib.Path(f"/proc/{pid}/cwd").resolve()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _port_of(pid: int) -> int | None:
    try:
        cmd = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\x00")
    except OSError:
        return None
    for i, a in enumerate(cmd):
        if a == b"--port" and i + 1 < len(cmd):
            try:
                return int(cmd[i + 1])
            except ValueError:
                pass
    return None


def _is_autoresearch_workspace(ws: pathlib.Path) -> bool:
    """Only watch fresh autoresearch workspaces, not live dev/managed-app builders."""
    return (
        ws.parent == pathlib.Path("/tmp")
        and ws.name.startswith("devpulse-")
        and (ws / ".agent-builder").is_dir()
    )


def _wal_mtime(workspace: pathlib.Path) -> float:
    wal = workspace / ".agent-builder" / "agent_builder.db-wal"
    try:
        return wal.stat().st_mtime
    except (FileNotFoundError, OSError):
        return 0.0


# -- Dump ---------------------------------------------------------------------


def _safe_run(cmd: list[str], cwd: str | None = None, timeout: int = 15) -> bytes:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        return f"# error: {type(exc).__name__}: {exc}\n".encode()


def _write_text_safe(path: pathlib.Path, text: str) -> None:
    try:
        path.write_text(text)
    except OSError:
        pass


def dump_diagnostics(
    *,
    pid: int,
    workspace: pathlib.Path,
    port: int | None,
    dump_root: pathlib.Path,
    idle_s: float,
    wal_mtime: float,
) -> pathlib.Path:
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    out = dump_root / f"{ts}-pid{pid}"
    out.mkdir(parents=True, exist_ok=True)

    meta = {
        "schema_version": "1",
        "detected_at_utc": ts,
        "builder_pid": pid,
        "builder_port": port,
        "workspace": str(workspace),
        "wal_last_mtime_epoch": wal_mtime,
        "wal_last_mtime_iso": (
            datetime.datetime.fromtimestamp(wal_mtime, tz=datetime.UTC).isoformat()
            if wal_mtime
            else None
        ),
        "idle_seconds": round(idle_s, 1),
        "py_spy_available": shutil.which("py-spy") is not None,
    }
    (out / "STUCK_DETECTED.json").write_text(json.dumps(meta, indent=2))

    (out / "builder_logs_error.json").write_bytes(
        _safe_run(
            ["builder", "logs", "--error", "--compact", "--json"],
            cwd=str(workspace),
        )
    )
    (out / "builder_sessions.json").write_bytes(
        _safe_run(
            ["builder", "agent", "sessions", "--limit", "5", "--full", "--json"],
            cwd=str(workspace),
        )
    )

    for fname, src in (
        ("process_status.txt", f"/proc/{pid}/status"),
        ("process_stack.txt", f"/proc/{pid}/stack"),
        ("process_wchan.txt", f"/proc/{pid}/wchan"),
    ):
        try:
            (out / fname).write_text(pathlib.Path(src).read_text(errors="replace"))
        except (OSError, PermissionError) as exc:
            _write_text_safe(out / f"{fname}.error", f"{type(exc).__name__}: {exc}\n")

    try:
        fd_dir = pathlib.Path(f"/proc/{pid}/fd")
        fds: list[str] = []
        for fd in fd_dir.iterdir():
            try:
                fds.append(f"{fd.name} -> {os.readlink(fd)}")
            except OSError:
                pass
        (out / "process_fds.txt").write_text("\n".join(sorted(fds)))
    except OSError as exc:
        _write_text_safe(out / "process_fds.error", f"{type(exc).__name__}: {exc}\n")

    try:
        task_dir = pathlib.Path(f"/proc/{pid}/task")
        thread_lines: list[str] = []
        for tid_p in task_dir.iterdir():
            try:
                wchan = (tid_p / "wchan").read_text(errors="replace").strip()
                status_lines = (tid_p / "status").read_text(errors="replace").splitlines()
                state = status_lines[1] if len(status_lines) > 1 else ""
                thread_lines.append(f"tid={tid_p.name} wchan={wchan} {state}")
            except OSError:
                pass
        (out / "process_threads.txt").write_text("\n".join(thread_lines))
    except OSError:
        pass

    if shutil.which("py-spy"):
        (out / "py_spy_dump.txt").write_bytes(
            _safe_run(["py-spy", "dump", "--pid", str(pid)], timeout=25)
        )
    else:
        (out / "py_spy_dump.txt").write_text(
            "py-spy not installed.\n"
            "Install via: pip install py-spy\n"
            "Re-run to capture Python stack on next hang.\n"
        )

    (out / "process_sockets.txt").write_bytes(_safe_run(["ss", "-tnp"]))

    agent_builder = workspace / ".agent-builder"
    for name in (
        "agent_builder.db",
        "agent_builder.db-wal",
        "agent_builder.db-shm",
    ):
        src = agent_builder / name
        if src.exists():
            try:
                shutil.copy2(src, out / name)
            except OSError as exc:
                _write_text_safe(
                    out / f"{name}.copy.error",
                    f"{type(exc).__name__}: {exc}\n",
                )

    return out


# -- Main loop ----------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="autoresearch hang watchdog")
    ap.add_argument(
        "--idle-seconds",
        type=int,
        default=180,
        help="Dump when DB-WAL hasn't been touched in this many seconds. Default 180.",
    )
    ap.add_argument("--poll-seconds", type=int, default=15)
    ap.add_argument(
        "--grace-seconds",
        type=int,
        default=90,
        help="Skip detection in the first N seconds after first sighting a process.",
    )
    ap.add_argument("--dump-root", default="/tmp/autoresearch/diagnostics")
    ap.add_argument(
        "--raw-bodies-root",
        action="append",
        default=[],
        help="Deprecated no-op (OTEL raw-body capture removed). Accepted for "
        "backward compatibility with existing spawn calls; ignored.",
    )
    ap.add_argument(
        "--once",
        action="store_true",
        help="Run a single pass and exit (for smoke tests).",
    )
    ap.add_argument(
        "--terminate-on-detect",
        action="store_true",
        help=(
            "After dumping diagnostics, SIGTERM the stuck builder process so "
            "run.py / baseline.py / loop.py can recover via their exception "
            "paths instead of burning the per-question timeout. Off by default "
            "(read-only stays the safe default)."
        ),
    )
    ap.add_argument(
        "--exit-on-detect",
        action="store_true",
        help=(
            "Exit (rc=2) after the first detection so a parent harness task "
            "receives an immediate completion notification. Use with "
            "--terminate-on-detect when running the watchdog as a Claude "
            "background task that needs to wake the operator the moment a "
            "hang is dumped — instead of waiting for the baseline to time out."
        ),
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    dump_root = pathlib.Path(args.dump_root)
    dump_root.mkdir(parents=True, exist_ok=True)

    seen: dict[int, dict[str, float]] = {}

    def log(msg: str) -> None:
        if not args.quiet:
            now = datetime.datetime.now(datetime.UTC).strftime("%H:%M:%S")
            print(f"[watchdog {now}] {msg}", file=sys.stderr, flush=True)

    log(
        f"started; idle_threshold={args.idle_seconds}s, "
        f"poll={args.poll_seconds}s, grace={args.grace_seconds}s, "
        f"dump_root={dump_root}"
    )

    running = True

    def _stop(*args: object) -> None:
        del args
        nonlocal running
        running = False
        log("received signal, exiting")

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while running:
        now = time.time()
        current_pids = set(_list_builder_pids())

        for dead in set(seen) - current_pids:
            log(f"pid {dead}: ended")
            del seen[dead]

        for pid in current_pids:
            ws = _workspace_of(pid)
            if ws is None or not _is_autoresearch_workspace(ws):
                continue
            wal_mt = _wal_mtime(ws)
            # Liveness signal: DB-WAL mtime. (A secondary raw_bodies/OTEL signal
            # was removed with the observability subsystem; a long pure-model
            # turn with no DB write now relies on the generous --idle-seconds
            # budget, set to 600s by baseline.py. Watch for P22-style false
            # positives; re-add a file-only liveness probe if they recur.)
            live_mt = wal_mt
            state = seen.setdefault(
                pid,
                {
                    "first_seen": now,
                    "last_live_mtime": live_mt,
                    "last_wal_mtime": wal_mt,
                    "last_dump_for_mtime": 0.0,
                },
            )

            if live_mt > state["last_live_mtime"]:
                state["last_live_mtime"] = live_mt
            if wal_mt > state["last_wal_mtime"]:
                state["last_wal_mtime"] = wal_mt

            age_since_first_seen = now - state["first_seen"]
            idle = now - state["last_live_mtime"] if state["last_live_mtime"] else 0.0

            if (
                age_since_first_seen >= args.grace_seconds
                and idle >= args.idle_seconds
                and state["last_live_mtime"] != state["last_dump_for_mtime"]
            ):
                port = _port_of(pid)
                out = dump_diagnostics(
                    pid=pid,
                    workspace=ws,
                    port=port,
                    dump_root=dump_root,
                    idle_s=idle,
                    wal_mtime=state["last_wal_mtime"],
                )
                log(
                    f"HANG DETECTED pid={pid} port={port} "
                    f"workspace={ws} idle={idle:.0f}s "
                    f"(wal_idle={now - state['last_wal_mtime']:.0f}s) "
                    f"diagnostics={out}"
                )
                state["last_dump_for_mtime"] = state["last_live_mtime"]
                if args.terminate_on_detect:
                    try:
                        os.kill(pid, signal.SIGTERM)
                        log(f"pid {pid}: SIGTERM sent (terminate-on-detect)")
                    except (ProcessLookupError, PermissionError) as exc:
                        log(f"pid {pid}: SIGTERM failed: {type(exc).__name__}: {exc}")
                if args.exit_on_detect:
                    log("exit-on-detect: returning rc=2")
                    return 2

        if args.once:
            break
        time.sleep(args.poll_seconds)

    return 0


if __name__ == "__main__":
    sys.exit(main())
