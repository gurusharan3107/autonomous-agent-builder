# Visual presence — operator-facing indicators

If the generated extension has any visible indicator (overlay cursor, toast, badge, animated mark), these rules apply. They come straight from hermes-chrome's hard-won lessons.

## The four indicator types

| Type | Footprint | When |
|---|---|---|
| **Toolbar badge** | Toolbar icon only; no DOM in pages | Default for most extensions |
| **Floating overlay cursor** | DOM element on the page; follows agent activity | Agent automation extensions where the operator must see where the agent is acting |
| **Toast** | Slide-in messages near a page corner | One-shot notifications |
| **Page-level overlay** | Fixed-position panel | Long-running tools (annotation widgets, dashboards) |

## Rules — all indicators

1. **At-rest position is informative.** The indicator's final location after an action tells the operator where the action landed. Never park at viewport edges, corners, or off-screen.
2. **Never auto-hide within the activity window.** Operators infer "extension stopped working" from disappearance. If you must dim after long idle, use ≥ 10s.
3. **No opacity flashes on rapid action.** CSS `transition: opacity 0.2s` looks fine on a single toggle but flickers visibly across rapid clicks. Either skip the toggle or use `visibility: hidden` (no transition).

## Rules — overlay cursor specifically

If the operator picks "Floating overlay cursor" at interview-time, the scaffolded `cursor.js` MUST encode:

1. **Host has `pointer-events: none`** — `elementFromPoint` already skips it, so no defensive remove/add of the visibility class around click handlers. Don't reintroduce the hide-flash.
2. **`createOverlay()` preserves position + visibility across re-injection.** Before destroying the prior cursor element, read its `style.transform` and `hermes-visible` class; after creating the new one, restore them. Without this, service-worker idle restart silently resets the cursor to `(-100,-100), opacity:0`.
3. **`elementFromPoint(cx, cy)` directly** — no synchronous hide/show dance around it. The host's `pointer-events: none` means the lookup returns the underlying page element correctly.
4. **z-index just below operator UI (`2147483647`)** — extension cursors compete with site toasts, lightboxes, etc. Use max-int to win, but document the rationale so it's not magic.

The scaffolded `cursor.js` template encodes all of the above. If the operator asks to extend the cursor (drag-and-drop, hover indicators, custom click animations), edit the file directly and re-validate; do not regenerate from template.

## Rules — toast / page overlay specifically

1. **Re-anchor on every state change.** If the popover / panel changes size (collapsed → expanded), re-call the placement function — don't trust the prior position.
2. **Measure with `getBoundingClientRect()`** — don't hard-code dimensions. Magic numbers (`viewport - 220px`) drift the moment the element grows.
3. **Flip-side fallback at viewport edges** — if the natural anchor would clip, fall back to the opposite side rather than truncating.

## Anti-patterns to avoid in the generated extension

- Toast that fades after 1-2s — operator may have looked away
- Cursor that auto-hides on idle — looks like a bug
- Badge that auto-clears on read — operator can't audit
- Panel that anchors to page coordinates (instead of viewport) — scrolls out of view
- Multiple indicators stacked at the same corner — operator can't tell which is active
