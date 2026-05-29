# hermes-chrome — Optimize reference

Surface map, diagnosis flow, per-surface fix procedure, and troubleshooting when
preflight exits 0 but Chrome is still unstable.
Loaded on demand from SKILL.md when a failure or quality issue is detected.

---

## Preflight exits 0 but Chrome is still unstable

Preflight validates the socket + native host + diagnostics. It does **not** validate
the page state or content-script attachment. The cases below produce a healthy bridge
with actions that still fail — none are fixed by re-running preflight.

### 1. Content script blocked — active tab is chrome://, about:newtab, or an error page

**Signal:** preflight prints `⚠ Content script blocked on active tab`.
Actions return `blocked: true` or silently no-op.

The Chrome extension cannot inject content scripts into `chrome://`, `about:*`,
`file://`, or extension pages. The bridge socket is alive, but no tab action can execute.

**Fix:** use `useSelectedTab: False` — `True` fails before `goto` runs when the active tab is `chrome://`.
```python
r = bridge({"type":"run","sessionName":"my-task","useSelectedTab":False,"actions":[
    {"type":"goto","url":"http://localhost:9876"},
    {"type":"wait_for_selector","selector":"h1","timeout":5000},
    {"type":"page_context"}
]})
```

Navigate Chrome to an `https://` or `http://localhost` page, then proceed.
Never proceed to click/fill while `blocked` is true.

---

### 2. SPA not hydrated — `goto` resolves but React/Vue hasn't rendered yet

**Signal:** `page_context` returns an empty body, missing headings, or only a spinner.
`wait_for_selector` times out on an element that should be present.

`goto` fires when the `load` event fires. SPAs often render the shell on `load` and
hydrate content asynchronously. The socket is healthy, the URL is correct, but the DOM
is not ready.

**Fix:** Replace `wait` with `wait_for_selector` targeting a real content element:
```python
# ❌ wrong — fires at arbitrary time
{"type": "goto", "url": "http://localhost:9877"},
{"type": "wait", "ms": 1500},

# ✅ correct — waits for actual content
{"type": "goto", "url": "http://localhost:9877"},
{"type": "wait_for_selector", "selector": "h1", "timeout": 8000},
{"type": "page_context"}
```

If `h1` is not a reliable signal for this page, use a more specific selector
(`wait_for_selector` supports any CSS selector). Increase timeout to 8–10s for
slow dev servers.

---

### 3. Multiple Chrome windows — extension reports the wrong window's active tab

**Signal:** `page_context` returns an unexpected URL (different site, wrong page).
Operator can see the correct page in another Chrome window.

When multiple Chrome windows are open, `useSelectedTab: true` attaches to the most
recently focused tab — which may not be the page being tested.

**Fix:** Ask the operator to click inside the correct Chrome window to make it the
foreground window, then re-run `page_context` to confirm:
```python
r = bridge({"type":"run","useSelectedTab":True,"actions":[{"type":"page_context"}]})
current_url = r["results"][0].get("url","")
# If URL is wrong, operator must click the correct Chrome window first
```

Do not proceed until `current_url` matches the expected URL.

---

### 4. Tab navigated by operator between preflight and first action

**Signal:** Preflight reports `ok` with URL `A`, but first `page_context` returns URL `B`.

The operator navigated Chrome while the agent was processing. The bridge is healthy —
the URL just changed.

**Fix:** Always re-verify at the start of every turn (SKILL.md Hard rule 6):
```python
# First action of every new turn — confirm URL before acting
r = bridge({"type":"run","useSelectedTab":True,"actions":[{"type":"page_context"}]})
current_url = r["results"][0].get("url","")
# If current_url != expected_url, navigate or abort
```

Never assume the tab is still where preflight left it.

---

### 5. Native host alive but Chrome tab closed after preflight

**Signal:** Socket exists, `status` returns `success: true`, but `page_context` returns
`{url: "about:blank"}` or an error, or `active_tab` is empty.

Chrome closed the tab (or all tabs) after preflight finished. The native host process
survives tab closure but cannot control a non-existent tab.

**Fix:**
```python
r = bridge({"type":"run","useSelectedTab":True,"actions":[
    {"type":"goto","url":"http://localhost:9877"},
    {"type":"wait_for_selector","selector":"h1","timeout":5000},
    {"type":"page_context"}
]})
```

Navigate to open a new tab at the target URL. If `goto` also fails, reload the
extension in `chrome://extensions` to reconnect the native host to the new tab.

---

### 6. Service worker went idle between preflight finish and first agent action

**Signal:** Preflight exits 0. First bridge call in the same session returns socket error
or empty response.

Chrome MV3 service workers idle-out after ~30s. The keep-alive alarm fires every 25s —
but if Chrome sleeps (system suspend, display off) or the alarm fires late, the worker
can die between preflight and the first action.

**Fix — inline recovery:**
```python
import subprocess, os

def bridge_call(payload, timeout=45):
    try:
        return bridge(payload)
    except OSError:
        result = subprocess.run(
            ["bash", os.path.expanduser(
                "~/.claude/plugin/hermes_chrome/scripts/preflight.sh")],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"preflight failed:\n{result.stdout.strip()}")
        return bridge(payload)   # one retry only
```

Use `bridge_call()` in place of `bridge()` for every action. **One retry only** — if
the second call also fails, stop and enter Optimize; do not loop.

**Permanent fix (structural):** The keep-alive alarm should prevent this. If it
recurs, confirm the `"alarms"` permission is present in `manifest.json` and the alarm
is created in `service_worker.js` with `periodInMinutes: 25/60`. Run `sync.sh` and
reload the extension.

---

### 7. Extension reloaded mid-session (resets socket)

**Signal:** Actions succeed early in a session, then start failing with socket errors.
Operator may have reloaded the extension from `chrome://extensions`.

Extension reload tears down the native messaging connection and creates a new socket.
The old socket file is deleted; the new one may have a different inode.

**Fix:** Re-run preflight inline (same recovery as case 6 above), then re-establish
ground state with a fresh `page_context`. Any selectors or URLs captured before the
reload are still valid.

**Prevention:** Tell the operator not to reload the extension during an active agent
session. If they need to apply extension updates, close the session first, reload,
then start a new session.

---

### 8. Click actions hitting wrong element — page not fully settled

**Signal:** `click_text` returns `point` with a match, but the page behaves as if a
different element was clicked, or nothing happens.

The page is animating (modal opening, dropdown expanding, lazy-load completing) when
the click fires. `click_text` found the element in a transitional DOM state.

**Fix:** Add `wait_for_selector` on a stable post-action element before clicking:
```python
# After navigation or a prior click, wait for the page to settle
{"type": "wait_for_selector", "selector": ".loaded-indicator", "timeout": 4000},
# Then click the intended element
{"type": "click_text", "text": "Submit"},
{"type": "wait_for_selector", "selector": ".success-banner", "timeout": 5000},
{"type": "page_context"}
```

Never retry a failed click without a fresh `snapshot` first — the DOM may have changed.

---

## Surface map

```
.claude/skills/hermes-chrome/          ← Skill (instructions, patterns)
.claude/plugin/hermes_chrome/          ← Plugin source (ALL code edits go here)
  extension/
    service_worker.js                  ← action routing, screenshot, page_context
    content-scripts/cursor-agent.js   ← DOM, snapshot, cursor, getPageContext
    manifest.json
    images/                            ← cursor SVG assets
  native/
    native_host.py                     ← Unix socket server, screenshot save
  diagnostics.py                       ← shared deterministic checks (run_diagnostics)
  tools.py                             ← bridge client; _diagnostics delegates here
  scripts/
    diagnose.py                        ← CLI wrapper for diagnostics (preflight step 1)
    sync.sh                            ← deploy: copy → Chrome extension + reload
~/.hermes/chrome-bridge/native/        ← live native host (synced from plugin/native/)
C:\Users\gurusharan.gupta\.claude\extension\  ← Chrome loads from here (synced from plugin/extension/)
~/.hermes/run/chrome-bridge.sock       ← Unix socket (created by native_host.py on Chrome connect)
```

**Edit rule:** all code edits go in `.claude/plugin/hermes_chrome/`. Never edit the
Windows extension dir or `~/.hermes/` directly — they are sync targets, not sources.

---

## Symptom → surface table

| Symptom | Surface | File to edit |
|---------|---------|-------------|
| Action type not recognised | Extension | `service_worker.js` → `runBrowserAction` |
| Action returns wrong data | Extension | `service_worker.js` or `cursor-agent.js` |
| Snapshot too verbose / duplication | Extension | `cursor-agent.js` → `getDOMSnapshot` |
| Snapshot missing interactive elements | Extension | `cursor-agent.js` → `getDOMSnapshot` selector |
| `page_context` missing nav / buttons | Extension | `cursor-agent.js` → `getPageContext` |
| Screenshot timeout | Extension | `service_worker.js` → screenshot action (must use JPEG) |
| Screenshot wrong format or too large | Extension + Plugin | `service_worker.js` format param + `native_host.py` ext |
| Cursor not visible on page | Extension | `cursor-agent.js` + `images/pointer-shape-animated.svg` |
| Cursor doesn't move / click misses when Chrome unfocused | Extension | `cursor-agent.js` → snap logical `cursorX/Y` to target + CSS transform transition (NOT `requestAnimationFrame`) |
| `ContentScript did not respond` after reload | Extension | `service_worker.js` → `ensureContentScript` guard clear |
| Bridge socket not found | Native host | `native_host.py` — check wsl batch is calling correct path |
| `tool_error` from bridge client | Plugin | `tools.py` → `_run_extension_bridge` |
| Skill instructions wrong / stale | Skill | `SKILL.md` + `references/*.md` |

---

## Recurring browser-control failures → root-cause surface

The failure modes agents hit *repeatedly* taking control of a browser. Fix at the
surface that owns the root cause — not where the symptom shows. `diagnose`
(`scripts/diagnose.py`) detects the deterministic ones up front.

| Recurring failure | Root cause | Surface to fix | diagnose check |
|---|---|---|---|
| "Socket not found" / no response | Chrome closed or extension not loaded | Operator action: open Chrome (visible), load extension | `bridge_socket_reachable` |
| Connect hangs / refused, socket file present | Native host died; stale socket left behind | `rm` socket + reload extension (host re-creates it) | `bridge_socket_reachable` (stale) |
| "I fixed the code but it still misbehaves" | Source edited, never deployed — Chrome runs stale code | **sync discipline** — run `sync.sh` | `deployed_matches_source` |
| Native messaging silently fails after re-loading extension | Manifest `allowed_origins` ↔ new extension id mismatch | **install script** — `install_*.py --extension-id <id>` | `native_manifest_valid` |
| Bridge never starts on a fresh machine | Launcher runs wrong interpreter (Windows python vs `wsl python3`) — AF_UNIX socket only works inside WSL2 | **install script** `install_runtime_wsl()` | `launcher_consistent` |
| Cursor invisible / `click_text` animation throws | `web_accessible` cursor assets not deployed | **extension assets + sync** | `cursor_assets_present` |
| "ContentScript did not respond" after a reload | Orphaned content script; injection guard not cleared | **extension** — `service_worker.js:ensureContentScript` | live `status` (step 3) |
| `click_text` clicks the wrong thing (e.g. a hidden skip-link, a 0×0 mobile-menu duplicate) | Loose substring match + first-DOM-order + no visibility filter | **extension** — `service_worker.js:findPointByText`/`findPointBySelector`: exact→starts-with→contains ranking over `__vis`-filtered, occlusion-checked candidates | live click test |
| Cursor doesn't move / click misses when Chrome is NOT the foreground window | Position integrated by `requestAnimationFrame`, which throttles to ~1fps in a backgrounded tab; click fired at the stale position | **extension** — `cursor-agent.js`: snap logical `cursorX/Y` to target immediately; glide visibly via a **CSS transform transition** (compositor-driven, runs backgrounded) | live click test, headless-window |
| Screenshot returns nothing | PNG > 1MB native-messaging limit, dropped silently | **extension** — JPEG default in screenshot action | — |
| Click lands on wrong/stale element | Acted before the page/SPA settled | **operate discipline** — `wait_for_selector` + fresh `snapshot`, never blind-retry | — |

**Click-reliability invariants (do not regress — these define operator trust):**

1. **Logical position == click target, always.** `cursor-agent.js:moveTo` snaps `cursorX/cursorY` to the target so `click()`/`elementFromPoint` resolve the intended element regardless of whether the visible glide finished or the tab is backgrounded. Never reintroduce a click that reads a lagging animated position.
2. **Visible glide is compositor-driven** (CSS `transition: transform`), never `requestAnimationFrame` — rAF throttles when Chrome isn't focused, which is the normal case while the operator watches from the terminal.
3. **Resolvers reject non-real targets** (`__vis`: ≤1px, `display:none`, `visibility:hidden`, `opacity:0`, `aria-hidden`, horizontally off-screen) and prefer **exact** text over substring, **interactive** tags, and **on-target** (non-occluded) points. Below/above the fold is allowed — `__point` scrolls into view.

**Rule of thumb:** setup/deploy regressions → `sync.sh` or the install script;
runtime behaviour bugs → extension JS; timing/targeting → operate discipline. Never
patch skill prose to work around a code bug.

---

## Diagnosis flow

### Step 1 — run the self-healing preflight first

```bash
bash ~/.claude/plugin/hermes_chrome/scripts/preflight.sh
```

This auto-fixes file deployment drift, stale sockets, and idle service workers.
Exit 0 = bridge healthy and ready. Exit 1 = prints the exact manual step needed.

Only fall through to manual steps below when preflight exits 0 but live actions
still fail (a content-script / page-state problem, not a setup problem).

For raw check output without auto-fix:
```bash
python3 ~/.claude/plugin/hermes_chrome/scripts/diagnose.py --json
```

### Step 2 — is the socket alive? (manual, if diagnose was READY)

```bash
ls -la ~/.hermes/run/chrome-bridge.sock
```

- Exists + is a socket → proceed to Step 4.
- Missing → Chrome extension not connected. Reload extension in `chrome://extensions`, then re-check.
- Exists but not a socket (stale file) → `rm ~/.hermes/run/chrome-bridge.sock`, reload extension.

### Step 3 — does status respond?

```python
r = bridge({"type": "status", "timeoutSeconds": 5})
```

- `success: true` → bridge live. Proceed to Step 4.
- Timeout → native host is not processing. Check batch file calls correct WSL path:
  ```
  C:\Users\gurusharan.gupta\.claude\hermes_chrome_bridge.bat
  → wsl python3 /home/gurusharangupta/.hermes/chrome-bridge/native/native_host.py
  ```

### Step 4 — isolate the failing action

Run the failing action alone with `useSelectedTab: true`. Read the full error:

```python
r = bridge({"type":"run","useSelectedTab":True,"actions":[{"type":"<failing-action>"}]})
print(r)
```

Match error to the symptom table above → identify the file to fix.

### Step 5 — inspect the source

```bash
# Extension JS
cat .claude/plugin/hermes_chrome/extension/service_worker.js | grep -n "<action-type>"
cat .claude/plugin/hermes_chrome/extension/content-scripts/cursor-agent.js | grep -n "getDOMSnapshot\|getPageContext"

# Native host
cat .claude/plugin/hermes_chrome/native/native_host.py | grep -n "screenshot\|socket"
```

---

## Fix by surface

### Extension (service_worker.js or cursor-agent.js)

1. Edit the file in `.claude/plugin/hermes_chrome/extension/`.
2. Run sync — deploys + hot-reloads Chrome:
   ```bash
   .claude/plugin/hermes_chrome/scripts/sync.sh
   ```
3. Re-run the failing action to confirm fix.

**Common extension fixes:**

- **Add a new action type** → add a branch in `runBrowserAction` in `service_worker.js`.
- **Fix snapshot verbosity** → remove `div,span` from the querySelector in `cursor-agent.js:getDOMSnapshot`.
- **Fix screenshot format** → ensure `format: 'jpeg'` is the default in the screenshot action in `service_worker.js`.
- **Fix cursor not moving / clicks missing when Chrome is unfocused** → in `cursor-agent.js:moveTo`, snap logical `cursorX/cursorY` to the target immediately and glide the element via a CSS `transition: transform` (compositor-driven). Do NOT integrate position with `requestAnimationFrame` — it throttles to ~1fps in a backgrounded tab. See "Click-reliability invariants" above.
- **Fix post-reload orphan** → in `service_worker.js:ensureContentScript`, clear the injection guard attribute before re-injecting.

### Native host (native_host.py)

1. Edit `.claude/plugin/hermes_chrome/native/native_host.py`.
2. Run sync (also copies native host to `~/.hermes/chrome-bridge/native/`):
   ```bash
   .claude/plugin/hermes_chrome/scripts/sync.sh
   ```
3. Reload Chrome extension to restart the native host process.

### Plugin tools.py (bridge client)

1. Edit `.claude/plugin/hermes_chrome/tools.py`.
2. Run sync (also copies to `~/.claude/plugin/hermes_chrome/`):
   ```bash
   .claude/plugin/hermes_chrome/scripts/sync.sh
   ```

### Skill (SKILL.md or references/)

1. Edit `.claude/skills/hermes-chrome/SKILL.md` or the relevant `references/*.md`.
2. Run validate:
   ```bash
   .claude/skills/hermes-chrome/scripts/validate.sh
   ```

This skill is **project-local only** — there is intentionally no
`~/.claude/skills/hermes-chrome` global copy (it drifts stale and incomplete).
Do not create one.

---

## After any fix

```bash
# 1. Deploy
.claude/plugin/hermes_chrome/scripts/sync.sh

# 2. Verify bridge is back
python3 -c "
import socket, json, os
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(os.path.expanduser('~/.hermes/run/chrome-bridge.sock'))
s.sendall(json.dumps({'type':'status','timeoutSeconds':5}).encode())
chunks = []
while True:
    c = s.recv(65536)
    if not c: break
    chunks.append(c)
s.close()
print(json.loads(b''.join(chunks)))
"

# 3. Re-run the originally failing action
```

After any change to `service_worker.js` (resolvers) or `cursor-agent.js` (motion),
run the live regression suite — it guards the click-reliability invariants:

```bash
python3 .claude/plugin/hermes_chrome/tests/test_dashboard_interactions.py
# exit 0 = all pass · 1 = regression · 2 = env unavailable (skipped)
```

---

## Skill self-update protocol

When the skill instructions are wrong, stale, or missing a pattern that was
needed during operation:

1. Note exactly what was missing or wrong.
2. Edit `SKILL.md` body (router) or the relevant `references/*.md` (detail).
3. Keep body ≤ 5000 tokens — bulk goes to references.
4. Run `./scripts/validate.sh` — exit 0 required.
5. Copy to global if needed (see Skill fix procedure above).
