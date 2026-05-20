"""Bounded async subprocess execution for internal Builder commands."""

from __future__ import annotations

import asyncio
import os
import signal
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BoundedProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


async def run_bounded_subprocess(
    *command: str,
    cwd: str | Path | None = None,
    timeout_seconds: float = 30.0,
    label: str | None = None,
) -> BoundedProcessResult:
    """Run an async subprocess with stdout/stderr capture and timeout cleanup."""
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd) if cwd is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        await _terminate_process_tree(proc)
        message = _timeout_message(command, timeout_seconds, label)
        return BoundedProcessResult(
            returncode=124,
            stdout="",
            stderr=message,
            timed_out=True,
        )
    return BoundedProcessResult(
        returncode=proc.returncode,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )


async def _terminate_process_tree(proc: asyncio.subprocess.Process) -> None:
    pid = getattr(proc, "pid", None)
    if pid is not None:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGTERM)
    else:
        with suppress(ProcessLookupError):
            proc.terminate()

    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
        return
    except TimeoutError:
        pass

    if pid is not None:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGKILL)
    else:
        with suppress(ProcessLookupError):
            proc.kill()
    with suppress(Exception):
        await asyncio.wait_for(proc.wait(), timeout=5)


def _timeout_message(command: tuple[str, ...], timeout_seconds: float, label: str | None) -> str:
    name = label or "subprocess"
    rendered = " ".join(command)
    return f"{name} timed out after {timeout_seconds:g}s: {rendered}"
