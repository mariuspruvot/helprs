import { useAuthStore } from '../../features/auth/store'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

let isRefreshing = false
let refreshPromise: Promise<string | null> | null = null

async function refreshToken(): Promise<string | null> {
  const resp = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!resp.ok) return null
  const data = await resp.json() as { access_token: string }
  return data.access_token
}

async function handleTokenRefresh(): Promise<string | null> {
  if (isRefreshing && refreshPromise) {
    return refreshPromise
  }
  isRefreshing = true
  refreshPromise = refreshToken().finally(() => {
    isRefreshing = false
    refreshPromise = null
  })
  return refreshPromise
}

export async function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const { accessToken } = useAuthStore.getState()

  const headers = new Headers(options.headers)
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (resp.status === 401 && accessToken) {
    const newToken = await handleTokenRefresh()
    if (newToken) {
      useAuthStore.getState().login(newToken)
      headers.set('Authorization', `Bearer ${newToken}`)
      return fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
        credentials: 'include',
      })
    }

    // Refresh failed — force re-auth
    useAuthStore.getState().logout()
    window.location.href = `${API_BASE}/api/v1/auth/github`
  }

  return resp
}
