/**
 * InstallationDetail — session history for a single installation.
 * Matches R2 redesign: completion bar, grid table, filter buttons.
 */

import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router'
import { fetchInstallationSessions } from './dashboardApi'
import type { PaginatedSessionsResponse } from './dashboardApi'
import { formatDuration, formatRelativeTime } from './formatters'
import { Button, Chip, Dot, Overline } from '../../shared/components'

const STATUS_OPTIONS = ['all', 'completed', 'failed', 'running', 'pending', 'timeout'] as const

export default function InstallationDetail() {
  const { installationId } = useParams<{ installationId: string }>()
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<PaginatedSessionsResponse['items']>([])
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
      const data = await fetchInstallationSessions(
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

  // Completion stats from loaded sessions (approximation from current page)
  const completed = sessions.filter((s) => s.status === 'completed').length
  const failed = sessions.filter((s) => s.status === 'failed').length
  const timeout = sessions.filter((s) => s.status === 'timeout').length
  const completionPct = total > 0 ? Math.round((completed / Math.max(sessions.length, 1)) * 100) : 0

  return (
    <div className="flex flex-col h-[calc(100vh-56px)]">
      {/* Sticky header + filters */}
      <div className="shrink-0 flex justify-between items-end mb-5">
        <div>
          <Overline className="mb-1.5">{'\u25b8'} SESSIONS {'\u00b7'} {total} TOTAL</Overline>
          <h1 className="font-mono text-2xl font-bold tracking-[-0.02em]">Session History</h1>
          <p className="font-mono text-sm text-dim mt-1">// every time Claude ran against one of your PRs</p>
        </div>
        <div className="flex gap-2">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt}
              onClick={() => handleStatusChange(opt)}
              className={`font-mono text-[13px] font-medium px-4 py-2 rounded-[7px] border transition-colors cursor-pointer ${
                statusFilter === opt
                  ? 'bg-accent/15 border-accent/30 text-accent'
                  : 'bg-card border-rule-str text-ink hover:bg-card-hi'
              }`}
            >
              {opt === 'all' ? 'Status: all' : opt.charAt(0).toUpperCase() + opt.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Completion bar */}
      {!loading && sessions.length > 0 && (
        <div className="shrink-0 flex items-center gap-5 px-4 py-3.5 bg-card border border-rule rounded-card mb-5">
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono text-[22px] font-bold">{completionPct}%</span>
            <span className="font-mono text-[10px] text-dim tracking-[0.12em] uppercase">completion</span>
          </div>
          <div className="flex-1 h-1.5 bg-bg2 rounded-full flex gap-0.5 overflow-hidden">
            {completed > 0 && <div className="bg-ok" style={{ flex: completed }} />}
            {timeout > 0 && <div className="bg-warn" style={{ flex: timeout }} />}
            {failed > 0 && <div className="bg-danger" style={{ flex: failed }} />}
          </div>
          <div className="flex gap-4 font-mono text-[11px] text-dim">
            <span><Dot color="ok" className="mr-1" />{completed} done</span>
            <span><Dot color="warn" className="mr-1" />{timeout} timeout</span>
            <span><Dot color="danger" className="mr-1" />{failed} failed</span>
          </div>
        </div>
      )}

      {/* Scrollable content */}
      <div className="flex-1 min-h-0 overflow-y-auto">

      {/* Error */}
      {error && (
        <div className="mb-4 px-4 py-3 bg-danger/8 border border-danger/20 rounded-card text-danger text-sm">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-dim text-sm py-12 text-center font-mono">
          <Dot pulse className="mr-2" /> Loading sessions...
        </div>
      )}

      {/* Empty */}
      {!loading && !error && sessions.length === 0 && (
        <div className="text-center py-12 bg-card border border-rule rounded-card">
          <p className="text-ink2 text-sm">
            {statusFilter === 'all' ? 'No sessions yet.' : `No ${statusFilter} sessions.`}
          </p>
        </div>
      )}

      {/* Session table */}
      {!loading && sessions.length > 0 && (
        <>
          <div className="border border-rule-str rounded-card overflow-hidden">
            {/* Header row */}
            <div
              className="grid bg-bg2 px-4 py-2.5 font-mono text-[10px] text-dim tracking-[0.18em] uppercase border-b border-rule"
              style={{ gridTemplateColumns: '36px 1fr 140px 110px 80px 80px' }}
            >
              <span>#</span>
              <span>REPO / PR</span>
              <span>SKILL</span>
              <span>STATUS</span>
              <span className="text-right">DURATION</span>
              <span className="text-right">RAN</span>
            </div>

            {/* Data rows */}
            {sessions.map((session, idx) => {
              const statusColor =
                session.status === 'completed' ? 'ok' as const :
                session.status === 'timeout' ? 'warn' as const :
                session.status === 'failed' ? 'danger' as const :
                'default' as const

              return (
                <button
                  key={session.id}
                  onClick={() => navigate(`/installations/${installationId}/sessions/${session.id}`)}
                  className={`w-full grid items-center px-4 py-3 text-[13px] transition-colors cursor-pointer hover:bg-card-hi ${
                    idx < sessions.length - 1 ? 'border-b border-rule' : ''
                  }`}
                  style={{ gridTemplateColumns: '36px 1fr 140px 110px 80px 80px' }}
                >
                  <span className="font-mono text-[11px] text-dim2">
                    {String(idx + 1 + (page - 1) * 20).padStart(2, '0')}
                  </span>
                  <span className="font-mono text-ink truncate">
                    {session.repo_full_name} <span className="text-accent">#{session.pr_number}</span>
                  </span>
                  <span><Chip variant="accent">{session.skill_name}</Chip></span>
                  <span><Chip variant={statusColor}>{session.status}</Chip></span>
                  <span className="font-mono text-xs text-ink2 text-right">
                    {formatDuration(session.started_at, session.completed_at)}
                  </span>
                  <span className="font-mono text-xs text-dim text-right">
                    {formatRelativeTime(session.created_at)}
                  </span>
                </button>
              )
            })}
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

      </div>{/* end scrollable */}
    </div>
  )
}
