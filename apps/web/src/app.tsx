import { BrowserRouter, Routes, Route } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import OAuthCallback from './features/auth/OAuthCallback'
import ProtectedRoute from './features/auth/ProtectedRoute'
import SetupView from './features/installation/SetupView'
import SettingsView from './features/installation/SettingsView'
import ChatView from './features/session/ChatView'
import LandingPage from './features/landing/LandingPage'

// Module-level singleton so the cache survives re-renders of <App />.
const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth/callback" element={<OAuthCallback />} />
          <Route path="/installations/:installationId/setup" element={<ProtectedRoute><SetupView /></ProtectedRoute>} />
          <Route path="/installations/:installationId/settings" element={<ProtectedRoute><SettingsView /></ProtectedRoute>} />
          <Route path="/sessions/:sessionId" element={<ProtectedRoute><ChatView /></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
