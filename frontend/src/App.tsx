import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { Resumes } from "./pages/Resumes";
import { Discovery } from "./pages/Discovery";
import { Jobs } from "./pages/Jobs";
import { Recruiters } from "./pages/Recruiters";
import { Applications } from "./pages/Applications";
import { System } from "./pages/System";
import { Settings } from "./pages/Settings";
import { ReferralFinder } from "./pages/ReferralFinder";

const nav = [
  { path: "dashboard", label: "Dashboard", icon: "📊" },
  { path: "resumes", label: "Resumes", icon: "📄" },
  { path: "referrals", label: "Referral Finder", icon: "🤝" },
  { path: "jobs", label: "Jobs", icon: "💼" },
  { path: "recruiters", label: "Recruiters", icon: "👥" },
  { path: "applications", label: "Applications", icon: "📝" },
  { path: "discovery", label: "Discovery", icon: "🔍" },
  { path: "system", label: "System", icon: "⚙️" },
  { path: "settings", label: "Settings", icon: "🔧" },
];

export default function App() {
  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <aside className="w-56 shrink-0 border-r border-white/10 bg-slate-900/60 p-4 space-y-1">
        <div className="mb-6 px-3 text-base font-bold tracking-wide text-indigo-400 flex items-center gap-2">
          <span>🚀</span> Job Intelligence
        </div>
        {nav.map((n) => (
          <NavLink
            key={n.path}
            to={`/${n.path}`}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                isActive ? "bg-indigo-600/30 text-indigo-200 border border-indigo-500/30" : "text-slate-400 hover:text-white hover:bg-white/5"
              }`
            }
          >
            <span>{n.icon}</span>
            <span>{n.label}</span>
          </NavLink>
        ))}
      </aside>
      <main className="flex-1 p-8 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/resumes" element={<Resumes />} />
          <Route path="/referrals" element={<ReferralFinder />} />
          <Route path="/discovery" element={<Discovery />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/recruiters" element={<Recruiters />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/system" element={<System />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
