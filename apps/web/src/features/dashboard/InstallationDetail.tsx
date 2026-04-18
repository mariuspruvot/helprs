/**
 * InstallationDetail — session history list for a single installation.
 */

import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router'
import { fetchInstallationSessions } from './dashboardApi'
import type { SessionSummary, PaginatedSessionsResponse } from './dashboardApi'
import StatusBadge from './StatusBadge'
import { formatDuration, formatRelativeTime } from './formatters'

const STATUS_OPTIONS = ['all', 'completed', 'failed', 'running', 'pending', 'timeout'] as const

export default function InstallationDetail() {
  const { installationId } = useParams<{ installationId: string }>()
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [total, setTotal] = useState(0)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!installationId) return
    setLoading(true)
    setError(null)
    try {
      const data: PaginatedSessionsResponse = await fetchInstallationSessions(
        Number(installationId),
        page,
        20,
        statusFilter === 'all' ? undefined : statusFilter,
      )
      setSessions(data.items)
      setTotalPages(data.total_pages)
      setTotal(data.total)
    } catch {
      setError('Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }, [installationId, page, statusFilter])

  useEffect(() => { load() }, [load])

  const handleStatusChange = (value: string) => {
    setStatusFilter(value)
    setPage(1)
  }

  return (
    <div className="min-h-screen bg-primary text-text-primary">
      {/* Header */}
      <div
        className="h-14 flex items-center px-6 gap-4 border-b"
        style={{ borderColor: 'rgba(255, 255, 255, 0.06)' }}
      >
        <Link
          to="/installations"
          className="text-text-secondary text-[13px] hover:text-text-primary transition-colors"
        >
          &larr; Installations
        </Link>
        <span className="text-text-muted text-[12px]">|</span>
        <span className="text-text-primary text-[14px] font-sans font-medium">
          Installation #{installationId}
        </span>
        <div className="ml-auto flex items-center gap-3">
          <Link
            to={`/installations/${installationId}/settings`}
            className="text-text-secondary text-[12px] font-sans hover:text-text-primary transition-colors"
          >
            Settings
          </Link>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-[20px] font-sans font-semibold">
            Session History
            {!loading && (
              <span className="text-text-muted text-[14px] font-normal ml-2">
                ({total})
              </span>
            )}
          </h1>

          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="text-[13px] font-sans px-3 py-1.5 rounded-lg cursor-pointer outline-none"
            style={{
              background: 'rgba(255, 255, 255, 0.04)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#fdfcfc',
            }}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt} value={opt} style={{ background: '#302c2c' }}>
                {opt.charAt(0).toUpperCase() + opt.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <div
            className="text-[13px] px-4 py-3 rounded-lg mb-6"
            style={{ background: 'rgba(255, 59, 48, 0.08)', color: '#ff6961' }}
          >
            {error}
          </div>
        )}

        {loading && (
          <div className="text-text-muted text-[14px] font-sans py-12 text-center">
            Loading...
          </div>
        )}

        {!loading && !error && sessions.length === 0 && (
          <div
            className="rounded-xl px-6 py-12 text-center"
            style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <p className="text-text-secondary text-[14px] font-sans">
              {statusFilter === 'all' ? 'No sessions yet.' : `No ${statusFilter} sessions.`}
            </p>
          </div>
        )}

        {!loading && sessions.length > 0 && (
          <>
            {/* Session list */}
            <div
              className="rounded-xl overflow-hidden"
              style={{ border: '1px solid rgba(255, 255, 255, 0.06)' }}
            >
              {sessions.map((session, idx) => (
                <button
                  key={session.id}
                  onClick={() => navigate(`/installations/${installationId}/sessions/${session.id}`)}
                  className="w-full text-left px-5 py-3.5 flex items-center gap-4 transition-colors cursor-pointer"
                  style={{
                    background: idx % 2 === 0 ? 'rgba(255, 255, 255, 0.02)' : 'transparent',
                    borderBottom: idx < sessions.length - 1 ? '1px solid rgba(255, 255, 255, 0.04)' : undefined,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)' }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = idx % 2 === 0 ? 'rgba(255, 255, 255, 0.02)' : 'transparent'
                  }}
                >
                  {/* Repo + PR */}
                  <div className="flex-1 min-w-0">
                    <span className="text-text-primary text-[13px] font-sans">
                      {session.repo_full_name}
                    </span>
                    <span className="text-text-muted text-[12px] ml-1.5">
                      #{session.pr_number}
                    </span>
                  </div>

                  {/* Skill */}
                  <span
                    className="text-[11px] px-2 py-0.5 rounded-full font-mono shrink-0"
                    style={{
                      color: '#E2A039',
                      background: 'rgba(226, 160, 57, 0.1)',
                    }}
                  >
                    {session.skill_name}
                  </span>

                  {/* Status */}
                  <div className="shrink-0 w-20 text-center">
                    <StatusBadge status={session.status} />
                  </div>

                  {/* Duration */}
                  <span className="text-text-muted text-[12px] font-mono shrink-0 w-16 text-right">
                    {formatDuration(session.started_at, session.completed_at)}
                  </span>

                  {/* Time ago */}
                  <span className="text-text-muted text-[12px] font-sans shrink-0 w-16 text-right">
                    {formatRelativeTime(session.created_at)}
                  </span>
                </button>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-4 mt-6">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="text-[13px] font-sans px-3 py-1.5 rounded-lg transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-default"
                  style={{
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                  }}
                >
                  Previous
                </button>
                <span className="text-text-muted text-[13px] font-sans">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="text-[13px] font-sans px-3 py-1.5 rounded-lg transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-default"
                  style={{
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                  }}
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
