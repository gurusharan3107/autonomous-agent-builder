from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
DESIGN_SYSTEM_ROOT = FRONTEND_SRC / "design-system"
BOARD_FEATURE_ROOT = FRONTEND_SRC / "features" / "board"
AGENT_FEATURE_ROOT = FRONTEND_SRC / "features" / "agent"


def board_source_text() -> str:
    board_files = [
        FRONTEND_SRC / "pages" / "BoardPage.tsx",
        *(sorted(BOARD_FEATURE_ROOT.glob("*.ts"))),
        *(sorted(BOARD_FEATURE_ROOT.glob("*.tsx"))),
    ]
    return "\n".join(path.read_text() for path in board_files)


def agent_source_text() -> str:
    agent_files = [
        FRONTEND_SRC / "pages" / "AgentPage.tsx",
        *(sorted(AGENT_FEATURE_ROOT.glob("*.ts"))),
        *(sorted(AGENT_FEATURE_ROOT.glob("*.tsx"))),
    ]
    return "\n".join(path.read_text() for path in agent_files)


def test_design_system_public_contract_files_exist() -> None:
    expected_files = {
        "index.ts",
        "page.ts",
        "primitives.tsx",
        "status.ts",
        "themes.ts",
    }

    assert expected_files <= {path.name for path in DESIGN_SYSTEM_ROOT.iterdir()}


def test_design_system_public_contract_exports_required_primitives() -> None:
    index_text = (DESIGN_SYSTEM_ROOT / "index.ts").read_text()
    primitives_text = (DESIGN_SYSTEM_ROOT / "primitives.tsx").read_text()
    page_text = (DESIGN_SYSTEM_ROOT / "page.ts").read_text()
    themes_text = (DESIGN_SYSTEM_ROOT / "themes.ts").read_text()
    status_text = (DESIGN_SYSTEM_ROOT / "status.ts").read_text()

    for module_name in ("page", "primitives", "status", "themes"):
        assert f'export * from "./{module_name}"' in index_text

    for export_name in (
        "StatusPill",
        "StatusDot",
        "Surface",
        "Eyebrow",
        "Button",
        "Tabs",
        "Input",
        "Code",
        "Kbd",
        "Meter",
        "Stat",
        "BrandMark",
    ):
        assert export_name in primitives_text

    assert "PageHeader as PageIntro" in page_text
    assert "DESIGN_THEMES" in themes_text
    assert "normalizeStatusForDisplay" in status_text


def test_design_theme_contract_matches_locked_reference_presets() -> None:
    themes_text = (DESIGN_SYSTEM_ROOT / "themes.ts").read_text()
    app_text = (FRONTEND_SRC / "App.tsx").read_text()

    for theme_id, name, mode, hue, density, radius in (
        ("calm", "Calm Paper", "light", 252, 1, 10),
        ("operator", "Operator", "dark", 212, 0.82, 4),
        ("sage", "Sage Studio", "light", 180, 1, 16),
        ("ember", "Ember", "light", 28, 1.15, 14),
        ("midnight", "Midnight", "dark", 264, 0.82, 8),
        ("paper", "Paper Mono", "light", 0, 1, 6),
    ):
        assert f'id: "{theme_id}"' in themes_text
        assert f'name: "{name}"' in themes_text
        assert f'mode: "{mode}"' in themes_text
        assert f"hue: {hue}" in themes_text
        assert f"density: {density}" in themes_text
        assert f"radius: {radius}" in themes_text

    assert "root.dataset.theme = activeTheme.mode" in app_text
    assert 'root.classList.toggle("dark", activeTheme.mode === "dark")' in app_text
    for token in ("--accent-hue", "--accent-chroma", "--density", "--radius-base"):
        assert f'root.style.setProperty("{token}"' in app_text


def test_top_level_pages_import_design_system_owner() -> None:
    forbidden_sources = (
        '"@/components/workspace"',
        '"@/components/ui/button"',
        '"@/components/ui/input"',
        '"@/components/ui/tabs"',
        '"@/lib/design-system"',
    )

    offenders: list[str] = []
    for path in sorted((FRONTEND_SRC / "pages").glob("*.tsx")):
        text = path.read_text()
        for forbidden in forbidden_sources:
            if forbidden in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports {forbidden}")

    assert offenders == []


def test_runtime_preferences_broadcast_same_window_theme_changes() -> None:
    hook_text = (FRONTEND_SRC / "hooks" / "use-runtime-preferences.ts").read_text()

    assert "aab:runtime-preferences-changed" in hook_text
    assert "window.dispatchEvent(new CustomEvent" in hook_text
    assert "window.addEventListener(PREFERENCE_EVENT" in hook_text


def test_settings_page_uses_operator_first_section_hierarchy() -> None:
    app_text = (FRONTEND_SRC / "App.tsx").read_text()
    types_text = (FRONTEND_SRC / "lib" / "types.ts").read_text()
    hook_text = (FRONTEND_SRC / "hooks" / "use-runtime-preferences.ts").read_text()

    for section_marker in (
        'eyebrow="01 - Voice & Realtime"',
        'title="Voice transport"',
        'eyebrow="02 - Board & Layout"',
        'title="Board density and surface modes"',
        'eyebrow="03 - Agent Surface"',
        'title="Inspector and transcript defaults"',
        'eyebrow="04 - Runtime"',
        'title="Runtime lane"',
        'eyebrow="05 - Appearance"',
        'title="Theme and design tokens"',
    ):
        assert section_marker in app_text

    assert "lg:grid-cols-[280px_minmax(0,1fr)]" in app_text
    assert "Jump to voice" in app_text

    for preference_key in (
        "realtimeModel",
        "realtimeVoice",
        "pushToTalkMode",
        "inlineTranscript",
        "bindVoiceToCurrentSession",
        "destructiveActionPhrase",
        "agentDefaultMode",
        "runTraceDefault",
    ):
        assert preference_key in types_text
    assert preference_key in hook_text

    assert "Theme and design tokens" in app_text
    assert "durable Settings hierarchy" in app_text
    assert "aab:open-design-drawer" not in app_text
    assert "DesignSystemDrawer" not in app_text


def test_agent_page_preserves_trace_explorer_and_conversation_rail_contract() -> None:
    agent_text = (FRONTEND_SRC / "pages" / "AgentPage.tsx").read_text()
    agent_surface_text = agent_source_text()
    hook_text = (FRONTEND_SRC / "hooks" / "use-runtime-preferences.ts").read_text()
    status_text = (FRONTEND_SRC / "lib" / "status.ts").read_text()

    assert 'agentDefaultMode: "chat"' in hook_text
    assert (
        'import { fetchBoard, fetchShellSummary, openBoardStream } from "@/lib/api";' in agent_text
    )
    assert "const stream = openBoardStream((board) => {" in agent_text
    assert "stream.close()" in agent_text
    assert "boardError && !boardData" in agent_surface_text
    assert 'ready: "Ready"' in status_text
    assert '        : "ready";' in agent_text
    assert '? shellSummary?.running_label ?? "agent · live"' in agent_text
    assert ': "agent · ready"' in agent_text
    assert "statusTokenAccounting(status);" in agent_text
    assert (
        'label="Non-cached + output" '
        "value={formatTokenCount(currentTurnTokens.noncachedPlusOutput)}"
    ) in agent_surface_text
    assert (
        'label="Raw tokens" value={formatTokenCount(currentTurnTokens.rawTotal)}'
    ) in agent_surface_text
    assert (
        'label="Cached tokens" value={formatTokenCount(currentTurnTokens.cached)}'
    ) in agent_surface_text
    assert 'label="Tokens" value={formatTokenCount(status?.tokens_used)}' not in agent_surface_text

    for state_marker in (
        "selectedTraceSprintId",
        "selectedTraceTaskId",
        "selectedTraceRunId",
    ):
        assert state_marker in agent_text

    for surface_marker in (
        "<SectionLabel>Run explorer</SectionLabel>",
        'text-muted-foreground">Tasks</p>',
        "<SectionLabel>Agent runs</SectionLabel>",
        "<SectionLabel>Selected run</SectionLabel>",
        "<SectionLabel>Recent work</SectionLabel>",
        "xl:grid-cols-[minmax(0,1fr)_340px]",
    ):
        assert surface_marker in agent_surface_text

    assert 'setAgentMode("trace")' in agent_text
    assert "runs.find((run) => run.session_id === sessionId) ?? runs[0] ?? null" in agent_text
    assert "border-l-2 border-primary" not in agent_text
    assert "No task selected" in agent_surface_text


def test_agent_page_refresh_defaults_to_timeline_transcript_layout() -> None:
    app_text = (FRONTEND_SRC / "App.tsx").read_text()
    hook_text = (FRONTEND_SRC / "hooks" / "use-runtime-preferences.ts").read_text()

    assert 'transcriptLayout: "timeline"' in hook_text
    assert (
        'const AGENT_TIMELINE_LAYOUT_MIGRATION_KEY = "aab:agent-timeline-layout-migrated";'
        in hook_text
    )
    assert 'preferences.transcriptLayout === "cards"' in hook_text
    assert 'transcriptLayout: "timeline" as const' in hook_text
    assert app_text.index('{ label: "Timeline", value: "timeline" }') < app_text.index(
        '{ label: "Cards", value: "cards" }',
    )


def test_realtime_voice_degrades_to_text_mode_without_microphone() -> None:
    agent_text = (FRONTEND_SRC / "pages" / "AgentPage.tsx").read_text()
    agent_surface_text = agent_source_text()
    voice_panel_text = (AGENT_FEATURE_ROOT / "AgentVoicePanel.tsx").read_text()
    voice_hook_text = (FRONTEND_SRC / "hooks" / "use-realtime-voice.tsx").read_text()

    assert 'export type VoiceMode = "audio" | "text"' in voice_hook_text
    assert "microphoneUnavailableMessage" in voice_hook_text
    assert "This browser or macOS did not expose a microphone." in voice_hook_text
    assert "check the input device and browser microphone permission" in voice_hook_text
    assert "Realtime text mode is available in the Voice tab." in voice_hook_text
    assert 'peer.addTransceiver("audio", { direction: "recvonly" })' in voice_hook_text
    assert "sendRealtimeText" in voice_hook_text
    assert 'type: "input_text"' in voice_hook_text
    assert 'type: "response.create"' in voice_hook_text
    assert "setVoiceNotice(null)" in voice_hook_text
    assert "setVoiceError(null)" in voice_hook_text

    assert "voiceNotice" in agent_text
    assert '{ value: "voice", label: "Voice" }' in agent_text
    assert "Realtime input" in agent_surface_text
    assert "buildVoiceTimelineEntries(voiceMessages)" in agent_text
    assert "<AgentTimeline entries={voiceTimelineEntries} />" in voice_panel_text
    assert voice_panel_text.index(
        "<AgentTimeline entries={voiceTimelineEntries} />"
    ) < voice_panel_text.index(
        '<Code className="text-[10px] uppercase tracking-[0.16em]">Realtime input</Code>',
    )
    assert "stream-card stream-card-operator w-full max-w-[880px]" not in agent_surface_text
    assert ': "Operator",' in agent_surface_text
    assert ': "Operator to Samantha",' not in agent_text
    assert (
        'kind: assistantMessage ? "assistant" : systemMessage ? "gate" : "user"'
        in agent_surface_text
    )
    assert (
        'heading: assistantMessage ? "Samantha" : systemMessage ? "Realtime system" : "Operator"'
        in agent_surface_text
    )
    assert "Samantha" in agent_surface_text
    assert 'voiceMode === "text" ? "Text mode" : "Audio + text"' in voice_panel_text
    assert (
        'voiceMode === "text" ? "Type to Samantha" : "Speak or type to Samantha"'
        in voice_panel_text
    )


def test_command_palette_has_grouped_keyboard_navigation_contract() -> None:
    app_text = (FRONTEND_SRC / "App.tsx").read_text()

    assert "groupedItems" in app_text
    assert "ArrowDown" in app_text
    assert "ArrowUp" in app_text
    assert 'event.key === "Enter"' in app_text
    assert 'event.key === "Escape"' in app_text
    assert "aria-selected={selected}" in app_text
    assert "onKeyDown={handleKeyDown}" in app_text


def test_app_chrome_has_responsive_navigation_contract() -> None:
    app_text = (FRONTEND_SRC / "App.tsx").read_text()

    assert "data-responsive-nav" in app_text
    assert "lg:hidden" in app_text
    assert "overflow-x-auto" in app_text
    assert "grid-cols-[1fr_auto]" in app_text
    assert "lg:grid-cols-[1fr_auto_1fr]" in app_text
    assert 'className="hidden sm:inline-flex"' in app_text


def test_app_shell_has_keyboard_skip_link_and_main_landmark() -> None:
    app_text = (FRONTEND_SRC / "App.tsx").read_text()

    assert 'href="#dashboard-main"' in app_text
    assert "Skip to dashboard" in app_text
    assert 'id="dashboard-main"' in app_text


def test_board_phase_timeline_does_not_mark_done_green_until_shipped() -> None:
    board_text = board_source_text()

    assert 'const isDone = item.id === "done"' not in board_text
    assert 'item.stage === "shipped" && activeStage === "shipped"' in board_text
    assert 'activeStage === "blocked" && item.stage === "implementation"' in board_text
    assert 'phaseStatus === "complete"' in board_text


def test_board_start_work_is_disabled_after_work_is_started() -> None:
    board_text = board_source_text()

    assert "const hasStartedWork =" in board_text
    assert "const hasUnresolvedStartedWork =" in board_text
    assert "filteredBoard.active.length > 0" in board_text
    assert "filteredBoard.review.length > 0" in board_text
    assert "filteredBoard.blocked.length > 0" in board_text
    assert "Work already started" in board_text
    assert "Continue work" in board_text
    assert "Start work" in board_text
    assert "dispatchButtonLabel" in board_text
    assert (
        "disabled={!dispatchableTask || hasUnresolvedStartedWork || dispatchingTaskId === dispatchableTask.id}"
        in board_text
    )


def test_agent_pending_decision_blocks_composer_and_duplicate_choice_panel() -> None:
    agent_text = agent_source_text()

    assert (
        "const agentRunPending = (loading || Boolean(status?.running)) && !streamingText && !pendingBlockingItem;"
        in agent_text
    )
    assert "Builder is blocked until you answer this decision." in agent_text
    assert "Pending decision response" in agent_text
    assert "pendingQuestionOptions" not in agent_text
    assert "Choose a suggested answer, or type another answer below" not in agent_text
    assert "entry.actions" not in (FRONTEND_SRC / "components" / "agent-native.tsx").read_text()


def test_reduced_motion_contract_disables_css_and_scripted_motion() -> None:
    css_text = (FRONTEND_SRC / "index.css").read_text()

    assert "@media (prefers-reduced-motion: reduce)" in css_text
    assert "animation-duration: 1ms !important" in css_text
    assert "animation-iteration-count: 1 !important" in css_text
    assert "transition-duration: 1ms !important" in css_text
    assert "scroll-behavior: auto !important" in css_text

    animated_sources = (
        FRONTEND_SRC / "hooks" / "use-agent-page-animations.ts",
        FRONTEND_SRC / "hooks" / "use-board-animations.ts",
        FRONTEND_SRC / "hooks" / "use-metrics-animations.ts",
        FRONTEND_SRC / "pages" / "OnboardingPage.tsx",
    )
    for source in animated_sources:
        text = source.read_text()
        assert 'window.matchMedia("(prefers-reduced-motion: reduce)").matches' in text
        assert "return;" in text


def test_numeric_display_uses_tabular_numeral_contract() -> None:
    css_text = (FRONTEND_SRC / "index.css").read_text()
    workspace_text = (FRONTEND_SRC / "components" / "workspace.tsx").read_text()
    agent_native_text = (FRONTEND_SRC / "components" / "agent-native.tsx").read_text()
    backlog_text = (FRONTEND_SRC / "pages" / "BacklogPage.tsx").read_text()

    assert 'font-feature-settings: "ss01", "cv11", "tnum"' in css_text
    assert "font-mono text-[11px] tabular-nums text-foreground" in workspace_text
    assert "font-mono tabular-nums text-foreground/80" in workspace_text
    assert "font-mono text-[22px] leading-none tabular-nums" in agent_native_text
    assert "font-mono tabular-nums" in agent_native_text
    assert "font-mono text-[10px] text-muted-foreground tabular-nums" in backlog_text


def test_backlog_detail_uses_design_system_metadata_primitives() -> None:
    backlog_text = (FRONTEND_SRC / "pages" / "BacklogPage.tsx").read_text()

    assert 'from "@/components/ui/badge"' not in backlog_text
    assert "BacklogCode" in backlog_text
    assert "StatusPill status={STATE_TONE[boardState(selectedFeature.status)]}" in backlog_text
    assert 'return value.replace(/^feature-/i, "item-");' in backlog_text
    assert "{itemDisplayId(selectedFeature.id)}" in backlog_text
    assert "{itemDisplayId(feature.id)}" in backlog_text


def test_dashboard_metadata_tags_use_design_system_primitives() -> None:
    checked_roots = [FRONTEND_SRC / "pages", FRONTEND_SRC / "components"]
    offenders: list[str] = []

    for root in checked_roots:
        for path in root.rglob("*.tsx"):
            if path.name == "badge.tsx":
                continue
            text = path.read_text()
            if 'from "@/components/ui/badge"' in text or "<Badge" in text or "</Badge>" in text:
                offenders.append(str(path.relative_to(FRONTEND_SRC)))

    assert offenders == []


def test_approval_fallback_preserves_page_pattern_contract() -> None:
    approval_text = (FRONTEND_SRC / "pages" / "ApprovalPage.tsx").read_text()

    assert "function ApprovalFallbackFrame" in approval_text
    assert 'data-screen-label="Approval"' in approval_text
    assert 'eyebrow="Decision needed"' in approval_text
    assert 'title="Review the proposed work"' in approval_text
    assert "return <ErrorState message={error} onRetry={reload} />" not in approval_text
    assert 'return <LoadingState label="Loading approval review..." />' not in approval_text
    assert "<ApprovalFallbackFrame streamState={streamState}>" in approval_text


def test_agent_run_trace_surfaces_token_breakdown() -> None:
    agent_surface_text = agent_source_text()
    agent_model_text = (FRONTEND_SRC / "features" / "agent" / "agent-model.ts").read_text()
    agent_presenter_text = (
        FRONTEND_SRC / "features" / "agent" / "AgentRunPresenters.tsx"
    ).read_text()

    assert "formatTokenCount," in agent_surface_text
    assert "function formatTokenCount" in agent_model_text
    assert "runTokenAccounting," in agent_surface_text
    assert "function runTokenAccounting" in agent_model_text
    assert "runTokenAccounting(selectedTraceRun)" in agent_surface_text
    assert 'label="Input tokens"' in agent_surface_text
    assert "run?.tokens_input" in agent_model_text
    assert 'label="Output tokens"' in agent_surface_text
    assert "run?.tokens_output" in agent_model_text
    assert 'label="Cached tokens"' in agent_surface_text
    assert "run?.tokens_cached" in agent_model_text
    assert "font-mono text-[11px] tabular-nums text-foreground" in agent_presenter_text


def test_status_language_contract_covers_backend_lifecycle_aliases() -> None:
    status_text = (FRONTEND_SRC / "lib" / "status.ts").read_text()

    expected_branches = {
        "queued": "pending",
        "quality_gates": 'active ? "running" : "review"',
        "pr_creation": 'active ? "running" : "review"',
        "build_verify": 'active ? "running" : "review"',
        "completed": "done",
        "allow": "approved",
        "denied": "denied",
        "passed": "pass",
        "capability_limit": "blocked",
        "timeout": "failed",
        "error": "failed",
    }

    for backend_status, design_status in expected_branches.items():
        assert f'case "{backend_status}"' in status_text
        assert design_status in status_text

    for allowed_status in (
        "running",
        "active",
        "implementation",
        "planning",
        "design",
        "review",
        "review_pending",
        "answered",
        "approved",
        "denied",
        "design_review",
        "pending",
        "done",
        "success",
        "pass",
        "blocked",
        "failed",
        "fail",
        "warn",
    ):
        assert f'| "{allowed_status}"' in status_text


def test_board_timeline_separates_gates_review_build_and_done() -> None:
    board_text = board_source_text()

    assert '{ id: "gates", label: "Gates", stage: "verify", statusKey: "verify" }' in board_text
    assert '{ id: "review", label: "Review", stage: "pr_review" }' in board_text
    assert '{ id: "build", label: "Build", stage: "build", statusKey: "build" }' in board_text
    assert '{ id: "done", label: "Done", stage: "shipped", statusKey: "shipped" }' in board_text
    assert 'case "build":' in board_text
    assert 'case "build_verify":' in board_text
    assert 'return "build";' in board_text
    assert 'stage === "pr_review"' in board_text
    assert 'stage === "build"' in board_text
    assert "GateEvidenceCard" in board_text
    assert "Review evidence" in board_text
    assert "Build and acceptance evidence" in board_text
