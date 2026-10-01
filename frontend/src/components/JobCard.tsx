import { ExternalLink, Building2, MapPin } from 'lucide-react';
import type { NormalizedJob } from '../types/api';

interface JobCardProps {
  job: NormalizedJob;
}

const WORK_MODE_LABELS: Record<string, string> = {
  remote: 'Remote',
  hybrid: 'Hybrid',
  on_site: 'On-site',
  unknown: 'Unknown',
};

export function JobCard({ job }: JobCardProps) {
  const modeLabel = WORK_MODE_LABELS[job.work_mode] ?? job.work_mode;

  // Score from tags or just display source
  const displayTags = job.tags.slice(0, 6);

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--color-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {job.title}
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.25rem', color: 'var(--color-text-dim)', fontSize: '0.82rem' }}>
            <Building2 size={12} />
            <span>{job.company_name}</span>
          </div>
        </div>
        <span className="badge badge-blue" style={{ flexShrink: 0, textTransform: 'capitalize' }}>
          {modeLabel}
        </span>
      </div>

      {/* Location */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', color: 'var(--color-text-dim)' }}>
        <MapPin size={12} />
        <span>{job.location}</span>
      </div>

      {/* Skills / Tags */}
      {displayTags.length > 0 && (
        <div>
          <p style={{ margin: '0 0 0.35rem', fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-dim)' }}>
            Skills
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {displayTags.map((tag) => (
              <span key={tag} className="tag">{tag}</span>
            ))}
            {job.tags.length > 6 && (
              <span className="tag" style={{ opacity: 0.6 }}>+{job.tags.length - 6} more</span>
            )}
          </div>
        </div>
      )}

      {/* Source + Footer */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '0.25rem', borderTop: '1px solid var(--color-border)' }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-dim)' }}>
          <span style={{ fontWeight: 600, color: 'var(--color-text-dim)', textTransform: 'capitalize' }}>
            via {job.source}
          </span>
          {job.posting_date && (
            <span style={{ marginLeft: '0.75rem' }}>
              {new Date(job.posting_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            </span>
          )}
        </div>
        <a
          href={job.job_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-primary btn-sm"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink size={13} /> Open Job
        </a>
      </div>
    </div>
  );
}
