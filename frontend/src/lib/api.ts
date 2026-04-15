import type {
  ApprovalDetails,
  ApprovalSubmission,
  BoardData,
  DispatchResponse,
  FeatureCreate,
  FeatureResponse,
  KBDocument,
  MemoryEntry,
  MetricsData,
  ProjectCreate,
  ProjectResponse,
} from "./types";

const BASE = "/api";

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

// Board
export const fetchBoard = () => fetchJSON<BoardData>("/dashboard/board");

// Metrics
export const fetchMetrics = () => fetchJSON<MetricsData>("/dashboard/metrics");

// Approval details
export const fetchApprovalDetails = (gateId: string) =>
  fetchJSON<ApprovalDetails>(`/dashboard/approvals/${gateId}`);

// Dispatch a task
export const dispatchTask = (taskId: string) =>
  postJSON<DispatchResponse>("/dispatch", { task_id: taskId });

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
export const listKBDocs = (params?: { task_id?: string; doc_type?: string; limit?: number }) => {
  const qs = params ? "?" + new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))
  ).toString() : "";
  return fetchJSON<KBDocument[]>(`/kb/${qs}`);
};

export const getKBDoc = (id: string) =>
  fetchJSON<KBDocument>(`/kb/${id}`);

export const searchKBDocs = (query: string) =>
  fetchJSON<KBDocument[]>(`/kb/search?q=${encodeURIComponent(query)}`);

// Memory
export const listMemories = () =>
  fetchJSON<MemoryEntry[]>("/memory/");

export const getMemory = (slug: string) =>
  fetchJSON<MemoryEntry>(`/memory/${slug}`);
