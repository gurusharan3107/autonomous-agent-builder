# Dashboard-First Validation

Canonical validation contract for testing autonomous builder workflows the way
a real product user experiences them.

Use this doc as the owner surface when changing:
- how validators act during forward-engineering or reverse-engineering runs
- which `builder` CLI commands are allowed during product validation
- what counts as a user-shaped Agent-page prompt
- how runtime evidence maps back to prompts, code, CLI, tools, MCP, model
  policy, context policy, or observability
- whether builder may use target-app scripts or CLIs while building and
  diagnosing user applications

## Purpose

`autonomous-agent-builder` exists to hide workflow, model, tool, context, and
environment orchestration from the user. Lifecycle validation must therefore
prove product behavior through the dashboard and Agent page, not through expert
CLI operation.

The validator may use CLI evidence to observe and debug the run. The validator
must not use CLI mutation to stand in for product behavior.

## User Persona

During validation, act as a normal product user after the repo is bootstrapped
and the product is running.

Allowed user behavior:
- type natural requests in the Agent page
- navigate dashboard pages such as Backlog, Board, Inbox, approvals, logs, and
  settings
- choose the desired runtime harness from first-run onboarding or Settings
- approve or reject visible product decisions through the browser
- describe product intent without internal tool names, phase names, or database
  state

Prompt shape:
- forward engineering: "Build a small local notes app with create, edit, and
  list views."
- forward continuation: "Continue building my app."
- reverse engineering: "Understand this repo and add one small user-visible
  improvement with tests."
- reverse continuation: "Ship this saved feature."

Avoid:
- "call `mcp__builder__task_dispatch`"
- "create backlog item X through the CLI"
- "move task Y to queued"
- "run phase `quality_gates`"
- "approve approval id 123"
- "use Sonnet with high effort"
- "set RUNTIME_SDK=codex_sdk from the CLI to stand in for onboarding"

The product must infer the workflow, model, effort, subagents, tools, MCP
servers, context strategy, and next task from durable product state. Runtime
harness choice is a product setting the user may select, but the builder still
owns model/effort/tool routing inside that selected harness.

Board selection must prefer the delivery project with the latest sprint
activity when multiple builder-created project rows exist for the same target
workspace. Setup or seed-planning rows must not hide the sprint the user just
shipped, and stale seeded completed projects must not hide a newer planned
delivery project when no sprint activity exists.

## Builder CLI Boundary

Allowed CLI use during lifecycle validation:
- environment bootstrap: create the disposable repo or clone, run `builder init`
  when the product has no browser bootstrap yet, and run `builder start`
- readiness and health checks: `builder --json doctor`, `builder readiness
  status --json`, `builder readiness assess --json`
- observability and diagnosis: `builder logs`, `builder logs analyze`,
  `builder agent sessions`, `builder agent history`, `builder agent runtime`,
  `builder metrics`, and read-only backlog/run/status inspection
- repo-doc retrieval and quality-gate retrieval needed to fix the builder
  itself

Forbidden CLI use as validation evidence:
- creating, updating, queuing, dispatching, or completing backlog items or tasks
- approving gates or moving phases
- writing feature specs that the Agent page should have produced
- direct database edits or API calls that bypass the browser path
- prompt shortcuts that mention internal MCP tool names, task ids, or phase ids
  unless the UI itself exposed those ids as the user-facing contract

Post-run maintainer closeout is outside the simulated user path. If repo rules
require `builder backlog item create` or `builder memory add` to capture a
durable validation finding, label that as closeout evidence. Do not count it as
proof that the product lifecycle works.

## Browser Validation Surface

Lifecycle validation must be driven through a browser-visible product surface.
Use the browser tool that best matches the evidence needed:

- Browser Use / in-app browser: preferred default for localhost lifecycle
  validation when available. Use it for stable Agent-page, Backlog, Board, Inbox,
  and approval interactions because DOM snapshots and selectors reduce
  coordinate mistakes while still exercising the real UI.
- Computer Use: use when the visible desktop browser state itself is the
  evidence, when validating whether a human can operate the current tab, or when
  Browser Use and DevTools are unavailable or interrupted.
- Chrome DevTools MCP: use when precise DOM, accessibility-tree, console,
  network, or screenshot evidence is needed to diagnose frontend failures.

Do not replace browser validation with `curl`, direct API calls, database edits,
or mutating `builder` CLI commands. Those are diagnosis channels, not the user
path.

## Validation Checkpoints

Every forward or reverse lifecycle run should prove:
- the tested browser tab belongs to the intended disposable repo or external
  clone
- Day-0 readiness gates the correct mode before autonomous work starts
- Agent-page prompts advance the lifecycle without exposing model, effort, MCP,
  tool, or phase choices to the user
- Backlog, Board, Inbox, approvals, quality gates, and shipping state are
  visible in the dashboard
- the Board defaults to the current sprint, shows only that sprint's task cards
  in the lanes, and provides a sprint selector for older shipped sprints plus an
  all-sprints diagnostic view
- forward-engineering sprint completion is visible as `Shipped` in the Board
  phase strip for the selected sprint, with all generated sprint tasks in the
  shipped/done lane and no stale blocked copy from earlier runs
- generated-app acceptance is proven in Browser Use through visible navigation
  and controls. Shell scripts can supplement that proof, but a flaky local
  headless browser command must not replace the in-app browser evidence.
- logs and session history explain failures without requiring direct database
  inspection
- if the UI and logs disagree, the product bug is fixed at the owner surface
  that caused the mismatch

## Optimization Evidence Routing

Use telemetry and observability to decide where the product should improve, not
as a second transcript store.

Route evidence to the smallest correct owner:
- system or agent prompt: wrong instruction hierarchy, missing output contract,
  missing verification loop, or repeated misunderstanding after correct product
  state was available
- orchestrator or code: wrong phase routing, state transition, retry behavior,
  blocked state, approval handling, or task dispatch
- `src/autonomous_agent_builder/agents/execution_policy.py`: wrong model,
  effort, subagent, context strategy, or budget for a lane
- builder CLI/API: missing compact diagnostic field, unstable JSON, poor `next`
  guidance, or no read-only way to inspect product state
- tool or MCP contract: wrong tool description, side-effect boundary,
  permission rule, retry behavior, or missing integration to a system the
  product should know how to use
- knowledge, memory, or docs: repeated retrieval failure, stale owner surface,
  or guidance that belongs outside a prompt
- observability: missing high-signal events, spans, costs, tool counts,
  stop reasons, or correlation ids needed to tune the builder
- runtime settings: wrong active harness, wrong telemetry lane, or cost display
  that treats subscription-backed Codex usage as metered `$0.0000`

Prefer compact derived signals over raw transcripts:
- model, effort, and fallback model
- turn count, tool count, and tool order
- token, cache-token, cost, and duration summaries
- phase transitions and blocked reasons
- retry count and stop reason
- context-efficiency warnings
- missing telemetry coverage

## Target-App CLI And Dev Environment

Builder may use a CLI or scripts for the application it is building or
reverse-engineering when that is the cleanest way to keep the app environment
deterministic and diagnosable.

Day-0 setup should also leave the target app with selected-runtime project
guidance: `CLAUDE.md` for Claude Agent SDK, `AGENTS.md` for Codex SDK. That
file is for runtime agents working in the target repo; do not fill it with
builder-operator instructions from the host repo.

Forward engineering:
- generated apps should expose boring, repeatable commands such as `dev`,
  `test`, `lint`, `build`, and a small `doctor` or `smoke` check when useful
- the builder should run those commands internally and surface results through
  product state
- generated apps may persist a compact Browser Use proof artifact when the
  stable proof lane is the in-app browser rather than a local Chrome headless
  subprocess. The artifact must be validated by an app-local script and tied to
  the visible URL/path that was exercised.
- if the disposable target is not a git repository, `git status` is an advisory
  integration metadata check. It should be surfaced as such, not as a blocker
  after build, test, lint, and browser proof pass.

Reverse engineering:
- prefer the target repo's existing package scripts, Make targets, task runner,
  or CLI before inventing a new one
- add or normalize a diagnostic command only when it reduces repeated ambiguity
  and fits the repo's conventions

The app CLI is not a user burden. It is a builder-owned tool for setup,
verification, and diagnosis, with evidence reflected back in the dashboard.
