import { ExternalLink, Building2, MapPin } from 'lucide-react';
import type { NormalizedJob } from '../types/api';

interface JobTableProps {
  jobs: NormalizedJob[];
}

export function JobTable({ jobs }: JobTableProps) {
  if (jobs.length === 0) return null;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Company</th>
            <th>Location</th>
            <th>Mode</th>
            <th>Source</th>
            <th>Skills</th>
            <th>Posted</th>
            <th style={{ textAlign: 'right' }}>Action</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.dedup_hash}>
              <td style={{ fontWeight: 600, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {job.title}
              </td>
              <td>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  <Building2 size={12} style={{ color: 'var(--color-text-dim)', flexShrink: 0 }} />
                  <span style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.company_name}</span>
                </div>
              </td>
              <td>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  <MapPin size={12} style={{ color: 'var(--color-text-dim)', flexShrink: 0 }} />
                  <span>{job.location}</span>
                </div>
              </td>
              <td>
                <span className={`badge ${job.work_mode === 'remote' ? 'badge-green' : job.work_mode === 'hybrid' ? 'badge-yellow' : 'badge-gray'}`} style={{ textTransform: 'capitalize' }}>
                  {job.work_mode.replace('_', '-')}
                </span>
              </td>
              <td style={{ textTransform: 'capitalize', color: 'var(--color-text-dim)' }}>{job.source}</td>
              <td>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2, maxWidth: 200 }}>
                  {job.tags.slice(0, 3).map((t) => (
                    <span key={t} className="tag">{t}</span>
                  ))}
                  {job.tags.length > 3 && <span className="tag" style={{ opacity: 0.6 }}>+{job.tags.length - 3}</span>}
                </div>
              </td>
              <td style={{ color: 'var(--color-text-dim)', fontSize: '0.8rem' }}>
                {job.posting_date ? new Date(job.posting_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}
              </td>
              <td style={{ textAlign: 'right' }}>
                <a href={job.job_url} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-sm">
                  <ExternalLink size={12} /> Open
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
