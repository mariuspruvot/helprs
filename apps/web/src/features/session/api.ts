import { apiFetch } from '../../shared/api/client'
import type { SessionResponse } from './types'

export class SessionFetchError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'SessionFetchError'
    this.status = status
  }
}

export async function fetchSession(sessionId: string): Promise<SessionResponse> {
  const resp = await apiFetch(`/api/v1/sessions/${sessionId}`)
  if (!resp.ok) {
    throw new SessionFetchError(resp.status, `Failed to fetch session: ${resp.status}`)
  }
  // Wrap `resp.json()` so a malformed / truncated / empty body throws a
  // `SessionFetchError` the caller can classify, instead of a raw
  // `SyntaxError` that `useSession.retry` would blindly retry.
  try {
    return (await resp.json()) as SessionResponse
  } catch {
    throw new SessionFetchError(resp.status, 'Malformed session response body')
  }
}
