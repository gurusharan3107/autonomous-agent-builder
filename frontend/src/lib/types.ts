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
  blocked_reason: string;
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

export type KBDocType = "adr" | "api_contract" | "schema" | "runbook" | "context";

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
