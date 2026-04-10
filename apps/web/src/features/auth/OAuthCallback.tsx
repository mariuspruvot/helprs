import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { useAuthStore } from './store'
import { apiFetch } from '../../shared/api/client'
import { RETURN_URL_STORAGE_KEY } from './ProtectedRoute'

function readPersistedReturnUrl(): string | null {
  try {
    return sessionStorage.getItem(RETURN_URL_STORAGE_KEY)
  } catch {
    return null
  }
}

function clearPersistedReturnUrl() {
  try {
    sessionStorage.removeItem(RETURN_URL_STORAGE_KEY)
  } catch {
    // noop — same fallback policy as write site.
  }
}

export default function OAuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { login, setUser, returnUrl, setReturnUrl } = useAuthStore()
  const processed = useRef(false)

  useEffect(() => {
    if (processed.current) return
    processed.current = true

    const token = searchParams.get('access_token')
    if (!token) {
      navigate('/', { replace: true })
      return
    }

    login(token)

    apiFetch('/api/v1/auth/me')
      .then((resp) => {
        if (!resp.ok) throw new Error('Failed to fetch user')
        return resp.json()
      })
      .then((user) => {
        setUser(user)
        // The in-memory store was wiped by the OAuth full-page round-trip,
        // so fall back to sessionStorage (persisted by ProtectedRoute).
        const destination = returnUrl ?? readPersistedReturnUrl() ?? '/'
        setReturnUrl(null)
        clearPersistedReturnUrl()
        navigate(destination, { replace: true })
      })
      .catch(() => {
        clearPersistedReturnUrl()
        navigate('/', { replace: true })
      })
  }, [searchParams, login, setUser, navigate, returnUrl, setReturnUrl])

  return (
    <div className="min-h-screen bg-primary text-text-primary flex items-center justify-center">
      <p className="text-text-secondary">Authenticating...</p>
    </div>
  )
}
