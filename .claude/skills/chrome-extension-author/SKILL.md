---
name: chrome-extension-author
description: "Scaffold a high-quality Chrome MV3 extension that is both operator-friendly (visible activity, no UX glitches, sensible permissions) and agent-friendly (deterministic message contracts, idempotent lifecycle, recoverable state). Asks the operator a structured set of requirements via AskUserQuestion (purpose, architecture, UI surfaces, native messaging, visual presence, icon style, permissions, lifecycle, storage), then generates the manifest, service worker, content scripts, optional popup, optional native messaging host, and SVG icon set. Encodes the hard-won lessons from hermes-chrome: cursor/indicator must stay visible, no opacity-flash on rapid toggles, preserve state across service-worker re-injection, debounce chatty event sources, never route info traces through console.error, guard every parse of user-controlled storage. Use when the operator says 'build a Chrome extension', 'create a browser extension', 'scaffold a Chrome MV3 extension', 'make a Chrome plugin', 'author an extension for X', 'add a Chrome extension to this repo', 'I need an extension that...', or any variant pairing 'Chrome / browser / MV3' with 'extension / plugin / addon' and 'create / scaffold / build / author / make / add'."
allowed-tools: Read, Write, Edit, Bash, AskUserQuestion
---

# chrome-extension-author — scaffold operator-friendly + agent-friendly Chrome MV3 extensions

Operators want a working extension installed in Chrome that they can use today. Agents want a codebase whose lifecycle, message contracts, and state preservation they don't have to relearn. This skill produces both from one structured requirements interview, scaffolding the extension's source tree with the patterns proven by hermes-chrome.

> **Self-validate after edits.** Run `./scripts/validate.sh` from the skill directory.

## Workflow (every run)

One pass: **Interview → Plan → Scaffold → Verify**. The Interview asks the operator the questions in this order via `AskUserQuestion`; each answer narrows the file set and the templates used.

| # | Question | Drives |
|---|---|---|
| 1 | Primary purpose (free-form via *Other*) | The description seed + default permission scope |
| 2 | Architecture pieces (multi-select: SW / content scripts / popup / native messaging) | Which file templates get scaffolded |
| 3 | Visual presence (badge / overlay cursor / toast / none) | Whether `visual-presence.md` patterns are included |
| 4 | Native messaging required? (yes / no) | Whether the Python native host + JSON manifest are scaffolded |
| 5 | Icon style (minimal mono-glyph / detailed / animated / branded text) | Which SVG icon template seeds the icon set |
| 6 | Permissions scope (activeTab / specific hosts / all_urls) | The `permissions` + `host_permissions` arrays in manifest |
| 7 | Storage (chrome.storage / none / IndexedDB) | Whether the `safeParseArray` defensive pattern is included |

Detailed question text + answer-to-template mapping → [`references/interview.md`](references/interview.md).

## Hard rules

1. **MV3 only.** Manifest v3, service-worker-based, no persistent background page. The browser will drop MV2 — don't scaffold dead code.
2. **The visible indicator never parks at viewport edges or off-screen.** If the extension has any operator-facing presence (cursor, toast, badge, overlay), its at-rest position must be informative — on the element just modified, the control just acted on, or a sensible center. Operators infer "is the agent working?" from where the indicator stops.
3. **No opacity-transition flashes on rapid toggles.** If you `classList.remove → DOM op → classList.add` synchronously on an element with `transition: opacity 0.2s`, the operator sees it flicker on every action. Either skip the toggle (the cursor host has `pointer-events: none` already), or use a no-transition property (`visibility: hidden`).
4. **`createOverlay` (or any re-init path) must preserve state.** Service-worker idle restart / extension reload re-runs content scripts. Before destroying the prior overlay element, read its position + visibility class; after creating the new one, restore them. Without this, the cursor / indicator silently resets to off-screen until the next action.
5. **Debounce chatty event sources.** `fs.watch`, `MutationObserver`, kernel inotify, native re-deliveries can fire 2–7× per logical change. Add a 30 ms trailing-edge coalesce before any broadcast.
6. **`console.error` is reserved for real errors.** Chrome MV3 surfaces `console.error` and uncaught exceptions to the extension's Errors page. Debug traces go through `console.debug` (filtered by default) or are removed before ship.
7. **Every parse of user-controlled storage is guarded.** `JSON.parse(localStorage.getItem(key) || "[]")` throws on corrupted data and can crash the IIFE before the extension loads. Wrap in `try/catch`; on error, `removeItem` the bad key and return a safe default.
8. **MV3 isolated-world CSP blocks inline `<script>` injected by content scripts.** If the extension injects runtime JS, serve it via `<script src=chrome-extension://...>` from `web_accessible_resources`, not as an inline string.
9. **Service-worker → content-script messages must be idempotent.** SW idles after ~30s; the same message may be re-delivered after restart. Handlers must tolerate duplicate or out-of-order delivery.
10. **WSL2 networking gotcha (if native host on Linux).** Chrome on Windows reaches Node bound to IPv6 wildcard via `localhost`, NOT `127.0.0.1`. The native messaging host must bind to `::` (or `0.0.0.0`) and the client uses `localhost`.
11. **Never inject content scripts on `chrome://`, `about:`, `view-source:`.** Chrome blocks them; the SW's `tabs.onUpdated` handler must guard.

## Closeout — CLOSEOUT (mandatory)

After scaffolding completes:

- Run the new extension's `scripts/validate.sh` (manifest valid, every referenced file exists, MV3 schema check). Must exit 0.
- Print install instructions — exact path to load in `chrome://extensions/` (Load unpacked → `<repo>/extensions/<name>/`). On WSL2, the path is the `\\wsl$\<distro>\...` UNC form.
- Print test instructions — open `chrome://extensions/` Errors page after loading to confirm zero errors; click the extension icon to confirm the popup (if any) opens.
- Record the architecture choices in the new extension's own `agent-handbook.md` so the next agent who edits the extension finds the rationale.
- Suggest follow-ups: hot-reload during development, automated install via `scripts/install.sh`, the hermes-chrome bridge pattern if the extension needs to talk to a local agent.

## Load references on need

| When | Load |
|---|---|
| The interview itself — exact questions, options, and answer→template mapping | [`references/interview.md`](references/interview.md) |
| Step-by-step scaffolding procedure (Interview → Plan → Scaffold → Verify) | [`references/operate.md`](references/operate.md) |
| Skill defaults — MV3 conventions, permissions hygiene, message-contract style | [`references/best-practices.md`](references/best-practices.md) |
| Diagnosing a runtime issue in the *generated* extension (cursor missing, SW idle, CSP error, native host crash, console.error flood) | [`references/optimize.md`](references/optimize.md) |
| Modifying or extending this skill itself | [`references/agent-handbook.md`](references/agent-handbook.md) |
| Visible cursor / overlay / indicator patterns to encode in the generated extension | [`references/visual-presence.md`](references/visual-presence.md) |
| Native messaging needed (OS-level integration) — Unix-socket pattern proven in hermes-chrome | [`references/native-messaging.md`](references/native-messaging.md) |
| Icon system (16/32/48/128 PNG from one SVG source) + optional animated cursor SVG | [`references/icon-design.md`](references/icon-design.md) |
| MV3 service-worker lifecycle (idle restart, re-injection, ensureContentScript, keepalive) | [`references/mv3-lifecycle.md`](references/mv3-lifecycle.md) |
| CSP + injection model (isolated vs main world, `web_accessible_resources`, runtime script load) | [`references/csp-and-injection.md`](references/csp-and-injection.md) |
| Scaffolding templates (manifest, SW, content script, popup, native host, icon SVG) | [`templates/`](templates/) |
