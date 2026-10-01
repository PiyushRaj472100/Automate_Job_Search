import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ExternalLink, FileText, User, Calendar, MapPin,
  Sheet, Plus, Eye, ChevronDown, ChevronUp,
} from 'lucide-react';
import { resumesApi } from '../api/resumes';
import { sheetsApi } from '../api/sheets';
import type {
  ResumeDetailResponse, ResumeProfileDetailResponse,
  SheetStatusResponse, SheetCreateResponse,
} from '../types/api';
import { Loading } from '../components/Loading';
import { ErrorMessage } from '../components/ErrorMessage';
import { useToast } from '../components/Toast';
import { getErrorMessage } from '../api/client';

export default function ResumeDetails() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [resume, setResume] = useState<ResumeDetailResponse | null>(null);
  const [sheetStatus, setSheetStatus] = useState<SheetStatusResponse | null>(null);
  const [profileData, setProfileData] = useState<Record<string, unknown> | null>(null);
  const [showProfile, setShowProfile] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creatingSheet, setCreatingSheet] = useState(false);
  const [sheetResult, setSheetResult] = useState<SheetCreateResponse | null>(null);

  const fetchAll = async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [r, s] = await Promise.all([
        resumesApi.getById(id),
        sheetsApi.getStatus(id),
      ]);
      setResume(r.data);
      setSheetStatus(s.data);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, [id]);

  const handleCreateSheet = async () => {
    if (!id) return;
    setCreatingSheet(true);
    try {
      const res = await sheetsApi.create(id);
      setSheetResult(res.data);
      setSheetStatus({ ...sheetStatus!, spreadsheet_url: res.data.spreadsheet_url, spreadsheet_id: res.data.spreadsheet_id, is_linked: true });
      showToast('Google Sheet created successfully!', 'success');
    } catch (e) {
      showToast(getErrorMessage(e), 'error');
    } finally {
      setCreatingSheet(false);
    }
  };

  const handleLoadProfile = async () => {
    if (!id) return;
    if (profileData) { setShowProfile(!showProfile); return; }
    setProfileLoading(true);
    setProfileError(null);
    try {
      const res = await resumesApi.getProfile(id);
      setProfileData(res.data);
      setShowProfile(true);
    } catch (e) {
      setProfileError(getErrorMessage(e));
    } finally {
      setProfileLoading(false);
    }
  };

  const activeProfile: ResumeProfileDetailResponse | undefined = resume?.profiles.find(p => p.is_active) ?? resume?.profiles[0];

  return (
    <div>
      <button className="back-link" onClick={() => navigate('/resumes')}>
        <ArrowLeft size={14} /> Back to Resumes
      </button>

      {loading && <Loading message="Loading resume details..." />}
      {error && <ErrorMessage message={error} onRetry={fetchAll} />}

      {!loading && !error && resume && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1.5rem', alignItems: 'start' }}>
          {/* Left: Resume details */}
          <div>
            {/* Header */}
            <div className="card" style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
                <div style={{ width: 48, height: 48, borderRadius: 12, background: 'rgba(59,130,246,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <FileText size={24} style={{ color: '#60a5fa' }} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <h1 style={{ margin: '0 0 0.25rem', fontSize: '1.1rem', fontWeight: 700, wordBreak: 'break-all' }}>{resume.file_name}</h1>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', fontSize: '0.78rem', color: 'var(--color-text-dim)' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                      <Calendar size={12} /> {new Date(resume.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                      <User size={12} /> {resume.profiles.length} profile{resume.profiles.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                  {resume.file_hash && (
                    <p style={{ margin: '0.4rem 0 0', fontSize: '0.72rem', color: 'var(--color-text-dim)', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                      hash: {resume.file_hash}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Active Profile */}
            {activeProfile && (
              <div className="card" style={{ marginBottom: '1rem' }}>
                <h2 style={{ margin: '0 0 1rem', fontSize: '0.875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-dim)' }}>
                  Active Profile
                </h2>
                <div>
                  <div className="info-row">
                    <span className="info-label">Profile Name</span>
                    <span className="info-value">{activeProfile.profile_name}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Target Role</span>
                    <span className="info-value">{activeProfile.target_role}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Max Experience</span>
                    <span className="info-value">{activeProfile.max_experience_years} years</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Work Modes</span>
                    <div className="info-value" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {activeProfile.work_modes.map(m => <span key={m} className="badge badge-blue" style={{ textTransform: 'capitalize' }}>{m.replace('_', '-')}</span>)}
                    </div>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Locations</span>
                    <div className="info-value" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {activeProfile.target_locations.map(l => (
                        <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: '0.78rem', color: 'var(--color-text-dim)' }}>
                          <MapPin size={11} />{l}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="info-row" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
                    <span className="info-label" style={{ marginBottom: '0.5rem' }}>Skills ({activeProfile.skills.length})</span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {activeProfile.skills.map((s) => <span key={s} className="tag">{s}</span>)}
                    </div>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Extracted</span>
                    <span className="info-value">{new Date(activeProfile.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Full Profile Toggle */}
            <div className="card" style={{ marginBottom: '1rem' }}>
              <button
                className="btn btn-secondary"
                style={{ width: '100%', justifyContent: 'space-between' }}
                onClick={handleLoadProfile}
                disabled={profileLoading}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Eye size={15} /> {profileLoading ? 'Loading profile...' : 'View Full Structured Profile'}
                </span>
                {showProfile ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
              {profileError && <div style={{ marginTop: '0.75rem' }}><ErrorMessage message={profileError} /></div>}
              {showProfile && profileData && (
                <div style={{ marginTop: '1rem' }}>
                  <pre style={{
                    background: 'var(--color-bg)', borderRadius: 8, padding: '1rem',
                    fontSize: '0.75rem', color: '#94a3b8', overflow: 'auto', maxHeight: 400,
                    margin: 0, lineHeight: 1.6,
                  }}>
                    {JSON.stringify(profileData, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>

          {/* Right: Google Sheets */}
          <div style={{ position: 'sticky', top: 0 }}>
            <div className="card">
              <h2 style={{ margin: '0 0 1rem', fontSize: '0.875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-dim)' }}>
                Google Sheets
              </h2>

              {sheetStatus?.is_linked ? (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-success)', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.75rem' }}>
                    ✓ Sheet Connected
                  </div>
                  <div className="info-row">
                    <span className="info-label">Sheet ID</span>
                    <span className="info-value" style={{ fontSize: '0.72rem', wordBreak: 'break-all' }}>{sheetStatus.spreadsheet_id}</span>
                  </div>
                  {sheetResult && (
                    <div style={{ margin: '0.5rem 0' }}>
                      <p style={{ margin: '0 0 0.5rem', fontSize: '0.78rem', color: 'var(--color-text-dim)' }}>Tabs: {sheetResult.worksheets.join(' · ')}</p>
                    </div>
                  )}
                  <a
                    href={sheetStatus.spreadsheet_url!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-success"
                    style={{ width: '100%', justifyContent: 'center', marginTop: '0.75rem' }}
                  >
                    <ExternalLink size={15} /> Open Google Sheet
                  </a>
                </div>
              ) : (
                <div>
                  <p style={{ margin: '0 0 1rem', fontSize: '0.825rem', color: 'var(--color-text-dim)' }}>
                    No Google Sheet linked to this resume.
                  </p>
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    onClick={handleCreateSheet}
                    disabled={creatingSheet}
                  >
                    {creatingSheet ? (
                      <><span className="animate-spin" style={{ display: 'inline-block' }}>⟳</span> Creating...</>
                    ) : (
                      <><Plus size={15} /> Create Google Sheet</>
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
