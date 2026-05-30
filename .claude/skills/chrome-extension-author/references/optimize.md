# chrome-extension-author — Optimize

Runtime diagnosis for the *generated* extension. Use when the operator reports the extension misbehaving in Chrome.

For modifying the chrome-extension-author skill itself, see [`agent-handbook.md`](agent-handbook.md).

---

## Symptom → diagnosis

### "Extension installs but does nothing"

1. Open `chrome://extensions/?errors=<ext-id>` — any red entries point at the failure directly.
2. Check the service worker console (`chrome://extensions/` → "service worker" link under the extension). If the link is gone, the SW is sleeping — click the extension's icon to wake it.
3. Verify `content_scripts.matches` in `manifest.json` actually matches the URL the operator is on. `<all_urls>` matches everything; specific patterns must include the protocol scheme.

### "Service worker shows up as inactive"

Normal — MV3 idles after ~30s. The SW will wake on the next event (alarm, message, tab update). If you need it active *now* for debugging, send a message: `chrome.runtime.sendMessage({type: "ping"})` from the extensions page DevTools.

### "Cursor / overlay / indicator vanishes mid-flow"

Two causes (both fixed in the scaffolded `cursor.js` template — if they recur, the template was edited):

1. **Opacity flash on rapid clicks** — the click handler is doing `classList.remove('hermes-visible')` → `elementFromPoint` → `classList.add('hermes-visible')`. With `transition: opacity 0.2s`, this flickers on every click. The host has `pointer-events: none`; `elementFromPoint` already skips it. Remove the hide/show dance.
2. **Reset on service-worker idle** — `createOverlay()` was called from a re-injected content script and rebuilt the element at (-100,-100) opacity 0. The scaffolded `createOverlay` reads the prior element's `style.transform` and visibility class first, then restores them. If you see this regression, that preservation logic was removed.

### "CSP error: Refused to execute inline script"

MV3 isolated-world CSP. Don't inject `<script>` with `textContent`; inject `<script src=chrome-extension://.../runtime.js>` and add `runtime.js` to `web_accessible_resources` in the manifest. See [`csp-and-injection.md`](csp-and-injection.md).

### "Native messaging host fails to connect"

In order of likelihood:

1. **Host manifest not installed** — `chrome.runtime.connectNative` requires `<host>.json` at the OS-specific Chrome native-messaging path. Run `native/install.sh` after capturing the extension ID from `chrome://extensions/`.
2. **`allowed_origins` doesn't match the extension ID** — extension IDs change on reload-unpacked unless you fix the key in `manifest.json`. Update `allowed_origins` after each unpacked install, or use a fixed `key` in the manifest.
3. **Host binary not executable** — `chmod +x native/host.py`. Chrome doesn't run non-executable hosts.
4. **WSL2 path translation** — on Windows-side Chrome with WSL host, the manifest's `path` must be a Windows-readable invocation like `wsl python3 /home/user/...`. The scaffolded `install.sh` writes this automatically when WSL is detected.

### "Errors page floods with traces"

Someone wrote `console.error("starting frob…")` for a trace. `console.error` surfaces in `chrome://extensions/?errors=`; `console.debug` does not. Replace traces with `console.debug` or remove them. The skill's `validate.sh` greps for `console.error` outside legitimate error paths and warns.

### "Permission warning on install is too aggressive"

Probably `host_permissions: ["<all_urls>"]` when `activeTab` would suffice. Re-run the interview's Q6 — most extensions only need `activeTab`.

### "Content scripts don't run on SPA route changes"

SPAs (React, Vue, etc.) don't fire `tabs.onUpdated complete` on virtual-route changes. Two options:
- **MutationObserver on `<body>`** inside the content script — detect when the SPA swaps content and re-init.
- **`chrome.webNavigation.onHistoryStateUpdated`** in the service worker — fires on SPA navigations. Use to re-inject if the CS doesn't survive.

### "Operator sees the cursor parked at the viewport edge"

Discipline violation, not a code bug. Whoever was scripting agent actions ended the last action at the wrong place. The agent should always finish on a meaningful target (the element acted on, the control just clicked). Edit the agent / driver code, not the extension.

### "WSL2: Chrome can't reach the local Node server"

Chrome on Windows + Node on WSL: localhost reaches IPv6 wildcard (`::`) but NOT `127.0.0.1`. Either bind the server to `::` or `0.0.0.0`, or use `localhost` from Chrome and ensure the host binds IPv6.

### "TCP latency is 4-9 seconds on small SSE writes"

Nagle's algorithm. The server must call `socket.setNoDelay(true)` on every connected socket and `res.flushHeaders()` for SSE. Documented in the scaffolded `service_worker.js` and `native/host.py` templates. If you stripped these, restore them.

---

## When to re-run the scaffold (vs. patch)

| Situation | Action |
|---|---|
| Single-file bug in the generated extension | Edit the file directly. Don't regenerate. |
| Architecture decision was wrong (no popup vs popup, no content script vs content script) | Re-run the interview, generate a new directory, manually migrate any operator code |
| Permission scope is wrong | Edit `manifest.json` directly |
| New requirement appears (need native messaging, didn't before) | Run the skill in "extend" mode (TODO — not yet a lane) or manually copy the relevant template files |

The scaffold is a starting point, not a recurring generator. After the first install, the extension is the operator's code; the skill's job is done.
