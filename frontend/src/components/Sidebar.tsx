import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, FileText, Search, Briefcase,
  Sheet, Activity, Brain, Menu, X, ChevronRight,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/dashboard', icon: <LayoutDashboard size={16} />, label: 'Dashboard' },
  { to: '/resumes', icon: <FileText size={16} />, label: 'Resumes' },
  { to: '/discovery', icon: <Search size={16} />, label: 'Job Discovery' },
  { to: '/jobs', icon: <Briefcase size={16} />, label: 'Job Results' },
  { to: '/sheets', icon: <Sheet size={16} />, label: 'Google Sheets' },
  { to: '/system-status', icon: <Activity size={16} />, label: 'System Status' },
];

interface SidebarProps {
  mobileOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ mobileOpen, onClose }: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      <div
        className={`sidebar-overlay ${mobileOpen ? 'visible' : ''}`}
        onClick={onClose}
      />
      <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
        {/* Logo */}
        <div style={{ padding: '1.25rem 1rem 1rem', borderBottom: '1px solid var(--color-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Brain size={17} style={{ color: 'white' }} />
            </div>
            <div>
              <p style={{ margin: 0, fontSize: '0.8rem', fontWeight: 700, color: 'var(--color-text)' }}>Job Intelligence</p>
              <p style={{ margin: 0, fontSize: '0.65rem', color: 'var(--color-text-dim)' }}>Personal Platform</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '0.75rem 0.5rem' }}>
          <p className="section-label">Navigation</p>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              onClick={onClose}
            >
              {item.icon}
              <span style={{ flex: 1 }}>{item.label}</span>
              <ChevronRight size={12} style={{ opacity: 0.4 }} />
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div style={{ padding: '0.75rem 1rem', borderTop: '1px solid var(--color-border)', fontSize: '0.72rem', color: 'var(--color-text-dim)' }}>
          Backend: <span style={{ color: 'var(--color-accent)' }}>localhost:8001</span>
        </div>
      </aside>
    </>
  );
}

export function MobileTopBar({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <div className="mobile-topbar">
      <button
        onClick={onMenuClick}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text)', display: 'flex', alignItems: 'center' }}
      >
        <Menu size={20} />
      </button>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <Brain size={16} style={{ color: '#60a5fa' }} />
        <span style={{ fontWeight: 700, fontSize: '0.875rem' }}>Job Intelligence</span>
      </div>
    </div>
  );
}
