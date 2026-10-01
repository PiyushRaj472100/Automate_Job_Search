import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorMessageProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorMessage({ message, onRetry }: ErrorMessageProps) {
  return (
    <div style={{
      background: 'rgba(239,68,68,0.08)',
      border: '1px solid rgba(239,68,68,0.25)',
      borderRadius: '10px',
      padding: '1rem 1.25rem',
      display: 'flex',
      alignItems: 'flex-start',
      gap: '0.75rem',
    }}>
      <AlertTriangle size={18} style={{ color: '#f87171', flexShrink: 0, marginTop: '1px' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ margin: 0, color: '#f87171', fontSize: '0.875rem', wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{message}</p>
      </div>
      {onRetry && (
        <button className="btn btn-sm btn-secondary" onClick={onRetry} style={{ flexShrink: 0 }}>
          <RefreshCw size={13} /> Retry
        </button>
      )}
    </div>
  );
}
