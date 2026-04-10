import { useEffect } from 'react'
import { useParams } from 'react-router'
import { SessionFetchError } from './api'
import { useSession } from './useSession'
import { useSessionStore } from './store'
import SessionHeader from './SessionHeader'
import SplitLayout from './SplitLayout'
import TabbedLayout from './TabbedLayout'
import MobileLayout from './MobileLayout'
import { useViewport } from '../../shared/hooks/useViewport'
import type { SessionResponse } from './types'

interface ErrorScreenProps {
  title: string
  message: string
  onRetry?: () => void
}

function ErrorScreen({ title, message, onRetry }: ErrorScreenProps) {
  return (
    <div className="min-h-screen bg-primary text-text-primary font-mono flex items-center justify-center px-6">
      <div className="max-w-md text-center space-y-4">
        <h1 className="text-[16px] font-bold">{title}</h1>
        <p className="text-[14px] text-text-secondary">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="px-6 py-3 rounded-lg bg-[var(--color-accent)] text-white font-semibold hover:opacity-90 transition-opacity"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

function SessionSkeleton() {
  return (
    <div
      className="min-h-screen bg-primary text-text-primary font-mono flex flex-col"
      data-testid="session-skeleton"
    >
      {/* Header placeholder — matches the 48px fixed header. */}
      <div className="h-12 border-b border-border flex items-center px-4 gap-4">
        <div className="h-3 w-40 bg-surface animate-pulse rounded" />
        <div className="h-3 w-64 bg-surface animate-pulse rounded" />
      </div>
      {/* Body: 60/40 dimmed placeholders. */}
      <div className="flex-1 flex">
        <div className="flex-[6] bg-primary border-r border-border animate-pulse" />
        <div className="flex-[4] bg-surface animate-pulse" />
      </div>
    </div>
  )
}

interface LoadedLayoutProps {
  session: SessionResponse
}

function LoadedLayout({ session }: LoadedLayoutProps) {
  const viewport = useViewport()
  const setSession = useSessionStore((s) => s.setSession)
  const clearSession = useSessionStore((s) => s.clearSession)

  // Sync the store with the current session on every new SessionResponse
  // identity (e.g. after a background refetch). Do NOT put clearSession in
  // this effect's cleanup — React-Query refetches produce a new object
  // identity, which would fire the cleanup and wipe panelRatio /
  // activeFileIndex mid-interaction. The store reset belongs to real
  // unmount only; see the separate effect below.
  useEffect(() => {
    setSession(session)
  }, [session, setSession])

  // Reset the UI-local store when the ChatView leaves the screen. Empty
  // deps — the cleanup fires on true unmount only, not on session refetch.
  // `clearSession` is a stable zustand selector (same reference across
  // renders) so omitting it from the dep array is safe.
  useEffect(() => {
    return () => {
      clearSession()
    }
  }, [clearSession])

  return (
    <div className="min-h-screen h-screen bg-primary text-text-primary font-mono flex flex-col">
      <SessionHeader session={session} />
      <div className="flex-1 min-h-0">
        {viewport === 'desktop' && <SplitLayout session={session} />}
        {viewport === 'tablet' && <TabbedLayout session={session} />}
        {viewport === 'mobile' && <MobileLayout session={session} />}
      </div>
    </div>
  )
}

export default function ChatView() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const query = useSession(sessionId)

  if (query.isLoading || query.isPending) {
    return <SessionSkeleton />
  }

  if (query.isError) {
    const status = query.error instanceof SessionFetchError ? query.error.status : undefined

    if (status === 403) {
      return (
        <ErrorScreen
          title="No access"
          message="You do not have access to this session's repository."
        />
      )
    }

    if (status === 404) {
      return (
        <ErrorScreen
          title="Session not found"
          message="This session does not exist or has been deleted."
        />
      )
    }

    return (
      <ErrorScreen
        title="Temporarily unavailable"
        message="We could not load your session. Please retry."
        onRetry={() => query.refetch()}
      />
    )
  }

  return <LoadedLayout session={query.data} />
}
