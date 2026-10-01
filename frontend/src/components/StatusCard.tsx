import React from 'react';
import { CheckCircle, AlertTriangle, XCircle } from 'lucide-react';

type StatusType = 'healthy' | 'degraded' | 'error' | 'unknown';

interface StatusCardProps {
  title: string;
  status: StatusType;
  value?: string;
  subValue?: string;
  icon?: React.ReactNode;
  extra?: React.ReactNode;
}

const STATUS_CONFIG: Record<StatusType, { label: string; color: string; icon: React.ReactNode }> = {
  healthy: { label: 'Healthy', color: '#10b981', icon: <CheckCircle size={14} /> },
  degraded: { label: 'Degraded', color: '#f59e0b', icon: <AlertTriangle size={14} /> },
  error: { label: 'Error', color: '#ef4444', icon: <XCircle size={14} /> },
  unknown: { label: 'Unknown', color: '#94a3b8', icon: <AlertTriangle size={14} /> },
};

export function StatusCard({ title, status, value, subValue, icon, extra }: StatusCardProps) {
  const cfg = STATUS_CONFIG[status];
  return (
    <div className="card" style={{ position: 'relative', overflow: 'hidden' }}>
      {/* Glow accent */}
      <div style={{
        position: 'absolute', top: 0, left: 0, width: '3px', height: '100%',
        background: cfg.color, borderRadius: '12px 0 0 12px',
      }} />
      <div style={{ paddingLeft: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-dim)' }}>
            {title}
          </span>
          {icon && <span style={{ color: 'var(--color-text-dim)', opacity: 0.6 }}>{icon}</span>}
        </div>
        {value !== undefined && (
          <p style={{ margin: '0 0 0.35rem', fontSize: '1.4rem', fontWeight: 700, color: 'var(--color-text)' }}>
            {value}
          </p>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: cfg.color, fontSize: '0.8rem', fontWeight: 500 }}>
          {cfg.icon} {cfg.label}
        </div>
        {subValue && (
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.775rem', color: 'var(--color-text-dim)' }}>{subValue}</p>
        )}
        {extra && <div style={{ marginTop: '0.75rem' }}>{extra}</div>}
      </div>
    </div>
  );
}

interface MetricCardProps {
  title: string;
  value: string | number;
  subValue?: string;
  icon?: React.ReactNode;
  accent?: string;
}

export function MetricCard({ title, value, subValue, icon, accent = '#3b82f6' }: MetricCardProps) {
  return (
    <div className="card" style={{ position: 'relative', overflow: 'hidden' }}>
      <div style={{
        position: 'absolute', top: 0, left: 0, width: '3px', height: '100%',
        background: accent, borderRadius: '12px 0 0 12px',
      }} />
      <div style={{ paddingLeft: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-dim)' }}>
            {title}
          </span>
          {icon && <span style={{ color: accent, opacity: 0.7 }}>{icon}</span>}
        </div>
        <p style={{ margin: '0 0 0.25rem', fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-text)' }}>
          {value}
        </p>
        {subValue && (
          <p style={{ margin: 0, fontSize: '0.775rem', color: 'var(--color-text-dim)' }}>{subValue}</p>
        )}
      </div>
    </div>
  );
}
