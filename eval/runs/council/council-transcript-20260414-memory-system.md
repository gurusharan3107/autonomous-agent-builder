# LLM Council Transcript: Per-Project Structured Memory System
**Date:** 2026-04-14
**Plan:** `~/.claude/plans/steady-drifting-garden.md`

## Original Question

Should we ship the per-project structured memory system plan as-is? What's strong, what's weak, what's missing?

## Framed Question

We're designing a per-project structured memory system for an AI agent CLI (Claude Code). The plan extends an existing workflow CLI (~1,400 lines Python) with two new modules: `workflow_memory.py` (~650 lines) for CRUD + progressive disclosure retrieval, and `workflow_memory_gc.py` (~350 lines) for 4 mechanical garbage collection rules. Key choices: pull-based retrieval, 3 memory types, 6-field frontmatter, routing.json cache with 1h TTL, correction priority in search scoring, 4 GC rules. What's strong, what's weak, what's missing?

---

## Advisor Responses

### The Contrarian

The plan is solid but has three critical failure modes. 1. Routing cache TTL is wrong. A 1h TTL means if the agent creates a memory at minute 50 and retrieves 10 minutes later against stale routing, it won't find what it just wrote. Need write-through invalidation or accept latency cliff. 2. Contradiction detection is too aggressive. Keyword overlap >0.5 between titles will create false positives constantly. "Token limit exceeded" vs "Token budgeting strategy" both match. What's the SLA for human review? Who marks it resolved? This becomes tech debt. 3. Graduation rule is fragile. Grepping CLAUDE.md for title keywords at 60% match is pattern-matching theatre. Fix the cache invalidation and graduation paths before shipping. Strong parts: frontmatter schema clean, pull-based retrieval right, separating structured memory from auto-memory sound.

### The First Principles Thinker

Pull-based retrieval is the right abstraction. Critical weakness: GC is a trust problem, not a mechanical problem. Contradiction detection via keyword overlap will produce false positives at scale. Missing cache invalidation — routing.json with 1h TTL masks a consistency bug. Underspecified: race conditions when two agents write simultaneously. Graduation at 60% grep fragile. The real risk: two separate systems (auto-memory + .memory/) without explaining why they can't be unified — bifurcation doubles maintenance.

### The Expansionist

Ship it. Pull-based progressive disclosure is exactly right. Frontmatter enforcement means every memory is queryable from day one. Composite routing keys scale from 10 to 10,000 memories. GC assuming humans review contradictions is safe. This unlocks agent learning loops — a 10x surface. Push: if corrections timestamp why they superseded a decision, could weight that in future searches.

### The Outsider

Curse of knowledge — consumption pattern unspecified. When the agent gets search results, what does it actually do? Three gaps: 1. No usage budget — when does pulling memory cost more than rediscovering? 2. Correction handling broken during live execution — agent hits contradiction, does what? 3. Scoring function arbitrary — why 3.0 vs 2.0? Missing validation: build 10 realistic memory files and a dozen queries, test whether retrieval surfaces what you'd expect.

### The Executor

Implementation order backwards — build GC first as constraints, then write path. Correction bonus (+1.0) biases negative patterns — justify or kill. No versioning/conflict resolution for concurrent writes. Missing: quota (ceiling before unmaintainable), audit trail, first-run adoption (bootstrap). What you do Monday: build GC as pure functions with tests, then wire.

---

## Peer Reviews

**Anonymization mapping:** A=Contrarian, B=First Principles, C=Expansionist, D=Outsider, E=Executor

### Review 1
Strongest: D (asks right operational questions). Biggest blind spot: C ("ship it" dismisses all hard problems). All missed: bootstrapping and cold-start.

### Review 2
Strongest: D (challenges assumptions not just mechanics). Biggest blind spot: C ("ship it" without addressing any failure mode). All missed: adoption friction — who writes first memory?

### Review 3
Strongest: D (root problem — system lacks operational grounding). Biggest blind spot: B (stops at "it's wrong" without proposing fixes). All missed: adoption friction — will agents actually use this?

### Review 4
Strongest: D (operational questions). Biggest blind spot: E (conflates implementation order with architectural completeness). All missed: eviction policy under contention. Also: why three memory types?

### Review 5
Strongest: D (consumption patterns matter most). Biggest blind spot: E (GC rules should be configurable not baked in). All missed: who owns memory conflicts.

---

## Chairman Verdict

### Where the Council Agrees

1. Pull-based retrieval is architecturally sound.
2. Routing cache with 1h TTL is broken — needs write-through invalidation.
3. Contradiction detection via keyword overlap >0.5 is unreliable.
4. Graduation at 60% grep match is pattern-matching theatre.
5. The system lacks operational grounding.
6. Auto-memory / .memory/ bifurcation is unexplained.

### Where the Council Clashes

- Expansionist vs Everyone: "ship it" vs "fix first." Disagreement about whether the harness catches problems in practice or whether design fixes are needed pre-ship.
- Mechanical GC vs Policy GC: whether the 4 rules are defensible defaults or should be configurable.

### Blind Spots Caught

1. No consumption pattern spec — what does the agent do with results?
2. Agent behavior during live contradictions — no spec
3. Cold-start and adoption friction — who writes the first memories?
4. Eviction policy under quota — what gets deleted?
5. Why three memory types, not two or four?
6. Correction scoring bias (+1.0) is arbitrary

### Recommendation

Do not ship as-is. Fix three things: (1) write-through cache invalidation, (2) replace keyword contradiction detection with dead-letter queue, (3) scrap graduation rule or make it explicit. Then specify consumption patterns, concurrency model, cold-start, and correction SLA.

### The One Thing to Do First

Build a test harness with 10 realistic memory files and 12 queries. Wire retrieval end-to-end with logging. This surfaces consumption pattern gaps and scoring assumptions before touching GC or caching.
