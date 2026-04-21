/**
 * InstallationDetail — session history list for a single installation.
 */

import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router'
import { fetchInstallationSessions } from './dashboardApi'
import type { SessionSummary, PaginatedSessionsResponse } from './dashboardApi'
import StatusBadge from './StatusBadge'
import { formatDuration, formatRelativeTime } from './formatters'
import { Button, Card, Chip, Dot, Overline } from '../../shared/components'

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
    <div>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 mb-6 text-sm">
        <Link to="/installations" className="text-dim hover:text-ink2 transition-colors font-mono">
          &larr; Installations
        </Link>
        <span className="text-dim2">|</span>
        <span className="text-ink font-mono font-medium">
          Installation #{installationId}
        </span>
        <div className="ml-auto">
          <Link
            to={`/installations/${installationId}/settings`}
            className="text-dim text-xs font-mono hover:text-ink2 transition-colors"
          >
            Settings
          </Link>
        </div>
      </div>

      {/* Title + filter */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-mono text-lg font-bold">
            Session History
            {!loading && (
              <span className="text-dim text-sm font-normal ml-2">({total})</span>
            )}
          </h1>
          <Overline className="mt-1">// every time Claude ran against one of your PRs</Overline>
        </div>

        <select
          value={statusFilter}
          onChange={(e) => handleStatusChange(e.target.value)}
          className="font-mono text-xs px-3 py-1.5 rounded-button bg-card border border-rule text-ink cursor-pointer outline-none"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt} value={opt} className="bg-card">
              {opt.charAt(0).toUpperCase() + opt.slice(1)}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <Card className="mb-6 border-danger/30">
          <p className="text-danger text-sm">{error}</p>
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-dim text-sm py-12 text-center font-mono">
          <Dot pulse className="mr-2" /> Loading sessions...
        </div>
      )}

      {/* Empty */}
      {!loading && !error && sessions.length === 0 && (
        <Card className="text-center py-12">
          <p className="text-ink2 text-sm">
            {statusFilter === 'all' ? 'No sessions yet.' : `No ${statusFilter} sessions.`}
          </p>
        </Card>
      )}

      {/* Session table */}
      {!loading && sessions.length > 0 && (
        <>
          <div className="rounded-card border border-rule overflow-hidden">
            {sessions.map((session, idx) => (
              <button
                key={session.id}
                onClick={() => navigate(`/installations/${installationId}/sessions/${session.id}`)}
                className={`w-full text-left px-5 py-3.5 flex items-center gap-4 transition-colors cursor-pointer hover:bg-card-hi ${idx % 2 === 0 ? 'bg-card/50' : 'bg-transparent'} ${idx < sessions.length - 1 ? 'border-b border-rule/50' : ''}`}
              >
                <div className="flex-1 min-w-0">
                  <span className="text-ink text-[13px]">{session.repo_full_name}</span>
                  <span className="text-dim text-xs ml-1.5">#{session.pr_number}</span>
                </div>
                <Chip variant="accent">{session.skill_name}</Chip>
                <div className="shrink-0 w-20 text-center">
                  <StatusBadge status={session.status} />
                </div>
                <span className="text-dim text-xs font-mono shrink-0 w-16 text-right">
                  {formatDuration(session.started_at, session.completed_at)}
                </span>
                <span className="text-dim text-xs shrink-0 w-16 text-right">
                  {formatRelativeTime(session.created_at)}
                </span>
              </button>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-4 mt-6">
              <Button
                variant="secondary"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="text-xs"
              >
                Previous
              </Button>
              <span className="text-dim text-xs font-mono">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="secondary"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="text-xs"
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
