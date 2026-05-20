import type {
  CommandIndex,
  ComparePayload,
  ApprovalDetails,
  ApprovalSubmission,
  BoardData,
  DispatchResponse,
  FeatureCreate,
  FeatureResponse,
  InboxItem,
  KBDocument,
  MemoryEntry,
  MetricsData,
  ObservabilityData,
  OnboardingStatus,
  ProjectCreate,
  ProjectResponse,
  RuntimeSettings,
  RuntimeSdk,
  ShellSummary,
  TaskRecoveryResponse,
} from "./types";

const BASE = "/api";

export function buildKBDocPath(
  id: string,
  scope: "local" | "global" = "local",
  suffix = "",
): string {
  const encodedId = id.split("/").map((segment) => encodeURIComponent(segment)).join("/");
  const params = new URLSearchParams({ scope });
  return `/kb/${encodedId}${suffix}?${params.toString()}`;
}

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

function openSnapshotStream<T>(
  path: string,
  onSnapshot: (payload: T) => void,
): EventSource {
  const stream = new EventSource(`${BASE}${path}`);
  stream.addEventListener("snapshot", (event) => {
    const message = event as MessageEvent<string>;
    onSnapshot(JSON.parse(message.data) as T);
  });
  return stream;
}

// Board
export const fetchBoard = () => fetchJSON<BoardData>("/dashboard/board");
export const openBoardStream = (onSnapshot: (payload: BoardData) => void) =>
  openSnapshotStream("/dashboard/board/stream", onSnapshot);

// Metrics
export const fetchMetrics = () => fetchJSON<MetricsData>("/dashboard/metrics");
export const fetchObservability = () => fetchJSON<ObservabilityData>("/dashboard/observability");
export const fetchShellSummary = () => fetchJSON<ShellSummary>("/dashboard/shell-summary");
export const fetchRuntimeSettings = () => fetchJSON<RuntimeSettings>("/agent/runtime");
export const updateRuntimeSettings = (sdk: RuntimeSdk) =>
  postJSON<RuntimeSettings>("/agent/runtime", { sdk });
export const fetchInbox = () => fetchJSON<InboxItem[]>("/dashboard/inbox");
export const fetchCompare = (leftRunId: string, rightRunId: string) =>
  fetchJSON<ComparePayload>(
    `/dashboard/compare?left_run_id=${encodeURIComponent(leftRunId)}&right_run_id=${encodeURIComponent(rightRunId)}`,
  );
export const fetchCommandIndex = () => fetchJSON<CommandIndex>("/dashboard/command-index");

// Approval details
export const fetchApprovalDetails = (gateId: string) =>
  fetchJSON<ApprovalDetails>(`/dashboard/approvals/${gateId}`);
export const openApprovalStream = (
  gateId: string,
  onSnapshot: (payload: ApprovalDetails) => void,
) => openSnapshotStream(`/dashboard/approvals/${gateId}/stream`, onSnapshot);

// Dispatch a task
export const dispatchTask = (taskId: string) =>
  postJSON<DispatchResponse>("/dispatch", { task_id: taskId });

export const recoverTask = (taskId: string) =>
  postJSON<TaskRecoveryResponse>(`/tasks/${taskId}/recover`, {});

// Submit approval
export const submitApproval = (gateId: string, data: ApprovalSubmission) =>
  postJSON<{ status: string; gate_status: string }>(
    `/approval-gates/${gateId}/approve`,
    data,
  );

// Projects
export const listProjects = () =>
  fetchJSON<ProjectResponse[]>("/projects/");

export const createProject = (data: ProjectCreate) =>
  postJSON<ProjectResponse>("/projects/", data);

// Features
export const listFeatures = (projectId: string) =>
  fetchJSON<FeatureResponse[]>(`/projects/${projectId}/features`);

export const createFeature = (projectId: string, data: FeatureCreate) =>
  postJSON<FeatureResponse>(`/projects/${projectId}/features`, data);

// Knowledge Base
export const listKBDocs = (params?: { task_id?: string; doc_type?: string; tags?: string; limit?: number; scope?: "local" | "global" }) => {
  const qs = params ? "?" + new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))
  ).toString() : "";
  return fetchJSON<KBDocument[]>(`/kb/${qs}`);
};

export const getKBDoc = (id: string, scope: "local" | "global" = "local") =>
  fetchJSON<KBDocument>(buildKBDocPath(id, scope));

export const searchKBDocs = (query: string, scope: "local" | "global" = "local") =>
  fetchJSON<KBDocument[]>(`/kb/search?q=${encodeURIComponent(query)}&scope=${scope}`);

export const getKBTags = (scope: "local" | "global" = "local") =>
  fetchJSON<import("./types").TagInfo[]>(`/kb/tags?scope=${scope}`);

export const getRelatedDocs = (docId: string, scope: "local" | "global" = "local") =>
  fetchJSON<import("./types").RelatedDocs>(buildKBDocPath(docId, scope, "/related"));

export const getAllTags = (scope: "local" | "global" = "local", selectedTags?: string[]) => {
  const params = new URLSearchParams({ scope });
  if (selectedTags && selectedTags.length > 0) {
    params.set("tags", selectedTags.join(","));
  }
  return fetchJSON<import("./types").TagInfo[]>(`/kb/tags?${params.toString()}`);
};

// Memory
export const listMemories = () =>
  fetchJSON<MemoryEntry[]>("/memory/");

export const getMemory = (slug: string) =>
  fetchJSON<MemoryEntry>(`/memory/${slug}`);

// Onboarding
export const fetchOnboardingStatus = () =>
  fetchJSON<OnboardingStatus>("/onboarding/status");

export const startOnboarding = (runtimeSdk?: RuntimeSdk) =>
  postJSON<OnboardingStatus>("/onboarding/start", runtimeSdk ? { runtime_sdk: runtimeSdk } : {});

export const retryOnboarding = () =>
  postJSON<OnboardingStatus>("/onboarding/retry", {});

export const openOnboardingStream = (
  onSnapshot: (payload: OnboardingStatus) => void,
) => openSnapshotStream("/onboarding/stream", onSnapshot);
