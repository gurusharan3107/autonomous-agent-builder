# Common gotchas — collected from v1 setup

> Loaded on demand from [autoresearch SKILL.md](../SKILL.md).

## Common gotchas (collected from v1 setup)

These cost real time on the v1 first-fixture-A test. Doing them right the first time saves ~30 min per gotcha:

| Gotcha | Why it bites | Fix / discipline |
| --- | --- | --- |
| Invoking harness scripts from the wrong CWD | `cd scripts/autoresearch && python3 scripts/autoresearch/run.py` resolves as nested path. Script not found. | Always invoke from repo root. `bootstrap.sh` / `teardown.sh` derive root from `BASH_SOURCE`; do the same in your shell scripts. |
| Empty `follow_ups` list on a fixture | Builder surfaces multiple intake/approval questions. Empty list stalls the run. | `default_answer: "recommended"` (baked into run.py's question loop) auto-approves unanswered questions. |
| Workspace stack mismatch | Harness defaults to `npm run build && test`; against a Python app the gate silently fails. | `preflight.py --recipe N` detects via `package.json` vs `pyproject.toml`. Extend `run_feature_check()` in `run.py` for Go/Rust/etc. |
| Jaeger image tag drift | Docker Hub removes old tags. | `bootstrap.sh` pre-pulls explicitly and surfaces the failure with a tag-lookup link. |
| WSL2 + Docker bridge networking | Container UP but `127.0.0.1:16686` unreachable from WSL host. | `docker-compose.yml` uses `network_mode: host` — listeners appear directly on the WSL host. |
| Live builder bound to OTEL ports | Two daemons can't share `:4318`. | `bootstrap.sh --auto-free-ports` detects + offers to stop conflicting processes; records state for teardown to restart. |
| Docker daemon group membership | First-time `usermod -aG docker $USER` + `chmod 666 /var/run/docker.sock`. | `bootstrap.sh` distinguishes "daemon down" from "no socket access" and prints the right remedy. |
| OneCLI auth not loaded | `CLAUDE_CODE_OAUTH_TOKEN` not in the spawned `builder start` env. | NOT an autoresearch concern (memory: `project_autoresearch_auth_scope.md`). Harness uses whatever auth Builder has. |
| TSV header drift | `run.py:SESSION_HEADERS` and the TSV header diverge across versions. Silent corruption. | `preflight.py --recipe N` verifies alignment via the canonical writer schema. |
| Stuck `/tmp/devpulse-<uuid>` workspaces | Iteration crashed before teardown's workspace cleanup. | `teardown.sh` removes UUID-pattern workspaces only; never touches `/tmp/devpulse-venv` etc. |
