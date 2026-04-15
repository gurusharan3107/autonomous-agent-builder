# LLM Council Transcript: Memory File Consolidation
**Date:** 2026-04-14
**Question:** Should we consolidate from one-file-per-memory (~500 max) to entity-level files (~15-30)?

## Advisor Responses

### The Contrarian
500 files is a vanity metric. Concurrent writes to shared entity files corrupt git history. HTML comment metadata is fragile. Keep current, archive quarterly if needed.

### The First Principles Thinker
Wrong metric. 100-150 at saturation is fine. Concurrent mutation is dangerous. HTML regresses from YAML. If forced, consolidate by type (3 files) not entity. Keep current.

### The Expansionist
Do it. Retrieval coherence, git diff hygiene, saner GC. HTML trivial. One entity = one file. Ship it.

### The Outsider
500 files fine for OS/git. Search index solves discoverability. Bundling creates write conflicts, merge risk, deletion complexity. Date subdirs if visual clutter.

### The Executor
Don't refactor on hypotheticals. Ship, observe 20-30 real memories, refactor on actual friction.

## Peer Reviews (anonymized A-E)

- **Reviews 2-5 unanimously ranked E (Executor) strongest** — only one grounded in evidence
- **All 5 reviews ranked C (Expansionist) as biggest blind spot** — dismisses real technical risks as trivial
- **Cross-cutting blind spots:** query behavior under load, access patterns, retrieval UX, zero production data

## Chairman Verdict

**Keep current design. Run 3 production sessions. Then decide.**

500 files is not a demonstrated problem. Consolidation trades known risks (concurrent writes, merge conflicts, deletion complexity) for hypothetical gains. Add retrieval instrumentation for 3 sessions, then make a data-driven decision.
