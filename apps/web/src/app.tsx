import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import { useAuthStore } from './features/auth/store'
import OAuthCallback from './features/auth/OAuthCallback'
import ProtectedRoute from './features/auth/ProtectedRoute'
import { AppShell, ErrorBoundary } from './shared/components'
import InstallationList from './features/dashboard/InstallationList'
import InstallationDetail from './features/dashboard/InstallationDetail'
import SessionReplay from './features/dashboard/SessionReplay'
import SetupView from './features/installation/SetupView'
import SettingsView from './features/installation/SettingsView'
import SessionView from './features/session/SessionView'
import LandingPage from './features/landing/LandingPage'

function AuthRedirect() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (isAuthenticated) return <Navigate to="/installations" replace />
  return <LandingPage />
}

export default function App() {
  return (
    <ErrorBoundary>
    <BrowserRouter>
      <Routes>
        {/* Public routes — no shell */}
        <Route path="/" element={<AuthRedirect />} />
        <Route path="/auth/callback" element={<OAuthCallback />} />

        {/* Protected routes — wrapped in AppShell */}
        <Route path="/installations" element={<ProtectedRoute><AppShell><InstallationList /></AppShell></ProtectedRoute>} />
        <Route path="/installations/:installationId" element={<ProtectedRoute><AppShell><InstallationDetail /></AppShell></ProtectedRoute>} />
        <Route path="/installations/:installationId/sessions/:sessionId" element={<ProtectedRoute><SessionReplay /></ProtectedRoute>} />
        <Route path="/installations/:installationId/setup" element={<ProtectedRoute><AppShell><SetupView /></AppShell></ProtectedRoute>} />
        <Route path="/installations/:installationId/settings" element={<ProtectedRoute><AppShell><SettingsView /></AppShell></ProtectedRoute>} />
        <Route path="/session/:installationId/*" element={<ProtectedRoute><SessionView /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
    </ErrorBoundary>
  )
}
