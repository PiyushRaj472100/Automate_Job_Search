import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getSettings, updateSettings } from "../api/client";

export function Settings() {
  const qc = useQueryClient();
  const { data: settings, isLoading } = useQuery({ queryKey: ["settings"], queryFn: getSettings });

  const [sheetUrl, setSheetUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [shareEmail, setShareEmail] = useState("");

  useEffect(() => {
    if (settings) {
      setSheetUrl(settings.google_sheet_url || "");
      setShareEmail(settings.share_email || "");
    }
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: () => updateSettings({
      google_sheet_url: sheetUrl,
      gemini_api_key: apiKey ? apiKey : undefined,
      share_email: shareEmail,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      alert("Settings saved successfully!");
    },
  });

  if (isLoading) return <div className="text-slate-400 text-sm">Loading settings…</div>;

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Platform Settings</h1>
        <p className="text-xs text-slate-400 mt-1">
          Configure external credentials, storage, and automated synchronization.
        </p>
      </div>

      <div className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-6">
        <div>
          <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider">
            Google Sheet Tracker URL
          </label>
          <p className="mt-0.5 text-xs text-slate-400">
            Link to your Google Sheet where new jobs, companies, and referral links are synced automatically.
          </p>
          <input
            type="url"
            value={sheetUrl}
            onChange={(e) => setSheetUrl(e.target.value)}
            placeholder="https://docs.google.com/spreadsheets/d/..."
            className="mt-2 w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-400"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider">
            Google Sheets Share Email
          </label>
          <p className="mt-0.5 text-xs text-slate-400">
            Your personal Gmail to share sheets with.
          </p>
          <input
            type="email"
            value={shareEmail}
            onChange={(e) => setShareEmail(e.target.value)}
            placeholder="your_email@gmail.com"
            className="mt-2 w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-400"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider">
            Gemini API Key
          </label>
          <p className="mt-0.5 text-xs text-slate-400">
            {settings?.gemini_api_key_configured ? "✓ Configured in .env" : "Not configured (optional for advanced AI reasoning)"}
          </p>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="AIzaSy... (leave blank to keep current)"
            className="mt-2 w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-400"
          />
        </div>

        <div className="pt-2">
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition cursor-pointer disabled:opacity-50"
          >
            {saveMutation.isPending ? "Saving…" : "Save Configuration"}
          </button>
        </div>
      </div>

      {/* System Info */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-2 text-xs text-slate-400">
        <div className="font-semibold text-slate-300">System Environment</div>
        <div>Project: <strong className="text-slate-200">{settings?.project_name}</strong> (v{settings?.version})</div>
        <div>Mode: <strong className="text-slate-200 capitalize">{settings?.environment}</strong></div>
        <div>Database: <span className="text-emerald-400">Connected (PostgreSQL)</span></div>
      </div>
    </div>
  );
}
