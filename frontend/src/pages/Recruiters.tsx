import { useQuery } from "@tanstack/react-query";
import { getRecruiters } from "../api/client";

export function Recruiters() {
  const { data: recruiters, isLoading, error } = useQuery({
    queryKey: ["recruiters"],
    queryFn: getRecruiters,
  });

  const copyTemplate = (text: string) => {
    navigator.clipboard.writeText(text);
    alert("Outreach message copied to clipboard! You can paste it into LinkedIn messages or InMail.");
  };

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Recruiter & Referral Intelligence</h1>
        <p className="text-xs text-slate-400 mt-1">
          Targeted LinkedIn search avenues for hiring managers, recruiters, and alumni at companies with active job openings.
        </p>
      </div>

      {isLoading && <div className="text-slate-400 text-sm">Finding recruiters and hiring contacts…</div>}
      {error && <div className="text-red-400 text-sm">Error: {(error as Error).message}</div>}

      {recruiters?.length === 0 && !isLoading && (
        <div className="rounded-xl border border-white/10 bg-white/5 p-8 text-center text-sm text-slate-400">
          No recruiters found yet. Discovered companies will appear here once jobs are loaded!
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {recruiters?.map((r, i) => (
          <div key={i} className="rounded-xl border border-white/10 bg-white/5 p-5 space-y-4 flex flex-col justify-between">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-white text-base">{r.company}</span>
                <span className="text-xs text-slate-500">{r.location}</span>
              </div>
              <div className="text-xs text-indigo-300">
                Opening: <a href={r.job_url} target="_blank" rel="noreferrer" className="underline hover:text-indigo-200">{r.job_title}</a>
              </div>

              {/* LinkedIn Search Links */}
              <div className="pt-2 space-y-1.5">
                <div className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Targeted LinkedIn Searches:</div>
                {r.search_links.map((link, idx) => (
                  <a
                    key={idx}
                    href={link.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between rounded-lg border border-white/5 bg-slate-900/60 p-2 text-xs text-slate-300 hover:border-indigo-500/30 hover:text-white transition"
                  >
                    <span>{link.title}</span>
                    <span className="text-indigo-400 text-xs">Search ↗</span>
                  </a>
                ))}
              </div>
            </div>

            {/* Template Copy Button */}
            <div className="pt-2 border-t border-white/5">
              <button
                onClick={() => copyTemplate(r.outreach_template)}
                className="w-full rounded-lg bg-indigo-600/20 border border-indigo-500/30 px-3 py-1.5 text-xs text-indigo-300 hover:bg-indigo-600/40 transition cursor-pointer flex items-center justify-center gap-1.5"
              >
                <span>📋</span> Copy Referral Outreach Template
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
