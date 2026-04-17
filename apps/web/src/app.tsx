import { BrowserRouter, Routes, Route } from 'react-router'
import OAuthCallback from './features/auth/OAuthCallback'
import ProtectedRoute from './features/auth/ProtectedRoute'
import SetupView from './features/installation/SetupView'
import SettingsView from './features/installation/SettingsView'
import SessionView from './features/session/SessionView'
import LandingPage from './features/landing/LandingPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/auth/callback" element={<OAuthCallback />} />
        <Route path="/installations/:installationId/setup" element={<ProtectedRoute><SetupView /></ProtectedRoute>} />
        <Route path="/installations/:installationId/settings" element={<ProtectedRoute><SettingsView /></ProtectedRoute>} />
        <Route path="/session/:installationId/*" element={<ProtectedRoute><SessionView /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  )
}
