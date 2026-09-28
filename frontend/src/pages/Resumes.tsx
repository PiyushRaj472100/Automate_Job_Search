import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { connectResumeSheet, createResumeSheet, getSettings, huntResumeJobs, listResumes, uploadResume } from "../api/client";

export function Resumes() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["resumes"], queryFn: listResumes });
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const up = useMutation({
    mutationFn: uploadResume,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resumes"] });
      alert("Resume uploaded! Autonomous job hunter has started finding entry-level Bangalore & Indian tech jobs for your skills.");
    }
  });

  const [sheetUrl, setSheetUrl] = useState("");
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [huntStatus, setHuntStatus] = useState<{ [id: string]: string }>({});
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
    setHuntStatus((prev) => ({ ...prev, [resumeId]: "Hunting entry-level Bangalore & Indian tech jobs..." }));
    try {
      const res = await huntResumeJobs(resumeId);
      setHuntStatus((prev) => ({
        ...prev,
        [resumeId]: `Found ${res.suitable_entry_level || res.discovered || 0} tech jobs (${res.new_persisted || 0} newly saved, ${res.synced_to_sheet || 0} synced to Sheet)!`
      }));
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["recruiters"] });
    } catch (err: any) {
      setHuntStatus((prev) => ({ ...prev, [resumeId]: "Hunt error: " + (err.message || err) }));
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Resumes & Autonomous Job Hunter</h1>
          <p className="text-xs text-slate-400 mt-1">
            Focus: Software / AI / Python Engineering in Bangalore & India. Verified LinkedIn recruiter & referral avenues included.
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
        <span className="block text-xs text-slate-500 mt-1">Extracts skills, triggers entry-level job hunting, and syncs every few hours.</span>
        <input type="file" accept=".pdf,.docx" className="hidden" onChange={(e) => e.target.files?.[0] && up.mutate(e.target.files[0])} />
      </label>

      {up.isPending && <p className="text-sm text-indigo-400 animate-pulse">Uploading and parsing profile…</p>}
      {up.isError && <p className="text-sm text-red-400">Upload error: {(up.error as Error).message}</p>}

      {/* Resumes List */}
      <div className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">Your Profiles</h2>
        {q.isLoading && <p className="text-slate-400 text-sm">Loading…</p>}
        {q.isError && <p className="text-red-400 text-sm">Error: {(q.error as Error).message}</p>}
        {q.data?.length === 0 && <p className="text-slate-500 text-sm italic">No resume uploaded yet.</p>}

        {q.data?.map((r) => (
          <div key={r.id} className="rounded-xl border border-white/10 bg-white/5 p-5 space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="font-semibold text-base text-white">{r.filename}</div>
                <div className="mt-1 text-xs text-slate-400">
                  Target Roles: <span className="text-slate-200">{r.target_roles.join(", ") || "General Developer"}</span> · Uploaded: {new Date(r.created_at).toLocaleDateString()}
                </div>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {r.skills.map((s) => (
                    <span key={s} className="rounded-md bg-indigo-500/15 border border-indigo-500/30 px-2 py-0.5 text-xs text-indigo-300">
                      {s}
                    </span>
                  ))}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => handleManualHunt(r.id)}
                  className="rounded-lg bg-indigo-600/30 border border-indigo-500/40 px-3 py-1.5 text-xs font-medium text-indigo-200 hover:bg-indigo-600/50 transition cursor-pointer flex items-center gap-1.5"
                >
                  <span>⚡</span> Hunt Entry-Level Jobs
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
                <span className="text-[10px] text-slate-500 uppercase tracking-wide">Autonomous Hunter</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
