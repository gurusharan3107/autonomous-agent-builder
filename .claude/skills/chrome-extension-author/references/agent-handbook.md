# Agent Handbook — modifying & troubleshooting chrome-extension-author

Read this before editing this skill's source or templates. `operate.md` is for USING the skill (scaffolding an extension); `optimize.md` is for fixing the *generated* extension's runtime issues; this handbook is for editing the SKILL ITSELF.

---

## Architecture map

```
chrome-extension-author/
├── SKILL.md                              # Router + decision aid (loaded every activation)
├── scripts/
│   └── validate.sh                       # Self-validate (calls create-skill audit)
├── references/
│   ├── interview.md                      # The AskUserQuestion script (Batch A + B)
│   ├── operate.md                        # Procedure: Interview → Plan → Scaffold → Verify
│   ├── best-practices.md                 # Defaults + the rules' rationale
│   ├── optimize.md                       # Diagnosing the GENERATED extension
│   ├── agent-handbook.md                 # This file — modify the skill itself
│   ├── visual-presence.md                # Cursor / badge / toast / overlay patterns
│   ├── native-messaging.md               # Unix-socket bridge pattern from hermes-chrome
│   ├── icon-design.md                    # One SVG → four PNGs workflow
│   ├── mv3-lifecycle.md                  # SW + content-script lifecycle, ensureContentScript
│   └── csp-and-injection.md              # Isolated vs main world, web_accessible_resources
└── templates/
    ├── manifest.json.template
    ├── service_worker.js.template
    ├── content-script.js.template
    ├── cursor.js.template                # Hardened per hermes-chrome lessons
    ├── popup.html.template + popup.js.template
    ├── native-host.py.template + native-host.json.template
    ├── icon-minimal.svg.template
    ├── icon-detailed.svg.template
    ├── icon-cursor.svg.template
    └── icon-brand.svg.template
```

The skill's job ends after scaffolding. The generated extension is the operator's code.

---

## Hard-won lessons — read before editing anything

### `cursor.js.template` must not be "simplified"

**Symptom:** Operator regenerates an extension and reports cursor flickering on clicks or vanishing after extension reload.

**Why:** Someone shortened `cursor.js.template` by removing the prior-state preservation in `createOverlay()` or by reintroducing the `classList.remove('hermes-visible')` → `elementFromPoint` → `classList.add('hermes-visible')` pattern. Both were specifically fixed in hermes-chrome after operator-visible regressions.

**Fix:** Don't simplify. The host has `pointer-events: none` so `elementFromPoint` already skips it (no defensive hide needed). `createOverlay` must read the prior element's `style.transform` and `hermes-visible` class before destroying it, then restore them on the new element.

**Where this lives:** `templates/cursor.js.template`.

### `web_accessible_resources` in MV3 takes objects, not strings

**Symptom:** Manifest fails to parse on install ("invalid web_accessible_resources").

**Why:** MV2 used a flat array of paths (`["runtime.js"]`); MV3 uses an array of `{resources, matches}` objects. Easy to revert by autocomplete.

**Fix:** `manifest.json.template` always emits the MV3 object shape:
```json
"web_accessible_resources": [{ "resources": ["runtime.js"], "matches": ["<all_urls>"] }]
```

**Where this lives:** `templates/manifest.json.template`.

### Async `onMessage` handlers MUST return `true`

**Symptom:** Operator says "the popup never gets a response from the service worker."

**Why:** `chrome.runtime.onMessage` synchronous handlers that start an async response without returning `true` close the message channel immediately. The sender's promise never resolves.

**Fix:** Service-worker template's `onMessage` listener always returns `true` for any async path:
```js
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "ping") { sendResponse({ ok: true }); return; }
  handleAsync(msg).then(sendResponse);
  return true;  // <-- non-optional
});
```

**Where this lives:** `templates/service_worker.js.template`.

### `chrome://` URL guards are non-optional in `tabs.onUpdated`

**Symptom:** Errors page floods with "Cannot access chrome:// URL" each time the operator opens Chrome's settings.

**Why:** Content scripts can't inject on `chrome://`, `about:`, `view-source:`, or new-tab page. Without an early-return guard, the SW tries on every tab navigation including these.

**Fix:** Service-worker template guards before injection:
```js
if (!tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("about:")) return;
```

**Where this lives:** `templates/service_worker.js.template`.

### Permission scope creep at interview-time

**Symptom:** Generated extension shows a loud "Read your data on all websites" install warning even though the operator's intent was a single-site tool.

**Why:** `host_permissions: ["<all_urls>"]` was scaffolded because the operator picked "all_urls" at Q6 (permissions scope) — possibly without understanding the install-warning cost.

**Fix:** At interview-time, if Q1 (purpose) doesn't name a universal use case AND Q6 selects all_urls, the skill must ask a follow-up: "Are you sure? `activeTab` will work for this purpose and won't show a permissions warning at install."

**Where this lives:** `references/interview.md` cross-validation rule.

### The `extensions/` target directory is at REPO ROOT, not inside `.claude/`

**Symptom:** Operator can't find the generated extension; ends up looking in `.claude/skills/chrome-extension-author/...`.

**Why:** First instinct is to scaffold under the skill's directory. Wrong — the skill's directory is the SKILL'S source, not the OUTPUT of running the skill.

**Fix:** Default `extensions/<name>/` at repo root. The skill's `operate.md` makes this explicit. If the repo already has an `extensions/` dir, it's used; otherwise `mkdir -p` creates it.

**Where this lives:** `references/operate.md` § Scaffold.

---

## Editing conventions

- **Always edit the templates** (not generated extension files). The generated extension is the operator's code — once scaffolded, it diverges from the template.
- **Test by scaffolding a sample extension** after every template change. Load it in Chrome. Verify zero Errors-page entries.
- **Self-validate** after every skill edit: `.claude/skills/chrome-extension-author/scripts/validate.sh`.
- **Preserve cross-references.** If you rename a reference file, grep for incoming links from SKILL.md and other references.

## Cross-references

- Action reference + patterns: [`operate.md`](operate.md)
- Diagnosis + per-surface fixes (for the GENERATED extension): [`optimize.md`](optimize.md)
- Defaults + calibration: [`best-practices.md`](best-practices.md)
- Skill entry point: [`SKILL.md`](../SKILL.md)
- Templates: [`../templates/`](../templates/)
