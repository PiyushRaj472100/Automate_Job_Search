import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applyToJob, deleteJob, getJobs } from "../api/client";

export function Jobs() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [workMode, setWorkMode] = useState("");
  const [city, setCity] = useState("");
  const [sortBy, setSortBy] = useState("latest");

  const { data: jobs, isLoading, error } = useQuery({
    queryKey: ["jobs", search, workMode, city, sortBy],
    queryFn: () => getJobs({ q: search, work_mode: workMode, city, sort_by: sortBy }),
  });

  const applyMutation = useMutation({
    mutationFn: applyToJob,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      alert(data.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-white tracking-tight">Discovered Jobs</h1>
            <span className="rounded-full bg-indigo-500/20 border border-indigo-500/30 px-2.5 py-0.5 text-[11px] text-indigo-300 font-medium">
              AI · ML · Python · Data Science Only
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            0-2 years & fresher roles sorted by recency (Bangalore #1 priority). Jobs older than 4 days are automatically pruned.
          </p>
        </div>

        {/* Filter & Sort Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <input
            type="text"
            placeholder="Search role or company..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-lg border border-white/10 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-400 w-44"
          />

          {/* City Filter */}
          <select
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-400"
          >
            <option value="">All Locations</option>
            <option value="bangalore">📍 Bangalore (Priority #1)</option>
            <option value="hyderabad">Hyderabad</option>
            <option value="pune">Pune</option>
            <option value="delhi">Delhi NCR / Gurgaon</option>
            <option value="mumbai">Mumbai</option>
            <option value="remote">🏠 Remote (India)</option>
          </select>

          {/* Work Mode */}
          <select
            value={workMode}
            onChange={(e) => setWorkMode(e.target.value)}
            className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-400"
          >
            <option value="">All Modes</option>
            <option value="office">Work from Office</option>
            <option value="hybrid">Hybrid</option>
            <option value="remote">Remote</option>
          </select>

          {/* Sort By */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="rounded-lg border border-indigo-500/30 bg-slate-900 px-2.5 py-1.5 text-xs text-indigo-300 font-medium focus:outline-none focus:border-indigo-400"
            title="Sort jobs by time recency or Bangalore priority"
          >
            <option value="latest">🕒 Latest First (Recency)</option>
            <option value="bangalore">🏢 Bangalore First</option>
          </select>
        </div>
      </div>

      {isLoading && <div className="text-slate-400 text-sm">Loading latest fresh jobs…</div>}
      {error && <div className="text-red-400 text-sm">Error: {(error as Error).message}</div>}

      {jobs?.length === 0 && !isLoading && (
        <div className="rounded-xl border border-white/10 bg-white/5 p-8 text-center text-sm text-slate-400">
          No jobs found for the selected filters. Click <strong>Hunt Entry Jobs</strong> in the Resumes tab to discover the freshest AI/ML/Python openings!
        </div>
      )}

      {/* Jobs List */}
      <div className="space-y-3">
        {jobs?.map((j) => (
          <div key={j.id} className="rounded-xl border border-white/10 bg-white/5 p-5 hover:border-indigo-500/30 transition flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1.5 max-w-2xl">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-white text-base">{j.title}</span>
                {/* Recency Badge */}
                <span className="rounded bg-sky-500/20 border border-sky-500/30 px-2 py-0.5 text-[11px] text-sky-300 font-medium">
                  🕒 Posted: {j.time_ago || "Recent"}
                </span>
                {/* Fresher Badge */}
                <span className="rounded bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[11px] text-emerald-300 font-medium">
                  0-2 yrs / Fresher
                </span>
                {/* Bangalore Priority Badge */}
                {j.is_bangalore && (
                  <span className="rounded bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 text-[11px] text-amber-300 font-medium">
                    📍 Bangalore
                  </span>
                )}
                {/* Work Mode */}
                <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-[11px] text-indigo-300">
                  {j.work_mode}
                </span>
                {j.application_status === "APPLIED" && (
                  <span className="rounded bg-emerald-500/20 border border-emerald-500/40 px-2 py-0.5 text-[11px] text-emerald-300 font-medium">
                    Applied
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-400">
                <span className="text-slate-200 font-medium">{j.company}</span> · {j.location} · Source: <span className="uppercase text-slate-300 font-semibold">{j.source}</span>
              </div>
              {j.description && (
                <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                  {j.description.replace(/<[^>]*>?/gm, "")}
                </p>
              )}
            </div>

            {/* Actions */}
            <div className="flex flex-wrap items-center gap-2 shrink-0">
              {j.linkedin_recruiter_url && (
                <a
                  href={j.linkedin_recruiter_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg bg-sky-950/40 border border-sky-500/30 px-2.5 py-1.5 text-xs text-sky-300 hover:bg-sky-900/60 transition"
                  title="Search for Bangalore recruiters at this company on LinkedIn"
                >
                  👤 Bangalore Recruiter
                </a>
              )}

              {j.linkedin_referral_url && (
                <a
                  href={j.linkedin_referral_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg bg-amber-950/40 border border-amber-500/30 px-2.5 py-1.5 text-xs text-amber-300 hover:bg-amber-900/60 transition"
                  title="Find software engineers at this company in Bangalore for referral"
                >
                  🤝 Referral / Peer
                </a>
              )}

              {j.application_status !== "APPLIED" && (
                <button
                  onClick={() => applyMutation.mutate(j.id)}
                  className="rounded-lg bg-indigo-600/30 border border-indigo-500/40 px-3 py-1.5 text-xs font-medium text-indigo-300 hover:bg-indigo-600/50 transition cursor-pointer"
                >
                  ✓ Mark Applied
                </button>
              )}

              <a
                href={j.job_url}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg bg-emerald-600/30 border border-emerald-500/40 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-600/50 transition"
              >
                Open Job ↗
              </a>

              <button
                onClick={() => {
                  if (confirm("Remove this job from your feed?")) {
                    deleteMutation.mutate(j.id);
                  }
                }}
                className="text-xs text-slate-500 hover:text-red-400 px-2 py-1 transition"
                title="Remove job"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
