import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { useAuthStore } from './store'
import { apiFetch } from '../../shared/api/client'

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
        const destination = returnUrl ?? '/'
        setReturnUrl(null)
        navigate(destination, { replace: true })
      })
      .catch(() => {
        navigate('/', { replace: true })
      })
  }, [searchParams, login, setUser, navigate, returnUrl, setReturnUrl])

  return (
    <div className="min-h-screen bg-primary text-text-primary flex items-center justify-center">
      <p className="text-text-secondary">Authenticating...</p>
    </div>
  )
}
