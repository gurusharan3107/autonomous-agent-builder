Use the builder-design-system skill. First read ~/.codex/AGENTS.md and repo AGENTS.md, then retrieve repo precedent with builder memory search for this task. Treat this as a product/design-system enforcement task, not a generic styling pass.

Goal: make the live Autonomous Agent Builder dashboard actually match the locked Builder design system and reference prototype. The reference is in /Users/gurusharan/Documents/remote-claude/active/apps/apps-design-system/Autonomous-agent-builder and may also be served as the prototype HTML. Compare the reference and current app page by page using screenshots, then inspect both codebases to identify what is blocking parity.

Focus areas:
- remove wasted space and excessive visual noise
- Thread view should show clean operator/agent chat
- approvals and questions should appear in Thread where the user can respond
- Run Trace should show task/run evidence, not operator chat noise
- design tweak controls belong in Settings, not a drawer
- shadcn/Luma defaults must not override the Builder design system
- use Builder primitives, tokens, density, status language, and page patterns

Process:
1. Load the design-language workflow and any relevant repo docs before editing.
2. Start or use the local dashboard.
3. Capture screenshots of each relevant reference page and the matching live page.
4. For each mismatch, compare reference source code against current frontend code and name the first-principles cause.
5. Patch the current app, staying within the repo’s design-system primitives and ownership boundaries.
6. Re-check screenshots after changes; keep iterating until the page visually converges with the reference.
7. Validate with the relevant dashboard UX gate/tests and report exact evidence.
8. If runtime/operator prompts or docs are touched, keep prompts operator-like, validate both claude and codex_sdk lanes, and avoid creating duplicate owner docs.

Full plan 

Plan: Adopt design-system v0.5, declutter Board, refit Agent page as 2-tab Conversation + Run-trace
Context
The user shipped a handoff bundle (Claude Design v0.5) for autonomous-agent-builder. The bundle locks tokens, primitives, motion choreography, and page archetypes ("operator console with editorial calm"). The repo's codex-designsystem-autonomousbuilder branch is already ~88% aligned (primitives, themes, GSAP), but two product pages are the priority:

Board (frontend/src/pages/BoardPage.tsx, 1.4k lines) — currently cluttered: each card carries too much chrome, sprint sidebar and run timeline are embedded inline.
Agent (frontend/src/pages/AgentPage.tsx, 1.7k lines) — currently a single page that switches modes via ?mode=trace. The user wants two real tabs:
Conversation — text chat + realtime voice in one unified thread, both feeding the SDK-backed agent. Voice transcripts, operator messages, agent questions, tool calls, and approvals all interleave.
Run trace — driven by a task selected on the Board, showing that task's run timeline / events / cost / gates.
Outcome: Board feels calm and scannable; the Agent page becomes the canonical "what is the agent doing and what is it asking me" surface, regardless of whether the user typed or spoke; deep-linking from Board → Run-trace stays functional.

Scope
In

Drop the locked spec into the repo as a reference surface.
Patch token gaps surfaced by the gap audit (status hues, prose widths, --line-2, --fg-on-accent, --status-active-line).
Restyle BoardPage to the prototype archetype (PageIntro + 5 lanes + decluttered TaskCard + sprint as drawer not inline).
Restructure AgentPage into a 2-tab Tabs primitive: Conversation and Run trace. Keep ?mode=trace&task=…&run=… as the URL contract that activates the Run-trace tab.
Unify chat + voice into one timeline using AgentTimeline mental model from the prototype, with voice-specific row variants (OperatorVoiceMessage, VoiceDelegationRow, AgentVoiceSummary).
Wire missing motion hooks: data-board-section, data-slot="card", data-agent-stage.
Out

Backend / SDK changes — none required. All endpoints already exist:
/api/agent/chat/{meta,history,stream,respond} (SSE)
POST /api/agent/chat
POST /api/agent/voice (WebRTC SDP)
/api/board
Routing changes — keep / for AgentPage, /board for BoardPage, URL params for trace handoff. No new routes.
New nav entries.
Per SKILL.md: backend/SDK and routing are out of scope.
Critical files to modify
File	Purpose
frontend/src/index.css	Add missing tokens (--status-*-hue, --status-active-line, --line-2, --fg-on-accent, prose widths). Align grid-dot opacity to spec.
frontend/src/design-system/spec/ (new)	Drop the 5 skill files (tokens.css, themes.json, components.md, patterns.md, status-language.md) as reference. Not imported at runtime.
frontend/src/design-system/primitives.tsx	Add Button soft variant if missing; expose Surface as canonical name (re-export SurfacePanel if needed).
frontend/src/pages/BoardPage.tsx	Declutter: extract BoardLane and TaskCard if still inline; reduce card to {ID + StatusPill, title, subtitle, optional progress meter, footer with cost/turns/duration}. Remove inline AgentRunTimelineList from card view. Move sprint detail to MemorySidebar-style drawer. Add data-board-section and data-slot="card" motion hooks.
frontend/src/components/agent-native.tsx	Likely host of TaskCard / AgentRunTimelineList; trim TaskCard chrome to match prototype agent-components.jsx:250-321.
frontend/src/pages/AgentPage.tsx	Replace mode === "trace" URL-driven branch with a real <Tabs> switch between Conversation and Run trace. Tab state syncs to ?mode= (chat→Conversation, trace→Run trace). When task param present and tab is Conversation, show a small "Viewing trace for TASK-123 ↗" pill that links to the Run-trace tab.
frontend/src/pages/AgentPage.tsx (Conversation tab)	Reuse existing SSE items[] model. Render via a single AgentTimeline that switches row component by item.type: user / assistant / tool / specialist / gate / ask_user_question / tool_approval_request / voice variants. Voice transcripts produced by aab:voice-transcript-sync event get appended to the same items[] (or merged via useMemo from a separate voice state) so chat and voice render in one chronological list. Mic affordance (VoiceComposerToggle) lives in the composer footer; FloatingVoiceDock mounts when voice status ≠ "idle".
frontend/src/pages/AgentPage.tsx (Run-trace tab)	Move the existing ?mode=trace branch into the Run-trace tab body. When no task is selected (Board didn't hand one off), show an EmptyState linking back to /board. When task is set, render AgentRunTimelineList (existing) + right rail with CostMeter, ConfidenceBar, PhaseStepper, gates, approvals. Add data-agent-stage motion hooks.
frontend/src/components/agent-native.tsx (or new file)	Add voice timeline row variants if not already centralized: OperatorVoiceMessage, VoiceDelegationRow, AgentVoiceSummary (share _VoiceTimelineRow chrome per prototype voice-chat.jsx).
frontend/src/hooks/useRealtimeVoice.ts (or current home)	Ensure aab:voice-transcript-sync event dispatches both operator utterances and agent voice responses with enough metadata (kind, body, timestamp, callId) to render as timeline rows. No backend change — only the client mapping.
Reuse — what's already there
StatusPill, StatusDot, Surface, Eyebrow, Tabs, Kbd, Meter, Stat, EmptyState, SectionLabel — all in frontend/src/components/workspace.tsx per gap audit; use as-is.
EditorialContent, KnowledgeCard, KnowledgeEditorialSummary, MemorySidebar, RelatedSidebar, TagCloud — all in frontend/src/components/*.tsx; reuse MemorySidebar for the sprint/task detail drawer on Board.
useRealtimeVoice() + /api/agent/voice — already negotiates WebRTC and dispatches aab:voice-transcript-sync; only the consumer needs to merge into the chat items[].
AgentRunTimelineList — already implemented per BoardPage usage; reuse verbatim in Run-trace tab.
Themes — 6 presets work; no change.
GSAP — wired in 5 components; only new hooks need to be attached.
Approach phasing (single PR on current branch, sequenced for low churn)
Tokens — patch index.css (≤30 lines). Drop spec files under frontend/src/design-system/spec/ (copy, not import). No runtime impact.
Board declutter — refactor BoardPage:
Page intro block (Eyebrow + display heading + lede + density toggle + Dispatch button).
5 lanes via data-board-section, each lane: tinted header with status dot + count + optional pulse on active.
TaskCard slimmed to prototype anatomy. Inline run timeline removed; onSelect opens MemorySidebar-style drawer with full task detail + "Open Run trace ↗" link.
Agent page tab split — wrap existing render in <Tabs items={[Conversation, Run trace]} value={…} onChange={…} /> bound to URL param. The current chat UI moves under Conversation; the trace branch moves under Run trace.
Unified Conversation thread — refactor the chat list to a single AgentTimeline. Merge voice transcript events into the same items[] (by timestamp). Mic toggle lives in the composer; floating voice dock appears when active. Agent questions and tool approvals stay as inline blocking rows with their existing response affordances.
Motion + audit — attach data-board-section, data-slot="card", data-agent-stage. Run the design-system contract test (tests/test_dashboard_design_system_contract.py) and the token check script.
Non-design follow-ups to call out (per SKILL.md "out of scope")
None required. aab:voice-transcript-sync already exists; if metadata is missing the only change is in the client mapper, not the backend.
Verification
Token check: python scripts/check_dashboard_design_tokens.py --json returns ok: true with no new findings; rg "#[0-9a-fA-F]{3,8}\b" frontend/src shows no new raw hex on touched files.
Contract test: pytest tests/test_dashboard_design_system_contract.py tests/test_dashboard_api.py tests/test_embedded_dashboard_streams.py -q — all pass.
Build: cd frontend && pnpm build (or repo equivalent) succeeds; dashboard assets are rebuilt and committed under src/autonomous_agent_builder/embedded/dashboard/.
Lint: builder lint --json exits 0 (pre-commit hook will run it anyway).
Manual browser pass via builder start --port 9876:
Board: 5 lanes render, cards show only ID/pill/title/subtitle/progress/footer (no inline timeline), density toggle works, clicking a card opens the drawer, "Open Run trace ↗" navigates to /?mode=trace&task=…&run=….
Agent / Conversation tab: typing in composer creates a user row; SSE assistant/tool/gate rows interleave correctly; pressing mic starts voice, floating dock appears, spoken utterance appears as OperatorVoiceMessage in the same list, agent voice response appears as AgentVoiceSummary, agent question (ask_user_question) blocks with response affordance, replying unblocks the stream.
Agent / Run trace tab: with no task → EmptyState linking to Board; with task → run timeline + right rail (cost / confidence / gates / approvals).
Theme sweep: cycle the 6 themes (calm/operator/sage/ember/midnight/paper) in Settings and toggle light/dark; both Board and Agent render correctly with no broken tokens.
Reduced motion: set prefers-reduced-motion: reduce in DevTools; verify no entrance tweens run and clearProps: "all" is honored.
Risks / open questions
Voice transcript timing: the prototype shows distinct OperatorVoiceMessage, VoiceDelegationRow, AgentVoiceSummary rows. If the current aab:voice-transcript-sync payload doesn't include role/kind, the client merger has to infer it. If inference is ambiguous, fall back to two minimal kinds: voice-user and voice-agent.
AgentPage size (1.7k lines): refactor in-place rather than rewrite; extract Conversation and RunTrace into co-located components in the same file or frontend/src/pages/agent/ to keep diff reviewable.
Run-trace tab without task: confirm with user the EmptyState copy and CTA (currently planned: "No task selected. Pick a task from the Board to see its trace. → Open Board").
