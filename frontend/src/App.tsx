import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Sidebar, MobileTopBar } from './components/Sidebar';
import { ToastProvider } from './components/Toast';
import Dashboard from './pages/Dashboard';
import Resumes from './pages/Resumes';
import ResumeDetails from './pages/ResumeDetails';
import Discovery from './pages/Discovery';
import Jobs from './pages/Jobs';
import GoogleSheets from './pages/GoogleSheets';
import SystemStatus from './pages/SystemStatus';
import './index.css';

function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="app-layout" style={{ flexDirection: 'column' }}>
      {/* Mobile top bar */}
      <MobileTopBar onMenuClick={() => setSidebarOpen(true)} />

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar mobileOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/resumes" element={<Resumes />} />
            <Route path="/resumes/:id" element={<ResumeDetails />} />
            <Route path="/discovery" element={<Discovery />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/sheets" element={<GoogleSheets />} />
            <Route path="/system-status" element={<SystemStatus />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppLayout />
      </ToastProvider>
    </BrowserRouter>
  );
}
