import { useQuery } from "@tanstack/react-query";
import { getHealth, getReadiness, getSources } from "../api/client";

export function System() {
  const h = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 15000 });
  const r = useQuery({ queryKey: ["ready"], queryFn: getReadiness, refetchInterval: 15000 });
  const s = useQuery({ queryKey: ["sources"], queryFn: getSources });
  return (
    <div>
      <h1 className="text-xl font-semibold">System</h1>
      <p className="mt-3 text-sm">API: {h.isError ? <span className="text-red-400">unreachable</span> : <span className="text-emerald-400">{h.data?.status ?? "…"}</span>}</p>
      <div className="mt-2 text-sm">{r.data && Object.entries(r.data.details).map(([k, v]) => <div key={k}>{k}: <span className={v === "ok" ? "text-emerald-400" : "text-amber-400"}>{v}</span></div>)}</div>
      <h2 className="mt-5 text-sm font-semibold text-slate-300">Sources</h2>
      {s.data?.map((x) => <div key={x.name} className="text-sm">{x.name} ({x.policy}) {x.circuit_open ? "⚠ circuit open" : "ok"}</div>)}
    </div>
  );
}
