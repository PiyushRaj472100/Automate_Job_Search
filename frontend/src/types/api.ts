// ============================================================
// TypeScript types derived directly from the backend schemas
// ============================================================

// ---- Health / Ready / Metrics ----

export interface HealthResponse {
  status: string;
  project: string;
  environment: string;
  version: string;
  timestamp: string;
}

export interface ReadyResponse {
  ready: boolean;
  details: Record<string, string>;
  timestamp: string;
}

export interface MetricsResponse {
  last_successful_run: string | null;
  last_failed_run: string | null;
  total_runs: number;
  failed_runs: number;
  timestamp: string;
}

// ---- Resumes ----

export interface ResumeSummaryResponse {
  id: string;
  file_name: string;
  file_hash: string | null;
  created_at: string;
  profiles_count: number;
}

export interface ResumeProfileDetailResponse {
  id: string;
  resume_id: string;
  profile_name: string;
  target_role: string;
  target_locations: string[];
  work_modes: string[];
  max_experience_years: number;
  is_active: boolean;
  skills: string[];
  structured_data: Record<string, unknown> | null;
  created_at: string;
}

export interface ResumeDetailResponse {
  id: string;
  file_name: string;
  file_hash: string | null;
  created_at: string;
  updated_at: string;
  profiles: ResumeProfileDetailResponse[];
  raw_text_preview: string | null;
}

export interface ResumeUploadResult {
  message: string;
  resume_id: string;
  profile_id: string;
  file_name: string;
  file_hash: string;
  is_duplicate: boolean;
  profile_name: string;
  target_role: string;
  seniority: string;
  skills_extracted_count: number;
}

// ---- Google Sheets ----

export interface SheetStatusResponse {
  resume_id: string;
  file_name: string;
  spreadsheet_id: string | null;
  spreadsheet_url: string | null;
  is_linked: boolean;
}

export interface SheetCreateResponse {
  message: string;
  resume_id: string;
  file_name: string;
  spreadsheet_id: string;
  spreadsheet_url: string;
  worksheets: string[];
}

// ---- Discovery ----

export interface SearchQuery {
  query_text: string;
  role_title: string;
  skills: string[];
  experience_level: string;
  location: string | null;
  work_mode: string | null;
  limit: number;
}

export interface SourcePolicy {
  source_name: string;
  source_type: string;
  base_url: string;
  official_api_available: boolean;
  feed_available: boolean;
  public_page_available: boolean;
  robots_restrictions: string;
  rate_limit_per_minute: number;
  authentication_required: boolean;
  permitted_access_method: string;
  notes: string;
}

export interface SourceHealthCheck {
  source_name: string;
  is_healthy: boolean;
  status_code: number | null;
  response_time_ms: number;
  details: string;
  timestamp: string;
}

export interface NormalizedJob {
  external_job_id: string | null;
  requisition_id: string | null;
  title: string;
  company_name: string;
  location: string;
  work_mode: string;
  description: string;
  job_url: string;
  application_url: string | null;
  canonical_url: string;
  source: string;
  posting_date: string | null;
  normalized_company: string;
  normalized_title: string;
  normalized_location: string;
  dedup_hash: string;
  tags: string[];
}

export interface DiscoveryExecutionSummary {
  total_queries: number;
  total_raw_found: number;
  total_normalized: number;
  total_deduplicated: number;
  successful_sources: string[];
  failed_sources: Record<string, string>;
}

export interface SearchDiscoveryResponse {
  summary: DiscoveryExecutionSummary;
  jobs: NormalizedJob[];
}

// ---- Query generation request ----

export interface QueryGenerationRequest {
  target_roles: string[];
  skills: string[];
  locations: string[];
  work_modes: string[];
  max_queries: number;
}

export interface SearchDiscoveryRequest {
  queries: SearchQuery[];
  sources: string[] | null;
}

// ---- API Error ----

export interface ApiError {
  detail: string | Record<string, unknown>;
}
