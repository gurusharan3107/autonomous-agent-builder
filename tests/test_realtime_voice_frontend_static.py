from __future__ import annotations

from pathlib import Path

AGENT_PAGE = Path("frontend/src/pages/AgentPage.tsx")
AGENT_FEATURE_ROOT = Path("frontend/src/features/agent")
AGENT_NATIVE = Path("frontend/src/components/agent-native.tsx")
APP = Path("frontend/src/App.tsx")
VOICE_ORB = Path("frontend/src/components/SamanthaVoiceOrb.tsx")
VOICE_HOOK = Path("frontend/src/hooks/use-realtime-voice.tsx")
VOICE_POLICY = Path("src/autonomous_agent_builder/services/realtime_voice_policy.py")

def agent_source_text() -> str:
    return "\n".join(
        [
            AGENT_PAGE.read_text(encoding="utf-8"),
            *(
                path.read_text(encoding="utf-8")
                for path in sorted(AGENT_FEATURE_ROOT.glob("*.ts*"))
            ),
        ]
    )


def test_agent_page_renders_realtime_voice_panel() -> None:
    source = agent_source_text()
    orb_source = VOICE_ORB.read_text(encoding="utf-8")
    voice_source = VOICE_HOOK.read_text(encoding="utf-8")
    policy_source = VOICE_POLICY.read_text(encoding="utf-8")
    combined = source + "\n" + orb_source + "\n" + voice_source + "\n" + policy_source

    assert "Realtime voice" in combined
    assert "Start voice" in combined
    assert "Stop voice" in combined
    assert '{ value: "voice", label: "Voice" }' in source
    assert "Voice and typed Samantha turns stay here" in source
    assert ': "Operator",' in source
    assert ': "Operator to Samantha",' not in source
    assert "Samantha" in source
    assert "voiceMessages" in source
    assert "voiceTimelineEntries" in source
    assert "clearVoiceTranscript" in source
    assert "clearVoiceTranscript" in voice_source
    assert "setVoiceEvents([])" in voice_source
    assert "setVoiceMessages([])" in voice_source
    assert "realtimeTextSubmittingRef.current" in source
    assert 'disabled={realtimeTextSubmitting}' in source
    assert '{realtimeTextSubmitting ? "Sending" : "Send"}' in source
    assert '<AgentTimeline entries={voiceTimelineEntries} />' in source
    assert "stream-card stream-card-operator w-full max-w-[880px]" not in source
    assert 'kind: assistantMessage ? "assistant" : systemMessage ? "gate" : "user"' in source
    assert 'heading: assistantMessage ? "Samantha" : systemMessage ? "Realtime system" : "Operator"' in source
    assert source.index('<AgentTimeline entries={voiceTimelineEntries} />') < source.index(
        '<Code className="text-[10px] uppercase tracking-[0.16em]">Realtime input</Code>',
    )
    assert "Agent working with" in source
    assert "loading || Boolean(status?.running)" in source
    assert "filteredItems.length === 0 && !streamingText && !agentRunPending" in source
    assert "This browser or macOS did not expose a microphone." in voice_source
    assert "check the input device and browser microphone permission" in voice_source
    assert "Realtime text mode is available in the Voice tab" in voice_source
    assert "gpt-realtime-mini" in combined
    assert "/api/realtime/session" in voice_source
    assert "RTCPeerConnection" in voice_source
    assert 'createDataChannel("oai-events")' in voice_source
    assert 'peer.addTransceiver("audio", { direction: "recvonly" })' in voice_source

    assert "microphoneUnavailableMessage" in voice_source
    assert "sendRealtimeText" in voice_source
    assert '"/api/realtime/text-control"' in voice_source
    assert 'voiceMode !== "text"' in voice_source
    assert "fallback_to_agent: !canUseRealtimeChannel" in voice_source
    assert 'voiceStatus === "connected" || voiceStatus === "error"' in source
    assert "Text fallback" in source
    assert "control.handled" in voice_source
    assert "text control handled" in voice_source
    assert "control.route" in voice_source
    assert 'new URL(control.route, window.location.origin).searchParams.get("session") || ""' in voice_source
    assert "detail: { route: control.route, session_id: delegatedSessionId }" in voice_source
    assert "dashboard navigation" in voice_source
    assert "normalizeQuestionOptions(item.payload.options)" in source
    assert "String(record.label ?? \"\").trim()" in source
    assert "{option.label}" in source
    assert "item.payload.options.map(String)" not in source
    assert "Raw tokens" in source
    assert "Non-cached + output" in source
    assert "Chunk pressure" in source
    assert "Large-output flags" in source
    assert "Zero-turn run" in source
    assert "Repeated retrieval" in source
    assert "runTokenAccounting(selectedTraceRun)" in source
    assert "runChunkAccounting(selectedTraceRun)" in source
    assert "runAvoidableFlags(selectedTraceRun)" in source
    assert '"conversation.item.create"' in voice_source
    assert '"input_text"' in voice_source
    assert '"response.create"' in voice_source
    assert 'eventType === "conversation.item.input_audio_transcription.completed"' in voice_source
    assert "if (!transcript) return" in voice_source
    assert 'dataChannel.send(JSON.stringify({ type: "response.create" }))' in voice_source
    assert 'instructions: "Say only: Hi there!"' in voice_source
    assert "builder_voice_activation_greeting" in voice_source
    voice_open_source = voice_source[
        voice_source.index('dataChannel.addEventListener("open"') : voice_source.index(
            'dataChannel.addEventListener("message"',
        )
    ]
    assert '"conversation.item.create"' not in voice_open_source
    assert 'text: "Hi"' not in voice_open_source
    assert "voiceConnectTimeoutRef" in voice_source
    assert "Realtime did not finish connecting" in voice_source
    assert "markRealtimeConnected" in voice_source
    assert 'if (dataChannel.readyState === "open")' in voice_source
    assert "Stop connecting" in source
    assert "Realtime input" in source
    assert "Text mode" in source
    assert "waitForVoiceIceGathering(peer)" in voice_source
    assert 'const localSdp = peer.localDescription?.sdp ?? "";' in voice_source
    assert "body: localSdp" in voice_source
    assert '"X-Agent-Session-Mode": requestedSessionId ? "current" : "fresh"' in voice_source
    assert 'voiceSessionHeaders["X-Agent-Session-Id"] = requestedSessionId' in voice_source
    assert 'response.headers.get("X-Agent-Session-Id")' in voice_source
    assert "SamanthaVoiceOrb" in orb_source
    assert "transition-opacity duration-150" in orb_source
    assert 'new CustomEvent("aab:voice-session-bound"' in voice_source
    assert 'new CustomEvent("aab:voice-control-action"' in voice_source
    assert 'new CustomEvent("aab:voice-navigation-request"' in voice_source
    assert 'const nextSessionId = typeof payload.session_id === "string" ? payload.session_id : ""' in voice_source
    assert "setBoundSessionId(nextSessionId)" in voice_source
    assert "voice_navigation_request" in voice_source
    assert "voice_control_action" in voice_source
    assert "applyVoiceNavigationPayload" in source
    assert 'const routeSessionId = route.startsWith("/")' in source
    assert 'new URL(route, window.location.origin).searchParams.get("session") || ""' in source
    assert 'typeof payload.session_id === "string" && payload.session_id ? payload.session_id : routeSessionId' in source
    assert "void loadHistory(nextSessionId)" in source
    assert "void loadSessionList(nextSessionId)" in source
    assert 'setAgentMode("trace")' in source
    assert "setSelectedTraceTaskId(targetUrl.searchParams.get(\"task\"))" in source
    assert "setSelectedTraceRunId(targetUrl.searchParams.get(\"run\"))" in source
    assert 'window.addEventListener("aab:voice-navigation-request"' in source
    assert "latestVoiceNavigationEventIdRef" in source
    assert "const applyVoiceHistoryIfRelevant" in source
    history_sync_source = source[
        source.index("const applyVoiceHistoryIfRelevant") : source.index("const syncVoiceTranscript")
    ]
    assert "applyVoiceNavigationPayload" not in history_sync_source
    assert "const navigationItem = [...items]" not in source
    assert "navigate(route)" in source
    assert "dashboard navigation" in voice_source
    assert "useNavigate" in voice_source
    assert "void loadHistory(sessionIdFromVoice)" in source
    assert 'throw new Error("Browser did not create a Realtime SDP offer.")' in voice_source
    assert "recover_board_task" in policy_source
    assert "dispatch_board_task" in policy_source
    assert "navigate_dashboard" in policy_source
    assert "delegate_to_builder_agent" in policy_source
    assert "switch_builder_runtime" in policy_source
    assert "confirm_high_risk_action" in policy_source
    assert "wait_for_user" in policy_source
    assert "voice_operator_message" in source
    assert "voice_final_summary" in source
    assert "voice_action_prepared" in source
    assert 'label: "Operator"' in source
    assert 'label: "operator by voice"' not in source
    assert 'label: voiceDelegation ? "Samantha" : undefined' in source
    assert "Agent summary for voice" in policy_source or "voice_final_summary" in combined
    assert 'label: "Builder"' in source
    assert "thread_mode" in policy_source
    assert "scheduleVoiceTranscriptSync" in source
    assert "const activeSessionId = sessionIdRef.current" in source
    assert "const historyUrl = activeSessionId" in source
    assert '"/api/agent/chat/history?fresh=1"' in source
    assert "fetch(historyUrl)" in source
    assert "voiceStatus !== \"connected\"" in source
    assert "window.setInterval(() => scheduleVoiceTranscriptSync(), 3000)" in source
    assert "if (switchingSession || !data.status?.running)" in source
    assert 'event.key === "Enter" && !event.shiftKey' in source
    assert "const realtimeTextInputRef = useRef<HTMLTextAreaElement>(null)" in source
    assert "realtimeTextInputRef.current?.value" in source
    assert "void submitRealtimeText(event.currentTarget.value)" in source
    assert 'searchParams.get("mode") ?? searchParams.get("tab")' in source
    assert 'nextSearchParams.set("mode", nextMode)' in source
    assert "setVoiceMessages([])" in voice_source
    assert "function getMicrophoneStreamWithTimeout" in voice_source
    assert '"TimeoutError"' in voice_source
    assert "Microphone did not respond quickly. Realtime text mode is available" in voice_source
    assert "Samantha -> Agent" not in source
    assert "SDK-backed Agent" not in source
    assert 'last?.role === "assistant" && last.status === "streaming"' in voice_source
    assert 'status: message.status === "streaming" ? "running" : undefined' in source
    assert 'if (voiceStatus === "idle" && !voiceError) return null' not in voice_source


def test_agent_page_bootstraps_empty_when_no_session_is_selected() -> None:
    source = AGENT_PAGE.read_text(encoding="utf-8")

    bootstrap_source = source[source.index("const bootstrap = async () => {") : source.index(
        "void bootstrap();"
    )]

    assert "if (!sessionStorageKey && !requestedSessionId) return;" not in source
    assert "const storedSessionId = requestedSessionId || readStoredSessionId();" in source
    assert "? await loadHistory(storedSessionId)" in source
    assert ": await loadHistory(null, { fresh: true });" in source
    assert 'setHistoryLoaded(false);' in source
    assert 'setHistoryLoaded(true);' in source
    assert 'loadHistory(null, { fresh: true })' in bootstrap_source
    assert "Resume" in source


def test_agent_page_new_thread_detaches_voice_session_history() -> None:
    source = AGENT_PAGE.read_text(encoding="utf-8")

    clear_source = source[source.index("const clearSession = () => {") : source.index("const openSession")]

    assert "const sessionIdRef = useRef<string | null>(null)" in source
    assert "const detachedVoiceSessionIdsRef = useRef<Set<string>>(new Set())" in source
    assert "detachedVoiceSessionIdsRef.current.has(data.session_id)" in source
    assert "detachedVoiceSessionIdsRef.current.has(sessionIdFromVoice)" in source
    assert "const activeSessionId = sessionIdRef.current" in source
    assert "stopVoiceSession()" in clear_source
    assert 'nextSearchParams.delete("session")' in clear_source
    assert 'nextSearchParams.delete("task")' in clear_source
    assert 'nextSearchParams.delete("run")' in clear_source
    assert 'nextSearchParams.delete("tab")' in clear_source
    assert 'nextSearchParams.set("mode", agentMode)' in clear_source
    assert "setActiveSessionId(null)" in clear_source
    assert 'await loadHistory(null, { fresh: true })' in clear_source


def test_agent_page_composer_answers_pending_questions() -> None:
    source = AGENT_PAGE.read_text(encoding="utf-8")
    agent_surface_source = agent_source_text()
    decision_source = (AGENT_FEATURE_ROOT / "AgentDecisionActions.tsx").read_text(encoding="utf-8")

    send_source = source[source.index("const sendMessage = async () => {") : source.index("const clearSession")]
    composer_source = source[source.index("const composerPlaceholder") : source.index("const currentPhaseIndex")]

    assert 'pendingBlockingItem?.type === "ask_user_question"' in send_source
    assert "await submitQuestion(pendingBlockingItem, { customText: prompt })" in send_source
    assert "approvalDecisionFromText(prompt)" in send_source
    assert "await submitApproval(pendingBlockingItem, decision, prompt)" in send_source
    assert 'navigateToSession(data.session_id, "chat")' in send_source
    assert "loading && !pendingBlockingItem" in send_source
    assert '"Other answer: type what you have in mind."' in composer_source
    assert '"Type approve/start or deny/hold."' in composer_source
    assert "(loading && !pendingBlockingItem)" in composer_source
    assert "disabled={composerSendDisabled}" in agent_surface_source
    assert 'aria-label="Send agent instruction"' in agent_surface_source
    assert 'aria-label={pendingBlockingItem ? "Send response" : "Send agent instruction"}' not in agent_surface_source
    assert "Builder is blocked until you answer this decision." in agent_surface_source
    assert "pendingQuestionOptions" not in agent_surface_source
    assert "Choose a suggested answer, or type another answer below" not in agent_surface_source
    assert 'aria-label="Question choices"' in decision_source
    assert "options.map((option)" in decision_source
    assert "submitQuestion(item, {" in decision_source
    assert "selectedOptions: [option.label]" in decision_source
    assert "operatorChoiceLabel(option.label)" in decision_source
    assert source.count("await loadHistory(sessionId)") >= 2
    assert source.count("void loadSessionList(sessionId)") >= 2


def test_agent_page_persists_new_chat_session_in_url_for_refresh() -> None:
    source = AGENT_PAGE.read_text(encoding="utf-8")

    helper_source = source[source.index("const navigateToSession = ") : source.index("const applyVoiceNavigationPayload")]
    question_source = source[source.index("const submitQuestion = ") : source.index("const submitApproval = ")]
    approval_source = source[source.index("const submitApproval = ") : source.index("const handleKeyDown")]
    open_source = source[source.index("const openSession = ") : source.index("const resumeLatestSession")]

    assert 'nextSearchParams.set("mode", nextMode)' in helper_source
    assert 'nextSearchParams.set("session", nextSessionId)' in helper_source
    assert 'navigate(`${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`, { replace: true })' in helper_source
    assert 'navigateToSession(sessionId, "chat")' in question_source
    assert 'navigateToSession(sessionId, "chat")' in approval_source
    assert "navigateToSession(nextSessionId)" in open_source


def test_agent_page_keeps_questions_and_approvals_inline_with_design_system() -> None:
    source = AGENT_PAGE.read_text(encoding="utf-8")
    agent_surface_source = agent_source_text()
    decision_source = (AGENT_FEATURE_ROOT / "AgentDecisionActions.tsx").read_text(encoding="utf-8")
    native_source = AGENT_NATIVE.read_text(encoding="utf-8")

    assert "DialogContent" not in source
    assert "const decisionDialog =" not in source
    assert "Builder needs one detail" not in source
    assert 'aria-label="Question dialog choices"' not in source
    assert "operatorChoiceLabel(option.label)" in decision_source
    assert "Other answer" in decision_source
    assert "Other answer: type what you have in mind." in decision_source
    assert "questionAnswerText(item)" in agent_surface_source
    assert "Answered with" in agent_surface_source
    assert "Result" in native_source
    assert "entry.result" in native_source
    assert "actions?: ReactNode" not in native_source
    assert "entry.actions" not in native_source
    assert "<AgentDecisionActions" in agent_surface_source
    assert "Pending decision response" in agent_surface_source
    assert 'placeholder="Add the missing specification"' not in source
    assert 'placeholder="Optional note"' in decision_source
    assert "Keep in thread" not in agent_surface_source
    assert 'aria-label="Approval choices"' in decision_source
    assert '<StatusPill status={decisionTimelineStatus(item)} />' in agent_surface_source
    assert 'bg-[color:var(--status-review-soft)]' in agent_surface_source
    assert 'className="h-auto justify-start rounded-[0.85rem] px-3 py-2 text-left text-[12px]"' in decision_source
    assert 'void submitQuestion(item, {' in decision_source
    assert 'void submitApproval(item, "allow")' in decision_source
    assert 'void submitApproval(item, "deny")' in decision_source
    assert "readablePayloadText" in agent_surface_source


def test_agent_page_keeps_tool_activity_visible_until_agent_response() -> None:
    source = agent_source_text()

    assert "const TOOL_ACTIVITY_EVENT_TYPES = new Set" in source
    assert "const AGENT_RESPONSE_EVENT_TYPES = new Set" in source
    assert "buildActiveToolActivity(items)" in source
    assert "AGENT_RESPONSE_EVENT_TYPES.has(item.type)" in source
    assert "activeToolActivity.itemIds.has(item.id)" in source
    assert "Agent is working through tool calls before the next response." in source
    assert "activeToolActivity.count} tool use" in source
    assert "agent-tool-activity" in source
    assert "agentRunPending = (loading || Boolean(status?.running)) && !streamingText && !pendingBlockingItem" in source
    assert "aria-label=\"Agent is thinking\"" not in source


def test_agent_page_inline_question_choice_submits_not_only_selects_draft() -> None:
    source = (AGENT_FEATURE_ROOT / "AgentDecisionActions.tsx").read_text(encoding="utf-8")
    question_card_source = source[
        source.index('if (item.type === "ask_user_question")') : source.index(
            "if (APPROVAL_EVENT_TYPES.has(item.type))"
        )
    ]
    option_start = question_card_source.index("title={option.description}")
    option_button_source = question_card_source[
        option_start : question_card_source.index("disabled={submittingEventId === item.id}", option_start)
    ]

    assert 'aria-label="Question choices"' in question_card_source
    assert "void submitQuestion(item, {" in option_button_source
    assert "selectedOptions: [option.label]" in option_button_source
    assert "setQuestionDrafts((current) => (" not in option_button_source


def test_agent_page_run_trace_collapses_uninformative_tool_use_rows_and_uses_runtime_icons() -> None:
    source = agent_source_text()
    native_source = AGENT_NATIVE.read_text(encoding="utf-8")

    assert "function isUninformativeToolUse(event: TaskActivityEvent)" in source
    assert 'action === "used tool"' in source
    assert 'event_type: "tool_use_summary"' in source
    assert "count: toolSummaryCount > 1 ? toolSummaryCount : undefined" in source
    assert "icon: runtimeTimelineIcon(event.runtime_sdk, event.provider)" in source
    assert 'icon: voiceDelegation ? "openai" : undefined' in source
    assert 'icon: assistantMessage ? "openai" : undefined' in source
    assert 'return <span className="font-mono text-[9px] font-semibold leading-none">CX</span>;' not in native_source
    assert 'return <span className="font-serif text-[13px] font-semibold leading-none">C</span>;' not in native_source
    assert 'if (icon === "codex")' in native_source
    assert 'if (icon === "claude")' in native_source
    assert 'if (icon === "openai")' in native_source
    # Runtime icons are now real brand-logo SVGs: codex→OpenAI mark, claude→Anthropic
    # mark (distinctive brand viewBox/fill), openai→inline waveform glyph.
    assert 'viewBox="0 0 512 509.639"' in native_source
    assert 'fill="#D77655"' in native_source
    assert 'M8.1 8.1 15.9 16M15.9 8.1 8.1 16M12 4.6v14.8' in native_source


def test_agent_page_timeline_uses_operator_labels_for_pending_decisions() -> None:
    source = agent_source_text()

    assert 'heading: item.type === "ask_user_question" ? "Question" : "Approval needed"' in source
    assert 'kind: "assistant"' in source
    assert "function decisionTimelineStatus(item: TimelineItem): string" in source
    assert 'status: decisionTimelineStatus(item)' in source
    assert 'if (normalized === "start shipping") return "Start now";' in source
    assert 'if (!decisionItemWasAnswered(item)) return "review_pending";' in source


def test_agent_page_transcript_scroll_waits_for_timeline_render() -> None:
    source = AGENT_PAGE.read_text(encoding="utf-8")

    assert 'const transcriptTailKey = `${items.length}:${items.at(-1)?.id ?? "empty"}:${streamingText}`;' in source
    assert "const animationFrame = requestAnimationFrame(() => {" in source
    assert "cancelAnimationFrame(animationFrame)" in source
    assert "}, [transcriptTailKey, pendingBlockingItemId]);" in source


def test_agent_page_recovers_persisted_pending_decisions_while_loading() -> None:
    source = agent_source_text()

    assert "function findPendingBlockingItem(items: TimelineItem[])" in source
    assert "function historyStillLoading(data: HistoryResponse)" in source
    assert "setLoading(historyStillLoading(data))" in source
    assert "setHistoryLoaded(true);\n      setItems(payload.items ?? [])" in source
    assert "setLoading(historyStillLoading(payload))" in source
    assert "const pendingBlockingItem = useMemo(() => findPendingBlockingItem(items), [items])" in source
    assert "const interval = window.setInterval(() => {" in source
    assert "void loadHistory(sessionId, { quiet: true })" in source
    assert "}, 2000)" in source


def test_agent_page_keeps_transcript_mounted_during_active_polling() -> None:
    source = AGENT_PAGE.read_text(encoding="utf-8")
    load_history_source = source[source.index("const loadHistory = async") : source.index("const applyVoiceHistoryIfRelevant")]

    assert "options?: { fresh?: boolean; quiet?: boolean }" in load_history_source
    assert "const quiet = Boolean(options?.quiet)" in load_history_source
    assert "if (!quiet) {\n      setHistoryLoaded(false);\n    }" in load_history_source
    assert "if (!quiet) {\n        setItems([]);\n        setStatus(null);\n      }" in load_history_source
    assert "if (!quiet) {\n        setHistoryLoaded(true);\n      }" in load_history_source


def test_agent_page_final_assistant_message_clears_pending_loading() -> None:
    source = AGENT_PAGE.read_text(encoding="utf-8")

    assert 'payload.type === "assistant_message"' in source
    assert 'if (payload.type !== "assistant_message" || payload.status === "completed") {' in source
    assert "setLoading(false);" in source


def test_agent_page_empty_fresh_session_does_not_block_on_history_loaded_flag() -> None:
    source = agent_surface_source = agent_source_text()

    assert (
        "const transcriptLoading = !historyLoaded && (loading || Boolean(status?.running) || Boolean(sessionId));"
        in source
    )
    assert "{transcriptLoading ? (" in agent_surface_source
    assert "{!historyLoaded ? (" not in agent_surface_source


def test_agent_page_session_rail_prefers_pending_decision_over_running_state() -> None:
    source = agent_source_text()

    assert "pendingBlocked={Boolean(pendingBlockingItem)}" in source
    assert 'value={pendingBlocked ? "blocked" : status?.running ? "running" : "ready"}' in source


def test_agent_voice_mode_does_not_keep_extra_sse_streams_open() -> None:
    source = AGENT_PAGE.read_text(encoding="utf-8")

    assert 'if (agentMode === "voice") {' in source
    assert 'const interval = window.setInterval(() => void loadFallback(), 15000);' in source
    assert 'if (agentMode === "voice") return;' in source
    assert '}, [sessionId, agentMode]);' in source


def test_samantha_voice_orb_is_single_bottom_right_entrypoint() -> None:
    app_source = APP.read_text(encoding="utf-8")
    orb_source = VOICE_ORB.read_text(encoding="utf-8")
    voice_source = VOICE_HOOK.read_text(encoding="utf-8")

    assert "SamanthaVoiceOrb" in app_source
    assert "<SamanthaVoiceOrb />" in app_source
    assert "SamanthaBottomTrigger" not in app_source
    assert "SamanthaOverlay" not in app_source
    assert "export function SamanthaBottomTrigger" not in voice_source
    assert not Path("frontend/src/components/SamanthaOverlay.tsx").exists()

    assert "export function SamanthaVoiceOrb()" in orb_source
    # Orb icon redesign: SamanthaKnotIcon → SamanthaVoiceIcon (sound-wave glyph).
    assert "function SamanthaVoiceIcon()" in orb_source
    assert "data-samantha-voice-icon" in orb_source
    assert 'viewBox="0 0 64 64"' in orb_source
    assert 'strokeWidth="4"' in orb_source
    assert "rgb(16 16 14)" in orb_source
    assert "data-samantha-voice-orb" in orb_source
    assert "useRealtimeVoice()" in orb_source
    assert 'voiceStatus === "error"' in orb_source
    assert 'voiceStatus === "connected" || voiceStatus === "connecting"' in orb_source
    assert "remoteAudioLevel * 0.18" in orb_source
    assert "remoteAudioLevel * 0.45" in orb_source
    assert "remoteAudioLevel * 0.085" in orb_source
    assert "remoteAudioLevel * 28" in orb_source
    assert "radial-gradient(ellipse at 100% 100%" in orb_source
    assert "radial-gradient(circle" in orb_source
    assert "onMouseEnter={() => setHovered(true)}" in orb_source
    assert "onMouseLeave={() => setHovered(false)}" in orb_source
    assert 'aria-label={active ? "End Samantha" : hasError ? "Retry Samantha" : "Activate Samantha"}' in orb_source
    assert 'title={active ? "End Samantha" : hasError ? (voiceError ?? "Voice error — click to retry") : undefined}' in orb_source
    assert "stopVoiceSession()" in orb_source
    assert "void startVoiceSession()" in orb_source
    assert '{hasError ? "error" : active ? "end" : "samantha"}' in orb_source


def test_agent_page_voice_panel_reports_backend_errors_and_closes_tracks() -> None:
    source = VOICE_HOOK.read_text(encoding="utf-8")

    assert "setVoiceError" in source
    assert "getResponseError(response)" in source
    assert "voiceStreamRef.current?.getTracks().forEach((track) => track.stop())" in source
    assert "voicePeerRef.current?.close()" in source


def test_metrics_page_renders_voice_cost_and_delegation_evidence() -> None:
    source = Path("frontend/src/pages/MetricsPage.tsx").read_text(encoding="utf-8")

    assert "Voice cost ledger" in source
    assert "Delegation ratio" in source
    assert "Tool calls" in source
    assert "sideband outputs" in source
    assert "usage_without_realtime_rate_card" in source
