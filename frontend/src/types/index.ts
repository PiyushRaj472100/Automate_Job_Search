export interface Resume { id: string; filename: string; file_hash: string; created_at: string; target_roles: string[]; seniority: string | null; skills: string[]; }
export interface ResumeProfile { target_roles: string[]; skills: string[]; seniority: string; projects: unknown[]; education: unknown[]; experience: unknown[]; }
export interface Health { status: string; project: string; environment: string; version: string; timestamp: string; }
export interface Readiness { ready: boolean; details: Record<string, string>; }
export interface SourceInfo { name: string; policy: string; enabled: boolean; circuit_open: boolean; last_error: string | null; }
export interface DiscoveredJob { source: string; source_job_id: string | null; title: string; company: string; location: string | null; work_mode: string | null; job_url: string | null; skills: string[]; }
export interface DiscoverySummary { summary: { total_requests: number; successful: number; failed: number; duration_s: number }; jobs: DiscoveredJob[]; errors: { source: string; query?: string; error: string }[]; note: string; }
