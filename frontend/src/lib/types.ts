// TypeScript types matching Pydantic response schemas

export type TaskStatus =
  | "pending"
  | "queued"
  | "planning"
  | "design"
  | "design_review"
  | "implementation"
  | "quality_gates"
  | "pr_creation"
  | "review_pending"
  | "build_verify"
  | "done"
  | "blocked"
  | "capability_limit"
  | "failed";

export type TaskPhase =
  | "requirements"
  | "planning"
  | "design"
  | "implementation"
  | "verification"
  | "integration"
  | "complete";

export type GateStatus = "pass" | "fail" | "warn" | "timeout" | "error" | "pending";

export type ApprovalDecision = "approve" | "reject" | "override" | "request_changes";

// Board

export interface TaskActivityEvent {
  id: string;
  run_id: string;
  agent_name: string;
  status: string;
  event_type: string;
  action: string;
  file_path: string;
  timestamp: string;
}

export interface TaskAgentRunSummary {
  id: string;
  agent_name: string;
  runtime_sdk: string;
  provider: string;
  model: string;
  effort?: string | null;
  cost_usd: number;
  estimated_cost_usd: number;
  estimated_codex_credits?: number | null;
  cost_source?: string;
  pricing_model?: string;
  pricing_note?: string;
  tokens_input: number;
  tokens_output: number;
  tokens_cached: number;
  num_turns: number;
  duration_ms: number;
  status: string;
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface TaskBoardItem {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  phase: TaskPhase;
  feature_id: string;
  feature_title: string;
  feature_description: string;
  feature_priority: number;
  feature_item_type: string;
  acceptance_criteria: string[];
  dependencies: string[];
  sprint_execution?: Record<string, unknown> | null;
  agent_name: string;
  runtime_sdk: string;
  provider: string;
  model: string;
  effort?: string | null;
  cost_usd: number;
  total_cost: number;
  tokens_input: number;
  tokens_output: number;
  tokens_cached: number;
  num_turns: number;
  duration_ms: number;
  approval_gate_id: string;
  approval_gate_type: string;
  pending_approval_count: number;
  blocked_reason: string;
  latest_run_status: string;
  observability?: Record<string, unknown> | null;
  agent_runs: TaskAgentRunSummary[];
  activity_timeline: TaskActivityEvent[];
  updated_at: string | null;
}

export interface SprintBatchSummary {
  id: string;
  title: string;
  execution_mode: string;
  model: string;
  effort: string;
  depends_on_batches: string[];
}

export interface SprintPlanSummary {
  plan_id: string;
  design_id: string;
  sprint_number: number;
  mode: string;
  model: string;
  effort: string;
  single_plan: boolean;
  single_design: boolean;
  strategy: string;
  batch_count: number;
  sequential_count: number;
  parallel_count: number;
  context_strategy: string;
  runtime_tool_strategy: Record<string, unknown>;
  batches: SprintBatchSummary[];
  plan_details: Record<string, unknown>;
  design_details: Record<string, unknown>;
}

export interface CurrentSprintItemSummary {
  id: string;
  title: string;
  status: string;
  description?: string;
  dependencies?: string[];
  sprint_execution?: Record<string, unknown>;
}

export interface CurrentSprintSummary {
  sprint_id: string;
  label: string;
  active_phase: string;
  phase_statuses: Record<string, string>;
  included_items: CurrentSprintItemSummary[];
  task_counts: Record<string, number>;
  plan_doc_id?: string | null;
  design_doc_id?: string | null;
  generated_task_ids: string[];
  generated_tasks: CurrentSprintItemSummary[];
  verification_status: string;
  verification_evidence?: Record<string, unknown> | null;
  runtime_sdk: string;
  model: string;
  effort: string;
}

export interface BoardData {
  pending: TaskBoardItem[];
  active: TaskBoardItem[];
  review: TaskBoardItem[];
  done: TaskBoardItem[];
  blocked: TaskBoardItem[];
  sprint_plan?: SprintPlanSummary | null;
  current_sprint?: CurrentSprintSummary | null;
  sprints: CurrentSprintSummary[];
}

export interface TaskRecoveryResponse {
  status: string;
  task_id: string;
  previous_status: string;
  current_status: string;
  next_step: string;
}

// Metrics

export interface DiffHunkPreview {
  file: string;
  added_lines: number;
  removed_lines: number;
  preview: string;
}

export interface DiffSummary {
  files_changed: number;
  insertions: number;
  deletions: number;
  hunks: DiffHunkPreview[];
}

export interface AgentRunItem {
  id: string;
  task_id: string;
  agent_name: string;
  runtime_sdk: string;
  provider: string;
  model: string;
  effort?: string | null;
  cost_usd: number;
  estimated_cost_usd: number;
  estimated_codex_credits?: number | null;
  cost_source?: string;
  pricing_model?: string;
  pricing_note?: string;
  tokens_input: number;
  tokens_output: number;
  tokens_cached: number;
  num_turns: number;
  duration_ms: number;
  stop_reason: string | null;
  status: string;
  error: string | null;
  confidence?: number | null;
  diff_summary?: DiffSummary | null;
  observability?: Record<string, unknown> | null;
  started_at: string;
  completed_at: string | null;
}

export interface OptimizationDriver {
  agent_name: string;
  runs: number;
  raw_tokens: number;
  noncached_plus_output_tokens: number;
  cached_tokens: number;
  avoidable_token_estimate: number;
}

export interface OptimizationSummary {
  raw_token_total: number;
  noncached_plus_output_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  cache_ratio: number;
  phase_ceremony_tokens: number;
  avoidable_token_estimate: number;
  avoidable_cost_flags: Array<{ flag: string; count: number }>;
  top_cost_drivers: OptimizationDriver[];
  recommended_next_change: string;
  benchmark: {
    target_min_raw_tokens: number;
    target_max_raw_tokens: number;
    status: string;
  };
  phase_token_breakdown: Record<string, number>;
}

export interface MetricsData {
  total_cost: number;
  total_estimated_cost_usd: number;
  total_estimated_codex_credits?: number | null;
  total_tokens: number;
  total_runs: number;
  gate_pass_rate: number;
  optimization_summary?: OptimizationSummary;
  optimization_decision?: OptimizationDecision;
  runtime_decision_summary?: RuntimeDecisionSummary;
  deterministic_script_candidates?: DeterministicScriptCandidate[];
  runs: AgentRunItem[];
}

// Observability

export interface ObservabilityCoverage {
  mode: "claude_otel" | "codex_app_server" | string;
  source: string;
  runtime_sdk: string;
  available_signals: string[];
  counts: {
    tools: number;
    errors: number;
    delegations: number;
  };
  otel: Record<string, unknown> & {
    enabled?: boolean;
    collector_status?: string;
    endpoint_configured?: boolean;
    endpoint_placeholder?: boolean;
    sensitive_data_flags?: string[];
  };
  codex: {
    app_server_events?: boolean;
    token_usage?: boolean;
    native_user_input?: boolean;
    estimated_cost_usd?: number;
    estimated_codex_credits?: number | null;
    raw_token_total?: number;
    cache_ratio?: number;
    top_cost_drivers?: OptimizationDriver[];
    avoidable_cost_flags?: Array<{ flag: string; count: number }>;
  };
  telemetry_health?: {
    selected_runtime?: string;
    claude_native?: TelemetryHealthArea;
    codex_native?: TelemetryHealthArea;
    builder_product?: TelemetryHealthArea & {
      complete?: boolean;
      missing_facts?: string[];
      counts?: Record<string, number>;
      canonical_facts?: string[];
    };
    contract?: string;
  };
  deterministic_recommendations?: DeterministicRecommendation[];
  resolved_recommendations?: DeterministicRecommendation[];
  recommendation_lifecycle?: {
    available?: boolean;
    counts?: Record<string, number>;
    by_code?: Record<string, unknown>;
  };
  missing_signals: string[];
  next: string;
}

export interface TelemetryHealthArea {
  status?: string;
  enabled?: boolean;
  configured?: boolean;
  source?: string;
  collector_status?: string;
  collector_reachable?: boolean | null;
  collector?: Record<string, unknown>;
  emitted_signals?: Record<string, boolean>;
  signals?: Record<string, boolean>;
  sensitive_data_flags?: string[];
  reason?: string;
  endpoint?: string;
  exporter?: string;
  project_local?: boolean;
}

export interface DeterministicRecommendation {
  code: string;
  severity: string;
  trigger: string;
  recommendation: string;
  source?: string;
  lifecycle_status?: string;
  decision_reason?: string;
  decided_at?: string;
  evidence?: Record<string, unknown>;
}

export interface RuntimeAggregateRow {
  agent_name?: string;
  runtime_sdk?: string;
  provider?: string;
  model?: string;
  effort?: string;
  runs: number;
  turns: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  cost_usd: number;
  estimated_cost_usd: number;
  estimated_codex_credits?: number | null;
  duration_ms: number;
}

export interface RuntimeAggregates {
  available: boolean;
  reason?: string;
  by_agent: RuntimeAggregateRow[];
  by_runtime: RuntimeAggregateRow[];
  by_model_effort: RuntimeAggregateRow[];
  totals: RuntimeAggregateRow;
  stop_reasons: Array<{ stop_reason: string; count: number }>;
  phase_ceremony: Record<string, unknown>;
  approval_wait: Record<string, unknown>;
  provider_limits: {
    available: boolean;
    count: number;
    ready_to_resume?: number;
    waiting_for_reset?: number;
    reset_at?: string[];
  };
  optimization_summary?: OptimizationSummary & { available?: boolean; reason?: string };
  tool_observability: {
    agent_run_events_available: boolean;
    agent_run_event_count: number;
    missing_tool_events: boolean;
    tool_counts: Array<{ tool_name: string; calls: number }>;
    repeated_retrieval_signal: {
      detected: boolean;
      tools: Array<{ tool_name: string; calls: number }>;
      summary_tools?: Array<{ tool_name: string; calls: number }>;
      summary_calls?: number;
    };
  };
  deterministic_script_candidates?: DeterministicScriptCandidate[];
}

export interface ObservabilityRecommendation {
  code: string;
  severity: "high" | "medium" | "low" | "info" | string;
  title: string;
  detail: string;
}

export interface RuntimeCapability {
  id: string;
  label: string;
  native: boolean;
  native_signal: string;
  fallback: string;
  diagnostic_gap: string;
  recommendation: string;
}

export interface RuntimeCapabilityMatrix {
  runtime: string;
  supported_runtimes: string[];
  capabilities: RuntimeCapability[];
  native_count: number;
  fallback_count: number;
  diagnostic_gaps: string[];
  principle: string;
}

export interface PhaseRuntimeDecision {
  phase: string;
  selected_runtime: string;
  model_effort: string;
  tool_route: string;
  subagent_policy: string;
  context_strategy: string;
  expected_evidence: string;
  reason_code: string;
}

export interface DeterministicScriptCandidate {
  code: string;
  trigger: string;
  recommendation: string;
  severity: string;
  estimated_savings_tokens?: number;
  estimated_savings_basis?: string;
}

export interface RuntimeDecisionSummary {
  runtime: string;
  capability_gaps: string[];
  native_capability_count: number;
  fallback_capability_count: number;
  phase_decisions: PhaseRuntimeDecision[];
  deterministic_script_candidates: DeterministicScriptCandidate[];
  next: string;
}

export interface OptimizationDecision {
  runtime: string;
  primary_score_surface: string;
  diagnostic_surface: string;
  cli_surface: string;
  next_action: string;
  target_area: string;
  reason: string;
  top_driver: Partial<OptimizationDriver>;
  deterministic_script_candidates: DeterministicScriptCandidate[];
  estimated_script_savings_tokens: number;
  model_effort_action: string;
  subagent_action: string;
  ui_placement: Record<string, string>;
}

export interface ObservabilityData {
  ok: boolean;
  status: string;
  schema_version: string;
  generated_at: string;
  runtime: {
    selected_runtime_sdk: "claude_agent_sdk" | "codex_sdk" | string;
    runtime_sdk: string;
    provider: string;
    model: string;
    effort: string;
    coverage_mode: string;
  };
  observability_coverage: ObservabilityCoverage;
  runtime_aggregates: RuntimeAggregates;
  optimization_summary?: OptimizationSummary & { available?: boolean; reason?: string };
  optimization_decision?: OptimizationDecision;
  runtime_capability_matrix?: RuntimeCapabilityMatrix;
  phase_runtime_decisions?: PhaseRuntimeDecision[];
  deterministic_script_candidates?: DeterministicScriptCandidate[];
  runtime_decision_summary?: RuntimeDecisionSummary;
  recommendations: ObservabilityRecommendation[];
  deterministic_recommendations?: DeterministicRecommendation[];
  resolved_recommendations?: DeterministicRecommendation[];
}

export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed" | string;
  active_form?: string | null;
}

export interface TodoSnapshot {
  session_id: string;
  pending_count: number;
  in_progress_count: number;
  completed_count: number;
  updated_at: string;
  todos: TodoItem[];
}

export interface ShellSummary {
  active_session_id: string | null;
  active_session_ids: string[];
  active_run_count: number;
  pending_approvals: number;
  pending_questions: number;
  running_label: string;
  total_cost: number;
  total_tokens: number;
  permission_mode: string;
  mcp_servers: string[];
  mcp_tools: string[];
  todo_snapshots: TodoSnapshot[];
}

export interface InboxItem {
  id: string;
  task_id: string;
  task_title: string;
  task_status: TaskStatus | string;
  feature_title: string;
  project_name: string;
  gate_type: string;
  status: string;
  created_at: string | null;
  resolved_at: string | null;
  latest_run_id: string | null;
  latest_run_agent: string | null;
  latest_run_status: string | null;
  latest_run_cost_usd: number;
  latest_run_turns: number;
  latest_run_duration_ms: number;
  approval_url: string;
}

export interface CompareRunSide extends AgentRunItem {
  task_title: string;
  feature_title: string;
  project_name: string;
  session_id: string | null;
  gate_results: GateResultItem[];
  approvals: Array<{
    id: string;
    gate_type: string;
    status: string;
    created_at: string | null;
    resolved_at: string | null;
  }>;
}

export interface ComparePayload {
  same_task: boolean;
  left: CompareRunSide;
  right: CompareRunSide;
}

export interface CommandPaletteItem {
  id: string;
  kind: string;
  label: string;
  description: string;
  route?: string | null;
  action?: string | null;
  task_id?: string | null;
  gate_id?: string | null;
  session_id?: string | null;
}

export interface CommandIndex {
  items: CommandPaletteItem[];
}

export interface RuntimePreferenceState {
  boardDensity: "comfortable" | "compact";
  agentInspectorDefault: "evidence" | "sessions";
  transcriptFilterDefault: "thread" | "full" | "logs";
  transcriptLayout: "cards" | "timeline";
  compareDisplayMode: "split" | "stacked";
}

export type RuntimeSdk = "claude" | "claude_managed" | "codex_sdk";

export interface RuntimeSettings {
  sdk: string;
  raw_sdk?: string | null;
  provider: string;
  model: string;
  api_base_url?: string | null;
  api_key_env?: string | null;
  codex_profile?: string | null;
  sandbox_mode?: string | null;
  approval_policy?: string | null;
  tracing?: string | null;
  telemetry?: {
    active_lane?: string;
    active_enabled?: boolean;
    inactive_disabled?: boolean;
    claude?: {
      enabled?: boolean;
      endpoint?: string;
      service_name?: string;
      include_session_id?: string;
    };
    codex?: {
      enabled?: boolean;
      source?: string;
      cost_source?: string;
    };
  };
  capabilities?: Record<string, boolean>;
  errors?: Array<Record<string, string>>;
  ok: boolean;
  status?: string;
  changed_keys?: string[];
}

// Approvals

export interface ThreadEntry {
  role: "agent" | "human";
  agent_name: string;
  author: string;
  content: string;
  timestamp: string;
}

export interface GateResultItem {
  id: string;
  gate_name: string;
  status: GateStatus;
  findings_count: number;
  elapsed_ms: number;
  timeout: boolean;
  evidence?: Record<string, unknown> | null;
  error_code?: string | null;
  remediation_attempted?: boolean;
  remediation_succeeded?: boolean;
  analysis_depth?: string | null;
}

export interface ApprovalDetails {
  gate_id: string;
  gate_type: string;
  gate_status: string;
  task_id: string;
  task_title: string;
  task_status: TaskStatus;
  task_description: string;
  feature_title: string;
  project_name: string;
  thread: ThreadEntry[];
  runs: AgentRunItem[];
  gate_results: GateResultItem[];
}

// Dispatch

export interface DispatchResponse {
  status: string;
  task_id: string;
  current_status: TaskStatus;
}

export interface ApprovalSubmission {
  approver_email: string;
  decision: ApprovalDecision;
  comment: string;
  reason: string;
}

// Projects

export interface ProjectCreate {
  name: string;
  description?: string;
  repo_url?: string;
  language?: string;
}

export interface ProjectResponse {
  id: string;
  name: string;
  description: string;
  repo_url: string;
  language: string;
  created_at: string;
}

// Features (CRUD)

export interface FeatureCreate {
  title: string;
  description?: string;
  priority?: number;
}

export interface FeatureResponse {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: string;
  priority: number;
  created_at: string;
}

// Knowledge Base

export type KBDocType =
  | "adr"
  | "api_contract"
  | "schema"
  | "runbook"
  | "context"
  | "raw"
  | "reverse-engineering"
  | "metadata";

export interface KBDocument {
  id: string;
  task_id: string;
  doc_type: KBDocType;
  title: string;
  content: string;
  version: number;
  created_at: string;
  wikilinks?: string[];
  tags?: string[];
  date_published?: string;
  source_author?: string;
  source_title?: string;
  source_url?: string;
  card_summary?: string;
  detail_summary?: string;
  excerpt?: string;
  scope?: "local" | "global";
  path?: string;
}

export interface RelatedDocs {
  wikilinks: KBDocument[];
  backlinks: KBDocument[];
  similar: Array<KBDocument & { similarity_score?: number; shared_tags?: string[] }>;
}

export interface TagInfo {
  name: string;
  count: number;
  related: Record<string, number>;
  available: boolean;
}

// Memory

export type MemoryType = "decision" | "pattern" | "correction";

export interface MemoryEntry {
  slug: string;
  file: string;
  title: string;
  type: MemoryType;
  phase: string;
  entity: string;
  tags: string[];
  status: string;
  date: string;
  content?: string;
}

export interface OnboardingPhase {
  id: string;
  title: string;
  status: "pending" | "running" | "passed" | "failed" | "blocked";
  message: string;
  started_at: string | null;
  finished_at: string | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export interface OnboardingStatus {
  repo: {
    root: string;
    name: string;
    language: string;
    framework: string;
    branch: string;
    dirty: boolean;
    status_lines: number;
  };
  current_phase: string;
  ready: boolean;
  started_at: string | null;
  updated_at: string;
  phases: OnboardingPhase[];
  entity_counts: {
    projects: number;
    features: number;
    tasks: number;
  };
  kb_status: {
    collection: string;
    document_count: number;
    lint_passed: boolean;
    quality_gate: string;
    message: string;
    rule_based_score?: number;
    rule_based_summary?: string;
    agent_score?: number;
    agent_summary?: string;
  };
  scan_summary: Record<string, unknown>;
  archives: Array<{ type: string; path: string }>;
  errors: Array<{ phase: string; error: string; timestamp: string }>;
}
