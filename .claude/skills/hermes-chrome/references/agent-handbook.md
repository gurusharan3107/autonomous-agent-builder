# Agent Handbook — modifying & troubleshooting hermes-chrome

Read this before editing the plugin or debugging a deeper issue than what
`optimize.md` covers. `operate.md` and `optimize.md` are for USING the bridge;
this handbook is for MODIFYING it.

Each lesson here is real — these are the failure modes that cost time when
they weren't written down.

---

## Architecture map (find the right file fast)

```
Operator's Chrome (Windows) ─┬─ extension (popup, service_worker, content_scripts)
                             │       │
                             │       │ native messaging (stdio)
                             │       ▼
                             │   native_host.py (runs in WSL via `wsl python3`)
                             │       │
                             │       │ AF_UNIX socket
                             │       ▼
                             └── tools.py (Python tool, called by agent harness)
                                     │
                             ~/.hermes/run/chrome-bridge.sock
```

Source-of-truth lives in **this repo**; `sync.sh` deploys to the install
locations Chrome and native-host actually read from:

| File | Source path (repo) | Install path (Chrome reads from here) | Role |
|---|---|---|---|
| Extension manifest | `.claude/plugin/hermes_chrome/extension/manifest.json` | `C:\Users\<you>\.claude\extension\` (WSL) or `~/.hermes/chrome-bridge/extension/` (macOS) | MV3 declarations |
| Service worker | `extension/service_worker.js` | (same install dir) | Native-messaging port; auto-injects cursor + feedback widget; toggle handlers |
| Cursor content script | `extension/content-scripts/cursor-agent.js` | (same) | Floating animated cursor overlay |
| Feedback content script | `extension/content-scripts/feedback-widget.js` | (same) | Mounts agent-feedback widget; CSP-safe |
| Feedback runtime | `extension/content-scripts/feedback-widget-runtime.js` | (same) | IIFE body extracted from agent-feedback-artifact's overlay.html on each sync |
| Popup | `extension/popup.{html,js}` | (same) | Status panel + Feedback Mode toggle |
| Native host | `native/native_host.py` | `~/.hermes/chrome-bridge/native/native_host.py` | Stdio ↔ AF_UNIX bridge; always runs in WSL |
| Tool (agent-callable) | `tools.py` | `~/.claude/plugin/hermes_chrome/tools.py` (synced via sync.sh) | Connects to AF_UNIX socket; exposed to agent harness |
| Preflight | `scripts/preflight.sh` | `.claude/plugin/hermes_chrome/scripts/preflight.sh` | Bring bridge to steady state |
| Diagnose | `scripts/diagnose.py` | (synced) | JSON health probe used by preflight |
| Sync | `scripts/sync.sh` | (not deployed; run from repo) | Deploys everything above + reloads via socket |

---

## Hard-won lessons — read before editing anything

### Service worker reload doesn't refresh content scripts in already-open tabs

**Symptom:** `sync.sh` runs, "Bridge ready" prints, but actions still fail with `"Content script did not respond after injection"` on the active tab.

**Why:** Chrome MV3 reloads the service worker on `chrome.runtime.reload()` (which is what the bridge's sync hot-reload triggers). The SW's new code is live, but content scripts in already-open tabs are the OLD instance. The new SW tries `chrome.tabs.sendMessage` to them — they don't respond because the new SW's message protocol doesn't match.

**Fix:** Reload the affected tab (any URL change including a cache-bust query forces a fresh content-script injection via the `chrome.tabs.onUpdated` listener). The bridge does this automatically for `goto` actions; for `useSelectedTab: True` with no `goto`, the operator must reload the tab manually. Document this when modifying sync flow.

**Where this lives:** `service_worker.js` — auto-inject runs on `chrome.tabs.onUpdated` `status: complete`.

### The bridge socket is a shared resource across Claude sessions

**Symptom:** Mid-test, the active tab unexpectedly changes URL, or actions land in a tab you didn't expect.

**Why:** `~/.hermes/run/chrome-bridge.sock` is one process-wide AF_UNIX socket. Multiple Claude Code sessions, terminal commands, and skill scripts all connect to it concurrently. Whatever sends the most recent action wins.

**Fix:** Before a multi-step bridge interaction, take a `page_context` snapshot. If the URL doesn't match what you expected, another session navigated. Don't fight it — recover with explicit `goto` + `useSelectedTab: False` (opens a fresh tab so other sessions don't share state with you). Hard rule: **never assume the active tab between two bridge calls is the same tab**.

### `useSelectedTab: True` fails when the active tab is `chrome://`

**Symptom:** `goto` returns `"Tab is no longer available"` or content script never injects.

**Why:** Chrome refuses content-script injection on `chrome://`, `about:*`, `file://`, and the new-tab page. With `useSelectedTab: True`, the bridge tries to use the current tab — fails before `goto` runs.

**Fix:** When you don't control the tab state, default to `useSelectedTab: False` for `goto` actions. This opens a fresh tab on the target URL. After that, use `True` to continue working in the same tab.

### `evaluate` action parameter is `expression`, not `script`

**Symptom:** `evaluate` returns `Failed to deserialize params.expression — BINDINGS: mandatory field missing`.

**Why:** Easy mistake when copying patterns from Playwright (`page.evaluate(script)`) or CDP (`Runtime.evaluate({expression})`).

**Fix:** Use `{"type": "evaluate", "expression": "..."}`. The bridge's action contract follows CDP's `Runtime.evaluate`, not Playwright's surface. If you change the parameter name in `service_worker.js`, also update `tools.py` and every reference in `operate.md` + this handbook.

### CDP path was abandoned. Do not re-introduce `cdp_bridge.py`.

**Symptom:** A previous agent (claude opus) re-introduced `cdp_bridge.py` (577 lines), `start_chrome_cdp.sh`, and the related sync wiring in commit `2a4789d`. Reverted in commit `ef86ae8`.

**Why:** The CDP path is dead architecture. The current bridge is extension-only (manifest + service worker + native messaging + AF_UNIX socket). `cdp_bridge.py` declared "Replaces the native-messaging extension path entirely" — which is the *opposite* direction. The SKILL.md `Hard rules` section explicitly forbids it.

**Fix:** Before committing any new file in `.claude/plugin/hermes_chrome/`, grep the codebase for who imports/invokes it. If nothing references it, it's dead. (This is the [[verify-new-file-wiring-before-commit]] memory.) Doctrine/code mismatches in commit bodies (e.g. "SKILL.md says no CDP but we ship cdp_bridge.py") are a STOP signal — pause and ask the operator, don't ship-with-a-note.

### MV3 isolated-world CSP forbids inline `<script>` injected by content scripts

**Symptom:** A content script injects HTML containing `<script>` tags into the page. The HTML renders but no JS executes. DevTools console (filter: extension errors) shows `Executing inline script violates the following Content Security Policy directive 'script-src 'self' 'wasm-unsafe-eval' 'inline-speculation-rules' chrome-extension://...'`.

**Why:** When a content script inserts an inline `<script>` into the page DOM, Chrome applies the **extension's** isolated-world CSP — which forbids `unsafe-inline` and you cannot relax it in MV3. The page's own CSP is unrelated.

**Fix:** Serve the script body from the extension's URL via `<script src="chrome-extension://<id>/.../runtime.js">`. The extension URL is in the CSP's `script-src 'self'` for content-script-injected content. Inline blocked; `src` allowed. Add the runtime file to `web_accessible_resources` in `manifest.json` so the page can fetch it.

**Example:** `feedback-widget.js` does this — strips `<script>` from the mounted HTML, then appends a separate `<script src=…>` for the runtime.

### Native host runs in WSL — Windows manifest invokes `wsl python3`

**Symptom:** Native host appears to start but immediately crashes; popup shows "Loaded ✓" but `chrome-bridge.sock` is missing.

**Why:** On Windows, Chrome's native-messaging manifest registers a `.bat` wrapper that invokes `wsl python3 /path/to/native_host.py`. If WSL isn't running or Python isn't on PATH, the launch silently fails.

**Fix:** `preflight.sh` validates this end-to-end. If it auto-fixes via `chrome-wake`, the WSL invocation succeeded. If it can't fix, the diagnose.py output tells you exactly which step (registry key, batch file, python3 in PATH, native_host.py file existence) failed.

### Extension uses `chrome.debugger` for some actions — DevTools collision possible

**Symptom:** Some actions return `"Another debugger is already attached"`.

**Why:** Chrome allows only one debugger client per tab. If DevTools is open on the same tab the agent is trying to control, `chrome.debugger.attach` fails.

**Fix:** Close DevTools on the target tab, OR `close_tab` then `goto` to create a fresh tab without DevTools. The bridge doesn't currently auto-recover from this; if you change attachment logic, add the recovery path in `service_worker.js` and document it here.

### `sync.sh` mirrors agent-feedback's overlay.html — keep the dependency one-way

**Symptom:** Editing `extension/content-scripts/overlay.html` directly works once but gets clobbered on the next sync.

**Why:** `scripts/sync.sh` reads the canonical overlay from `.claude/skills/agent-feedback-artifact/references/overlay.html`, copies it to `extension/content-scripts/overlay.html`, and extracts the IIFE body to `feedback-widget-runtime.js` via awk. Any direct edit to the extension copies is overwritten.

**Fix:** Edit the canonical file in the agent-feedback-artifact skill. Then run `sync.sh` to propagate. If you need a feedback-widget change that's hermes-chrome-specific (not a capability change), that's a sign the boundary is wrong — escalate before adding plugin-only widget logic.

### Don't hide the cursor around `elementFromPoint` — it flashes opacity

**Symptom:** Operator sees the cursor briefly fade out or disappear on every click. With several clicks queued, it looks like the cursor is gone "for a couple of seconds."

**Why:** Earlier `click()`, `tripleClick()`, `rightClick()`, `dblClick()`, `focusAndType()`, `keyPress()`, `dragTo()` each did `classList.remove('hermes-visible') → elementFromPoint → classList.add('hermes-visible')`. The host CSS has `transition: opacity 0.2s ease`, so each toggle ran the fade animation — visible flicker on every click. The hide was added defensively, assuming `elementFromPoint` would return the cursor element.

**Fix:** Never hide the cursor for hit-test. The cursor host has `pointer-events: none`, which makes `elementFromPoint` skip it natively (per CSSOM spec). All 7 functions now call `elementFromPoint` directly without toggling visibility. **Do not re-introduce the hide/show dance** under the rationale "to make elementFromPoint work" — it never needed it.

### Logging hygiene — `console.error` is reserved for real errors

**Symptom:** Operator opens the extension's Errors page (chrome://extensions/?errors=…) and finds it cluttered with informational traces like `runBrowserAction: cursor_move, tabId=…`, `sendToContentScript: starting click`, etc. Real errors get lost in the noise.

**Why:** Debug traces in `service_worker.js` were written with `console.error()` (carryover from initial trace-and-find-bugs phase). Chrome's MV3 Errors page surfaces `console.error` and uncaught exceptions; `console.log/debug/info` go to the regular console only.

**Fix:** Use `console.error` ONLY when something has actually gone wrong (a caught exception, a contract violation, a state the agent cannot recover from). For traces, use `console.debug()` (filtered by default) or remove entirely. The 4 stray traces (`sendToContentScript: starting/done`, `runBrowserAction:`) have been deleted; if you re-add tracing for a debug session, gate it behind a `DEBUG` const or use `console.debug`.

### `createOverlay()` must preserve cursor position + visibility across re-injection

**Symptom:** After an extension reload or service-worker idle restart, the cursor element is at (-100, -100) with `opacity: 0` until the next `cursor_move`. From the operator's perspective the cursor vanished mid-flow.

**Why:** `createOverlay()` removed the existing cursor element and created a fresh one with the default CSS (`opacity: 0`, transform at `-100, -100`). The IIFE's closure variables (`cursorX/Y`, `isVisible`) are reset on re-injection. Until the agent issued another `cursor_move`, the cursor was invisible at the corner.

**Fix:** Before removing the old element, read its `style.transform` and `classList.contains('hermes-visible')`. After creating the new element, restore the transform, parse it back into `cursorX/Y`, and re-add `hermes-visible` if it was set. The cursor stays parked where it was, visibly. **Whenever you change `createOverlay()`, preserve this contract.**

### `popup.js` init must be fault-isolated — never gate a critical control behind a throwable `await`

**Symptom:** A new popup feature with an unguarded `await` (e.g. `chrome.storage.local.get`) placed early in the `DOMContentLoaded` handler silently **bricks the whole popup** — the Feedback Mode toggle and status panel never wire up, because one throw aborts the rest of the async handler.

**Why:** The handler is one async function running independent concerns sequentially. With no fault isolation, ordering decides survival: any `await` that throws skips everything after it. Critical controls placed *after* a fragile optional feature die with it.

**Fix:** Each concern runs in its own guard via `safeInit(label, fn)` (try/catch + `console.error` + non-fatal `err` surface) so a failure degrades alone. **Order critical controls first** (status → tab/content-script → Feedback Mode toggle), optional features last (queue-origin). **Attach interaction listeners (`addEventListener`) BEFORE any throwable `await`** so the control is operable even if its state read fails. When adding any popup/service-worker init feature, isolate it the same way — an optional feature must never precede or share a failure path with a critical control. (Regression-tested: with `chrome.storage.local.get` throwing, the toggle's click listener still attaches.)

---

## Diagnostic recipes

### "Action returns 'Content script did not respond after injection'"

1. `bash .claude/plugin/hermes_chrome/scripts/preflight.sh` — must exit 0.
2. If preflight prints `⚠ Content script blocked on active tab`, the active tab is `chrome://` or an error page. Use `useSelectedTab: False` with a `goto` to a real URL.
3. If preflight is clean but action still fails → **stale content script** from a recent extension reload. Reload the affected tab (any URL change works) and retry.
4. If a tab reload doesn't fix it → there might be a CSP conflict from another installed extension. Check DevTools console for CSP violations.

### "Bridge socket present but no actions execute"

1. `lsof ~/.hermes/run/chrome-bridge.sock` — does Chrome's native host hold it?
2. `ps aux | grep native_host` — is the python process running? If no, preflight should auto-restart it.
3. `tail -50 ~/.hermes/chrome-bridge/native_host.log` (if your build writes one) — last error?
4. Restart from scratch: kill native_host, reload the extension at `chrome://extensions`, re-run `preflight.sh`.

### "Action succeeded but the result is wrong/empty"

1. Bypass the bridge: open the same page in Chrome directly, run the equivalent JS in DevTools console.
2. If DevTools confirms the page state, the bug is in the bridge's translation (e.g. `getPageContext` filter logic in `cursor-agent.js`).
3. If DevTools also shows the wrong state, the page itself hasn't reached the expected state — add a `wait_for_selector` step before the read.

### "Tabs keep changing under me"

Another Claude session is using the bridge. Use `useSelectedTab: False` to open a tab whose state only your session controls. Don't try to coordinate via session names alone — `session_name` groups tabs in the UI but doesn't isolate the socket.

---

## Editing conventions

- **Always edit in the repo (`.claude/plugin/hermes_chrome/`).** Never edit the installed copy under `~/.claude/plugin/` or `~/.hermes/` directly — `sync.sh` will overwrite it.
- **Run `sync.sh` after every change.** No exceptions. The `Hard rules` in `SKILL.md` say this explicitly. The sync also hot-reloads the extension via the bridge socket.
- **After sync, expect open tabs to need a reload.** Document this in your turn output so the operator knows.
- **Adding a new action?** Update `service_worker.js` handler + `cursor-agent.js` (if content-side) + `tools.py` (the python-side contract) + `operate.md` (action reference) — four places.
- **Never widen permissions in `manifest.json` without justification.** MV3 reviewers (Chrome Web Store) will flag broad permissions. Even for unpacked dev installs, every permission added is attack surface.
- **`web_accessible_resources` must list every file a content script's `<script src>` will load from the extension URL.** If you forget it, the page can't fetch the file → silent failure → CSP-error in console (sometimes).
- **`debugger` permission stays.** Some actions need `chrome.debugger.attach` for things the extension API doesn't expose. Removing it would break those paths.
- **Never re-introduce `cdp_bridge.py` or any CDP transport.** See the dead-code lesson above. If you genuinely need CDP for a new capability, talk to the operator first — there's a design reason CDP was removed.
- **Token efficiency for the agent calling tools.py:** `page_context` is ~1 KB, `snapshot` is 8–30× larger. Default to `page_context`. Only escalate to `snapshot` when you need selectors for elements not in headings/nav/buttons/inputs.

---

## Cross-references

- Action reference + patterns: [`operate.md`](operate.md)
- Diagnosis + per-surface fixes: [`optimize.md`](optimize.md)
- Skill entry point: [`SKILL.md`](../SKILL.md)
- Plugin source: `.claude/plugin/hermes_chrome/`
- Feedback widget capability (uses this bridge for delivery): `.claude/skills/agent-feedback-artifact/`
