import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getDashboardStats } from "../api/client";

export function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: getDashboardStats,
    refetchInterval: 10000,
  });

  if (isLoading) return <div className="text-slate-400 text-sm">Loading dashboard metrics…</div>;
  if (error) return <div className="text-red-400 text-sm">Error loading dashboard: {(error as Error).message}</div>;

  return (
    <div className="max-w-5xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Intelligence Dashboard</h1>
        <p className="text-xs text-slate-400 mt-1">
          Real-time metrics on autonomous job hunting, application pipeline, and connected data sources.
        </p>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="text-xs font-medium text-slate-400">Discovered Jobs</div>
          <div className="mt-2 text-3xl font-bold text-white">{data?.jobs_count ?? 0}</div>
          <div className="mt-1 text-[11px] text-emerald-400">Across 3 tech sources</div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="text-xs font-medium text-slate-400">Applications Tracked</div>
          <div className="mt-2 text-3xl font-bold text-indigo-300">{data?.applications_count ?? 0}</div>
          <div className="mt-1 text-[11px] text-indigo-400">Active pipeline</div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="text-xs font-medium text-slate-400">Interviews</div>
          <div className="mt-2 text-3xl font-bold text-emerald-300">{data?.interviews_count ?? 0}</div>
          <div className="mt-1 text-[11px] text-emerald-400">Scheduled / in-progress</div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="text-xs font-medium text-slate-400">Connected Sheets</div>
          <div className="mt-2 text-3xl font-bold text-amber-300">{data?.connected_sheets ?? 0}</div>
          <div className="mt-1 text-[11px] text-amber-400">Auto-sync enabled</div>
        </div>
      </div>

      {/* Recent Discovered Jobs */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">Latest Discovered Jobs</h2>
          <Link to="/jobs" className="text-xs text-indigo-400 hover:text-indigo-300">View All Jobs →</Link>
        </div>

        {(!data?.recent_jobs || data.recent_jobs.length === 0) ? (
          <div className="rounded-xl border border-white/10 bg-white/5 p-6 text-center text-sm text-slate-400">
            No jobs discovered yet. Head over to <Link to="/resumes" className="text-indigo-400 underline">Resumes</Link> and upload your CV or click Hunt Entry-Level Jobs!
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.recent_jobs.map((j) => (
              <div key={j.id} className="rounded-xl border border-white/10 bg-white/5 p-4 flex flex-col justify-between hover:border-indigo-500/30 transition">
                <div>
                  <div className="font-medium text-slate-200 text-sm">{j.title}</div>
                  <div className="mt-1 text-xs text-slate-400">{j.company} · {j.location}</div>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-[11px] text-indigo-300 capitalize">{j.work_mode}</span>
                    <span className="rounded bg-slate-700/50 px-2 py-0.5 text-[11px] text-slate-400 uppercase">{j.source}</span>
                  </div>
                </div>
                <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between">
                  <span className="text-[11px] text-slate-500">{j.created_at ? new Date(j.created_at).toLocaleDateString() : ""}</span>
                  <a href={j.job_url} target="_blank" rel="noreferrer" className="text-xs text-indigo-400 hover:underline">Apply / View →</a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Connected Job Boards Status */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-5">
        <h2 className="text-sm font-semibold text-white">Active Discovery Search Sources</h2>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
          {data?.sources.map((s) => (
            <div key={s.name} className="rounded-lg border border-white/5 bg-slate-900/60 p-3 flex items-center justify-between">
              <div>
                <div className="font-medium text-xs text-slate-200 capitalize">{s.name}</div>
                <div className="text-[10px] text-slate-500">{s.policy}</div>
              </div>
              <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> Online
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
