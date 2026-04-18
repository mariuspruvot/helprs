import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import { useAuthStore } from './features/auth/store'
import OAuthCallback from './features/auth/OAuthCallback'
import ProtectedRoute from './features/auth/ProtectedRoute'
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
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AuthRedirect />} />
        <Route path="/auth/callback" element={<OAuthCallback />} />
        <Route path="/installations" element={<ProtectedRoute><InstallationList /></ProtectedRoute>} />
        <Route path="/installations/:installationId" element={<ProtectedRoute><InstallationDetail /></ProtectedRoute>} />
        <Route path="/installations/:installationId/sessions/:sessionId" element={<ProtectedRoute><SessionReplay /></ProtectedRoute>} />
        <Route path="/installations/:installationId/setup" element={<ProtectedRoute><SetupView /></ProtectedRoute>} />
        <Route path="/installations/:installationId/settings" element={<ProtectedRoute><SettingsView /></ProtectedRoute>} />
        <Route path="/session/:installationId/*" element={<ProtectedRoute><SessionView /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  )
}
