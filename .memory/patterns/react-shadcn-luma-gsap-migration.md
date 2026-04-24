---
title: React + shadcn Luma + GSAP migration patterns
type: pattern
date: 2026-04-13
phase: implementation
entity: frontend
tags: [react, shadcn, gsap, spa, vite]
status: active
---

## Approach

Specific gotchas and patterns discovered during the Vite+React+shadcn/Luma migration.

### shadcn/ui Luma initialization (non-interactive)

```
/c/Program Files/nodejs/npx.cmd shadcn@latest init --template vite --base radix --preset luma --yes --force
```

**Prerequisites (must exist before running shadcn init or it fails):**
1. `src/index.css` must contain `@import "tailwindcss";`
2. `@tailwindcss/vite` plugin must be in `vite.config.ts`
3. Both `tsconfig.json` AND `tsconfig.app.json` must have `baseUrl: "."` + `paths: {"@/*": ["./src/*"]}`
4. Add `"ignoreDeprecations": "6.0"` to `tsconfig.app.json` for TS7 + Tailwind v4 compat

### FastAPI SPA fallback route order

Routes MUST be in this order or `/health` returns 404:
1. Health check route (`@app.get("/health")`)
2. All `/api/*` routers
3. `/assets` static mount
4. SPA catch-all LAST: `@app.get("/{full_path:path}")` returning `index.html`

DO NOT use `app.mount("/", StaticFiles(html=True))` — it intercepts all routes including `/health`.

### GSAP + React pattern

- `@gsap/react` `useGSAP` hook with `{ scope: containerRef }` — scoped selectors
- Store animation hooks in `src/hooks/use-*-animations.ts` files
- GSAP only on Board + Metrics pages (not Approvals)
- `revertOnUpdate: true` needed if data-driven animation targets change

## When To Reuse

Any time frontend components are added/modified, or if shadcn/Luma needs re-init. The SPA route order gotcha applies whenever new API routes are added.

## Evidence

Discovered during migration session (2026-04-13). SPA route bug caused 30+ minutes of debugging before identifying `StaticFiles(html=True)` as the interceptor.
