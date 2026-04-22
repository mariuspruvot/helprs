/**
 * InstallationDetail — session history for a single installation.
 * Responsive layout: adapts table and header to screen size.
 */

import { useState, useEffect, useCallback } from 'react'
import { Link, useParams, useNavigate } from 'react-router'
import { deleteSession, fetchInstallationSessions } from './dashboardApi'
import type { PaginatedSessionsResponse } from './dashboardApi'
import { formatDuration, formatRelativeTime } from './formatters'
import { Button, Card, Chip, Dot, Overline } from '../../shared/components'

const STATUS_OPTIONS = ['all', 'completed', 'failed', 'running', 'pending', 'timeout'] as const
const COL_TEMPLATE = 'minmax(24px, 32px) minmax(120px, 1fr) minmax(90px, 130px) minmax(80px, 110px) minmax(56px, 80px) minmax(56px, 80px) 28px'

// Approximate row height (py-2.5 + text) — used to size the page to available height.
const ROW_HEIGHT_PX = 40
// Space consumed by header, completion bar, table header, pagination, etc.
const CHROME_HEIGHT_PX = 320
const MIN_PER_PAGE = 10
const MAX_PER_PAGE = 40

function computePerPage(viewportHeight: number): number {
  const rows = Math.floor((viewportHeight - CHROME_HEIGHT_PX) / ROW_HEIGHT_PX)
  return Math.max(MIN_PER_PAGE, Math.min(MAX_PER_PAGE, rows))
}

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
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; label: string } | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [perPage, setPerPage] = useState(() =>
    typeof window === 'undefined' ? MIN_PER_PAGE : computePerPage(window.innerHeight),
  )

  useEffect(() => {
    const update = () => {
      const next = computePerPage(window.innerHeight)
      setPerPage((prev) => (prev === next ? prev : next))
    }
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  // Reset to first page when per-page changes so we don't land on an out-of-range page.
  useEffect(() => { setPage(1) }, [perPage])

  const load = useCallback(async () => {
    if (!installationId) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchInstallationSessions(
        Number(installationId),
        page,
        perPage,
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
  }, [installationId, page, perPage, statusFilter])

  useEffect(() => { load() }, [load])

  const handleStatusChange = (value: string) => {
    setStatusFilter(value)
    setPage(1)
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteSession(deleteTarget.id)
      setSessions((prev) => prev.filter((s) => s.id !== deleteTarget.id))
      setTotal((prev) => prev - 1)
    } catch {
      // silently ignore
    } finally {
      setDeleting(false)
      setDeleteTarget(null)
    }
  }

  const completed = sessions.filter((s) => s.status === 'completed').length
  const failed = sessions.filter((s) => s.status === 'failed').length
  const timeout = sessions.filter((s) => s.status === 'timeout').length
  const completionPct = total > 0 ? Math.round((completed / Math.max(sessions.length, 1)) * 100) : 0

  return (
    <>
    <div className="flex flex-col h-full">
      {/* Breadcrumb + settings — pinned to the very top */}
      <div className="shrink-0 flex items-center justify-between gap-3 mb-3">
        <Overline>
          <Link to="/installations" className="hover:text-ink2 transition-colors">installations</Link>
          {' '}{'\u00b7'}{' '}
          <span className="text-ink2">history</span>
          {' '}{'\u00b7'}{' '}
          {total} total
        </Overline>
        <Link
          to={`/installations/${installationId}/settings`}
          className="font-mono text-[11px] lg:text-[12px] font-medium px-2.5 py-1 lg:px-3 lg:py-1.5 rounded-[6px] border border-rule-str bg-card text-ink hover:bg-card-hi transition-colors inline-flex items-center gap-1.5"
        >
          <span aria-hidden="true" className="text-dim">{'\u2699'}</span>
          Settings
        </Link>
      </div>

      {/* Header + filters — wraps on small screens */}
      <div className="shrink-0 flex flex-col lg:flex-row lg:justify-between lg:items-end gap-3 mb-4">
        <div className="min-w-0">
          <h1 className="font-mono text-xl lg:text-2xl font-bold tracking-[-0.02em]">Session History</h1>
          <p className="font-mono text-[13px] text-dim mt-0.5">// every time Claude ran against one of your PRs</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt}
              onClick={() => handleStatusChange(opt)}
              className={`font-mono text-[11px] lg:text-[12px] font-medium px-2.5 py-1 lg:px-3 lg:py-1.5 rounded-[6px] border transition-colors cursor-pointer ${
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

      {/* Completion bar — stacks on small screens */}
      {!loading && sessions.length > 0 && (
        <div className="shrink-0 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 px-4 py-2.5 bg-card border border-rule rounded-[8px] mb-4">
          <div className="flex items-baseline gap-1.5 shrink-0">
            <span className="font-mono text-lg font-bold">{completionPct}%</span>
            <span className="font-mono text-[10px] text-dim tracking-[0.12em] uppercase">completion</span>
          </div>
          <div className="flex-1 h-1.5 bg-bg2 rounded-full flex gap-0.5 overflow-hidden">
            {completed > 0 && <div className="bg-ok" style={{ flex: completed }} />}
            {timeout > 0 && <div className="bg-warn" style={{ flex: timeout }} />}
            {failed > 0 && <div className="bg-danger" style={{ flex: failed }} />}
          </div>
          <div className="flex gap-3 sm:gap-4 font-mono text-[10px] sm:text-[11px] text-dim shrink-0">
            <span><Dot color="ok" className="mr-1" />{completed} done</span>
            <span><Dot color="warn" className="mr-1" />{timeout} timeout</span>
            <span><Dot color="danger" className="mr-1" />{failed} failed</span>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="shrink-0 mb-3 px-4 py-2.5 bg-danger/8 border border-danger/20 rounded-[8px] text-danger text-sm">
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
        <div className="text-center py-12 bg-card border border-rule rounded-[8px]">
          <p className="text-ink2 text-sm">
            {statusFilter === 'all' ? 'No sessions yet.' : `No ${statusFilter} sessions.`}
          </p>
        </div>
      )}

      {/* Session table */}
      {!loading && sessions.length > 0 && (
        <div className="flex-1 min-h-0 flex flex-col">
        <div className="max-h-full min-h-0 flex flex-col border border-rule-str rounded-[8px] overflow-hidden">
          {/* Table header */}
          <div
            className="shrink-0 grid bg-bg2 px-3 lg:px-4 py-2 font-mono text-[9px] lg:text-[10px] text-dim tracking-[0.18em] uppercase border-b border-rule"
            style={{ gridTemplateColumns: COL_TEMPLATE }}
          >
            <span>#</span>
            <span>REPO / PR</span>
            <span>SKILL</span>
            <span>STATUS</span>
            <span className="text-right">DURATION</span>
            <span className="text-right">RAN</span>
            <span></span>
          </div>

          {/* Scrollable rows */}
          <div className="flex-1 min-h-0 overflow-y-auto">
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
                  className={`group w-full grid items-center text-left px-3 lg:px-4 py-2 lg:py-2.5 text-[12px] lg:text-[13px] transition-colors cursor-pointer hover:bg-card-hi ${
                    idx < sessions.length - 1 ? 'border-b border-rule' : ''
                  }`}
                  style={{ gridTemplateColumns: COL_TEMPLATE }}
                >
                  <span className="font-mono text-[10px] lg:text-[11px] text-dim2">
                    {String(idx + 1 + (page - 1) * perPage).padStart(2, '0')}
                  </span>
                  <span className="font-mono text-ink truncate">
                    {session.repo_full_name} <span className="text-accent">#{session.pr_number}</span>
                  </span>
                  <span><Chip variant="accent">{session.skill_name}</Chip></span>
                  <span><Chip variant={statusColor}>{session.status}</Chip></span>
                  <span className="font-mono text-[10px] lg:text-[11px] text-ink2 text-right">
                    {formatDuration(session.started_at, session.completed_at)}
                  </span>
                  <span className="font-mono text-[10px] lg:text-[11px] text-dim text-right">
                    {formatRelativeTime(session.created_at)}
                  </span>
                  <span
                    className="text-center text-dim2 hover:text-danger transition-colors cursor-pointer opacity-0 group-hover:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation()
                      setDeleteTarget({
                        id: session.id,
                        label: `${session.repo_full_name}#${session.pr_number}`,
                      })
                    }}
                    title="Delete session"
                  >
                    {'\u2715'}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
        </div>
      )}

      {/* Pagination */}
      {!loading && totalPages > 1 && (
        <div className="shrink-0 flex items-center justify-center gap-4 py-3">
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
    </div>

    {/* Delete confirmation modal */}
    {deleteTarget && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 backdrop-blur-sm p-4">
        <Card className="w-full max-w-sm">
          <Overline className="mb-3 text-danger">{'\u25b8'} DELETE SESSION</Overline>
          <p className="text-ink text-sm font-sans mb-1">
            Delete this session and all its events?
          </p>
          <p className="text-dim text-xs font-mono mb-5">
            // {deleteTarget.label}
          </p>
          <div className="flex gap-2">
            <Button
              variant="danger"
              onClick={confirmDelete}
              disabled={deleting}
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
            <Button
              variant="ghost"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
            >
              Cancel
            </Button>
          </div>
        </Card>
      </div>
    )}
    </>
  )
}
