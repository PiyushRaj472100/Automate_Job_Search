import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sheet, ExternalLink, Plus, FileText } from 'lucide-react';
import { resumesApi } from '../api/resumes';
import { sheetsApi } from '../api/sheets';
import type { ResumeSummaryResponse, SheetStatusResponse } from '../types/api';
import { Loading } from '../components/Loading';
import { ErrorMessage } from '../components/ErrorMessage';
import { getErrorMessage } from '../api/client';
import { useToast } from '../components/Toast';

interface ResumeSheetPair {
  resume: ResumeSummaryResponse;
  sheet: SheetStatusResponse | null;
  sheetLoading: boolean;
}

export default function GoogleSheets() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [pairs, setPairs] = useState<ResumeSheetPair[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await resumesApi.list();
      const initial: ResumeSheetPair[] = res.data.map((r) => ({ resume: r, sheet: null, sheetLoading: true }));
      setPairs(initial);

      // Fetch sheet status for each
      const updated = await Promise.all(
        res.data.map(async (r) => {
          try {
            const s = await sheetsApi.getStatus(r.id);
            return { resume: r, sheet: s.data, sheetLoading: false };
          } catch {
            return { resume: r, sheet: null, sheetLoading: false };
          }
        })
      );
      setPairs(updated);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const handleCreate = async (resumeId: string) => {
    setCreating(resumeId);
    try {
      const res = await sheetsApi.create(resumeId);
      setPairs((prev) => prev.map((p) =>
        p.resume.id === resumeId
          ? { ...p, sheet: { resume_id: resumeId, file_name: p.resume.file_name, spreadsheet_id: res.data.spreadsheet_id, spreadsheet_url: res.data.spreadsheet_url, is_linked: true } }
          : p
      ));
      showToast('Google Sheet created successfully!', 'success');
    } catch (e) {
      showToast(getErrorMessage(e), 'error');
    } finally {
      setCreating(null);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Google Sheets</h1>
          <p className="page-subtitle">Manage spreadsheet dashboards linked to your resumes</p>
        </div>
      </div>

      {loading && <Loading message="Loading resumes and sheets..." />}
      {error && <ErrorMessage message={error} onRetry={fetchAll} />}

      {!loading && !error && pairs.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📊</div>
          <h3>No resumes yet</h3>
          <p>Upload a resume first to create a Google Sheet.</p>
          <button className="btn btn-primary" onClick={() => navigate('/resumes')}>
            <FileText size={15} /> Go to Resumes
          </button>
        </div>
      )}

      {!loading && !error && pairs.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {pairs.map(({ resume, sheet, sheetLoading }) => (
            <div key={resume.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              {/* Resume info */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: 0 }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(59,130,246,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <FileText size={18} style={{ color: '#60a5fa' }} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{resume.file_name}</p>
                  <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--color-text-dim)' }}>
                    {new Date(resume.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                  </p>
                </div>
              </div>

              {/* Sheet status */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexShrink: 0 }}>
                {sheetLoading ? (
                  <span style={{ fontSize: '0.78rem', color: 'var(--color-text-dim)' }}>Loading...</span>
                ) : sheet?.is_linked ? (
                  <>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.8rem', color: 'var(--color-success)', fontWeight: 600 }}>
                      <Sheet size={14} /> Connected
                    </span>
                    <a
                      href={sheet.spreadsheet_url!}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-success btn-sm"
                    >
                      <ExternalLink size={13} /> Open Sheet
                    </a>
                  </>
                ) : (
                  <>
                    <span style={{ fontSize: '0.8rem', color: 'var(--color-text-dim)' }}>Not connected</span>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleCreate(resume.id)}
                      disabled={creating === resume.id}
                    >
                      {creating === resume.id ? (
                        <><span className="animate-spin" style={{ display: 'inline-block' }}>⟳</span> Creating...</>
                      ) : (
                        <><Plus size={13} /> Create Sheet</>
                      )}
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
