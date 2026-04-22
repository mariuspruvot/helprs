/**
 * API client for dashboard endpoints.
 */

import { apiFetch } from '../../shared/api/client'

export interface InstallationSummary {
  id: string
  github_installation_id: number
  account_login: string
  account_type: string
  repository_selection: string
  suspended_at: string | null
  created_at: string
  byok_configured: boolean
  byok_key_hint: string | null
  byok_key_status: string | null
  suppression_labels: string[]
  session_count: number
}

export interface InstallationListResponse {
  items: InstallationSummary[]
  total: number
}

export interface SessionSummary {
  id: string
  pr_number: number
  repo_full_name: string
  skill_name: string
  status: string
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export interface PaginatedSessionsResponse {
  items: SessionSummary[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

export async function fetchInstallations(): Promise<InstallationListResponse> {
  const resp = await apiFetch('/api/v1/installations')
  if (!resp.ok) throw new Error(`Failed to fetch installations: ${resp.status}`)
  return resp.json() as Promise<InstallationListResponse>
}

export interface DailyCount {
  date: string
  count: number
}

export interface StatusTotals {
  completed: number
  failed: number
  timeout: number
  total: number
}

export interface UserStats {
  daily_counts: DailyCount[]
  totals: StatusTotals
}

export async function fetchUserStats(): Promise<UserStats> {
  const resp = await apiFetch('/api/v1/auth/me/stats')
  if (!resp.ok) throw new Error(`Failed to fetch stats: ${resp.status}`)
  return resp.json() as Promise<UserStats>
}

export async function fetchInstallationSessions(
  installationId: number,
  page: number = 1,
  perPage: number = 20,
  status?: string,
): Promise<PaginatedSessionsResponse> {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  })
  if (status) params.set('status', status)

  const resp = await apiFetch(`/api/v1/installations/${installationId}/sessions?${params}`)
  if (!resp.ok) throw new Error(`Failed to fetch sessions: ${resp.status}`)
  return resp.json() as Promise<PaginatedSessionsResponse>
}

export async function deleteSession(sessionId: string): Promise<void> {
  const resp = await apiFetch(`/api/v1/containers/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  if (!resp.ok) throw new Error(`Failed to delete session: ${resp.status}`)
}
