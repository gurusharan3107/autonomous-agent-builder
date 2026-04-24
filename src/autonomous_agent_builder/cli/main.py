"""Root CLI application — `builder` command entry point.

Command shape: builder <resource> <verb>
Help is grouped by job for structured discoverability.
"""

from __future__ import annotations

import difflib
import errno
import os
from pathlib import Path
import sys
from typing import TextIO, cast

import click
import httpx
import typer
from dotenv import load_dotenv

# Load repo-local env for standalone builder CLI commands so subprocess-backed
# Claude lanes inherit auth such as CLAUDE_CODE_OAUTH_TOKEN.
load_dotenv()

from autonomous_agent_builder.cli.commands import (
    agent,
    backlog,
    board,
    context,
    gate,
    knowledge,
    logs,
    map,
    memory,
    metrics,
    script,
)
from autonomous_agent_builder.cli.commands.init import init_command
from autonomous_agent_builder.cli.commands.start import start_command
from autonomous_agent_builder.cli.client import (
    _safe_json_or_text,
    _valid_health_payload,
    resolve_base_url_with_source,
)
from autonomous_agent_builder.cli.output import emit_error, render, sanitize_error_detail
from autonomous_agent_builder.cli.project_discovery import ProjectNotFoundError, find_agent_builder_dir


def _root_invalid_usage_hint(
    root_group: click.Group,
    args: list[str],
) -> str:
    command_name = next((arg for arg in args if arg and not arg.startswith("-")), "")
    if command_name:
        suggestion = difflib.get_close_matches(command_name, list(root_group.commands), n=1)
        if suggestion:
            return (
                f"Run 'builder {suggestion[0]} --help' for the closest command, "
                "or 'builder --help' to inspect the full top-level surface."
            )
    return (
        "Run 'builder --help' to inspect top-level commands, "
        "or 'builder --json doctor' for startup orientation."
    )


class BuilderRootGroup(typer.core.TyperGroup):
    """Root group with deterministic invalid-usage recovery for agents."""

    def main(
        self,
        args: list[str] | tuple[str, ...] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: object,
    ) -> object:
        if args is None:
            runtime_args = sys.argv[1:]
            if os.name == "nt" and windows_expand_args:  # pragma: no cover
                runtime_args = click.utils._expand_args(runtime_args)
        else:
            runtime_args = list(args)
        raw_args = list(runtime_args)
        use_json = "--json" in raw_args

        resolved_prog_name = prog_name or click.utils._detect_program_name()
        self._main_shell_completion(extra, resolved_prog_name, complete_var)

        try:
            with self.make_context(resolved_prog_name, runtime_args, **extra) as ctx:
                rv = self.invoke(ctx)
                if not standalone_mode:
                    return rv
                ctx.exit()
        except EOFError as exc:
            click.echo(file=sys.stderr)
            raise click.Abort() from exc
        except KeyboardInterrupt as exc:
            raise click.exceptions.Exit(130) from exc
        except click.ClickException as exc:
            if isinstance(exc, (click.NoSuchOption, click.UsageError)):
                hint = _root_invalid_usage_hint(self, raw_args)
                usage = exc.ctx.get_usage() if getattr(exc, "ctx", None) else ""
                message = exc.format_message()
                if use_json:
                    emit_error(
                        message,
                        code="invalid_usage",
                        hint=hint,
                        detail={"usage": usage, "args": raw_args},
                        use_json=True,
                    )
                else:
                    if usage:
                        click.echo(usage, err=True)
                    click.echo(f"Error: {message}", err=True)
                    click.echo(f"Hint: {hint}", err=True)
                if standalone_mode:
                    sys.exit(exc.exit_code)
                return exc.exit_code
            if not standalone_mode:
                raise
            if typer.core.rich and self.rich_markup_mode is not None:
                typer.rich_utils.rich_format_error(exc)
            else:
                exc.show()
            sys.exit(exc.exit_code)
        except OSError as exc:
            if exc.errno == errno.EPIPE:
                sys.stdout = cast(TextIO, click.utils.PacifyFlushWrapper(sys.stdout))
                sys.stderr = cast(TextIO, click.utils.PacifyFlushWrapper(sys.stderr))
                sys.exit(1)
            raise
        except click.exceptions.Exit as exc:
            if standalone_mode:
                sys.exit(exc.exit_code)
            return exc.exit_code
        except click.Abort:
            if not standalone_mode:
                raise
            if typer.core.rich and self.rich_markup_mode is not None:
                typer.rich_utils.rich_abort_error()
            else:
                click.echo("Aborted!", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            if use_json:
                emit_error(
                    "internal builder CLI error",
                    code="internal_error",
                    hint="Run 'builder doctor --json' to verify startup state, then retry the command.",
                    detail={"type": exc.__class__.__name__, "message": sanitize_error_detail(str(exc))},
                    exit_code=1,
                    use_json=True,
                )
                if standalone_mode:
                    sys.exit(1)
                return 1
            raise

# ── Root app ──
app = typer.Typer(
    name="builder",
    cls=BuilderRootGroup,
    help=(
        "Autonomous SDLC builder CLI — agent-first interface.\n\n"
        "Operates the repo-local product surface: agent chat, board, backlog, "
        "knowledge, memory, metrics, and operator entrypoints.\n\n"
        "Start here:\n"
        "  builder --json doctor     Check startup contract and connectivity\n"
        "  builder init              Initialize agent builder in current repo\n"
        "  builder start --port 9876 Start the local dashboard and API\n"
        "  builder logs --error      Tail embedded agent chat errors\n"
        "  builder agent sessions    View saved agent chat sessions\n"
        "  builder board show        View the task pipeline\n"
        "  builder backlog task list List current task backlog\n"
        "  builder knowledge list    List local knowledge docs\n"
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    json: bool = typer.Option(False, "--json", help="Output as JSON for root-level commands."),
) -> None:
    """Carry global CLI flags for startup paths like `doctor`."""
    ctx.obj = {"json": json}


def _root_json(ctx: typer.Context, explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    if isinstance(ctx.obj, dict):
        return bool(ctx.obj.get("json", False))
    return False


def _doctor_payload() -> dict[str, object]:
    cwd = Path.cwd().resolve()
    base_url, base_url_source = resolve_base_url_with_source()
    try:
        agent_builder_dir = find_agent_builder_dir(cwd)
        project_initialized = True
        project_root = agent_builder_dir.parent
        project_hint = ""
    except ProjectNotFoundError as exc:
        agent_builder_dir = None
        project_initialized = False
        project_root = cwd
        project_hint = exc.hint

    server_payload: dict[str, object]
    next_step = ""
    try:
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            response = client.get("/health")
        raw_payload = _safe_json_or_text(response)
        if response.status_code >= 400:
            server_payload = {
                "reachable": False,
                "healthy": False,
                "status_code": response.status_code,
                "contract_ok": False,
                "error": "health_endpoint_error",
                "detail": raw_payload,
            }
            next_step = "builder start"
        elif _valid_health_payload(raw_payload):
            server_payload = {
                "reachable": True,
                "healthy": True,
                "status_code": response.status_code,
                "contract_ok": True,
                "payload": raw_payload,
            }
        else:
            server_payload = {
                "reachable": True,
                "healthy": False,
                "status_code": response.status_code,
                "contract_ok": False,
                "error": "invalid_health_payload",
                "detail": raw_payload,
            }
            next_step = "builder start"
    except httpx.TimeoutException:
        server_payload = {
            "reachable": False,
            "healthy": False,
            "status_code": None,
            "contract_ok": False,
            "error": "connectivity_timeout",
            "detail": None,
        }
        next_step = "builder start"
    except httpx.HTTPError as exc:
        server_payload = {
            "reachable": False,
            "healthy": False,
            "status_code": None,
            "contract_ok": False,
            "error": "connectivity_error",
            "detail": str(exc),
        }
        next_step = "builder start"

    if not next_step:
        if not project_initialized:
            next_step = "builder init"
        elif not server_payload.get("healthy"):
            next_step = "builder start"
        else:
            next_step = "builder map"

    return {
        "ok": True,
        "status": "ok",
        "exit_code": 0,
        "passed": bool(project_initialized and server_payload.get("healthy")),
        "schema_version": "1",
        "tool": "builder",
        "checks": {
            "project": {
                "initialized": project_initialized,
                "cwd": str(cwd),
                "project_root": str(project_root),
                "agent_builder_dir": str(agent_builder_dir) if agent_builder_dir else "",
                "hint": project_hint,
            },
            "config": {
                "api_base_url": base_url,
                "api_base_url_source": base_url_source,
                "auth_required": False,
                "auth_source": "not_required",
            },
            "server": server_payload,
        },
        "next": next_step,
        "next_step": next_step,
    }


@app.command()
def doctor(
    ctx: typer.Context,
    json: bool | None = typer.Option(None, "--json", help="Output as JSON."),
) -> None:
    """Verify startup contract: project scope, config, and server reachability."""
    payload = _doctor_payload()
    use_json = _root_json(ctx, json)

    def fmt(data: dict[str, object]) -> str:
        checks = data["checks"]
        project = checks["project"]
        config = checks["config"]
        server_info = checks["server"]
        lines = [
            f"project_initialized: {project['initialized']}",
            f"project_root: {project['project_root']}",
            f"api_base_url: {config['api_base_url']} ({config['api_base_url_source']})",
            f"server_reachable: {server_info['reachable']}",
            f"server_healthy: {server_info['healthy']}",
            f"next: {data['next_step']}",
        ]
        if project.get("hint"):
            lines.append(f"hint: {project['hint']}")
        return "\n".join(lines)

    render(payload, fmt, use_json=use_json)

# ── Project Initialization ──
app.command(name="init", help="Initialize agent builder (start here).")(init_command)
app.command(name="start", help="Build/publish the dashboard, then start the local product.")(start_command)

# ── Operator Entry Points ──
app.command(name="map", help="Bounded workspace digest for startup orientation.")(map.map_command)
app.command(name="context", help="Task bootstrap context for named profiles.")(context.context_command)
app.command(name="quality-gate", help="Local quality-gate surfaces.")(gate.quality_gate_command)
app.add_typer(logs.app, name="logs", help="Embedded agent chat and tool logs.")

# ── Product Surfaces ──
app.add_typer(agent.app, name="agent", help="Agent chat sessions and runtime metadata.")
app.add_typer(board.app, name="board", help="Task pipeline board and active-work routing.")
app.add_typer(backlog.app, name="backlog", help="Backlog planning and execution surfaces.")
app.add_typer(
    knowledge.app,
    name="knowledge",
    help="Project-local knowledge surfaces.",
)
app.add_typer(metrics.app, name="metrics", help="Cost and verification metrics.")
app.add_typer(memory.app, name="memory", help="Project memory — decisions and patterns.")

# ── Script Library ──
app.add_typer(script.app, name="script", help="Script library — pre-built agent scripts.")


def main() -> None:
    """CLI entry point."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    app()


if __name__ == "__main__":
    main()
