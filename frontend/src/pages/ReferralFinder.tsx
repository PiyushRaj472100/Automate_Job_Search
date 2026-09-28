import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { analyzeReferralJD, getReferralHistory, type ReferralAnalysis } from "../api/client";

const POPULAR_COMPANIES = [
  "Amazon", "Microsoft", "Google", "Flipkart", "Swiggy", "Zomato",
  "Uber", "Infosys", "TCS", "Wipro", "PhonePe", "Razorpay"
];

export function ReferralFinder() {
  const qc = useQueryClient();
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [location, setLocation] = useState("Bengaluru, India");
  const [jd, setJd] = useState("");
  const [currentResult, setCurrentResult] = useState<ReferralAnalysis | null>(null);
  const [copiedTemplate, setCopiedTemplate] = useState(false);

  const historyQuery = useQuery({
    queryKey: ["referralHistory"],
    queryFn: getReferralHistory,
  });

  const analyzeMutation = useMutation({
    mutationFn: analyzeReferralJD,
    onSuccess: (data) => {
      setCurrentResult(data);
      qc.invalidateQueries({ queryKey: ["referralHistory"] });
    },
    onError: (err: any) => {
      alert("Analysis error: " + (err.message || err));
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!company.trim()) {
      alert("Please enter a company name.");
      return;
    }
    analyzeMutation.mutate({
      company: company.trim(),
      role: role.trim() || "Software Engineer",
      location: location.trim() || "Bengaluru, India",
      job_description: jd.trim(),
    });
  };

  const handleCopyTemplate = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedTemplate(true);
    setTimeout(() => setCopiedTemplate(false), 2500);
  };

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
          <span>🤝</span> JD Referral & Recruiter Matcher
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Paste any Job Description, Role, and Company to discover verified LinkedIn recruiters, hiring managers, peer referral avenues, and corporate email patterns.
        </p>
      </div>

      {/* Input Form */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Company */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Company Name <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Amazon, Swiggy, TCS"
                required
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-400"
              />
            </div>

            {/* Role */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Job Title / Role
              </label>
              <input
                type="text"
                placeholder="e.g. Python Backend Developer / SDE 1"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-400"
              />
            </div>

            {/* Location */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Location
              </label>
              <input
                type="text"
                placeholder="e.g. Bengaluru, India"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-400"
              />
            </div>
          </div>

          {/* Quick Company Tags */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] text-slate-400">Quick fill:</span>
            {POPULAR_COMPANIES.map((c) => (
              <button
                type="button"
                key={c}
                onClick={() => setCompany(c)}
                className="rounded-md bg-white/5 border border-white/10 px-2 py-0.5 text-[11px] text-slate-300 hover:border-indigo-400 hover:text-white transition cursor-pointer"
              >
                {c}
              </button>
            ))}
          </div>

          {/* Job Description Textarea */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              Paste Full Job Description (JD)
            </label>
            <textarea
              rows={5}
              placeholder="Paste the full job posting text here. The system will parse key skills, tech stack, and customize your cold outreach..."
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-slate-900 p-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-400 font-mono leading-relaxed"
            />
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={analyzeMutation.isPending}
            className="w-full rounded-lg bg-indigo-600 border border-indigo-500/50 py-2.5 text-xs font-semibold text-white hover:bg-indigo-500 transition cursor-pointer disabled:opacity-50 flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20"
          >
            {analyzeMutation.isPending ? (
              <span>Analyzing JD & Searching Hiring Contacts...</span>
            ) : (
              <span>🔍 Find Referral & Recruiter Contacts</span>
            )}
          </button>
        </form>
      </div>

      {/* Analysis Result */}
      {currentResult && (
        <div className="rounded-xl border border-indigo-500/30 bg-gradient-to-b from-indigo-950/30 to-slate-900/60 p-6 space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-white/10 pb-4">
            <div>
              <div className="text-lg font-bold text-white">
                {currentResult.role} @ <span className="text-indigo-300">{currentResult.company}</span>
              </div>
              <div className="text-xs text-slate-400 mt-0.5">
                Location: <span className="text-slate-200">{currentResult.location}</span>
              </div>
            </div>

            {/* Extracted Skills */}
            {currentResult.detected_skills.length > 0 && (
              <div className="flex flex-wrap gap-1.5 items-center">
                <span className="text-[11px] text-slate-400">Skills Detected:</span>
                {currentResult.detected_skills.map((s) => (
                  <span key={s} className="rounded bg-indigo-500/20 border border-indigo-500/30 px-2 py-0.5 text-[11px] font-medium text-indigo-300">
                    {s}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Section 1: Verified LinkedIn Searches */}
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <span>🎯</span> Verified LinkedIn People Searches (1-Click)
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {currentResult.search_links.map((link, idx) => (
                <a
                  key={idx}
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-white/10 bg-slate-900/80 p-3.5 hover:border-indigo-400 hover:bg-slate-900 transition flex flex-col justify-between group"
                >
                  <div className="space-y-1">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-indigo-400">
                      {link.category}
                    </div>
                    <div className="text-xs font-medium text-white group-hover:text-indigo-200 transition">
                      {link.title}
                    </div>
                    <p className="text-[11px] text-slate-400 leading-snug">
                      {link.purpose}
                    </p>
                  </div>
                  <div className="pt-2 text-right">
                    <span className="text-xs font-semibold text-indigo-400 group-hover:text-indigo-300">Open on LinkedIn ↗</span>
                  </div>
                </a>
              ))}
            </div>
          </div>

          {/* Section 2: Corporate Email Patterns */}
          <div className="space-y-3 pt-2">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <span>✉️</span> Corporate Email Syntax & Inboxes
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5">
              {currentResult.email_formats.map((ef, idx) => (
                <div key={idx} className="rounded-lg border border-white/5 bg-slate-900/60 p-3 space-y-1">
                  <div className="font-mono text-xs text-emerald-400 font-semibold">{ef.pattern}</div>
                  <div className="text-[11px] text-slate-400">Ex: <code className="text-slate-300">{ef.example}</code></div>
                  <div className="text-[10px] text-slate-500 leading-tight">{ef.usage}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Section 3: Tailored Cold Referral Message */}
          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <span>💬</span> Tailored Referral Outreach Message
              </h2>
              <button
                type="button"
                onClick={() => handleCopyTemplate(currentResult.outreach_template)}
                className="rounded-lg bg-indigo-600/30 border border-indigo-500/40 px-3 py-1.5 text-xs text-indigo-200 hover:bg-indigo-600/50 transition cursor-pointer flex items-center gap-1.5"
              >
                <span>{copiedTemplate ? "✓ Copied!" : "📋 Copy Message"}</span>
              </button>
            </div>
            <pre className="rounded-lg border border-white/10 bg-slate-950 p-4 text-xs text-slate-300 font-sans whitespace-pre-wrap leading-relaxed select-all">
              {currentResult.outreach_template}
            </pre>
          </div>
        </div>
      )}

      {/* History */}
      {historyQuery.data && historyQuery.data.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/5 p-5 space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Recent JD Lookups ({historyQuery.data.length})
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
            {historyQuery.data.map((h) => (
              <div
                key={h.id}
                onClick={() => setCurrentResult(h)}
                className="rounded-lg border border-white/5 bg-slate-900/60 p-3 hover:border-indigo-400/40 hover:bg-slate-900 transition cursor-pointer space-y-1"
              >
                <div className="text-xs font-semibold text-white truncate">{h.role}</div>
                <div className="text-[11px] text-indigo-300 truncate">@{h.company} · {h.location}</div>
                <div className="text-[10px] text-slate-500">
                  {new Date(h.created_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
