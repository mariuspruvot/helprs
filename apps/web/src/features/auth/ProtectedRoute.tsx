import type { ReactNode } from 'react'
import { useEffect } from 'react'
import { useAuthStore } from './store'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

interface ProtectedRouteProps {
  children: ReactNode
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, setReturnUrl } = useAuthStore()

  useEffect(() => {
    if (!isAuthenticated) {
      setReturnUrl(window.location.pathname)
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
