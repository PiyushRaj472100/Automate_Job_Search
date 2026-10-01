import { useState, KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Zap, X, Plus, ChevronRight } from 'lucide-react';
import { discoveryApi } from '../api/discovery';
import type { SearchQuery, QueryGenerationRequest } from '../types/api';
import { Loading } from '../components/Loading';
import { ErrorMessage } from '../components/ErrorMessage';
import { useToast } from '../components/Toast';
import { getErrorMessage } from '../api/client';

const WORK_MODE_OPTIONS = ['remote', 'hybrid', 'on_site'];

interface TagInputProps {
  label: string;
  placeholder: string;
  values: string[];
  onChange: (v: string[]) => void;
}

function TagInput({ label, placeholder, values, onChange }: TagInputProps) {
  const [input, setInput] = useState('');

  const addTag = () => {
    const val = input.trim();
    if (val && !values.includes(val)) onChange([...values, val]);
    setInput('');
  };

  const removeTag = (i: number) => onChange(values.filter((_, idx) => idx !== i));

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag(); }
    if (e.key === 'Backspace' && !input && values.length) removeTag(values.length - 1);
  };

  return (
    <div style={{ marginBottom: '1rem' }}>
      <label className="input-label">{label}</label>
      <div className="tag-input-wrap" onClick={() => document.querySelector<HTMLInputElement>(`#input-${label}`)?.focus()}>
        {values.map((v, i) => (
          <span key={i} className="chip">
            {v}
            <span className="tag-remove" onClick={() => removeTag(i)}><X size={11} /></span>
          </span>
        ))}
        <input
          id={`input-${label}`}
          className="tag-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={addTag}
          placeholder={values.length ? '' : placeholder}
        />
      </div>
      <p style={{ margin: '0.25rem 0 0', fontSize: '0.72rem', color: 'var(--color-text-dim)' }}>Press Enter or comma to add</p>
    </div>
  );
}

export default function Discovery() {
  const navigate = useNavigate();
  const { showToast } = useToast();

  // Form state
  const [roles, setRoles] = useState<string[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [workModes, setWorkModes] = useState<string[]>(['remote']);
  const [maxQueries, setMaxQueries] = useState(5);

  // Generated queries
  const [queries, setQueries] = useState<SearchQuery[]>([]);
  const [generatingQueries, setGeneratingQueries] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);

  // Search
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const toggleWorkMode = (mode: string) => {
    setWorkModes((prev) => prev.includes(mode) ? prev.filter(m => m !== mode) : [...prev, mode]);
  };

  const handleGenerateQueries = async () => {
    if (roles.length === 0) { setQueryError('Please add at least one target role.'); return; }
    setQueryError(null);
    setGeneratingQueries(true);
    setQueries([]);
    try {
      const payload: QueryGenerationRequest = { target_roles: roles, skills, locations, work_modes: workModes, max_queries: maxQueries };
      const res = await discoveryApi.generateQueries(payload);
      setQueries(res.data);
      showToast(`Generated ${res.data.length} search queries`, 'success');
    } catch (e) {
      setQueryError(getErrorMessage(e));
    } finally {
      setGeneratingQueries(false);
    }
  };

  const handleSearch = async () => {
    if (queries.length === 0) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await discoveryApi.search({ queries, sources: null });
      // Store results in sessionStorage so Jobs page can read them
      sessionStorage.setItem('jobResults', JSON.stringify(res.data));
      showToast(`Found ${res.data.jobs.length} jobs!`, 'success');
      navigate('/jobs');
    } catch (e) {
      setSearchError(getErrorMessage(e));
    } finally {
      setSearching(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Job Discovery</h1>
          <p className="page-subtitle">Generate smart queries and search for matching jobs</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Search Form */}
        <div className="card">
          <h2 style={{ margin: '0 0 1.25rem', fontSize: '0.875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-dim)' }}>
            Search Parameters
          </h2>

          <TagInput label="Target Roles" placeholder="Backend Engineer, Python Developer…" values={roles} onChange={setRoles} />
          <TagInput label="Skills" placeholder="Python, FastAPI, SQL…" values={skills} onChange={setSkills} />
          <TagInput label="Locations" placeholder="Remote, Bangalore, Hyderabad…" values={locations} onChange={setLocations} />

          {/* Work Modes */}
          <div style={{ marginBottom: '1rem' }}>
            <label className="input-label">Work Modes</label>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {WORK_MODE_OPTIONS.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => toggleWorkMode(mode)}
                  style={{
                    padding: '0.4rem 0.85rem', borderRadius: 8, fontSize: '0.825rem', fontWeight: 500,
                    cursor: 'pointer', transition: 'all 0.15s', border: '1px solid',
                    background: workModes.includes(mode) ? 'rgba(59,130,246,0.15)' : 'var(--color-surface-2)',
                    borderColor: workModes.includes(mode) ? 'rgba(59,130,246,0.5)' : 'var(--color-border)',
                    color: workModes.includes(mode) ? '#60a5fa' : 'var(--color-text-dim)',
                  }}
                >
                  {mode.replace('_', '-')}
                </button>
              ))}
            </div>
          </div>

          {/* Max queries */}
          <div style={{ marginBottom: '1.25rem' }}>
            <label className="input-label">Maximum Queries</label>
            <input
              type="number"
              className="input"
              value={maxQueries}
              min={1}
              max={20}
              onChange={(e) => setMaxQueries(Number(e.target.value))}
              style={{ maxWidth: 120 }}
            />
          </div>

          {queryError && <div style={{ marginBottom: '1rem' }}><ErrorMessage message={queryError} /></div>}

          <button
            className="btn btn-primary"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={handleGenerateQueries}
            disabled={generatingQueries}
          >
            {generatingQueries ? (
              <><span className="animate-spin" style={{ display: 'inline-block' }}>⟳</span> Generating queries...</>
            ) : (
              <><Zap size={15} /> Generate Queries</>
            )}
          </button>
        </div>

        {/* Generated Queries */}
        <div>
          {generatingQueries && (
            <div className="card">
              <Loading message="Generating queries..." />
            </div>
          )}

          {!generatingQueries && queries.length > 0 && (
            <div className="card" style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <h2 style={{ margin: 0, fontSize: '0.875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-dim)' }}>
                  Generated Queries ({queries.length})
                </h2>
              </div>
              <div className="table-wrap" style={{ marginBottom: '1rem' }}>
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Query</th>
                      <th>Role</th>
                      <th>Location</th>
                      <th>Mode</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queries.map((q, i) => (
                      <tr key={i}>
                        <td style={{ color: 'var(--color-text-dim)', fontSize: '0.8rem' }}>{i + 1}</td>
                        <td style={{ fontWeight: 500, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{q.query_text}</td>
                        <td style={{ color: 'var(--color-text-dim)' }}>{q.role_title}</td>
                        <td style={{ color: 'var(--color-text-dim)' }}>{q.location ?? '—'}</td>
                        <td>
                          <span className={`badge ${q.work_mode === 'remote' ? 'badge-green' : q.work_mode === 'hybrid' ? 'badge-yellow' : 'badge-gray'}`} style={{ textTransform: 'capitalize' }}>
                            {q.work_mode?.replace('_', '-') ?? '—'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {searchError && <div style={{ marginBottom: '1rem' }}><ErrorMessage message={searchError} /></div>}

              <button
                className="btn btn-success"
                style={{ width: '100%', justifyContent: 'center', padding: '0.75rem' }}
                onClick={handleSearch}
                disabled={searching}
              >
                {searching ? (
                  <><span className="animate-spin" style={{ display: 'inline-block' }}>⟳</span> Searching Jobs...</>
                ) : (
                  <><Search size={16} /> Search Jobs</>
                )}
              </button>
            </div>
          )}

          {!generatingQueries && queries.length === 0 && (
            <div className="card">
              <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                <div className="empty-state-icon">🔍</div>
                <h3>Ready to search</h3>
                <p>Fill in the form and generate queries to find matching jobs.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
