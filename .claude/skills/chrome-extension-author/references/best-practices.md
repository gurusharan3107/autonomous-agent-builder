# chrome-extension-author — Best Practices

Skill-specific defaults and conventions. Read on first use; internalize. The SKILL.md hard-rules table is enough thereafter.

This file captures the **why** behind the rules — and the calibration around them.

---

## Operator-vs-agent compatibility — both audiences first-class

Most Chrome extensions optimize for one audience: either a human clicking the icon, or an automation pipeline driving via native messaging. Production extensions need both:

- **Operator** sees activity through visible indicators (cursor / badge / toast) and the popup UI. Confused operator = bad extension.
- **Agent** drives via messages and expects idempotent, deterministic responses. Flaky messaging = bad extension.

Every scaffolded file should be reviewed through both lenses. The rules below are derived from running into the operator-vs-agent mismatch the hard way in hermes-chrome.

---

## Permissions hygiene

| Scope | When | Risk |
|---|---|---|
| `activeTab` | Operator-triggered, single-page interactions | Lowest — no install warning, single tab at a time |
| Specific host patterns | Domain-scoped tools (`"*://*.example.com/*"`) | Medium — install warning on broad patterns |
| `<all_urls>` | Universal extensions only | Loud install warning; many users decline |

**Default to `activeTab`.** Broaden only when the requirement justifies it. The skill MUST warn the operator at interview-time if Q1 (purpose) doesn't justify `all_urls`.

For `host_permissions` vs `permissions["host"]`: in MV3, page-content access goes in `host_permissions`. Old MV2 patterns of declaring URLs under `permissions` are silently downgraded.

---

## Message-contract conventions

When the extension communicates between service worker, content scripts, popup, and (optionally) native host, the message envelope shape matters.

**Inside the extension** (SW ↔ CS ↔ popup):

```js
{ action: "verb", args: { ... }, requestId: "<uuid>" }
```

- Always a `requestId` for idempotency. The same message may arrive twice after SW idle restart.
- `action` is a verb (`click`, `getStatus`, `inject`). Operators write code against verbs, not types.
- Responses MUST always include `{ success: true|false }` plus the result or error reason.

**Native messaging** (SW ↔ native host process):

- Use line-delimited JSON over the Unix socket (one JSON object per line, `\n`-terminated).
- Set `socket.setNoDelay(true)` on the server side — TCP Nagle adds 4–9s latency to small writes on WSL2.
- Use `res.flushHeaders()` for SSE-style streams.
- Bind to `::` (IPv6) on WSL2; Chrome on Windows reaches Node-bound localhost that way but NOT `127.0.0.1`.

---

## State preservation

Two state surfaces:

- **Service worker** — wiped on idle restart (~30s no activity). Use `chrome.storage.local` for anything that must survive.
- **Content scripts** — wiped on extension reload AND on page navigation. Local state (cursor position, overlay UI state) needs explicit preservation in the IIFE re-init path; see [`visual-presence.md`](visual-presence.md).

**Never assume the prior closure's variables are still alive.** Always read from the DOM / `chrome.storage` on init, restore visible state, then proceed.

---

## CSS-transition hygiene

Operator-visible elements with `transition: opacity 0.2s ease` will fade out and back in any time you toggle `hermes-visible` (or equivalent) synchronously around a DOM operation. The user perceives a flicker. Three rules:

1. **Don't toggle visibility around `elementFromPoint`** — the cursor's host has `pointer-events: none` so it's already skipped. No defensive hide needed.
2. **If you must hide briefly**, use `visibility: hidden` (no transition) rather than `opacity: 0`.
3. **Test with rapid clicks** — single click never triggers visible flicker, but 3 clicks in 100ms expose the bug.

---

## Icon design — one SVG, four PNGs

Manifest declares icons at 16/32/48/128px. Workflow:

1. Author a single `images/icon.svg` (operator picks the style at interview-time).
2. At scaffold time, rasterize each size with `rsvg-convert` (or `inkscape --export-png`, or `magick convert`).
3. The 16px is the toolbar size — verify it's legible at that size before shipping. Detailed pictograms degrade poorly; minimal mono-glyphs survive.

If the extension also has an animated overlay cursor (visual-presence = overlay cursor), the cursor SVG is a separate file from the toolbar icon — same style family, but a different shape (typically a pointer or arrow rather than a glyph). See [`icon-design.md`](icon-design.md).

---

## Logging hygiene

`console.error` and uncaught exceptions surface on `chrome://extensions/?errors=<id>`. The Errors page is the operator's window into "is this extension healthy?" — polluting it with traces hides real problems.

- `console.error(msg, e)` — caught exceptions, contract violations, unrecoverable states
- `console.warn(msg)` — recoverable anomalies the operator should know about
- `console.log` / `console.info` — generally avoid in shipped code; if needed for operator-visible status, prefer a real UI surface (badge, toast)
- `console.debug` — trace points for development; filtered by default

If you find yourself adding traces during a debug session, gate them behind a `const DEBUG = false;` const so a future grep can clean them up.

---

## Manifest hygiene

- `manifest_version: 3` always
- `name`, `description` — what the operator sees in the install prompt. Lead with what it does, not what it's called.
- `version` — semver-ish (`"0.1.0"`). Auto-update is not the agent's problem; just start sensible.
- `permissions` — minimum that works. Each permission is an item in the install warning.
- `host_permissions` — separate from `permissions` in MV3
- `background.service_worker` — relative path; no `"persistent": true` (that's MV2)
- `action.default_icon` — object keyed by size, NOT a single string
- `web_accessible_resources` — list every file the content script needs to inject (runtime JS, SVGs, fonts). If you skip this, the file 404s silently in the page console.

---

## When the extension talks to a local agent

If the extension exists primarily to give an agent control of Chrome (Q1 = "Agent automation bridge"), the architecture follows the hermes-chrome shape:

1. Native messaging host as a long-lived Python process bound to a Unix socket.
2. Service worker connects via `chrome.runtime.connectNative` on demand; re-connect after SW idle.
3. Content script provides DOM access; SW relays between native host and CS via `chrome.tabs.sendMessage`.
4. The agent's process speaks to the Unix socket; never to Chrome directly.

This four-tier path (agent → socket → native host → SW → CS → page) sounds heavy but is what makes the system survive SW idles, tab navigations, and extension reloads without losing state. See [`native-messaging.md`](native-messaging.md).
