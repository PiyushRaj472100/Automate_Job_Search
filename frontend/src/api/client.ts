import type { DiscoverySummary, Health, Readiness, Resume, ResumeProfile, SourceInfo } from "../types";

const BASE = import.meta.env.VITE_API_URL ?? "https://automate-job-search.onrender.com";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try { res = await fetch(`${BASE}${path}`, init); }
  catch { throw new ApiError(0, "Backend unreachable"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok && res.status !== 503) throw new ApiError(res.status, body.detail ?? res.statusText);
  if (!res.ok && path !== "/ready") throw new ApiError(503, body.detail ?? "Service unavailable");
  return body as T;
}

const json = (b: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(b)
});

export const getHealth = () => req<Health>("/health");
export const getReadiness = () => req<Readiness>("/ready");

// Resumes
export const listResumes = () => req<Resume[]>("/resumes");
export const getResume = (id: string) => req<Resume>(`/resumes/${id}`);
export const getResumeProfile = (id: string) => req<ResumeProfile>(`/resumes/${id}/profile`);
export const uploadResume = (file: File) => {
  const f = new FormData();
  f.append("file", file);
  return req<Resume>("/resumes", { method: "POST", body: f });
};

// Discovery
export const getSources = () => req<SourceInfo[]>("/discovery/sources");
export const generateQueries = (b: { target_roles: string[]; skills: string[]; locations: string[] }) =>
  req<{ queries: string[] }>("/discovery/generate-queries", json(b));
export const runDiscovery = (queries: string[]) => req<DiscoverySummary>("/discovery/search", json({ queries }));

// Google Sheets
export const getResumeSheet = (id: string) => req<{ spreadsheet_url: string }>(`/resumes/${id}/sheets`);
export const createResumeSheet = (id: string) => req<{ spreadsheet_url: string }>(`/resumes/${id}/sheets`, { method: "POST" });
export const connectResumeSheet = (id: string, spreadsheet_url: string) =>
  req<{ spreadsheet_url: string; message: string }>(`/resumes/${id}/connect-sheet`, json({ spreadsheet_url }));
export const huntResumeJobs = (id: string) =>
  req<{ status: string; discovered: number; suitable_entry_level: number; new_persisted: number; synced_to_sheet: number }>(`/resumes/${id}/hunt`, { method: "POST" });

// Dashboard
export const getDashboardStats = () => req<{
  resumes_count: number;
  jobs_count: number;
  applications_count: number;
  interviews_count: number;
  connected_sheets: number;
  recent_jobs: Array<{
    id: string;
    title: string;
    company: string;
    location: string;
    work_mode: string;
    source: string;
    job_url: string;
    created_at: string;
  }>;
  sources: Array<{ name: string; enabled: boolean; policy: string }>;
  timestamp: string;
}>("/dashboard/stats");

// Jobs
export interface JobItem {
  id: string;
  resume_id: string;
  title: string;
  company: string;
  location: string;
  work_mode: string;
  job_url: string;
  application_url?: string;
  description?: string;
  source: string;
  status: string;
  application_status: string;
  created_at: string;
  linkedin_recruiter_url?: string;
  linkedin_manager_url?: string;
  linkedin_referral_url?: string;
}

export const getJobs = (params?: { q?: string; work_mode?: string }) => {
  const sp = new URLSearchParams();
  if (params?.q) sp.set("q", params.q);
  if (params?.work_mode) sp.set("work_mode", params.work_mode);
  return req<JobItem[]>(`/jobs?${sp.toString()}`);
};
export const applyToJob = (id: string) => req<{ message: string; application_id: string }>(`/jobs/${id}/apply`, { method: "POST" });
export const deleteJob = (id: string) => req<{ message: string }>(`/jobs/${id}`, { method: "DELETE" });

// Recruiters
export interface RecruiterItem {
  company: string;
  job_title: string;
  job_url: string;
  location: string;
  search_links: Array<{ title: string; url: string; role_type: string }>;
  outreach_template: string;
}
export const getRecruiters = () => req<RecruiterItem[]>("/recruiters");

// Applications
export interface ApplicationItem {
  id: string;
  resume_id: string;
  job_id: string;
  status: "SAVED" | "APPLIED" | "INTERVIEWING" | "OFFER" | "REJECTED";
  notes?: string;
  applied_at?: string;
  created_at?: string;
  job?: {
    title: string;
    company: string;
    location: string;
    work_mode: string;
    job_url: string;
    source: string;
  };
}
export const getApplications = (status?: string) => {
  const url = status ? `/applications?status=${status}` : "/applications";
  return req<ApplicationItem[]>(url);
};
export const updateApplication = (id: string, data: { status?: string; notes?: string }) =>
  req<ApplicationItem>(`/applications/${id}`, json(data, "PATCH"));
export const deleteApplication = (id: string) => req<{ message: string }>(`/applications/${id}`, { method: "DELETE" });

// Settings
export const getSettings = () => req<{
  project_name: string;
  environment: string;
  database_configured: boolean;
  google_sheets_configured: boolean;
  service_account_email?: string;
  google_sheet_url: string;
  share_email: string;
  gemini_api_key_configured: boolean;
  gemini_model: string;
  version: string;
}>("/settings");
export const updateSettings = (data: { google_sheet_url?: string; gemini_api_key?: string; share_email?: string }) =>
  req<{ status: string; message: string; google_sheet_url: string }>("/settings", json(data, "PATCH"));
