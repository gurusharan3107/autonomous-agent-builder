# hermes-chrome — Optimize reference

Surface map, diagnosis flow, and per-surface fix procedure.
Loaded on demand from SKILL.md when a failure or quality issue is detected.

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
| Click lands on wrong/stale element | Acted before the page/SPA settled | **operate discipline** — `wait` + fresh `snapshot`, never blind-retry | — |

**Click-reliability invariants (do not regress — these define operator trust):**

1. **Logical position == click target, always.** `cursor-agent.js:moveTo` snaps `cursorX/cursorY` to the target so `click()`/`elementFromPoint` resolve the intended element regardless of whether the visible glide finished or the tab is backgrounded. Never reintroduce a click that reads a lagging animated position.
2. **Visible glide is compositor-driven** (CSS `transition: transform`), never `requestAnimationFrame` — rAF throttles when Chrome isn't focused, which is the normal case while the operator watches from the terminal.
3. **Resolvers reject non-real targets** (`__vis`: ≤1px, `display:none`, `visibility:hidden`, `opacity:0`, `aria-hidden`, horizontally off-screen) and prefer **exact** text over substring, **interactive** tags, and **on-target** (non-occluded) points. Below/above the fold is allowed — `__point` scrolls into view.

**Rule of thumb:** setup/deploy regressions → `sync.sh` or the install script;
runtime behaviour bugs → extension JS; timing/targeting → operate discipline. Never
patch skill prose to work around a code bug.

---

## Diagnosis flow

### Step 1 — run the deterministic diagnose first

```bash
python3 .claude/plugin/hermes_chrome/scripts/diagnose.py
```

This is bridge-independent — it inspects the filesystem + native manifest, so it
works even when the live bridge is dead. Each failed check prints its `surface`
and `fix`. Resolve `blocking_checks` before anything else; most map to `sync.sh`,
the install skill, or `chrome://extensions` reload. Only fall through to the
manual steps below when diagnose is `READY` but live actions still fail (a live
bridge / content-script / page-state problem, not a setup problem).

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
