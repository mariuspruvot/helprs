import type { ReactNode } from 'react'
import { useEffect } from 'react'
import { useAuthStore } from './store'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// The OAuth handshake is a full-page round-trip (app → GitHub.com → app),
// which wipes the in-memory Zustand store. sessionStorage survives the reload
// and is scoped to the tab, so it's the right place for a short-lived
// returnUrl. Keep the store field in sync for components that read it live.
export const RETURN_URL_STORAGE_KEY = 'helprs.returnUrl'

interface ProtectedRouteProps {
  children: ReactNode
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, setReturnUrl } = useAuthStore()

  useEffect(() => {
    if (!isAuthenticated) {
      const target = window.location.pathname + window.location.search
      setReturnUrl(target)
      try {
        sessionStorage.setItem(RETURN_URL_STORAGE_KEY, target)
      } catch {
        // sessionStorage disabled (private mode, quota) — fall back to '/'
        // on return; the store field is already set for same-tab reads.
      }
      window.location.href = `${API_BASE}/api/v1/auth/github`
    }
  }, [isAuthenticated, setReturnUrl])

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-primary text-text-primary flex items-center justify-center">
        <p className="text-text-secondary">Redirecting to login...</p>
      </div>
    )
  }

  return <>{children}</>
}
