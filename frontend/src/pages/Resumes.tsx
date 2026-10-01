import { useState, useEffect, useRef } from 'react';
import { Plus, Upload, X, FileText } from 'lucide-react';
import { resumesApi } from '../api/resumes';
import type { ResumeSummaryResponse, ResumeUploadResult } from '../types/api';
import { ResumeCard } from '../components/ResumeCard';
import { Loading } from '../components/Loading';
import { ErrorMessage } from '../components/ErrorMessage';
import { useToast } from '../components/Toast';
import { getErrorMessage } from '../api/client';

export default function Resumes() {
  const { showToast } = useToast();
  const [resumes, setResumes] = useState<ResumeSummaryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [uploadResult, setUploadResult] = useState<ResumeUploadResult | null>(null);

  const fetchResumes = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await resumesApi.list();
      setResumes(res.data);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchResumes(); }, []);

  const handleUploadSuccess = (result: ResumeUploadResult) => {
    setUploadResult(result);
    showToast('Resume uploaded successfully!', 'success');
    fetchResumes();
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">My Resumes</h1>
          <p className="page-subtitle">Upload and manage your resume profiles</p>
        </div>
        <button className="btn btn-primary" onClick={() => { setUploadResult(null); setShowModal(true); }}>
          <Plus size={16} /> Upload Resume
        </button>
      </div>

      {loading && <Loading message="Loading resumes..." />}
      {error && <ErrorMessage message={error} onRetry={fetchResumes} />}

      {!loading && !error && resumes.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📄</div>
          <h3>No resumes yet</h3>
          <p>Upload your first resume to start searching for jobs.</p>
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            <Upload size={16} /> Upload Resume
          </button>
        </div>
      )}

      {!loading && !error && resumes.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {resumes.map((r) => <ResumeCard key={r.id} resume={r} />)}
        </div>
      )}

      {/* Upload Modal */}
      {showModal && (
        <UploadModal
          onClose={() => setShowModal(false)}
          onSuccess={handleUploadSuccess}
        />
      )}

      {/* Success result */}
      {uploadResult && (
        <UploadResultCard result={uploadResult} onDismiss={() => setUploadResult(null)} />
      )}
    </div>
  );
}

// ---- Upload Modal ----

function UploadModal({ onClose, onSuccess }: {
  onClose: () => void;
  onSuccess: (r: ResumeUploadResult) => void;
}) {
  const { showToast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [profileName, setProfileName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) { setError('Please select a file.'); return; }
    setError(null);
    setUploading(true);
    try {
      const res = await resumesApi.upload(file, profileName);
      onSuccess(res.data);
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>Upload Resume</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-dim)' }}>
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {/* File drop zone */}
          <div
            onClick={() => fileRef.current?.click()}
            style={{
              border: `2px dashed ${file ? 'var(--color-success)' : 'var(--color-border)'}`,
              borderRadius: 10, padding: '1.5rem', textAlign: 'center', cursor: 'pointer',
              transition: 'border-color 0.2s', marginBottom: '1rem',
              background: file ? 'rgba(16,185,129,0.05)' : 'transparent',
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx"
              style={{ display: 'none' }}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <FileText size={28} style={{ color: file ? 'var(--color-success)' : 'var(--color-text-dim)', marginBottom: '0.5rem' }} />
            {file ? (
              <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--color-success)', fontWeight: 600 }}>{file.name}</p>
            ) : (
              <>
                <p style={{ margin: '0 0 0.25rem', fontWeight: 600, fontSize: '0.875rem' }}>Click to select file</p>
                <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--color-text-dim)' }}>PDF or DOCX files only</p>
              </>
            )}
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <label className="input-label">Profile Name (optional)</label>
            <input
              type="text"
              className="input"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              placeholder="e.g. Backend Engineer Profile"
            />
          </div>

          {error && <ErrorMessage message={error} />}

          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '1.25rem' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={uploading}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={uploading || !file}>
              {uploading ? (
                <><span className="animate-spin" style={{ display: 'inline-block' }}>⟳</span> Uploading...</>
              ) : (
                <><Upload size={15} /> Upload</>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---- Upload Result Card ----

function UploadResultCard({ result, onDismiss }: { result: ResumeUploadResult; onDismiss: () => void }) {
  return (
    <div style={{
      position: 'fixed', bottom: '5rem', right: '1.5rem', width: 340,
      background: 'var(--color-surface)', border: '1px solid rgba(16,185,129,0.3)',
      borderRadius: 12, padding: '1.25rem', zIndex: 40,
      boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      animation: 'slideInRight 0.25s ease',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <p style={{ margin: 0, fontWeight: 700, color: 'var(--color-success)', fontSize: '0.875rem' }}>
          ✓ Resume Successfully Uploaded
        </p>
        <button onClick={onDismiss} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-dim)' }}>
          <X size={14} />
        </button>
      </div>
      <div style={{ fontSize: '0.8rem', color: 'var(--color-text-dim)' }}>
        <div className="info-row"><span className="info-label">Resume ID</span><span className="info-value" style={{ fontSize: '0.72rem', wordBreak: 'break-all' }}>{result.resume_id}</span></div>
        <div className="info-row"><span className="info-label">Filename</span><span className="info-value">{result.file_name}</span></div>
        <div className="info-row"><span className="info-label">Profile Name</span><span className="info-value">{result.profile_name}</span></div>
        <div className="info-row"><span className="info-label">Target Role</span><span className="info-value">{result.target_role}</span></div>
        <div className="info-row"><span className="info-label">Seniority</span><span className="info-value">{result.seniority}</span></div>
        <div className="info-row"><span className="info-label">Skills Extracted</span><span className="info-value">{result.skills_extracted_count}</span></div>
        {result.is_duplicate && (
          <p style={{ margin: '0.5rem 0 0', color: 'var(--color-warning)', fontSize: '0.78rem' }}>⚠ Duplicate resume — new profile version created</p>
        )}
      </div>
    </div>
  );
}
