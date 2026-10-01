import { Loader2 } from 'lucide-react';

interface LoadingProps {
  message?: string;
  size?: number;
}

export function Loading({ message = 'Loading...', size = 20 }: LoadingProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--color-text-dim)', padding: '1.5rem 0', justifyContent: 'center' }}>
      <Loader2 size={size} className="animate-spin" />
      <span style={{ fontSize: '0.875rem' }}>{message}</span>
    </div>
  );
}

export function PageLoading({ message }: { message?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', flexDirection: 'column', gap: '1rem' }}>
      <Loader2 size={36} className="animate-spin" style={{ color: 'var(--color-accent)' }} />
      <p style={{ color: 'var(--color-text-dim)', fontSize: '0.9rem' }}>{message ?? 'Loading...'}</p>
    </div>
  );
}
