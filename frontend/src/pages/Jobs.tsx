import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LayoutGrid, List, ArrowLeft, Briefcase } from 'lucide-react';
import type { SearchDiscoveryResponse, NormalizedJob } from '../types/api';
import { JobCard } from '../components/JobCard';
import { JobTable } from '../components/JobTable';

export default function Jobs() {
  const navigate = useNavigate();
  const [data, setData] = useState<SearchDiscoveryResponse | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');

  useEffect(() => {
    const stored = sessionStorage.getItem('jobResults');
    if (stored) {
      try { setData(JSON.parse(stored)); } catch { /* ignore */ }
    }
  }, []);

  if (!data) {
    return (
      <div>
        <div className="page-header">
          <h1 className="page-title">Job Results</h1>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon">💼</div>
          <h3>No jobs found yet</h3>
          <p>Run a job search from the Job Discovery page to see results here.</p>
          <button className="btn btn-primary" onClick={() => navigate('/discovery')}>
            <Briefcase size={15} /> Go to Discovery
          </button>
        </div>
      </div>
    );
  }

  const { summary, jobs } = data;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Job Results</h1>
          <p className="page-subtitle">{jobs.length} jobs found across {summary.successful_sources.length} source{summary.successful_sources.length !== 1 ? 's' : ''}</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            className={`btn btn-sm ${viewMode === 'grid' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode('grid')}
          >
            <LayoutGrid size={14} />
          </button>
          <button
            className={`btn btn-sm ${viewMode === 'table' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode('table')}
          >
            <List size={14} />
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/discovery')}>
            <ArrowLeft size={14} /> New Search
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <p style={{ margin: '0 0 0.25rem', fontSize: '1.75rem', fontWeight: 800, color: 'var(--color-text)' }}>{summary.total_queries}</p>
          <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--color-text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Queries</p>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <p style={{ margin: '0 0 0.25rem', fontSize: '1.75rem', fontWeight: 800, color: '#10b981' }}>{summary.successful_sources.length}</p>
          <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--color-text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Sources OK</p>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <p style={{ margin: '0 0 0.25rem', fontSize: '1.75rem', fontWeight: 800, color: '#ef4444' }}>{Object.keys(summary.failed_sources).length}</p>
          <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--color-text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Sources Failed</p>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <p style={{ margin: '0 0 0.25rem', fontSize: '1.75rem', fontWeight: 800, color: '#3b82f6' }}>{summary.total_raw_found}</p>
          <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--color-text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Raw Found</p>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <p style={{ margin: '0 0 0.25rem', fontSize: '1.75rem', fontWeight: 800, color: '#8b5cf6' }}>{summary.total_deduplicated}</p>
          <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--color-text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Unique Jobs</p>
        </div>
      </div>

      {/* Failed sources warning */}
      {Object.keys(summary.failed_sources).length > 0 && (
        <div style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)', borderRadius: 10, padding: '0.75rem 1rem', marginBottom: '1rem', fontSize: '0.825rem', color: '#fbbf24' }}>
          ⚠ Failed sources: {Object.keys(summary.failed_sources).join(', ')}
        </div>
      )}

      {/* Jobs */}
      {jobs.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">🔍</div>
          <h3>No jobs found</h3>
          <p>Try different roles, skills, locations, or sources.</p>
          <button className="btn btn-primary" onClick={() => navigate('/discovery')}>
            New Search
          </button>
        </div>
      ) : viewMode === 'grid' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
          {jobs.map((job) => <JobCard key={job.dedup_hash} job={job} />)}
        </div>
      ) : (
        <JobTable jobs={jobs} />
      )}
    </div>
  );
}
