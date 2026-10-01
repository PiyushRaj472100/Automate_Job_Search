import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Server, Database, Sheet, Activity, Clock, CheckCircle, XCircle, Search, FileText,
} from 'lucide-react';
import { healthApi } from '../api/health';
import { resumesApi } from '../api/resumes';
import type { HealthResponse, ReadyResponse, MetricsResponse } from '../types/api';
import { StatusCard, MetricCard } from '../components/StatusCard';
import { Loading } from '../components/Loading';
import { ErrorMessage } from '../components/ErrorMessage';
import { getErrorMessage } from '../api/client';

function formatTimestamp(ts: string | null) {
  if (!ts) return 'Never';
  return new Date(ts).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [resumeCount, setResumeCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, m, resumes] = await Promise.all([
        healthApi.getHealth(),
        healthApi.getMetrics(),
        resumesApi.list(),
      ]);
      setHealth(h.data);
      setMetrics(m.data);
      setResumeCount(resumes.data.length);

      // Ready check can fail (503) — handle independently
      try {
        const r = await healthApi.getReady();
        setReady(r.data);
      } catch (e: any) {
        // 503 response data can have { ready, details, timestamp } or { detail: ... }
        const data = e?.response?.data;
        if (data) {
          const details = data.details || data.detail || {};
          setReady({
            ready: Boolean(data.ready),
            details: typeof details === 'object' && details !== null ? details : {},
            timestamp: data.timestamp || new Date().toISOString(),
          });
        }
      }
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const details = ready?.details ?? {};
  const dbStatus = details.database ? (details.database === 'ok' ? 'healthy' : 'error') : 'unknown';
  const sheetsStatus = details.google_sheets ? (details.google_sheets === 'ok' ? 'healthy' : 'error') : 'unknown';
  const backendStatus = health ? 'healthy' : 'error';

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title gradient-text">Personal Job Intelligence</h1>
          <p className="page-subtitle">Your AI-powered job search platform</p>
        </div>
        <button className="btn btn-secondary" onClick={fetchAll}>
          <Activity size={14} /> Refresh
        </button>
      </div>

      {loading && <Loading message="Checking system status..." />}
      {error && <ErrorMessage message={error} onRetry={fetchAll} />}

      {!loading && !error && (
        <>
          {/* System Status Row */}
          <h2 style={{ fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--color-text-dim)', marginBottom: '0.75rem' }}>
            System Status
          </h2>
          <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
            <StatusCard
              title="Backend"
              status={backendStatus}
              value={health?.version ?? '—'}
              subValue={health?.environment}
              icon={<Server size={16} />}
            />
            <StatusCard
              title="Database"
              status={dbStatus}
              subValue={details.database}
              icon={<Database size={16} />}
            />
            <StatusCard
              title="Google Sheets"
              status={sheetsStatus}
              subValue={details.google_sheets === 'ok' ? 'Connected' : details.google_sheets}
              icon={<Sheet size={16} />}
            />
          </div>

          {/* Pipeline Metrics */}
          <h2 style={{ fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--color-text-dim)', marginBottom: '0.75rem' }}>
            Pipeline Metrics
          </h2>
          <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
            <MetricCard
              title="Total Pipeline Runs"
              value={metrics?.total_runs ?? 0}
              icon={<Activity size={16} />}
              accent="#3b82f6"
            />
            <MetricCard
              title="Failed Runs"
              value={metrics?.failed_runs ?? 0}
              icon={<XCircle size={16} />}
              accent="#ef4444"
            />
            <MetricCard
              title="Last Successful Run"
              value={formatTimestamp(metrics?.last_successful_run ?? null)}
              icon={<CheckCircle size={16} />}
              accent="#10b981"
            />
            <MetricCard
              title="Last Failed Run"
              value={formatTimestamp(metrics?.last_failed_run ?? null)}
              icon={<Clock size={16} />}
              accent="#f59e0b"
            />
          </div>

          {/* Quick Actions */}
          <h2 style={{ fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--color-text-dim)', marginBottom: '0.75rem' }}>
            Quick Actions
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '1rem' }}>
            <div className="card" style={{ cursor: 'pointer' }} onClick={() => navigate('/resumes')}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(59,130,246,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <FileText size={18} style={{ color: '#60a5fa' }} />
                </div>
                <div>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: '0.9rem' }}>Manage Resumes</p>
                  <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--color-text-dim)' }}>
                    {resumeCount !== null ? `${resumeCount} resume${resumeCount !== 1 ? 's' : ''} uploaded` : 'Upload & view resumes'}
                  </p>
                </div>
              </div>
            </div>
            <div className="card" style={{ cursor: 'pointer' }} onClick={() => navigate('/discovery')}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(139,92,246,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Search size={18} style={{ color: '#a78bfa' }} />
                </div>
                <div>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: '0.9rem' }}>Discover Jobs</p>
                  <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--color-text-dim)' }}>Generate queries & search</p>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
