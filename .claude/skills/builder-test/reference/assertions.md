# Assertions — builder-test

Load this file when Phase 1 (bad-string grep) or Phase 2 (unit assertions)
needs domain context. Not needed for Phase 0, 3, 4, or 5.

---

## Known Bad Patterns (Phase 1 grep targets)

Run these against recently changed files. Any match = WARN with file:line.

### Publisher hardcoded questions
Files: `agent_chat_result_publisher.py`, `agent_prompt_builders.py`
```bash
grep -n "Ready for Builder to start now\|should I hold\|or should I" \
  src/autonomous_agent_builder/embedded/server/agent_chat_result_publisher.py \
  src/autonomous_agent_builder/embedded/server/agent_prompt_builders.py
```
Why: hardcoded question strings in publisher bypass AskUserQuestion entirely
and render as dead plain text in the dashboard. The correct pattern is
`_append_persisted_delivery_permission_question_if_needed()` with `force=True`.

### Plain-text questions in agent definitions
Files: `definitions.py`
```bash
grep -n "?" \
  src/autonomous_agent_builder/agents/definitions.py | grep -v "AskUserQuestion\|mcp__builder"
```
Questions embedded as plain strings in the prompt teach the model bad vocabulary.
**Known benign hits** (WARN, not FAIL):
- QUESTION RULE section: the `?` is inside a quoted negative example showing what NOT to do.
- Gate-remediator sub-agent prompt: diagnostic question for the model, not an operator-facing question.

### Delivery permission patterns taught as negative examples
Files: `agent_prompt_builders.py`
```bash
grep -n "Ready for Builder\|start now\|should I hold" \
  src/autonomous_agent_builder/embedded/server/agent_prompt_builders.py
```
Negative examples that quote the bad phrase verbatim reinforce it.

### `json=` instead of `json_body=` in _api_request calls
Files: `builder_tool_service.py`, any file calling `_api_request`
```bash
grep -n "_api_request.*json=" \
  src/autonomous_agent_builder/services/builder_tool_service.py
```
`_api_request` uses `json_body=` not `json=`. The wrong kwarg silently drops
the payload.

---

## Unit Assertions (Phase 2)

### Intent classifier: `message_requests_read_only_status`
File: `agent_message_intent.py`

| Message | Expected | Why |
|---|---|---|
| `"what is the status of the backlog"` | `True` | has intent token (status) + scope token (backlog) |
| `"check the current board"` | `True` | has intent token (check) + scope token (board) |
| `"verify the sprint status"` | `True` | has intent token (verify, status) + scope token (sprint) |
| `"implement fix for the backlog"` | `False` | implementation exclusion token |
| `"fix the intent classifier"` | `False` | "fix" is exclusion token |
| `"create a new feature for backlog"` | `False` | "create" is exclusion token |
| `"dispatch the next task"` | `False` | "dispatch" is exclusion token |
| `"update the status of item X"` | `False` | "update" is exclusion token |

**Note**: `message_requests_read_only_status` requires BOTH an intent token from
`READ_ONLY_STATUS_INTENT_TOKENS` (status, check, verify, any, remaining, approval, …)
AND a scope token from `READ_ONLY_STATUS_SCOPE_TOKENS` (board, backlog, sprint, status, …).
Phrases like "show me the board" or "what tasks are in progress" return False — they
route via `dashboard_navigation_route_from_message` instead.

Run the full set — a single false positive blocks `model_backed_delivery_context_requested`.

### Tool registry: `mcp__builder__backlog_item_update` present
File: `tool_registry.py`
```bash
grep -n "mcp__builder__backlog_item_update" \
  src/autonomous_agent_builder/agents/tool_registry.py
```
If absent: the chat agent cannot update backlog item status without a new session.

### Chat agent definition: AskUserQuestion in tools
File: `definitions.py`
```bash
grep -n "AskUserQuestion" \
  src/autonomous_agent_builder/agents/definitions.py
```
AskUserQuestion must be in the chat agent's tools tuple. If absent, the QUESTION
RULE in the prompt is unenforceable — the model can't call a tool it doesn't have.

### Publisher: `feature_captured = False` initialization
File: `agent_chat_result_publisher.py`
```bash
grep -n "feature_captured" \
  src/autonomous_agent_builder/embedded/server/agent_chat_result_publisher.py
```
Must find: `feature_captured = False` (init) + `feature_captured = True` (set on
persist) + `force=feature_captured` (passed to delivery permission function).
All three must be present or the AskUserQuestion force-fire is broken.

### Sprint planning: `force` parameter present
File: `agent_sprint_planning.py`
```bash
grep -n "force" \
  src/autonomous_agent_builder/embedded/server/agent_sprint_planning.py | head -5
```
Must find `force: bool = False` in `append_persisted_delivery_permission_question_if_needed`.

### Chat agent model routing: `"chat"` in implementation_model set
File: `execution_policy.py`
```bash
grep -n '"chat"' \
  src/autonomous_agent_builder/agents/execution_policy.py
```
Must find `"chat"` inside the `implementation_model` block (alongside `"code-gen"`,
`"init-project-chat"`, etc.). If absent, `_model_for_agent()` falls through to
`agent_def.model` which is `"haiku"` — Haiku does not reliably follow complex
tool-use instructions and will produce plain-text responses instead of dispatching.
This was the root cause of 5 consecutive E2E failures (sessions with 2 messages,
no tool calls, plain-text questions).

### Chat runtime prompt surface: `_general_chat_prompt` in agent_prompt_builders.py
File: `agent_prompt_builders.py`
```bash
grep -n "_general_chat_prompt\|LOOKUP RULE" \
  src/autonomous_agent_builder/embedded/server/agent_prompt_builders.py | head -5
```
Must find `_general_chat_prompt` function definition and `LOOKUP RULE — MANDATORY`
block. The chat prompt is NOT `prompt_template` in `definitions.py` — that field
is for orchestrator agents only. Chat sessions go through
`build_chat_turn_prompt_plan()` → `_general_chat_prompt()`. Behavioral changes
for the chat agent must target `agent_prompt_builders.py`.

---

## E2E Observation Checklist (Phase 4)

After a session completes, verify these in order:

| Check | PASS signal | FAIL signal |
|---|---|---|
| Session started | run_status event with `running: True` | No events or 409 conflict |
| Dispatch reached | tool call `mcp__builder__task_dispatch` in logs | Only exploration tools used |
| Turn count | ≤ configured max (typically 20) | `stop_reason: max_turns` |
| Output type | `ask_user_question` event emitted OR `end_turn` with task dispatched | Plain text with "?" in content |
| No plain-text question | last `assistant_message` content has no `?` after confirmation text | Content contains "should I", "Ready to", etc. |
| Side-effects | ≥1 backlog item exists with correct status | 0 items OR status = `sprint_planned` stale |
| No duplicates | all backlog item titles unique | Same title appears twice |
