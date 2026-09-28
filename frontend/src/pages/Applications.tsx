import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteApplication, getApplications, updateApplication } from "../api/client";

const STAGES = [
  { key: "SAVED", label: "Saved / Ready", color: "border-slate-500/40 text-slate-300" },
  { key: "APPLIED", label: "Applied", color: "border-indigo-500/40 text-indigo-300" },
  { key: "INTERVIEWING", label: "Interviewing", color: "border-amber-500/40 text-amber-300" },
  { key: "OFFER", label: "Offer Received", color: "border-emerald-500/40 text-emerald-300" },
  { key: "REJECTED", label: "Archived / Rejected", color: "border-rose-500/40 text-rose-300" },
];

export function Applications() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<string>("ALL");

  const { data: apps, isLoading, error } = useQuery({
    queryKey: ["applications", activeTab],
    queryFn: () => getApplications(activeTab === "ALL" ? undefined : activeTab),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status, notes }: { id: string; status?: string; notes?: string }) =>
      updateApplication(id, { status, notes }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteApplication,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Applications Tracker</h1>
          <p className="text-xs text-slate-400 mt-1">
            Track interview stages, application dates, and notes for all your active job candidacies.
          </p>
        </div>

        {/* Stage Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5 bg-slate-900/60 p-1 rounded-xl border border-white/10">
          <button
            onClick={() => setActiveTab("ALL")}
            className={`rounded-lg px-3 py-1 text-xs font-medium transition ${activeTab === "ALL" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"}`}
          >
            All ({apps?.length ?? 0})
          </button>
          {STAGES.map((s) => (
            <button
              key={s.key}
              onClick={() => setActiveTab(s.key)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${activeTab === s.key ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"}`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <div className="text-slate-400 text-sm">Loading applications…</div>}
      {error && <div className="text-red-400 text-sm">Error: {(error as Error).message}</div>}

      {apps?.length === 0 && !isLoading && (
        <div className="rounded-xl border border-white/10 bg-white/5 p-8 text-center text-sm text-slate-400">
          No applications tracked in this stage. When you find a role on the <span className="text-indigo-400 font-medium">Jobs</span> page, click &quot;Mark Applied&quot;!
        </div>
      )}

      {/* Applications Cards */}
      <div className="space-y-3">
        {apps?.map((a) => (
          <div key={a.id} className="rounded-xl border border-white/10 bg-white/5 p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1.5 max-w-xl">
              <div className="flex items-center gap-2.5">
                <span className="font-semibold text-white text-base">{a.job?.title || "Target Role"}</span>
                <span className="text-xs text-slate-400">at <strong className="text-slate-200">{a.job?.company}</strong></span>
              </div>

              <div className="text-xs text-slate-400">
                Applied on: {a.applied_at ? new Date(a.applied_at).toLocaleDateString() : "Recently"} · Mode: {a.job?.work_mode || "Remote"}
              </div>

              {a.notes && (
                <div className="text-xs text-slate-400 bg-slate-900/60 p-2 rounded-lg border border-white/5">
                  <span className="text-slate-500 font-medium">Note:</span> {a.notes}
                </div>
              )}
            </div>

            {/* Stage Selector & Actions */}
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-1.5">
                <label className="text-xs text-slate-500">Stage:</label>
                <select
                  value={a.status}
                  onChange={(e) => updateMutation.mutate({ id: a.id, status: e.target.value })}
                  className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-400"
                >
                  {STAGES.map((s) => (
                    <option key={s.key} value={s.key}>{s.label}</option>
                  ))}
                </select>
              </div>

              {a.job?.job_url && (
                <a
                  href={a.job.job_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg bg-indigo-600/30 border border-indigo-500/40 px-3 py-1 text-xs font-medium text-indigo-300 hover:bg-indigo-600/50 transition"
                >
                  View Job ↗
                </a>
              )}

              <button
                onClick={() => {
                  const note = prompt("Enter a note or interview detail:", a.notes || "");
                  if (note !== null) {
                    updateMutation.mutate({ id: a.id, notes: note });
                  }
                }}
                className="text-xs text-slate-400 hover:text-white px-2 py-1 transition"
                title="Edit notes"
              >
                ✏️ Notes
              </button>

              <button
                onClick={() => {
                  if (confirm("Delete this application tracking record?")) {
                    deleteMutation.mutate(a.id);
                  }
                }}
                className="text-xs text-slate-500 hover:text-red-400 px-2 py-1 transition"
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
