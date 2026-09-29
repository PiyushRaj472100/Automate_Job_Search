import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  connectResumeSheet,
  createResumeSheet,
  getSettings,
  huntResumeJobs,
  listResumes,
  toggleResumeActive,
  uploadResume,
} from "../api/client";

export function Resumes() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["resumes"], queryFn: listResumes });
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const up = useMutation({
    mutationFn: uploadResume,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resumes"] });
      alert("Resume uploaded! Live Resume Job Hunter is now active and continuously discovering relevant opportunities 5–8 times per day.");
    }
  });

  const [sheetUrl, setSheetUrl] = useState("");
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [huntStatus, setHuntStatus] = useState<{ [id: string]: string }>({});
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [copiedEmail, setCopiedEmail] = useState(false);

  useEffect(() => {
    if (settingsQuery.data?.google_sheet_url && !sheetUrl) {
      setSheetUrl(settingsQuery.data.google_sheet_url);
    }
  }, [settingsQuery.data?.google_sheet_url]);

  const saEmail = settingsQuery.data?.service_account_email || "job-intelligence-sheets@automate-job-search-510002.iam.gserviceaccount.com";

  const handleCopyEmail = () => {
    navigator.clipboard.writeText(saEmail);
    setCopiedEmail(true);
    setTimeout(() => setCopiedEmail(false), 2500);
  };

  const handleToggleActive = async (resumeId: string, newState: boolean) => {
    setTogglingId(resumeId);
    try {
      const res = await toggleResumeActive(resumeId, newState);
      await qc.invalidateQueries({ queryKey: ["resumes"] });
      setHuntStatus((prev) => ({
        ...prev,
        [resumeId]: res.message,
      }));
    } catch (err: any) {
      alert("Could not change resume active status: " + (err.message || err));
    } finally {
      setTogglingId(null);
    }
  };

  const handleConnectSheet = async (resumeId: string) => {
    if (!sheetUrl.trim()) {
      alert("Please paste your Google Sheet link first!");
      return;
    }
    setConnectingId(resumeId);
    try {
      const res = await connectResumeSheet(resumeId, sheetUrl.trim());
      alert(res.message || "Google Sheet connected!");
      if (res.spreadsheet_url) {
        window.open(res.spreadsheet_url, "_blank");
      }
    } catch (err: any) {
      alert(
        "Google Sheets Connection Notice:\n\n" +
        (err.message || err) +
        "\n\nSteps to fix:\n" +
        "1. Open your sheet in your browser\n" +
        "2. Click the 'Share' button in Google Sheets (top right)\n" +
        "3. In 'Add people and groups', paste:\n   " + saEmail + "\n" +
        "4. Set permission to 'Editor'\n" +
        "5. Click 'Share' / 'Send'\n" +
        "6. Click 'Link & Open Sheet' again!"
      );
    } finally {
      setConnectingId(null);
    }
  };

  const handleManualHunt = async (resumeId: string) => {
    setHuntStatus((prev) => ({ ...prev, [resumeId]: "Live Agent hunting across official portals, LinkedIn & Indian startups..." }));
    try {
      const res = await huntResumeJobs(resumeId);
      setHuntStatus((prev) => ({
        ...prev,
        [resumeId]: `Found ${res.suitable_tech_india || res.suitable_entry_level || res.discovered || 0} matching tech jobs (${res.new_persisted || 0} new, ${res.synced_to_sheet || 0} synced to Sheet)!`
      }));
      qc.invalidateQueries({ queryKey: ["resumes"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["recruiters"] });
    } catch (err: any) {
      setHuntStatus((prev) => ({ ...prev, [resumeId]: "Hunt error: " + (err.message || err) }));
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-white">Live Resume Job Hunter</h1>
            <span className="rounded-full bg-emerald-500/20 border border-emerald-500/40 px-2 py-0.5 text-[11px] font-semibold text-emerald-300">
              Continuous 5–8x / Day
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Uploaded resumes act as active job-hunting agents. Prioritizes fresh jobs (&lt;24h, 1–7d), official company portals, LinkedIn, and Indian startups.
          </p>
        </div>
      </div>

      {/* Google Sheet Setup Card */}
      <div className="rounded-xl border border-indigo-500/20 bg-gradient-to-r from-indigo-950/40 to-slate-900/40 p-5 space-y-3">
        <h2 className="text-sm font-semibold text-indigo-300 flex items-center gap-2">
          <span>📊</span> Connect Your Google Sheet
        </h2>
        <p className="text-xs text-slate-300 leading-relaxed">
          Google Service Accounts require edit access to write your jobs. Share your sheet with:
        </p>

        <div className="flex flex-wrap items-center gap-2 bg-slate-900/90 border border-slate-700/60 rounded-lg p-2.5">
          <code className="text-xs text-indigo-300 font-mono select-all flex-1 break-all">
            {saEmail}
          </code>
          <button
            onClick={handleCopyEmail}
            className="rounded bg-indigo-600/30 border border-indigo-500/40 px-2.5 py-1 text-xs text-indigo-200 hover:bg-indigo-600/50 transition cursor-pointer shrink-0"
          >
            {copiedEmail ? "✓ Copied!" : "📋 Copy Email"}
          </button>
        </div>

        <div className="text-[11px] text-slate-400 space-y-1 bg-black/20 p-2.5 rounded-lg border border-white/5">
          <div>1. Open your Google Sheet (e.g. <a href="https://sheets.new" target="_blank" rel="noreferrer" className="text-indigo-400 underline font-medium">sheets.new</a>)</div>
          <div>2. Click <strong>Share</strong> (top right) ➔ Paste the copied email in <em>"Add people and groups"</em></div>
          <div>3. Choose <strong>Editor</strong> permission and click <strong>Share</strong> / <strong>Send</strong></div>
          <div>4. Paste your sheet URL below and click <strong>Link & Open Sheet</strong>:</div>
        </div>

        <div className="flex gap-2 pt-1">
          <input
            type="url"
            placeholder="https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
            className="flex-1 rounded-md border border-white/10 bg-slate-900/80 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-400"
            value={sheetUrl}
            onChange={(e) => setSheetUrl(e.target.value)}
          />
        </div>
      </div>

      {/* Upload Box */}
      <label className="block cursor-pointer rounded-xl border border-dashed border-white/20 bg-white/[0.02] p-6 text-center text-sm text-slate-400 hover:border-indigo-400 hover:bg-white/[0.04] transition">
        <span className="font-medium text-slate-300">Click to upload your Resume (PDF or DOCX)</span>
        <span className="block text-xs text-slate-500 mt-1">
          Instantly activates a persistent Live Resume profile that hunts 5–8 times a day and adds fresh jobs to your Sheet.
        </span>
        <input type="file" accept=".pdf,.docx" className="hidden" onChange={(e) => e.target.files?.[0] && up.mutate(e.target.files[0])} />
      </label>

      {up.isPending && <p className="text-sm text-indigo-400 animate-pulse">Uploading and parsing profile…</p>}
      {up.isError && <p className="text-sm text-red-400">Upload error: {(up.error as Error).message}</p>}

      {/* Resumes List */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">Active Job Search Profiles</h2>
          <span className="text-xs text-slate-500">Each resume hunts independently</span>
        </div>
        {q.isLoading && <p className="text-slate-400 text-sm">Loading…</p>}
        {q.isError && <p className="text-red-400 text-sm">Error: {(q.error as Error).message}</p>}
        {q.data?.length === 0 && <p className="text-slate-500 text-sm italic">No resume uploaded yet.</p>}

        {q.data?.map((r, index) => {
          const isActive = r.is_active !== false;
          return (
            <div
              key={r.id}
              className={`rounded-xl border p-5 space-y-4 transition ${
                isActive
                  ? "border-emerald-500/25 bg-gradient-to-b from-emerald-950/10 via-slate-900/60 to-slate-900/40"
                  : "border-slate-800 bg-slate-950/40 opacity-80"
              }`}
            >
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                <div className="space-y-2 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-base text-white">{r.filename}</span>
                    <span className="text-xs text-slate-400 font-mono">Tab: Resume {index + 1}</span>

                    {/* Live Agent Status Badge */}
                    {isActive ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 border border-emerald-500/40 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300">
                        <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                        LIVE AGENT ACTIVE (5–8x / Day)
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 border border-amber-500/40 px-2.5 py-0.5 text-[11px] font-semibold text-amber-300">
                        <span className="h-2 w-2 rounded-full bg-amber-400" />
                        PAUSED / DEACTIVATED
                      </span>
                    )}
                  </div>

                  <div className="text-xs text-slate-400">
                    Target Roles: <span className="text-slate-200">{r.target_roles.join(", ") || "Software / AI Engineer"}</span> · Uploaded: {new Date(r.created_at).toLocaleDateString()}
                  </div>

                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                    {r.skills.map((s) => (
                      <span key={s} className="rounded-md bg-indigo-500/15 border border-indigo-500/30 px-2 py-0.5 text-xs text-indigo-300">
                        {s}
                      </span>
                    ))}
                  </div>

                  {/* Hunting Stats */}
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-400 pt-1">
                    <span>
                      Last Hunt:{" "}
                      <strong className="text-slate-200">
                        {r.last_hunted_at ? new Date(r.last_hunted_at).toLocaleTimeString() : "Pending first sweep"}
                      </strong>
                    </span>
                    <span>·</span>
                    <span>
                      Hunt Cycles: <strong className="text-slate-200">{r.hunt_count || 0}</strong>
                    </span>
                    <span>·</span>
                    <span className="text-emerald-400/90">
                      {isActive ? "Continuous search enabled" : "Paused by user"}
                    </span>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  {/* User Active/Pause Toggle Control */}
                  {isActive ? (
                    <button
                      onClick={() => handleToggleActive(r.id, false)}
                      disabled={togglingId === r.id}
                      className="rounded-lg bg-amber-600/20 border border-amber-500/40 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-600/30 transition cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
                      title="Pause continuous 5-8x daily searches for this resume"
                    >
                      <span>⏸</span> Stop Job Search
                    </button>
                  ) : (
                    <button
                      onClick={() => handleToggleActive(r.id, true)}
                      disabled={togglingId === r.id}
                      className="rounded-lg bg-emerald-600/30 border border-emerald-500/50 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-600/50 transition cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
                      title="Resume continuous 5-8x daily searches for this resume"
                    >
                      <span>▶</span> Activate Job Search
                    </button>
                  )}

                  <button
                    onClick={() => handleManualHunt(r.id)}
                    className="rounded-lg bg-indigo-600/30 border border-indigo-500/40 px-3 py-1.5 text-xs font-medium text-indigo-200 hover:bg-indigo-600/50 transition cursor-pointer flex items-center gap-1.5"
                  >
                    <span>⚡</span> Run Immediate Hunt
                  </button>

                  <button
                    onClick={async () => {
                      if (sheetUrl.trim()) {
                        await handleConnectSheet(r.id);
                      } else {
                        try {
                          const res = await createResumeSheet(r.id);
                          if (res?.spreadsheet_url) {
                            window.open(res.spreadsheet_url, "_blank");
                          }
                        } catch (err: any) {
                          alert("Google Sheets: " + (err.message || err));
                        }
                      }
                    }}
                    disabled={connectingId === r.id}
                    className="rounded-lg bg-emerald-600/30 border border-emerald-500/40 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-600/50 transition cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <span>📊</span> {sheetUrl.trim() ? "Link & Open Sheet" : "Open Google Sheet"}
                  </button>
                </div>
              </div>

              {/* Hunt status / feedback */}
              {huntStatus[r.id] && (
                <div className="rounded-lg bg-slate-900/90 border border-slate-700/60 p-2.5 text-xs text-indigo-300 flex items-center justify-between">
                  <span>{huntStatus[r.id]}</span>
                  <span className="text-[10px] text-slate-500 uppercase tracking-wide">Live Agent</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
