import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { applyToJob, deleteJob, getJobs } from "../api/client";

// Platform metadata: source key -> display label + icon
const PLATFORMS = [
  { key: "", label: "All Platforms", icon: "🌐" },
  { key: "company_portals", label: "Career Pages (Greenhouse/Lever)", icon: "🏢" },
  { key: "linkedin_india", label: "LinkedIn India", icon: "🔗" },
  { key: "instahyre", label: "Instahyre", icon: "🔍" },
  { key: "internshala", label: "Internshala", icon: "🎓" },
  { key: "naukri", label: "Naukri.com", icon: "🇮🇳" },
  { key: "foundit", label: "Foundit (Monster India)", icon: "🎯" },
  { key: "cutshort", label: "Cutshort.io", icon: "✂️" },
  { key: "wellfound", label: "Wellfound (AngelList)", icon: "🚀" },
  { key: "hasjob_india", label: "Hasjob India", icon: "📋" },
  { key: "web_fresher", label: "WebFresher", icon: "🆕" },
  { key: "remoteok", label: "RemoteOK", icon: "🏠" },
  { key: "working_nomads", label: "Working Nomads", icon: "🌍" },
  { key: "remotive", label: "Remotive", icon: "💻" },
  { key: "jobicy", label: "Jobicy", icon: "💼" },
  { key: "arbeitnow", label: "Arbeitnow", icon: "🤝" },
  { key: "ai_jobs", label: "AI-Jobs (HN/Remotive)", icon: "🤖" },
  { key: "yc_jobs", label: "YC Jobs", icon: "🔶" },
  { key: "startup_jobs", label: "Startup.jobs", icon: "⚡" },
];

export function Jobs() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [workMode, setWorkMode] = useState("");
  const [city, setCity] = useState("");
  const [source, setSource] = useState("");
  const [sortBy, setSortBy] = useState("latest");

  const { data: jobs, isLoading, error } = useQuery({
    queryKey: ["jobs", search, workMode, city, source, sortBy],
    queryFn: () => getJobs({ q: search, work_mode: workMode, city, source: source || undefined, sort_by: sortBy }),
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

  // Group jobs by platform for stats display
  const platformCounts: Record<string, number> = {};
  jobs?.forEach(j => {
    platformCounts[j.source] = (platformCounts[j.source] || 0) + 1;
  });

  const activePlatforms = Object.entries(platformCounts).sort((a, b) => b[1] - a[1]);

  const currentPlatform = PLATFORMS.find(p => p.key === source);

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-white tracking-tight">Discovered Jobs</h1>
              <span className="rounded-full bg-indigo-500/20 border border-indigo-500/30 px-2.5 py-0.5 text-[11px] text-indigo-300 font-medium">
                AI · ML · Python · Backend
              </span>
              {jobs && (
                <span className="rounded-full bg-emerald-500/20 border border-emerald-500/30 px-2.5 py-0.5 text-[11px] text-emerald-300 font-medium">
                  {jobs.length} jobs
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Sorted by recency · Bangalore & Remote priority · Auto-pruned every 4 days
            </p>
          </div>

          {/* Platform Stats Pills */}
          {activePlatforms.length > 0 && (
            <div className="flex flex-wrap gap-1.5 max-w-md">
              {activePlatforms.slice(0, 6).map(([src, count]) => {
                const meta = PLATFORMS.find(p => p.key === src);
                return (
                  <button
                    key={src}
                    onClick={() => setSource(source === src ? "" : src)}
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition cursor-pointer ${
                      source === src
                        ? "bg-indigo-500/40 border border-indigo-400/60 text-indigo-200"
                        : "bg-white/5 border border-white/10 text-slate-400 hover:text-slate-200 hover:bg-white/10"
                    }`}
                  >
                    {meta?.icon || "🌐"} {meta?.label.split(" (")[0].split("/")[0] || src} ({count})
                  </button>
                );
              })}
            </div>
          )}
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

          {/* Platform Source Filter */}
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="rounded-lg border border-indigo-500/30 bg-slate-900 px-2.5 py-1.5 text-xs text-indigo-200 focus:outline-none focus:border-indigo-400"
            title="Filter by job platform source"
          >
            {PLATFORMS.map(p => (
              <option key={p.key} value={p.key}>
                {p.icon} {p.label}
              </option>
            ))}
          </select>

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
          >
            <option value="latest">🕒 Latest First</option>
            <option value="bangalore">📍 Bangalore First</option>
            <option value="source">📁 Group by Platform</option>
            <option value="company">🏢 Group by Company</option>
          </select>

          {/* Clear Filters */}
          {(search || source || city || workMode || sortBy !== "latest") && (
            <button
              onClick={() => { setSearch(""); setSource(""); setCity(""); setWorkMode(""); setSortBy("latest"); }}
              className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition cursor-pointer"
            >
              ✕ Clear
            </button>
          )}
        </div>

        {/* Active filter badge */}
        {source && currentPlatform && (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="rounded bg-indigo-500/20 border border-indigo-500/30 px-2 py-0.5 text-indigo-300">
              {currentPlatform.icon} Filtering by: {currentPlatform.label}
            </span>
            <button onClick={() => setSource("")} className="text-slate-500 hover:text-slate-300 transition">
              × clear filter
            </button>
          </div>
        )}
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
                  🕒 {j.time_ago || "Recent"}
                </span>
                {/* Source/Platform Badge */}
                <span
                  className="rounded bg-purple-500/20 border border-purple-500/30 px-2 py-0.5 text-[11px] text-purple-300 font-medium cursor-pointer hover:bg-purple-500/30 transition"
                  onClick={() => setSource(j.source)}
                  title={`Filter by ${j.source}`}
                >
                  {PLATFORMS.find(p => p.key === j.source)?.icon || "🌐"} {j.source.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
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
                    ✓ Applied
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-400">
                <span className="text-slate-200 font-medium">{j.company}</span> · {j.location}
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
                  👤 Recruiter
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
                  🤝 Referral
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