import { BrowserRouter, Routes, Route } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import OAuthCallback from './features/auth/OAuthCallback'
import ProtectedRoute from './features/auth/ProtectedRoute'
import SetupView from './features/installation/SetupView'
import SettingsView from './features/installation/SettingsView'
import ChatView from './features/session/ChatView'

// Module-level singleton so the cache survives re-renders of <App />.
const queryClient = new QueryClient()

function Home() {
  return (
    <div className="min-h-screen bg-primary text-text-primary font-mono flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-[38px] font-bold mb-4">helPRs</h1>
        <p className="text-text-secondary text-[16px]">
          Socratic comprehension sessions for pull requests
        </p>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/auth/callback" element={<OAuthCallback />} />
          <Route path="/installations/:installationId/setup" element={<ProtectedRoute><SetupView /></ProtectedRoute>} />
          <Route path="/installations/:installationId/settings" element={<ProtectedRoute><SettingsView /></ProtectedRoute>} />
          <Route path="/sessions/:sessionId" element={<ProtectedRoute><ChatView /></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
