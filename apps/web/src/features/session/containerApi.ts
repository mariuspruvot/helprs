/**
 * API client functions for container session endpoints.
 */

import { apiFetch, API_BASE } from '../../shared/api/client'
import type {
  ContainerSessionRequest,
  ContainerSessionResponse,
  SessionEventsListResponse,
  StopSessionResponse,
} from './containerTypes'

export class ContainerSessionError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ContainerSessionError'
    this.status = status
  }
}

export async function createContainerSession(
  body: ContainerSessionRequest,
  signal?: AbortSignal,
): Promise<ContainerSessionResponse> {
  const resp = await apiFetch('/api/v1/containers/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!resp.ok) {
    throw new ContainerSessionError(resp.status, `Failed to create session: ${resp.status}`)
  }
  try {
    return (await resp.json()) as ContainerSessionResponse
  } catch {
    throw new ContainerSessionError(resp.status, 'Malformed session response body')
  }
}

export async function stopContainerSession(sessionId: string): Promise<StopSessionResponse> {
  const resp = await apiFetch(`/api/v1/containers/sessions/${sessionId}/stop`, {
    method: 'POST',
  })
  if (!resp.ok) {
    throw new ContainerSessionError(resp.status, `Failed to stop session: ${resp.status}`)
  }
  try {
    return (await resp.json()) as StopSessionResponse
  } catch {
    throw new ContainerSessionError(resp.status, 'Malformed stop response body')
  }
}

export async function getContainerSession(sessionId: string): Promise<ContainerSessionResponse> {
  const resp = await apiFetch(`/api/v1/containers/sessions/${sessionId}`)
  if (!resp.ok) {
    throw new ContainerSessionError(resp.status, `Failed to fetch session: ${resp.status}`)
  }
  try {
    return (await resp.json()) as ContainerSessionResponse
  } catch {
    throw new ContainerSessionError(resp.status, 'Malformed session response body')
  }
}

/**
 * Build the SSE stream URL for a container session.
 * Auth token is appended as a query parameter since EventSource cannot send headers.
 */
export async function sendMessage(sessionId: string, content: string): Promise<void> {
  const resp = await apiFetch(`/api/v1/containers/sessions/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!resp.ok) {
    throw new ContainerSessionError(resp.status, `Failed to send message: ${resp.status}`)
  }
}

export async function getSessionEvents(sessionId: string): Promise<SessionEventsListResponse> {
  const resp = await apiFetch(`/api/v1/containers/sessions/${sessionId}/events`)
  if (!resp.ok) {
    throw new ContainerSessionError(resp.status, `Failed to fetch session events: ${resp.status}`)
  }
  try {
    return (await resp.json()) as SessionEventsListResponse
  } catch {
    throw new ContainerSessionError(resp.status, 'Malformed events response body')
  }
}

/**
 * Build the SSE stream URL for a container session.
 * Auth token is appended as a query parameter since EventSource cannot send headers.
 * Optional `offset` skips already-received events on reconnect.
 */
export interface ScorecardResponse {
  skill: string
  version: number
  dimensions: Record<string, number>
  summary: string
  questions_asked?: number
  questions_answered?: number
  highlights?: string[]
}

export async function fetchScorecard(sessionId: string): Promise<ScorecardResponse | null> {
  const resp = await apiFetch(`/api/v1/containers/sessions/${sessionId}/scorecard`)
  if (!resp.ok) {
    if (resp.status === 404) return null
    throw new ContainerSessionError(resp.status, `Failed to fetch scorecard: ${resp.status}`)
  }
  try {
    const data = (await resp.json()) as Record<string, unknown>
    // The API returns {session_id, scorecard, xp_earned} — extract the nested scorecard
    const scorecard = (data.scorecard ?? data) as ScorecardResponse
    if (!scorecard.dimensions || !scorecard.skill) return null
    return scorecard
  } catch {
    return null
  }
}

export function buildStreamUrl(sessionId: string, accessToken: string, offset?: number): string {
  let url = `${API_BASE}/api/v1/containers/sessions/${sessionId}/stream?access_token=${encodeURIComponent(accessToken)}`
  if (offset && offset > 0) {
    url += `&offset=${offset}`
  }
  return url
}
