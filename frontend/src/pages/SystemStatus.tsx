import { useEffect, useState } from 'react';
import {
  Server, Database, Sheet, Activity, CheckCircle, AlertTriangle, XCircle, RefreshCw,
} from 'lucide-react';
import { healthApi } from '../api/health';
import { discoveryApi } from '../api/discovery';
import type { HealthResponse, ReadyResponse, MetricsResponse, SourceHealthCheck } from '../types/api';
import { Loading } from '../components/Loading';
import { ErrorMessage } from '../components/ErrorMessage';
import { getErrorMessage } from '../api/client';

type StatusLevel = 'healthy' | 'degraded' | 'error' | 'unknown';

function statusIcon(s: StatusLevel) {
  if (s === 'healthy') return <CheckCircle size={16} style={{ color: '#10b981' }} />;
  if (s === 'degraded') return <AlertTriangle size={16} style={{ color: '#f59e0b' }} />;
  if (s === 'error') return <XCircle size={16} style={{ color: '#ef4444' }} />;
  return <AlertTriangle size={16} style={{ color: '#94a3b8' }} />;
}

function statusLabel(s: StatusLevel) {
  const MAP = { healthy: 'Healthy', degraded: 'Degraded', error: 'Error', unknown: 'Unknown' };
  const COLOR = { healthy: '#10b981', degraded: '#f59e0b', error: '#ef4444', unknown: '#94a3b8' };
  return <span style={{ color: COLOR[s], fontWeight: 600, fontSize: '0.85rem' }}>{MAP[s]}</span>;
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--color-border)' }}>
        <span style={{ color: 'var(--color-accent)' }}>{icon}</span>
        <h2 style={{ margin: 0, fontSize: '0.875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-text-dim)' }}>
          {title}
        </h2>
      </div>
      {children}
    </div>
  );
}

function Row({ label, value, status }: { label: string; value?: string; status?: StatusLevel }) {
  return (
    <div className="info-row">
      <span className="info-label">{label}</span>
      <span className="info-value">
        {status && <span style={{ marginRight: '0.5rem' }}>{statusIcon(status)}</span>}
        {status && statusLabel(status)}
        {value && <span style={{ color: 'var(--color-text-dim)', marginLeft: status ? ' 0.5rem' : 0 }}>{value}</span>}
      </span>
    </div>
  );
}

function formatTs(ts: string | null) {
  if (!ts) return 'Never';
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function SystemStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ready, setReady] = useState<ReadyResponse | { ready: boolean; details: Record<string, string>; timestamp: string } | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [sourceHealth, setSourceHealth] = useState<Record<string, SourceHealthCheck> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, m, sh] = await Promise.all([
        healthApi.getHealth(),
        healthApi.getMetrics(),
        discoveryApi.getSourceHealth(),
      ]);
      setHealth(h.data);
      setMetrics(m.data);
      setSourceHealth(sh.data);

      try {
        const r = await healthApi.getReady();
        setReady(r.data);
      } catch (e: any) {
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
  const dbStatus: StatusLevel = details.database ? (details.database === 'ok' ? 'healthy' : 'error') : 'unknown';
  const sheetsStatus: StatusLevel = details.google_sheets ? (details.google_sheets === 'ok' ? 'healthy' : 'error') : 'unknown';

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">System Status</h1>
          <p className="page-subtitle">Health and diagnostics for all platform components</p>
        </div>
        <button className="btn btn-secondary" onClick={fetchAll} disabled={loading}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {loading && <Loading message="Checking system status..." />}
      {error && <ErrorMessage message={error} onRetry={fetchAll} />}

      {!loading && !error && (
        <>
          {/* Application */}
          <Section title="Application" icon={<Server size={16} />}>
            <Row label="Status" status={health ? 'healthy' : 'error'} />
            <Row label="Project" value={health?.project} />
            <Row label="Version" value={health?.version} />
            <Row label="Environment" value={health?.environment} />
            <Row label="Checked At" value={health ? new Date(health.timestamp).toLocaleTimeString() : '—'} />
          </Section>

          {/* Database */}
          <Section title="Database" icon={<Database size={16} />}>
            <Row label="Status" status={dbStatus} value={details.database !== 'ok' ? details.database : undefined} />
          </Section>

          {/* Google Sheets */}
          <Section title="Google Sheets" icon={<Sheet size={16} />}>
            <Row label="Status" status={sheetsStatus} value={details.google_sheets !== 'ok' ? details.google_sheets : undefined} />
          </Section>

          {/* Job Sources */}
          <Section title="Job Sources" icon={<Activity size={16} />}>
            {sourceHealth && Object.keys(sourceHealth).length > 0 ? (
              Object.entries(sourceHealth).map(([name, check]) => (
                <div key={name} className="info-row">
                  <span className="info-label" style={{ textTransform: 'capitalize' }}>{name}</span>
                  <span className="info-value" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
                    {statusIcon(check.is_healthy ? 'healthy' : 'error')}
                    {statusLabel(check.is_healthy ? 'healthy' : 'error')}
                    <span style={{ color: 'var(--color-text-dim)', fontSize: '0.78rem' }}>{check.response_time_ms.toFixed(0)}ms</span>
                    {!check.is_healthy && (
                      <span style={{ color: '#f87171', fontSize: '0.78rem' }}>{check.details}</span>
                    )}
                  </span>
                </div>
              ))
            ) : (
              <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--color-text-dim)' }}>No sources configured.</p>
            )}
          </Section>

          {/* Pipeline */}
          <Section title="Pipeline Metrics" icon={<Activity size={16} />}>
            <Row label="Total Runs" value={String(metrics?.total_runs ?? 0)} />
            <Row label="Failed Runs" value={String(metrics?.failed_runs ?? 0)} />
            <Row
              label="Pipeline Status"
              status={metrics ? (metrics.failed_runs > 0 ? 'degraded' : 'healthy') : 'unknown'}
            />
            <Row label="Last Successful Run" value={formatTs(metrics?.last_successful_run ?? null)} />
            <Row label="Last Failed Run" value={formatTs(metrics?.last_failed_run ?? null)} />
            <Row label="Metrics Checked At" value={metrics ? new Date(metrics.timestamp).toLocaleTimeString() : '—'} />
          </Section>
        </>
      )}
    </div>
  );
}
