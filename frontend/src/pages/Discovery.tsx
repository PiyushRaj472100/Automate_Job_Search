import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { generateQueries, runDiscovery } from "../api/client";

export function Discovery() {
  const [roles, setRoles] = useState("AI Engineer, Python Developer");
  const [skills, setSkills] = useState("Python, FastAPI");
  const [queries, setQueries] = useState<string[]>([]);
  const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  const gen = useMutation({ mutationFn: () => generateQueries({ target_roles: split(roles), skills: split(skills), locations: [] }), onSuccess: (d) => setQueries(d.queries) });
  const run = useMutation({ mutationFn: () => runDiscovery(queries) });
  const inp = "w-full rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm";
  return (
    <div className="max-w-3xl">
      <h1 className="text-xl font-semibold">Discovery</h1>
      <div className="mt-4 space-y-2"><input className={inp} value={roles} onChange={(e) => setRoles(e.target.value)} /><input className={inp} value={skills} onChange={(e) => setSkills(e.target.value)} /></div>
      <div className="mt-3 flex gap-2">
        <button onClick={() => gen.mutate()} className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm">Generate Queries</button>
        <button disabled={!queries.length || run.isPending} onClick={() => run.mutate()} className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm disabled:opacity-40">{run.isPending ? "Running…" : "Run Discovery"}</button>
      </div>
      <ul className="mt-3 text-sm text-slate-300">{queries.map((q) => <li key={q}>• {q}</li>)}</ul>
      {run.isError && <p className="mt-3 text-red-400">Discovery failed: {(run.error as Error).message}</p>}
      {run.data && (
        <div className="mt-5">
          <p className="text-sm text-slate-400">Requests {run.data.summary.total_requests} · ok {run.data.summary.successful} · failed {run.data.summary.failed} · {run.data.summary.duration_s}s</p>
          <p className="text-xs text-amber-400">{run.data.note}</p>
          {run.data.jobs.length === 0 && run.data.summary.failed === 0 && <p className="mt-2 text-slate-400">No jobs found (sources responded successfully).</p>}
          {run.data.errors.map((e, i) => <p key={i} className="text-sm text-red-400">Source {e.source}: {e.error}</p>)}
          {run.data.jobs.map((j, i) => (
            <div key={i} className="mt-2 rounded-lg border border-white/10 bg-white/5 p-3 text-sm">
              <div className="font-medium">{j.title} — {j.company}</div>
              <div className="text-xs text-slate-400">{j.location} · {j.source} · unverified</div>
              {j.job_url && <a className="text-xs text-indigo-300" href={j.job_url} target="_blank" rel="noreferrer">Open job</a>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
