# Icon design — one SVG, four PNGs

Chrome MV3 declares icons at 16/32/48/128 pixels. The workflow: author one SVG, rasterize to four PNGs at scaffold time.

## The four sizes

| Size | Where shown | Design constraint |
|---|---|---|
| 16px | Toolbar (compact view), favicon-like | Must be readable. No fine detail. Single shape, single bold color. |
| 32px | Toolbar (regular DPI), small UI | Some detail OK, but legibility wins |
| 48px | Extension management page, install dialog | Full detail visible |
| 128px | Chrome Web Store, install dialog primary | Brand-quality render; pixel-grid tuning matters less |

**Design for 16px first.** If the glyph doesn't survive 16px, it's the wrong glyph. Add detail for 48/128 if you have brand requirements; never reverse.

## Four supported styles (operator picks at interview-time)

### Minimal mono-glyph
Single shape (circle, square, arrow, drop) on a flat or gradient background. Two colors max. Survives 16px perfectly. Default for utilities.

### Detailed pictogram
Recognizable object (gear, eye, bridge). Two-color, more visual identity. Tradeoff: degrades at 16px. Provide a simplified 16px variant if you want crispness at that size.

### Animated cursor / pointer
Use ONLY if the extension also has an on-page cursor presence. The toolbar icon mirrors the cursor's shape so operators connect "the thing on the page" ↔ "the thing in the toolbar." The SVG is the same file used as the in-page cursor (via `chrome.runtime.getURL("images/pointer.svg")`).

### Branded text mark
1–3 letter monogram in a custom typeface. Effective for products with strong brand. Legible at 32px+; 16px usually needs a single character.

## Rasterization workflow

Scaffold-time, run for each size:

```bash
rsvg-convert -w 16  -h 16  images/icon.svg -o images/icon16.png
rsvg-convert -w 32  -h 32  images/icon.svg -o images/icon32.png
rsvg-convert -w 48  -h 48  images/icon.svg -o images/icon48.png
rsvg-convert -w 128 -h 128 images/icon.svg -o images/icon128.png
```

Alternatives:
- `inkscape --export-png=icon16.png -w 16 -h 16 images/icon.svg`
- `magick convert -background none -resize 16x16 images/icon.svg images/icon16.png`
- Online SVG-to-PNG (less reliable, not in CI)

The skill's `scaffold.sh` (or the manual `Do` steps in [`operate.md`](operate.md)) uses `rsvg-convert` by default; if not installed, fall back to ImageMagick.

## SVG authoring conventions

- **Viewbox `0 0 24 24` or `0 0 32 32`** — match Chrome's expected pixel grid.
- **Strokes ≥ 1.5 units at viewbox scale** so 16px render stays visible.
- **Use `currentColor` for stroke/fill** if the icon is monochromatic — lets the same SVG render in different colors when injected as an inline cursor.
- **Single root `<svg>`** — no wrapper `<g>` with transforms unless necessary; flat structure rasterizes cleaner.
- **No external assets** — embedded fonts, no `<image>` tags pointing to external URLs.

## Manifest reference

```json
"icons": {
  "16":  "images/icon16.png",
  "32":  "images/icon32.png",
  "48":  "images/icon48.png",
  "128": "images/icon128.png"
},
"action": {
  "default_icon": {
    "16":  "images/icon16.png",
    "32":  "images/icon32.png",
    "48":  "images/icon48.png",
    "128": "images/icon128.png"
  }
}
```

Validators check that every referenced PNG exists. The scaffolded `validate.sh` enforces this.

## If the extension has an animated cursor

The toolbar icon's SVG and the in-page cursor's SVG should share visual DNA but are separate files:

- `images/icon.svg` — the toolbar glyph (static)
- `images/pointer.svg` — the cursor for in-page overlay (may have subtle animation via CSS in the content script)

Don't try to reuse one file for both — the toolbar 16px is too small for cursor-shape detail, and the cursor is rendered at 18-24px on-page. Same designer, two files.
