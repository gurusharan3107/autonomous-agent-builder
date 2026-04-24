// TypeScript types matching Pydantic response schemas

export type TaskStatus =
  | "pending"
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

export type GateStatus = "pass" | "fail" | "warn" | "timeout" | "error" | "pending";

export type ApprovalDecision = "approve" | "reject" | "override" | "request_changes";

// Board

export interface TaskBoardItem {
  id: string;
  title: string;
  status: TaskStatus;
  feature_title: string;
  agent_name: string;
  cost_usd: number;
  total_cost: number;
  num_turns: number;
  duration_ms: number;
  approval_gate_id: string;
  approval_gate_type: string;
  pending_approval_count: number;
  blocked_reason: string;
  latest_run_status: string;
  updated_at: string | null;
}

export interface BoardData {
  pending: TaskBoardItem[];
  active: TaskBoardItem[];
  review: TaskBoardItem[];
  done: TaskBoardItem[];
  blocked: TaskBoardItem[];
}

// Metrics

export interface AgentRunItem {
  id: string;
  task_id: string;
  agent_name: string;
  cost_usd: number;
  tokens_input: number;
  tokens_output: number;
  tokens_cached: number;
  num_turns: number;
  duration_ms: number;
  stop_reason: string | null;
  status: string;
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface MetricsData {
  total_cost: number;
  total_tokens: number;
  total_runs: number;
  gate_pass_rate: number;
  runs: AgentRunItem[];
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
  compareDisplayMode: "split" | "stacked";
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
