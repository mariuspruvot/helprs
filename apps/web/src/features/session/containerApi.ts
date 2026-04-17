/**
 * API client functions for container session endpoints.
 */

import { apiFetch, API_BASE } from '../../shared/api/client'
import type {
  ContainerSessionRequest,
  ContainerSessionResponse,
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
): Promise<ContainerSessionResponse> {
  const resp = await apiFetch('/api/v1/containers/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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

/**
 * Build the SSE stream URL for a container session.
 * Auth token is appended as a query parameter since EventSource cannot send headers.
 */
export function buildStreamUrl(sessionId: string, accessToken: string): string {
  return `${API_BASE}/api/v1/containers/sessions/${sessionId}/stream?access_token=${encodeURIComponent(accessToken)}`
}
