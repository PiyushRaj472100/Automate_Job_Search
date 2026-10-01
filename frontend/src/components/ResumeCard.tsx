import { FileText, Calendar, User, ChevronRight } from 'lucide-react';
import type { ResumeSummaryResponse } from '../types/api';
import { useNavigate } from 'react-router-dom';

interface ResumeCardProps {
  resume: ResumeSummaryResponse;
}

export function ResumeCard({ resume }: ResumeCardProps) {
  const navigate = useNavigate();

  const formattedDate = new Date(resume.created_at).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  });

  return (
    <div
      className="card"
      style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '1rem' }}
      onClick={() => navigate(`/resumes/${resume.id}`)}
    >
      {/* Icon */}
      <div style={{
        width: 44, height: 44, borderRadius: 10,
        background: 'rgba(59,130,246,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <FileText size={20} style={{ color: '#60a5fa' }} />
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ margin: 0, fontWeight: 600, fontSize: '0.9rem', color: 'var(--color-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {resume.file_name}
        </p>
        <div style={{ display: 'flex', gap: '1rem', marginTop: '0.3rem' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.75rem', color: 'var(--color-text-dim)' }}>
            <Calendar size={12} /> {formattedDate}
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.75rem', color: 'var(--color-text-dim)' }}>
            <User size={12} /> {resume.profiles_count} profile{resume.profiles_count !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      <ChevronRight size={16} style={{ color: 'var(--color-text-dim)', flexShrink: 0 }} />
    </div>
  );
}
